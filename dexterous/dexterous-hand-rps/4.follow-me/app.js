/**
 * 跟随模式：摄像头 + MediaPipe 手部检测 + 与 Python gesture_engine 对齐的 10 关节角度计算，
 * 经 EMA 平滑后映射为 0–255 逻辑量，通过 POST /api/follow/batch 按设备下发 CAN。
 */

// ── MediaPipe 关键点索引（与 Python 一致）────────────────────────────
const WRIST = 0;
const THUMB_CMC = 1, THUMB_MCP = 2, THUMB_IP = 3, THUMB_TIP = 4;
const INDEX_MCP = 5, INDEX_PIP = 6, INDEX_DIP = 7, INDEX_TIP = 8;
const MIDDLE_MCP = 9, MIDDLE_PIP = 10, MIDDLE_DIP = 11, MIDDLE_TIP = 12;
const RING_MCP = 13, RING_PIP = 14, RING_DIP = 15, RING_TIP = 16;
const PINKY_MCP = 17, PINKY_PIP = 18, PINKY_DIP = 19, PINKY_TIP = 20;

/** 每关节 EMA 系数（与 Python _JOINT_SMOOTH 一致） */
const JOINT_SMOOTH = [0.4, 0.4, 0.4, 0.4, 0.4, 0.2, 0.4, 0.4, 0.2, 0.4];

const SEND_INTERVAL_MS = 50;
const FOLLOW_MIN_CHANGED_VALUE = 2;
/** 笔记本前置自拍镜像画面用 true；OBS / 外置摄像头用 false */
const MIRROR_HAND_LABELS = false;
const FPS_UPDATE_INTERVAL_MS = 250;
const DEBUG_INFO_UPDATE_INTERVAL_MS = 200;
const JOINT_BARS_UPDATE_INTERVAL_MS = 100;

let lastFpsUpdate = 0;
let lastDebugInfoUpdate = 0;
let lastJointBarsUpdate = 0;
let lastHandCountText = '';
let lastGestureDisplayText = '';

function toArr(lm) {
    return [lm.x, lm.y, lm.z];
}

