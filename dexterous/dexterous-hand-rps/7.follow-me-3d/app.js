/**
 * 3D 跟随模式（D405）：WebSocket 收 3D 手系 + 2D 骨架点 → L6 跟随
 * 左右手标签、组包、关节条显示与 4.follow-me 对齐。
 */

const RETARGET = window.HandRetarget;
/** D405 外置摄像头：与 4.follow-me MIRROR_HAND_LABELS 一致 */
RETARGET.MIRROR_HAND_LABELS = false;

const SEND_INTERVAL_MS = 50;
const FOLLOW_MIN_CHANGED_VALUE = 2;
/** 检测偶发丢帧时保持上一帧手数据，避免骨架/关节条闪烁 */
const HANDS_HOLD_MS = 250;

const statusDiv = document.getElementById('status');
const connectBtn = document.getElementById('connect-btn');
const disconnectBtn = document.getElementById('disconnect-btn');
const wsUrlInput = document.getElementById('ws-url');
const previewImg = document.getElementById('preview');
const fpsCounter = document.getElementById('fps');
const gestureDisplay = document.getElementById('gesture-display');
const handCountSpan = document.getElementById('hand-count');
const landmarksInfo = document.getElementById('landmarks-info');
const jointBarsEl = document.getElementById('joint-bars');
const wristDepthEl = document.getElementById('wrist-depth');
const proofWristEl = document.getElementById('proof-wrist');
const proofSpreadEl = document.getElementById('proof-spread');
const proofIndexDepthEl = document.getElementById('proof-index-depth');
const depthBarFillEl = document.getElementById('depth-bar-fill');
const ixX = document.getElementById('ix-x');
const ixY = document.getElementById('ix-y');
const ixZ = document.getElementById('ix-z');
const thX = document.getElementById('th-x');
const thY = document.getElementById('th-y');
const thZ = document.getElementById('th-z');

const DEPTH_BAR_NEAR_CM = 20;
const DEPTH_BAR_FAR_CM = 60;

let ws = null;
let deviceConfig = null;
let baseHost = 'http://localhost:7080';
let batchHost = 'http://localhost:8899';

let smoothedLeft = null;
let smoothedRight = null;
let lastFollowSend = 0;
let followSendInFlight = false;
let queuedFollowDevices = null;
let lastSentFollowDevices = null;
let lastGoodHands = [];
let lastGoodHandsAt = 0;

function setText(el, text) {
    if (el && el.textContent !== text) {
        el.textContent = text;
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
            console.log('设备配置:', deviceConfig);
            return deviceConfig;
        }
        console.warn('设备配置为空');
        return null;
    } catch (error) {
        console.error('加载设备配置失败:', error);
        return null;
    }
}

