/**
 * 共享模块：21 手部关键点 → L6/L10 跟随用 10 关节角（0–100）→ CAN logical 映射
 * 供 4.follow-me（2D）与 7.follow-me-3d（RealSense 3D）共用
 */
(function (global) {
    const WRIST = 0;
    const THUMB_CMC = 1;
    const THUMB_MCP = 2;
    const THUMB_IP = 3;
    const THUMB_TIP = 4;
    const INDEX_MCP = 5;
    const INDEX_PIP = 6;
    const INDEX_DIP = 7;
    const INDEX_TIP = 8;
    const MIDDLE_MCP = 9;
    const MIDDLE_PIP = 10;
    const MIDDLE_DIP = 11;
    const MIDDLE_TIP = 12;
    const RING_MCP = 13;
    const RING_PIP = 14;
    const RING_DIP = 15;
    const RING_TIP = 16;
    const PINKY_MCP = 17;
    const PINKY_PIP = 18;
    const PINKY_DIP = 19;
    const PINKY_TIP = 20;

    const JOINT_SMOOTH = [0.4, 0.4, 0.4, 0.4, 0.4, 0.2, 0.4, 0.4, 0.2, 0.4];

    /** 与 4.follow-me 一致：外置/D405 摄像头为 false，笔记本自拍为 true */
    let MIRROR_HAND_LABELS = false;

    /** 2D 页同款短标签；index 0–5 为 L6 跟随下发 */
    const JOINT_LABELS_SHORT = [
        "拇屈", "拇展", "食", "中", "无", "小", "食展", "无展", "小展", "拇摆",
    ];

    const L6_DRIVEN_JOINT_COUNT = 6;

    const JOINT_LABELS = [
        "拇指屈伸",
        "拇指旋转",
        "食指屈伸",
        "中指屈伸",
        "无名指屈伸",
        "小指屈伸",
        "食指侧摆",
        "无名指侧摆",
        "小指侧摆",
        "拇指侧摆",
    ];

    function toPoint(lm, index) {
        const p = lm[index];
        if (Array.isArray(p)) {
            return { x: p[0], y: p[1], z: p[2] };
        }
        return { x: p.x, y: p.y, z: p.z || 0 };
    }

    function toArr(lm, index) {
        const p = toPoint(lm, index);
        return [p.x, p.y, p.z];
    }

    function angle3D(a, b, c) {
        const ba = [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
        const bc = [c[0] - b[0], c[1] - b[1], c[2] - b[2]];
        const nba = Math.hypot(ba[0], ba[1], ba[2]) + 1e-8;
        const nbc = Math.hypot(bc[0], bc[1], bc[2]) + 1e-8;
        const cosA = (ba[0] * bc[0] + ba[1] * bc[1] + ba[2] * bc[2]) / (nba * nbc);
        return (Math.acos(Math.max(-1, Math.min(1, cosA))) * 180) / Math.PI;
    }

    function dist3D(a, b) {
        return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    }

    function distPlanar(a, b, use3D) {
        if (use3D) {
            return dist3D(a, b);
        }
        return Math.hypot(a[0] - b[0], a[1] - b[1]);
    }

    function angleBetweenVectors(v1, v2) {
        const n1 = Math.hypot(v1[0], v1[1], v1[2]) + 1e-8;
        const n2 = Math.hypot(v2[0], v2[1], v2[2]) + 1e-8;
        const dot = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2);
        return (Math.acos(Math.max(-1, Math.min(1, dot))) * 180) / Math.PI;
    }

    function fingerFlex(lm, tip, dip, pip, mcp) {
        const pts = [toArr(lm, tip), toArr(lm, dip), toArr(lm, pip), toArr(lm, mcp)];
        const ang = angle3D(pts[0], pts[2], pts[3]);
        return Math.max(0, Math.min(100, ((ang - 60) / 120) * 100));
    }

    function fingerSwingCalc(lm, mcp1, pip1, mcp2, pip2, minAng, maxAng) {
        const p1 = toPoint(lm, mcp1);
        const p2 = toPoint(lm, pip1);
        const p3 = toPoint(lm, mcp2);
        const p4 = toPoint(lm, pip2);
        const v1 = [p2.x - p1.x, p2.y - p1.y, p2.z - p1.z];
        const v2 = [p4.x - p3.x, p4.y - p3.y, p4.z - p3.z];
        const ang = angleBetweenVectors(v1, v2);
        return Math.max(0, Math.min(100, ((ang - minAng) / (maxAng - minAng)) * 100));
    }

    function thumbSwingCalc(lm, use3D) {
        const dThumbIndex = distPlanar(toArr(lm, THUMB_TIP), toArr(lm, INDEX_MCP), use3D);
        const palmLength = distPlanar(toArr(lm, WRIST), toArr(lm, INDEX_MCP), use3D);
        const ratio = dThumbIndex / (palmLength + 1e-8);
        return Math.max(0, Math.min(100, ((ratio - 0.4) / 0.5) * 100));
    }

    function thumbRotCalc(lm, use3D) {
        const dThumbPinky = distPlanar(toArr(lm, THUMB_TIP), toArr(lm, PINKY_MCP), use3D);
        const palmWidth = distPlanar(toArr(lm, INDEX_MCP), toArr(lm, PINKY_MCP), use3D);
        const ratio = dThumbPinky / (palmWidth + 1e-8);
        const rawResult = Math.max(0, Math.min(100, ((1.8 - ratio) / 1) * 100));
        return 100 - rawResult;
    }

    function pinkyFlex(lm) {
        const pts = [
            toArr(lm, PINKY_TIP),
            toArr(lm, PINKY_DIP),
            toArr(lm, PINKY_PIP),
            toArr(lm, PINKY_MCP),
        ];
        const ang = angle3D(pts[0], pts[2], pts[3]);
        return Math.max(0, Math.min(100, ((ang - 40) / 120) * 100));
    }

    function thumbFlex(lm) {
        const pts = [
            toArr(lm, THUMB_TIP),
            toArr(lm, THUMB_IP),
            toArr(lm, THUMB_MCP),
            toArr(lm, THUMB_CMC),
        ];
        const ang = angle3D(pts[0], pts[1], pts[2]);
        return Math.max(0, Math.min(100, ((ang - 130) / 30) * 100));
    }

    /**
     * @param {Array} landmarks 21 点，元素为 {x,y,z} 或 [x,y,z]
     * @param {{ use3D?: boolean }} [options] use3D=true 时使用真实 3D 距离（RealSense 手系）
     */
    function computeAngles(landmarks, options) {
        const use3D = Boolean(options && options.use3D);
        const lm = landmarks;
        return [
            thumbFlex(lm),
            thumbRotCalc(lm, use3D),
            fingerFlex(lm, INDEX_TIP, INDEX_DIP, INDEX_PIP, INDEX_MCP),
            fingerFlex(lm, MIDDLE_TIP, MIDDLE_DIP, MIDDLE_PIP, MIDDLE_MCP),
            fingerFlex(lm, RING_TIP, RING_DIP, RING_PIP, RING_MCP),
            pinkyFlex(lm),
            fingerSwingCalc(lm, INDEX_MCP, INDEX_PIP, MIDDLE_MCP, MIDDLE_PIP, 1.5, 10),
            fingerSwingCalc(lm, RING_MCP, RING_PIP, MIDDLE_MCP, MIDDLE_PIP, 1.0, 6),
            fingerSwingCalc(lm, PINKY_MCP, PINKY_PIP, RING_MCP, RING_PIP, 2.0, 12),
            thumbSwingCalc(lm, use3D),
        ];
    }

    function smoothAngles(prev, current) {
        if (!prev) {
            return current.slice();
        }
        return current.map((c, i) => JOINT_SMOOTH[i] * c + (1 - JOINT_SMOOTH[i]) * prev[i]);
    }

    function scale255(v) {
        return Math.max(0, Math.min(255, Math.round((v / 100) * 255)));
    }

    function anglesToLogical(angles) {
        return {
            basic: {
                thumb: scale255(angles[0]),
                thumb_rot: scale255(angles[1]),
                index: scale255(angles[2]),
                middle: scale255(angles[3]),
                ring: scale255(angles[4]),
                pinky: scale255(angles[5]),
            },
            swing: {
                index_swing: scale255(angles[6]),
                ring_swing: scale255(angles[7]),
                pinky_swing: scale255(angles[8]),
                thumb_swing: scale255(angles[9]),
            },
        };
    }

    function logicalToFollowData(presetKey, basic, swing) {
        const t = basic.thumb;
        const tr = basic.thumb_rot;
        const i = basic.index;
        const m = basic.middle;
        const r = basic.ring;
        const p = basic.pinky;
        const isw = swing.index_swing;
        const rsw = swing.ring_swing;
        const psw = swing.pinky_swing;
        const tsw = swing.thumb_swing;

        if (presetKey === "L10_worm_gear" || presetKey === "L10_ball_joint") {
            const finger = [1, t, tr, i, m, r, p].map((v) => Number(v) & 0xff);
            const palm = [4, isw, rsw, psw, tsw].map((v) => Number(v) & 0xff);
            return { supported: true, data: [finger, palm] };
        }
        if (presetKey === "O6/L6") {
            const finger = [1, t, tr, i, m, r, p].map((v) => Number(v) & 0xff);
            return { supported: true, data: [finger] };
        }
        return { supported: false, data: [] };
    }

    /** MediaPipe Left/Right → 用户真实左右（与 4.follow-me userHandLabel 一致） */
    function userHandLabel(mediaPipeLabel) {
        if (!MIRROR_HAND_LABELS) return mediaPipeLabel;
        return mediaPipeLabel === "Left" ? "Right" : "Left";
    }

    function getTrueHandLabel(mediaPipeLabel) {
        return userHandLabel(mediaPipeLabel);
    }

    /** WebSocket hands[] → 匹配设备 side 的那只手 */
    function findHandForSide(hands, deviceSide) {
        const want = deviceSide === "left" ? "Left" : "Right";
        for (const hand of hands) {
            if (userHandLabel(hand.label) === want) {
                return hand;
            }
        }
        return null;
    }

    global.HandRetarget = {
        get MIRROR_HAND_LABELS() {
            return MIRROR_HAND_LABELS;
        },
        set MIRROR_HAND_LABELS(value) {
            MIRROR_HAND_LABELS = Boolean(value);
        },
        JOINT_SMOOTH,
        JOINT_LABELS,
        JOINT_LABELS_SHORT,
        L6_DRIVEN_JOINT_COUNT,
        computeAngles,
        smoothAngles,
        scale255,
        anglesToLogical,
        logicalToFollowData,
        userHandLabel,
        getTrueHandLabel,
        findHandForSide,
    };
})(window);