function angle3D(a, b, c) {
    const ba = [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    const bc = [c[0] - b[0], c[1] - b[1], c[2] - b[2]];
    const nba = Math.hypot(ba[0], ba[1], ba[2]) + 1e-8;
    const nbc = Math.hypot(bc[0], bc[1], bc[2]) + 1e-8;
    const cosA = (ba[0] * bc[0] + ba[1] * bc[1] + ba[2] * bc[2]) / (nba * nbc);
    const clipped = Math.max(-1, Math.min(1, cosA));
    return (Math.acos(clipped) * 180) / Math.PI;
}
// 计算三维空间两点之间的距离
function dist3D(a, b) {
    return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

// 计算两个空间向量之间的夹角（度数）
function angleBetweenVectors(v1, v2) {
    const n1 = Math.hypot(v1[0], v1[1], v1[2]) + 1e-8;
    const n2 = Math.hypot(v2[0], v2[1], v2[2]) + 1e-8;
    const dot = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2);
    const clipped = Math.max(-1, Math.min(1, dot));
    return (Math.acos(clipped) * 180) / Math.PI;
}
function fingerFlex(lm, tip, dip, pip, mcp) {
    const pts = [toArr(lm[tip]), toArr(lm[dip]), toArr(lm[pip]), toArr(lm[mcp])];
    const ang = angle3D(pts[0], pts[2], pts[3]);
    return Math.max(0, Math.min(100, ((ang - 60) / 120) * 100));
}

// 新增：仅使用 X, Y 轴计算画面内的相对距离，规避 MediaPipe Z 轴的剧烈误差
function dist2D(a, b) {
    return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

/**
 * 优化版 Swing：支持传入 minAng 和 maxAng 进行自定义放大
 * minAng: 算作 0 的起始角度
 * maxAng: 算作 100 的满分角度（越小，越容易达到 100，即放得越大）
 */
function fingerSwingCalc(lm, mcp1, pip1, mcp2, pip2, minAng = 1.5, maxAng = 10) {
    const v1 = [lm[pip1].x - lm[mcp1].x, lm[pip1].y - lm[mcp1].y, lm[pip1].z - lm[mcp1].z];
    const v2 = [lm[pip2].x - lm[mcp2].x, lm[pip2].y - lm[mcp2].y, lm[pip2].z - lm[mcp2].z];
    const ang = angleBetweenVectors(v1, v2);
    // 将实际夹角映射到 0-100，利用 maxAng 缩小满分门槛来实现放大
    return Math.max(0, Math.min(100, ((ang - minAng) / (maxAng - minAng)) * 100));
}

/**
 * 拇摆 (Thumb_Swing) - 拇指与食指的距离
 */
function thumbSwingCalc(lm) {
    // 改用指尖 (THUMB_TIP) 到食指根部，并使用 dist2D
    const dThumbIndex = dist2D(toArr(lm[THUMB_TIP]), toArr(lm[INDEX_MCP]));
    const palmLength = dist2D(toArr(lm[WRIST]), toArr(lm[INDEX_MCP]));
    const ratio = dThumbIndex / palmLength;
    
    // 阈值大幅缩紧：贴合时 ratio 约 0.4，张开时 ratio 约 0.9 就能满分
    return Math.max(0, Math.min(100, ((ratio - 0.4) / 0.5) * 100));
}

/**
 * 拇展 (Thumb_Rot) - 向掌心旋转内扣
 */
function thumbRotCalc(lm) {
    // 改用指尖 (THUMB_TIP) 到小指根部，并使用 dist2D
    const dThumbPinky = dist2D(toArr(lm[THUMB_TIP]), toArr(lm[PINKY_MCP]));
    const palmWidth = dist2D(toArr(lm[INDEX_MCP]), toArr(lm[PINKY_MCP]));
    const ratio = dThumbPinky / palmWidth;

    // 完全张开(如你的截图)时，ratio 约 1.8~2.0。内扣对掌时，ratio 会缩小到 0.4 左右。
    // 原始映射：1.8 时为 0，0.5 时为 100 (对掌值)
    let rawResult = Math.max(0, Math.min(100, ((1.8 - ratio) / 1) * 100));

    // 反转逻辑：张开时值大，对掌时值小
    // 当 rawResult 接近 0 (张开) 时，finalResult 接近 100
    // 当 rawResult 接近 100 (对掌) 时，finalResult 接近 0
    let finalResult = 100 - rawResult;

    return finalResult;
}
function pinkyFlex(lm) {
    const pts = [
        toArr(lm[PINKY_TIP]),
        toArr(lm[PINKY_DIP]),
        toArr(lm[PINKY_PIP]),
        toArr(lm[PINKY_MCP]),
    ];
    const ang = angle3D(pts[0], pts[2], pts[3]);
    return Math.max(0, Math.min(100, ((ang - 40) / 120) * 100));
}

function thumbFlex(lm) {
    const pts = [
        toArr(lm[THUMB_TIP]),
        toArr(lm[THUMB_IP]),
        toArr(lm[THUMB_MCP]),
        toArr(lm[THUMB_CMC]),
    ];
    const ang = angle3D(pts[0], pts[1], pts[2]);
    return Math.max(0, Math.min(100, ((ang - 130) / 30) * 100));
}

function abduction(lm, f1Mcp, f2Mcp, wrist) {
    const ang = angle3D(toArr(lm[f1Mcp]), toArr(lm[wrist]), toArr(lm[f2Mcp]));
    return Math.max(0, Math.min(100, ((ang - 5) / 30) * 100));
}

function thumbAbd(lm) {
    // 计算拇指指尖 (THUMB_TIP) 与食指根部 (INDEX_MCP) 之间的 3D 距离
    const distance = dist3D(toArr(lm[THUMB_TIP]), toArr(lm[INDEX_MCP]));

    // --- 关键参数：设定距离阈值 ---
    // 这些值需要根据实际手部大小和摄像头距离进行微调
    const MIN_DISTANCE = 0.15; // 认为是“重合”或“最近”的距离（单位：归一化坐标）
    const MAX_DISTANCE = 0.0;  // 认为是“最远”或“满分”的距离（单位：归一化坐标）

    // 将距离映射到 0-100 范围
    // 当 distance <= MIN_DISTANCE 时，result = 0
    // 当 distance >= MAX_DISTANCE 时，result = 100
    let result = ((distance - MIN_DISTANCE) / (MAX_DISTANCE - MIN_DISTANCE)) * 100;

    // 限制在 0-100 范围内
    result = Math.max(0, Math.min(100, result));

    return result;
}

function norm3(v) {
    const n = Math.hypot(v[0], v[1], v[2]) + 1e-8;
    return [v[0] / n, v[1] / n, v[2] / n];
}

function cross(a, b) {
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ];
}

function thumbYaw(lm) {
    const wrist = toArr(lm[WRIST]);
    const n = cross(
        [toArr(lm[INDEX_MCP])[0] - wrist[0], toArr(lm[INDEX_MCP])[1] - wrist[1], toArr(lm[INDEX_MCP])[2] - wrist[2]],
        [toArr(lm[PINKY_MCP])[0] - wrist[0], toArr(lm[PINKY_MCP])[1] - wrist[1], toArr(lm[PINKY_MCP])[2] - wrist[2]]
    );
    const normal = norm3(n);
    let thumbDir = [
        toArr(lm[THUMB_TIP])[0] - toArr(lm[THUMB_MCP])[0],
        toArr(lm[THUMB_TIP])[1] - toArr(lm[THUMB_MCP])[1],
        toArr(lm[THUMB_TIP])[2] - toArr(lm[THUMB_MCP])[2],
    ];
    thumbDir = norm3(thumbDir);
    const d =
        Math.abs(thumbDir[0] * normal[0] + thumbDir[1] * normal[1] + thumbDir[2] * normal[2]);
    return Math.max(0, Math.min(100, 100 - d * 100));
}

/**
 * 从 MediaPipe 21 点计算 10 个关节角度（0–100），与 Python compute_angles 一致。
 */
// function computeAngles(landmarks) {
//     const lm = landmarks;
//     return [
//         thumbFlex(lm),
//         thumbAbd(lm),
//         fingerFlex(lm, INDEX_TIP, INDEX_DIP, INDEX_PIP, INDEX_MCP),
//         fingerFlex(lm, MIDDLE_TIP, MIDDLE_DIP, MIDDLE_PIP, MIDDLE_MCP),
//         fingerFlex(lm, RING_TIP, RING_DIP, RING_PIP, RING_MCP),
//         pinkyFlex(lm),
//         abduction(lm, INDEX_MCP, MIDDLE_MCP, WRIST),
//         abduction(lm, RING_MCP, MIDDLE_MCP, WRIST),
//         abduction(lm, PINKY_MCP, RING_MCP, WRIST),
//         thumbYaw(lm),
//     ];
// }
/**
 * 从 MediaPipe 21 点计算 10 个关节角度（0–100）
 */
/**
 * 从 MediaPipe 21 点计算 10 个关节角度（0–100）
 */
function computeAngles(landmarks) {
    const lm = landmarks;
    return [
        thumbFlex(lm),
        thumbRotCalc(lm),
        fingerFlex(lm, INDEX_TIP, INDEX_DIP, INDEX_PIP, INDEX_MCP),
        fingerFlex(lm, MIDDLE_TIP, MIDDLE_DIP, MIDDLE_PIP, MIDDLE_MCP),
        fingerFlex(lm, RING_TIP, RING_DIP, RING_PIP, RING_MCP),
        pinkyFlex(lm),
        
        // 分别赋予不同的满分角度(maxAng)：
        // 食指：10度就满分
        fingerSwingCalc(lm, INDEX_MCP, INDEX_PIP, MIDDLE_MCP, MIDDLE_PIP, 1.5, 10),
        // 无名指：生理上最难张开，只要达到 6 度就给 100 满分（大幅放大）
        fingerSwingCalc(lm, RING_MCP, RING_PIP, MIDDLE_MCP, MIDDLE_PIP, 1.0, 6),
        // 小指：比较灵活，设为 12 度满分
        fingerSwingCalc(lm, PINKY_MCP, PINKY_PIP, RING_MCP, RING_PIP, 2.0, 12),
        
        thumbSwingCalc(lm),
    ];
}
/** 每关节 EMA 平滑 */
function smoothAngles(prev, current) {
    if (!prev) return current;
    return current.map((c, i) => JOINT_SMOOTH[i] * c + (1 - JOINT_SMOOTH[i]) * prev[i]);
}

function scale255(v) {
    return Math.max(0, Math.min(255, Math.round((v / 100) * 255)));
}

/**
 * 将 10 个角度转为 dashboard 风格 logical（0–255），与 Python angles_to_logical 一致。
 */
function anglesToLogical(angles) {
    const basic = {
        thumb: scale255(angles[0]),
        thumb_rot: scale255(angles[1]),
        index: scale255(angles[2]),
        middle: scale255(angles[3]),
        ring: scale255(angles[4]),
        pinky: scale255(angles[5]),
    };
    const swing = {
        index_swing: scale255(angles[6]),
        ring_swing: scale255(angles[7]),
        pinky_swing: scale255(angles[8]),
        thumb_swing: scale255(angles[9]),
    };
    return { basic, swing };
}

/**
 * 将 logical 映射为当前型号的 CAN 行（多行顺序发送：先 finger 再 palm）。
 * L10：finger 7 字节 + palm 5 字节；O6/L6：单条 7 字节 finger。
 */
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

    if (presetKey === 'L10_worm_gear' || presetKey === 'L10_ball_joint') {
        const finger = [1, t, tr, i, m, r, p].map((v) => Number(v) & 0xff);
        const palm = [4, isw, rsw, psw, tsw].map((v) => Number(v) & 0xff);
        return { supported: true, data: [finger, palm] };
    }
    if (presetKey === 'O6/L6') {
        const finger = [1, t, tr, i, m, r, p].map((v) => Number(v) & 0xff);
        return { supported: true, data: [finger] };
    }
    return { supported: false, data: [] };
}