async function sendFollowBatch(devices) {
    if (!devices || devices.length === 0) return false;
    try {
        const response = await fetch(`${batchHost}/api/follow/batch`, {
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
        if (Math.abs(a[i] - b[i]) >= FOLLOW_MIN_CHANGED_VALUE) return true;
    }
    return false;
}

async function sendFollowBatchCoalesced(devices) {
    if (!devices || devices.length === 0) return;
    if (!hasMeaningfulFollowChange(lastSentFollowDevices, devices)) return;
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

/** 与 4.follow-me buildFollowDevices 相同逻辑 */
function buildFollowDevices(hands) {
    if (!deviceConfig || deviceConfig.length === 0) return [];

    const devices = [];
    for (const config of deviceConfig) {
        const presetKey = getGesturePresetKey(config);
        if (presetKey === 'L25') continue;

        const hand = RETARGET.findHandForSide(hands, config.side);
        if (!hand) continue;

        const angles = config.side === 'left' ? smoothedLeft : smoothedRight;
        if (!angles) continue;

        const { basic, swing } = RETARGET.anglesToLogical(angles);
        const pack = RETARGET.logicalToFollowData(presetKey, basic, swing);
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

/** 短时保留上一帧手部，与 Python 端 HANDS_HOLD_S 配合 */
function getStableHands(hands) {
    if (hands.length > 0) {
        lastGoodHands = hands;
        lastGoodHandsAt = performance.now();
        return hands;
    }
    if (performance.now() - lastGoodHandsAt < HANDS_HOLD_MS && lastGoodHands.length > 0) {
        return lastGoodHands;
    }
    return [];
}

function pickPrimaryHand(hands) {
    const cfg = deviceConfig && deviceConfig[0];
    if (cfg) {
        const matched = RETARGET.findHandForSide(hands, cfg.side);
        if (matched) return matched;
    }
    return hands[0] || null;
}

function fmtM(v) {
    return typeof v === 'number' && !Number.isNaN(v) ? v.toFixed(3) : '--';
}

function clearDepthProof() {
    if (wristDepthEl) wristDepthEl.textContent = '-- cm';
    if (proofWristEl) proofWristEl.textContent = '-- cm';
    if (proofSpreadEl) proofSpreadEl.textContent = '-- cm';
    if (proofIndexDepthEl) proofIndexDepthEl.textContent = '-- cm';
    if (depthBarFillEl) depthBarFillEl.style.width = '0%';
    [ixX, ixY, ixZ, thX, thY, thZ].forEach((el) => {
        if (el) el.textContent = '--';
    });
}

function updateDepthProof(hand) {
    const proof = hand && hand.depth_proof;
    if (!proof) {
        clearDepthProof();
        return;
    }

    const wristCm = proof.wrist_depth_cm;
    const spreadCm = proof.finger_spread_cm;
    const indexCm = proof.index_tip_depth_cm;

    if (wristDepthEl) wristDepthEl.textContent = `${wristCm} cm`;
    if (proofWristEl) proofWristEl.textContent = `${wristCm} cm`;
    if (proofSpreadEl) proofSpreadEl.textContent = `${spreadCm} cm`;
    if (proofIndexDepthEl) proofIndexDepthEl.textContent = `${indexCm} cm`;

    if (depthBarFillEl && typeof wristCm === 'number') {
        const t = (wristCm - DEPTH_BAR_NEAR_CM) / (DEPTH_BAR_FAR_CM - DEPTH_BAR_NEAR_CM);
        const pct = Math.max(0, Math.min(100, t * 100));
        depthBarFillEl.style.width = `${pct}%`;
    }

    const ix = proof.index_tip_3d || [];
    const th = proof.thumb_tip_3d || [];
    if (ixX) ixX.textContent = fmtM(ix[0]);
    if (ixY) ixY.textContent = fmtM(ix[1]);
    if (ixZ) ixZ.textContent = fmtM(ix[2]);
    if (thX) thX.textContent = fmtM(th[0]);
    if (thY) thY.textContent = fmtM(th[1]);
    if (thZ) thZ.textContent = fmtM(th[2]);
}

function updateJointBars(angles) {
    if (!jointBarsEl || !angles) return;
    const names = RETARGET.JOINT_LABELS_SHORT;
    const driven = RETARGET.L6_DRIVEN_JOINT_COUNT;
    jointBarsEl.innerHTML = names
        .map((name, i) => {
            const v = Math.round(angles[i]);
            const inactive = i >= driven;
            const suffix = inactive ? '·' : '';
            const cls = inactive ? 'joint-row inactive' : 'joint-row';
            return `<div class="${cls}"><span>${name}${suffix}</span><div class="joint-bar"><i style="width:${v}%"></i></div><span>${v}</span></div>`;
        })
        .join('');
}

function processFrame(payload) {
    const rawHands = payload.hands || [];
    const hands = getStableHands(rawHands);
    const hasLiveHand = rawHands.length > 0;

    setText(handCountSpan, String(hasLiveHand ? rawHands.length : hands.length));
    setText(fpsCounter, `FPS: ${payload.fps || 0}`);

    if (payload.preview) {
        previewImg.src = `data:image/jpeg;base64,${payload.preview}`;
    }

    if (hands.length === 0) {
        if (!hasLiveHand) {
            smoothedLeft = null;
            smoothedRight = null;
            queuedFollowDevices = null;
            lastSentFollowDevices = null;
            setText(gestureDisplay, '等待 3D 手部…');
            setText(landmarksInfo, '尚未检测到手部');
            if (jointBarsEl) jointBarsEl.innerHTML = '';
            clearDepthProof();
        }
        return;
    }

    const primaryHand = pickPrimaryHand(hands);
    updateDepthProof(primaryHand);

    let infoText = '';
    for (const hand of hands) {
        const trueLabel = RETARGET.getTrueHandLabel(hand.label);
        const raw = RETARGET.computeAngles(hand.landmarks, { use3D: true });
        if (trueLabel === 'Left') {
            smoothedLeft = RETARGET.smoothAngles(smoothedLeft, raw);
        } else {
            smoothedRight = RETARGET.smoothAngles(smoothedRight, raw);
        }
        infoText += `${trueLabel === 'Left' ? '左' : '右'}手 (score ${hand.score})\n`;
        if (hand.depth_proof) {
            const p = hand.depth_proof;
            infoText += `  深度: 腕 ${p.wrist_depth_cm}cm | 指展 ${p.finger_spread_cm}cm\n`;
        }
        infoText += `  角度(0-100): ${raw.map((x) => Math.round(x)).join(', ')}\n\n`;
    }
    setText(landmarksInfo, infoText.trim());

    const primaryConfig = deviceConfig && deviceConfig[0];
    if (primaryConfig) {
        const trueLabel = primaryConfig.side === 'left' ? 'Left' : 'Right';
        const sm = primaryConfig.side === 'left' ? smoothedLeft : smoothedRight;
        if (sm) {
            updateJointBars(sm);
            setText(gestureDisplay, `3D 跟随 · ${trueLabel === 'Left' ? '左' : '右'}手`);
        }
    } else {
        const first = hands[0];
        const trueLabel0 = RETARGET.getTrueHandLabel(first.label);
        const sm0 = trueLabel0 === 'Left' ? smoothedLeft : smoothedRight;
        if (sm0) {
            updateJointBars(sm0);
            setText(gestureDisplay, `3D 跟随 · ${trueLabel0 === 'Left' ? '左' : '右'}手`);
        }
    }

    const now = performance.now();
    if (now - lastFollowSend >= SEND_INTERVAL_MS) {
        lastFollowSend = now;
        const devices = buildFollowDevices(hands);
        if (devices.length > 0) {
            sendFollowBatchCoalesced(devices);
        } else if (deviceConfig?.length && (smoothedLeft || smoothedRight)) {
            console.warn(
                '检测到 hand 但未组包 CAN：左右手标签与设备 side 不匹配，可切换 HandRetarget.MIRROR_HAND_LABELS'
            );
        }
    }
}

function connectTracking() {
    const url = wsUrlInput.value.trim();
    if (!url) {
        statusDiv.textContent = '请填写 WebSocket 地址';
        return;
    }
    if (ws) {
        ws.close();
    }
    statusDiv.textContent = `正在连接 ${url} …`;
    ws = new WebSocket(url);

    ws.onopen = () => {
        statusDiv.textContent = '3D 跟踪已连接，请将手伸到 D405 前方';
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
        wsUrlInput.disabled = true;
    };

    ws.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'frame') {
                processFrame(payload);
            }
        } catch (e) {
            console.warn('解析帧失败:', e);
        }
    };

    ws.onerror = () => {
        statusDiv.textContent = 'WebSocket 连接失败，请确认 hand_tracking_service.py 已启动';
    };

    ws.onclose = () => {
        ws = null;
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
        wsUrlInput.disabled = false;
        statusDiv.textContent = '3D 跟踪已断开';
        setText(handCountSpan, '0');
        setText(gestureDisplay, '等待 3D 手部…');
        clearDepthProof();
    };
}

function disconnectTracking() {
    if (ws) {
        ws.close();
    }
}

connectBtn.addEventListener('click', connectTracking);
disconnectBtn.addEventListener('click', disconnectTracking);

window.addEventListener('load', async () => {
    await loadDeviceConfig();
    if (deviceConfig && deviceConfig.length > 0) {
        statusDiv.textContent =
            '设备配置已加载。请启动 hand_tracking_service.py 后点击「连接 3D 跟踪」';
    } else {
        statusDiv.textContent = '未加载到灵巧手配置（7080）。跟随仍可调试，但无法控手。';
    }
});