async function loadDeviceConfig() {
    try {
        const response = await fetch(`${baseHost}/api/hand/devices`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });

        const data = await response.json();

        if (data.status === 'ok' && data.data && data.data.length > 0) {
            deviceConfig = data.data.map((config) => ({
                interface: config.interface || 'can0',
                model: config.model || 'unknown',
                variant: config.variant || '',
                side: config.side || 'right',
            }));

            console.log('设备配置加载成功，共', deviceConfig.length, '个设备:', deviceConfig);
            return deviceConfig;
        }
        console.error('获取设备配置失败:', data.message || data.error);
        return null;
    } catch (error) {
        console.error('加载设备配置时发生错误:', error);
        return null;
    }
}

function getGesturePresetKey(config) {
    if (!config) return 'O6/L6';
    const { model, variant } = config;
    if (model === 'L25') return 'L25';
    if (model === 'L10') {
        if (variant === 'worm_gear') return 'L10_worm_gear';
        if (variant === 'ball_joint') return 'L10_ball_joint';
        return 'L10_worm_gear';
    }
    if (model === 'O6/L6' || model === 'O6' || model === 'L6') return 'O6/L6';
    return 'O6/L6';
}

function getCanId(side) {
    return side === 'left' ? 0x28 : 0x27;
}

/** 跟随专用：每设备独立载荷，支持左右手不同 CAN 数据 */
async function sendFollowBatch(devices) {
    if (!devices || devices.length === 0) return false;
    const backendUrl = `${batchHost}/api/follow/batch`;
    try {
        const response = await fetch(backendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ devices }),
        });
        const data = await response.json();
        return data.status === 'ok';
    } catch (e) {
        console.warn('跟随下发失败:', e);
        return false;
    }
}

function flattenFollowDevices(devices) {
    return devices.flatMap((dev) => [
        dev.model,
        dev.interface,
        dev.id,
        ...dev.data.flatMap((row) => row),
    ]);
}

function hasMeaningfulFollowChange(prev, next) {
    if (!prev) return true;
    const a = flattenFollowDevices(prev);
    const b = flattenFollowDevices(next);
    if (a.length !== b.length) return true;

    for (let i = 0; i < a.length; i++) {
        if (typeof a[i] !== 'number' || typeof b[i] !== 'number') {
            if (a[i] !== b[i]) return true;
            continue;
        }
        if (Math.abs(a[i] - b[i]) >= FOLLOW_MIN_CHANGED_VALUE) {
            return true;
        }
    }
    return false;
}

let followSendInFlight = false;
let queuedFollowDevices = null;
let lastSentFollowDevices = null;

async function sendFollowBatchCoalesced(devices) {
    if (!devices || devices.length === 0) return;
    if (!hasMeaningfulFollowChange(lastSentFollowDevices, devices)) {
        return;
    }

    if (followSendInFlight) {
        queuedFollowDevices = devices;
        return;
    }

    followSendInFlight = true;
    try {
        if (await sendFollowBatch(devices)) {
            lastSentFollowDevices = devices;
        }
    } finally {
        followSendInFlight = false;
        if (queuedFollowDevices) {
            const latest = queuedFollowDevices;
            queuedFollowDevices = null;
            sendFollowBatchCoalesced(latest);
        }
    }
}

function setTextIfChanged(element, text) {
    if (element && element.textContent !== text) {
        element.textContent = text;
    }
}

// ── DOM ─────────────────────────────────────────────────────────────
const video = document.getElementById('webcam');
const canvas = document.getElementById('output-canvas');
const ctx = canvas.getContext('2d');
const statusDiv = document.getElementById('status');
const startButton = document.getElementById('start-btn');
const stopButton = document.getElementById('stop-btn');
const cameraSelect = document.getElementById('camera-select');
const handCountSpan = document.getElementById('hand-count');
const landmarksInfo = document.getElementById('landmarks-info');
const fpsCounter = document.getElementById('fps');
const gestureDisplay = document.getElementById('gesture-display');
const jointBarsEl = document.getElementById('joint-bars');

let hands;
/** 手部模型是否已就绪 */
let handModelReady = false;
/** requestAnimationFrame 驱动 hands.send，避免 Camera 二次 getUserMedia */
let videoFrameRafId = null;
let lastFrameTime = 0;
let isRunning = false;
let deviceConfig = null;
let baseHost = 'http://localhost:7080';
let batchHost = 'http://localhost:8899';

/** 左右手各一套平滑后的角度 */
let smoothedLeft = null;
let smoothedRight = null;
let lastFollowSend = 0;

const HAND_CONNECTIONS = [
    [0, 1], [1, 2], [2, 3], [3, 4],
    [0, 5], [5, 6], [6, 7], [7, 8],
    [0, 9], [9, 10], [10, 11], [11, 12],
    [0, 13], [13, 14], [14, 15], [15, 16],
    [0, 17], [17, 18], [18, 19], [19, 20],
    [5, 9], [9, 13], [13, 17],
    [0, 5], [0, 17],
];

function setupCanvas() {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
}

async function initHandDetection() {
    try {
        handModelReady = false;
        statusDiv.textContent = '正在加载手部检测模型...';

        hands = new Hands({
            locateFile: (file) => `../6.gameplay/libs/mediapipe/hands/${file}`,
        });

        await hands.setOptions({
            maxNumHands: 2,
            modelComplexity: 1,
            minDetectionConfidence: 0.7,
            minTrackingConfidence: 0.6,
        });

        hands.onResults(onResults);

        handModelReady = true;
        statusDiv.textContent = '模型加载完成，请选择摄像头后点击「启动摄像头」';
        updateStartButtonState();
    } catch (error) {
        handModelReady = false;
        statusDiv.textContent = `初始化失败: ${error.message}`;
        console.error('初始化失败:', error);
        updateStartButtonState();
    }
}

/** MediaPipe Left/Right → 用户真实左右（外置摄像头通常不需翻转） */
function userHandLabel(mediaPipeLabel) {
    if (!MIRROR_HAND_LABELS) return mediaPipeLabel;
    return mediaPipeLabel === 'Left' ? 'Right' : 'Left';
}

function getTrueHandLabel(mediaPipeLabel) {
    return userHandLabel(mediaPipeLabel);
}

function findLandmarksForSide(multiHandLandmarks, multiHandedness, deviceSide) {
    const want = deviceSide === 'left' ? 'Left' : 'Right';
    for (let i = 0; i < multiHandLandmarks.length; i++) {
        if (userHandLabel(multiHandedness[i].label) === want) {
            return multiHandLandmarks[i];
        }
    }
    return null;
}

/**
 * 在 onResults 已更新 smoothedLeft / smoothedRight 后调用，仅组 CAN，不再做平滑。
 */
function buildFollowDevices(multiHandLandmarks, multiHandedness) {
    if (!deviceConfig || deviceConfig.length === 0) return [];

    const devices = [];
    for (const config of deviceConfig) {
        const presetKey = getGesturePresetKey(config);
        if (presetKey === 'L25') {
            continue;
        }
        const lm = findLandmarksForSide(multiHandLandmarks, multiHandedness, config.side);
        if (!lm) continue;

        const angles = config.side === 'left' ? smoothedLeft : smoothedRight;
        if (!angles) continue;

        const { basic, swing } = anglesToLogical(angles);
        const pack = logicalToFollowData(presetKey, basic, swing);
        if (!pack.supported || pack.data.length === 0) continue;

        devices.push({
            model: presetKey,
            interface: config.interface,
            id: getCanId(config.side),
            data: pack.data,
        });
    }
    return devices;
}

function updateJointBarsDisplay(angles) {
    if (!jointBarsEl || !angles) return;
    const names = ['拇屈', '拇展', '食', '中', '无', '小', '食展', '无展', '小展', '拇摆'];
    const html = names
        .map((name, i) => {
            const pct = Math.round(angles[i]);
            return `<div class="joint-row"><span>${name}</span><div class="joint-bar"><i style="width:${pct}%"></i></div><span>${pct}</span></div>`;
        })
        .join('');
    if (jointBarsEl.innerHTML !== html) {
        jointBarsEl.innerHTML = html;
    }
}

function onResults(results) {
    const now = performance.now();
    const elapsed = now - lastFrameTime;
    lastFrameTime = now;
    if (now - lastFpsUpdate >= FPS_UPDATE_INTERVAL_MS) {
        lastFpsUpdate = now;
        setTextIfChanged(fpsCounter, `FPS: ${Math.round(1000 / elapsed)}`);
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const handCount = results.multiHandLandmarks?.length || 0;
    if (`${handCount}` !== lastHandCountText) {
        lastHandCountText = `${handCount}`;
        setTextIfChanged(handCountSpan, lastHandCountText);
    }

    if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        for (let i = 0; i < results.multiHandLandmarks.length; i++) {
            const landmarks = results.multiHandLandmarks[i];
            // MediaPipe 返回的标签是镜像的
            const handedness = results.multiHandedness[i].label; 
            // 获取“真实”的手部标签（相对于用户）
            const trueHandLabel = getTrueHandLabel(handedness);

            drawConnectors(ctx, landmarks, HAND_CONNECTIONS, {
                color: trueHandLabel === 'Left' ? '#00FF00' : '#FF0000', // 使用真实标签上色
                lineWidth: 5,
            });
            drawLandmarks(ctx, landmarks, {
                color: trueHandLabel === 'Left' ? '#00CC00' : '#CC0000', // 使用真实标签上色
                lineWidth: 2,
            });

            const wrist = landmarks[0];
            ctx.fillStyle = trueHandLabel === 'Left' ? '#00FF00' : '#FF0000'; // 使用真实标签上色
            ctx.font = '16px Arial';
            // 显示真实的标签
            ctx.fillText(
                trueHandLabel === 'Left' ? '左手' : '右手', 
                wrist.x * canvas.width,
                wrist.y * canvas.height - 10
            );

            const raw = computeAngles(landmarks);
            // 使用“真实”的手部标签来更新平滑数组
            const smoothed =
                trueHandLabel === 'Left' // 使用真实标签判断
                    ? smoothAngles(smoothedLeft, raw)
                    : smoothAngles(smoothedRight, raw);
            if (trueHandLabel === 'Left') smoothedLeft = smoothed; // 使用真实标签判断
            else smoothedRight = smoothed; // 使用真实标签判断

            ctx.font = '14px Arial';
            ctx.fillStyle = '#FFFFFF';
            ctx.strokeStyle = '#000000';
            ctx.lineWidth = 2;
            const summary = raw.map((x) => Math.round(x)).join(',');
            const textY = wrist.y * canvas.height - 28;
            ctx.strokeText(`角度(0-100): ${summary}`, wrist.x * canvas.width, textY);
            ctx.fillText(`角度(0-100): ${summary}`, wrist.x * canvas.width, textY);
        }

        if (now - lastDebugInfoUpdate >= DEBUG_INFO_UPDATE_INTERVAL_MS) {
            lastDebugInfoUpdate = now;
            updateLandmarksInfo(results.multiHandLandmarks, results.multiHandedness);
        }

        const t = performance.now();
        if (t - lastFollowSend >= SEND_INTERVAL_MS) {
            lastFollowSend = t;
            const devices = buildFollowDevices(results.multiHandLandmarks, results.multiHandedness);
            if (devices.length > 0) {
                sendFollowBatchCoalesced(devices);
            } else if (deviceConfig?.length && (smoothedLeft || smoothedRight)) {
                console.warn(
                    '检测到 hand 但未组包 CAN：左右手标签与设备 side 不匹配，可切换 MIRROR_HAND_LABELS'
                );
            }
        }
    } else {
        setTextIfChanged(landmarksInfo, '尚未检测到手部');
        smoothedLeft = null;
        smoothedRight = null;
        queuedFollowDevices = null;
        lastSentFollowDevices = null;
        if (jointBarsEl) jointBarsEl.innerHTML = '';
        lastGestureDisplayText = '等待手部…';
        setTextIfChanged(gestureDisplay, lastGestureDisplayText);
    }

    if (results.multiHandLandmarks?.length) {
        // 这里也需要用真实标签来显示
        const trueH0Label = getTrueHandLabel(results.multiHandedness[0].label);
        const sm = trueH0Label === 'Left' ? smoothedLeft : smoothedRight;
        if (sm) {
            if (now - lastJointBarsUpdate >= JOINT_BARS_UPDATE_INTERVAL_MS) {
                lastJointBarsUpdate = now;
                updateJointBarsDisplay(sm);
            }
            const text = `跟随中 · ${trueH0Label === 'Left' ? '左' : '右'}手 10 关节`;
            if (text !== lastGestureDisplayText) {
                lastGestureDisplayText = text;
                setTextIfChanged(gestureDisplay, text);
            }
        }
    }
}

function updateLandmarksInfo(multiHandLandmarks, multiHandedness) {
    let infoText = '';
    for (let i = 0; i < multiHandLandmarks.length; i++) {
        // 使用真实标签
        const trueHandLabel = getTrueHandLabel(multiHandedness[i].label);
        const score = multiHandedness[i].score.toFixed(2);
        const landmarks = multiHandLandmarks[i];
        const raw = computeAngles(landmarks);
        infoText += `手 #${i + 1} (${trueHandLabel === 'Left' ? '左' : '右'}手, ${score})\n`; // 显示真实标签
        infoText += `  10 关节(0-100): ${raw.map((x) => x.toFixed(1)).join(', ')}\n\n`;
    }
    setTextIfChanged(landmarksInfo, infoText || '尚未检测到手部');
}

function updateStartButtonState() {
    const selected = cameraSelect && cameraSelect.value;
    const canStart = Boolean(handModelReady && selected && !isRunning);
    startButton.disabled = !canStart;
}

async function startCamera() {
    const selectedDeviceId = cameraSelect.value;
    if (!selectedDeviceId) {
        statusDiv.textContent = '请先在下拉框中选择摄像头';
        return;
    }
    if (!handModelReady || !hands) {
        statusDiv.textContent = '模型尚未就绪，请稍候';
        return;
    }

    try {
        statusDiv.textContent = '正在启动摄像头...';

        const constraints = {
            video: {
                deviceId: { exact: selectedDeviceId },
                width: { ideal: 640 },
                height: { ideal: 480 },
            },
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = stream;

        video.addEventListener(
            'loadedmetadata',
            async () => {
                setupCanvas();
                try {
                    await loadCameraDevices(selectedDeviceId);
                } catch (e) {
                    console.warn('刷新摄像头列表失败:', e);
                }
                startDetection();
            },
            { once: true }
        );

        startButton.disabled = true;
        stopButton.disabled = false;
        cameraSelect.disabled = true;
    } catch (error) {
        statusDiv.textContent = `摄像头启动失败: ${error.message}`;
        console.error('摄像头启动失败:', error);
        updateStartButtonState();
    }
}

function startDetection() {
    if (isRunning) return;
    isRunning = true;
    statusDiv.textContent = '正在检测手部（关节跟随）…';

    const loop = () => {
        if (!isRunning) {
            return;
        }
        Promise.resolve(hands.send({ image: video }))
            .then(() => {
                videoFrameRafId = requestAnimationFrame(loop);
            })
            .catch((err) => {
                console.error('hands.send 失败:', err);
                statusDiv.textContent = `检测中断: ${err.message}`;
                stopDetection();
            });
    };
    videoFrameRafId = requestAnimationFrame(loop);
}

function stopDetection() {
    if (!isRunning && !video.srcObject) {
        return;
    }

    isRunning = false;

    if (videoFrameRafId != null) {
        cancelAnimationFrame(videoFrameRafId);
        videoFrameRafId = null;
    }

    if (video.srcObject) {
        video.srcObject.getTracks().forEach((t) => t.stop());
        video.srcObject = null;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    lastHandCountText = '0';
    setTextIfChanged(handCountSpan, lastHandCountText);
    setTextIfChanged(landmarksInfo, '尚未检测到手部');
    statusDiv.textContent = '检测已停止';
    lastGestureDisplayText = '等待手部…';
    setTextIfChanged(gestureDisplay, lastGestureDisplayText);
    smoothedLeft = null;
    smoothedRight = null;
    queuedFollowDevices = null;
    lastSentFollowDevices = null;
    if (jointBarsEl) jointBarsEl.innerHTML = '';

    stopButton.disabled = true;
    if (cameraSelect) {
        cameraSelect.disabled = false;
    }
    updateStartButtonState();
}

function drawConnectors(ctx2, landmarks, connections, options) {
    const { color = 'white', lineWidth = 1 } = options || {};
    ctx2.strokeStyle = color;
    ctx2.lineWidth = lineWidth;
    for (const connection of connections) {
        const [i, j] = connection;
        const from = landmarks[i];
        const to = landmarks[j];
        if (from && to) {
            ctx2.beginPath();
            ctx2.moveTo(from.x * canvas.width, from.y * canvas.height);
            ctx2.lineTo(to.x * canvas.width, to.y * canvas.height);
            ctx2.stroke();
        }
    }
}

function drawLandmarks(ctx2, landmarks, options) {
    const { color = 'red', lineWidth = 2 } = options || {};
    ctx2.fillStyle = color;
    for (const landmark of landmarks) {
        ctx2.beginPath();
        ctx2.arc(
            landmark.x * canvas.width,
            landmark.y * canvas.height,
            lineWidth * 2,
            0,
            2 * Math.PI
        );
        ctx2.fill();
    }
}

startButton.addEventListener('click', startCamera);
stopButton.addEventListener('click', stopDetection);
cameraSelect.addEventListener('change', () => {
    updateStartButtonState();
});

if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', () => {
        const keepId = cameraSelect.value;
        loadCameraDevices(keepId).catch((e) => console.warn('devicechange 刷新列表失败:', e));
    });
}

/**
 * 枚举视频输入设备；未授权时 label 可能为空。
 * @param {string} [preferredDeviceId] 重建后恢复选中
 */
async function loadCameraDevices(preferredDeviceId) {
    const previousId =
        preferredDeviceId !== undefined ? preferredDeviceId : cameraSelect.value;

    const appendPlaceholder = () => {
        const ph = document.createElement('option');
        ph.value = '';
        ph.textContent = '请选择摄像头';
        cameraSelect.appendChild(ph);
    };

    try {
        cameraSelect.innerHTML = '';
        appendPlaceholder();

        const devices = await navigator.mediaDevices.enumerateDevices();
        const cameras = devices.filter((d) => d.kind === 'videoinput');

        if (cameras.length === 0) {
            cameraSelect.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '未检测到摄像头';
            cameraSelect.appendChild(option);
            updateStartButtonState();
            return;
        }

        cameras.forEach((cam, index) => {
            const option = document.createElement('option');
            option.value = cam.deviceId;
            option.textContent = cam.label || `摄像头 ${index + 1}`;
            cameraSelect.appendChild(option);
        });

        const ids = new Set([...cameraSelect.options].map((o) => o.value));
        if (previousId && ids.has(previousId)) {
            cameraSelect.value = previousId;
        }

        updateStartButtonState();
    } catch (error) {
        console.error('加载摄像头列表失败:', error);
        cameraSelect.innerHTML = '';
        const errOpt = document.createElement('option');
        errOpt.value = '';
        errOpt.textContent = '摄像头列表加载失败';
        cameraSelect.appendChild(errOpt);
        updateStartButtonState();
    }
}

window.addEventListener('load', async () => {
    await loadDeviceConfig();
    await loadCameraDevices();
    initHandDetection();
});
