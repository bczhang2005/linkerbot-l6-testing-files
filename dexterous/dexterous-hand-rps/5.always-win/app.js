// 剪刀石头布的姿势定义（按不同手型号分类）
const GesturePresets = {
    // L10 蜗轮蜗杆型号
    'L10_worm_gear': {
        ROCK: {
            finger: [1,49, 128, 40, 36, 41, 46],
            palm: [4,128, 128, 128, 128]
        },
        PAPER: {
            finger: [1,255, 255, 255, 255, 255, 255],
            palm: [4,128, 128, 128, 128]
        },
        SCISSORS: {
            finger: [1,0, 103, 255, 255, 0, 0],
            palm: [4,255, 128, 128, 128]
        }
    },
    // L10 球关节型号
    'L10_ball_joint': {
        ROCK: {
            finger: [1,49, 128, 40, 36, 41, 46],
            palm: [4,128, 128, 128, 128]
        },
        PAPER: {
            finger: [1,255, 255, 255, 255, 255, 255],
            palm: [4,128, 128, 128, 128]
        },
        SCISSORS: {
            finger: [1,0, 103, 255, 255, 0, 0],
            palm: [4,255, 128, 128, 128]
        }
    },
    // O6/L6 型号
    'O6/L6': {
        ROCK: {
            finger: [1,65, 170, 25, 25, 25, 25]
        },
        PAPER: {
            finger: [1,255, 255, 255, 255, 255, 255]
          
        },
        SCISSORS: {
            finger: [1,65,180,255,255,25,25]
        }
    },
    // L25 型号（base64 编码的帧序列，每帧解码后为一条 CAN 数据）
    'L25': {
        ROCK: {
            frames: [
                "AaAAAAAA", "Av+jgVY+", "A4xB////", "BqaK////",
                "AYAAAAAA", "Av+AgICA", "A7sNAAUP", "Bm4MDAIJ"
            ]
        },
        PAPER: {
            frames: [
                "AYAAAAAA", "Av+jgVY+", "A///////", "Bv//////"
            ]
        },
        SCISSORS: {
            frames: [
                "AYAAAAAA", "Av/LgYCA", "A7v//wUP", "Bm7//wIJ"
            ]
        }
    }
};

function parseBaseUrl(url) {
    const urlObj = new URL(url);
    return urlObj.searchParams.get('baseurl');
}

// 获取设备配置信息（页面加载时调用一次）
async function loadDeviceConfig() {
    try {
        const response = await fetch(`${baseHost}/api/hand/devices`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });
        
        const data = await response.json();
        
        if (data.status === 'ok' && data.data && data.data.length > 0) {
            // 保存所有设备配置信息（数组）
            deviceConfig = data.data.map(config => {
                // 处理 model 字段，可能是 "O6/L6" 这样的格式
                let model = config.model || 'unknown';
                // 保持原始格式，不拆分
                
                return {
                    interface: config.interface || 'can0',
                    model: model, // L10 / L6 / O6 / O7 / O6/L6
                    variant: config.variant || '', // 仅 L10 有此字段：worm_gear 或 ball_joint
                    side: config.side || 'right' // left / right
                };
            });
            
            console.log('设备配置加载成功，共', deviceConfig.length, '个设备:', deviceConfig);
            
            // 输出每个设备的信息
            deviceConfig.forEach((config, index) => {
                if (config.model === 'L10') {
                    console.log(`设备 ${index + 1}: L10 型号，变体: ${config.variant || '未指定'}, 接口: ${config.interface}, 手: ${config.side}`);
                } else {
                    console.log(`设备 ${index + 1}: ${config.model} 型号, 接口: ${config.interface}, 手: ${config.side}`);
                }
            });
            
            return deviceConfig;
        } else {
            console.error('获取设备配置失败:', data.message || data.error);
            return null;
        }
    } catch (error) {
        console.error('加载设备配置时发生错误:', error);
        return null;
    }
}

// 批量发送 CAN 消息到后端（按型号分组，后端使用二级协程处理）
async function sendBatchCanMessages(modelsData) {
    const backendUrl = `${batchHost}/api/gesture/batch`;
    
    try {
        const response = await fetch(backendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ models: modelsData })
        });

        const data = await response.json();
        if (data.status === 'ok') {
            console.log(`批量 CAN 消息发送完成: 成功 ${data.success}, 失败 ${data.failed}`);
            if (data.errors && data.errors.length > 0) {
                console.warn('部分消息发送失败:', data.errors);
            }
            return data.success > 0;
        } else {
            console.error(`批量 CAN 消息发送失败:`, data.message || '未知错误');
            return false;
        }
    } catch (error) {
        console.error(`批量 CAN 消息请求错误:`, error);
        return false;
    }
}

// 根据设备配置获取对应的手势预设键
function getGesturePresetKey(config) {
    if (!config) {
        console.warn('设备配置为空，使用默认配置');
        return 'O6/L6'; // 默认使用 O6/L6
    }
    
    const { model, variant } = config;
    
    // L25 型号
    if (model === 'L25') {
        return 'L25';
    }
    // L10 型号根据 variant 区分
    else if (model === 'L10') {
        if (variant === 'worm_gear') {
            return 'L10_worm_gear';
        } else if (variant === 'ball_joint') {
            return 'L10_ball_joint';
        } else {
            // L10 但没有指定 variant，默认使用 worm_gear
            console.warn('L10 型号未指定 variant，默认使用 worm_gear');
            return 'L10_worm_gear';
        }
    }
    // O6/L6 型号
    else if (model === 'O6/L6' || model === 'O6' || model === 'L6') {
        return 'O6/L6';
    }
    // 其他未知型号，默认使用 O6/L6
    else {
        console.warn(`未知型号 ${model}，使用默认配置 O6/L6`);
        return 'O6/L6';
    }
}

// 根据左右手获取 CAN ID
function getCanId(side) {
    // 左手为 0x28，右手为 0x27
    return side === 'left' ? 0x28 : 0x27;
}

// 封装调用函数 - 批量发送所有设备的 CAN 消息到后端（后端负责并发发送并复用连接）
async function performGesture(gesture) {
    // 检查设备配置是否已加载
    if (!deviceConfig || !Array.isArray(deviceConfig) || deviceConfig.length === 0) {
        console.error('设备配置未加载或为空，无法执行手势');
        return;
    }
    
    console.log(`开始执行手势 ${gesture}，共 ${deviceConfig.length} 个设备（按型号分组发送到后端）`);
    
    // 按型号分组组织数据
    const modelsData = {};
    
    for (let index = 0; index < deviceConfig.length; index++) {
        const config = deviceConfig[index];
        
        try {
            const presetKey = getGesturePresetKey(config);
            const modelPresets = GesturePresets[presetKey];
            
            if (!modelPresets) {
                console.error(`设备 ${index + 1} (${config.interface}): 未找到对应型号的手势预设:`, presetKey);
                continue;
            }
            
            // 获取具体的手势预设（ROCK、PAPER 或 SCISSORS）
            const preset = modelPresets[gesture];
            
            if (!preset) {
                console.error(`设备 ${index + 1} (${config.interface}): 无效的手势:`, gesture);
                continue;
            }
            
            // 使用 presetKey 作为型号标识（如 'L10_worm_gear', 'O6/L6', 'L25'）
            if (!modelsData[presetKey]) {
                modelsData[presetKey] = {
                    interface: [],
                    id: [],
                    data: []
                };
            }
            
            // 添加接口和ID
            modelsData[presetKey].interface.push(config.interface);
            modelsData[presetKey].id.push(getCanId(config.side));
            
            // 收集数据，每种型号只需填充一次 data
            if (modelsData[presetKey].data.length === 0) {
                if (preset.frames) {
                    // L25 等使用 frames 字段：base64 字符串数组，解码为 [[int...], ...]
                    for (const b64 of preset.frames) {
                        const bytes = Array.from(atob(b64), c => c.charCodeAt(0));
                        modelsData[presetKey].data.push(bytes);
                    }
                } else {
                    // 其他型号使用 finger / palm 字段
                    modelsData[presetKey].data.push(preset.finger);
                    if (preset.palm) {
                        modelsData[presetKey].data.push(preset.palm);
                    }
                }
            }
            
            if (DEBUG_CAN_LOG) {
                console.log(`设备 ${index + 1} (${config.interface}, ${config.side}手): 使用 ${presetKey} 配置执行手势 ${gesture}`);
            }
        } catch (error) {
            console.error(`设备 ${index + 1} (${config.interface}): 准备消息失败`, error);
        }
    }
    
    // 批量发送所有消息到后端（按型号分组）
    if (Object.keys(modelsData).length > 0) {
        await sendBatchCanMessages(modelsData);
        const totalInterfaces = Object.values(modelsData).reduce((sum, model) => sum + model.interface.length, 0);
        console.log(`手势 ${gesture} 执行完成（已按型号分组发送，共 ${Object.keys(modelsData).length} 个型号，${totalInterfaces} 个接口）`);
    } else {
        console.warn(`手势 ${gesture} 没有可发送的消息`);
    }
}

function getCounterGesture(gesture) {
    switch (gesture) {
        case "石头":
            return "PAPER";
        case "布":
            return "SCISSORS";
        case "剪刀":
            return "ROCK";
        default:
            return null;
    }
}

async function sendCounterGesture(gesture) {
    const counterGesture = getCounterGesture(gesture);
    if (!counterGesture) {
        return;
    }

    // 后端还没响应时，不叠加请求；只保留最新动作，避免请求风暴。
    if (gestureSendInFlight) {
        queuedCounterGesture = counterGesture;
        return;
    }

    gestureSendInFlight = true;
    try {
        await performGesture(counterGesture);
    } finally {
        gestureSendInFlight = false;
        if (queuedCounterGesture && queuedCounterGesture !== counterGesture) {
            const nextGesture = queuedCounterGesture;
            queuedCounterGesture = null;
            gestureSendInFlight = true;
            try {
                await performGesture(nextGesture);
            } finally {
                gestureSendInFlight = false;
            }
        } else {
            queuedCounterGesture = null;
        }
    }
}

function resetGestureTriggerState() {
    lastDetectedGesture = "";
    pendingGesture = "";
    queuedCounterGesture = null;
    if (gestureChangeTimeout) {
        clearTimeout(gestureChangeTimeout);
        gestureChangeTimeout = null;
    }
}

// 处理手势变化，使用防抖动技术确保手势稳定
function handleGestureChange(newGesture, confidence) {
    const isValidGesture = newGesture !== "未识别" && confidence >= GESTURE_ACCEPT_CONFIDENCE;

    if (!isValidGesture) {
        resetGestureTriggerState();
        return;
    }

    if (newGesture === lastDetectedGesture || newGesture === pendingGesture) {
        return;
    }

    if (gestureChangeTimeout) {
        clearTimeout(gestureChangeTimeout);
    }

    pendingGesture = newGesture;
    // 手势稳定一段时间后才触发，且同一稳定手势只下发一次。
    gestureChangeTimeout = setTimeout(() => {
        lastDetectedGesture = newGesture;
        pendingGesture = "";
        gestureChangeTimeout = null;

        playGestureSound(newGesture);
        sendCounterGesture(newGesture);
    }, GESTURE_STABLE_DELAY_MS);
}

// 播放手势音效 (可选功能)
function playGestureSound(gesture) {
    // 这里可以根据不同手势播放不同的音效
    // 简单的音效实现
    const context = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = context.createOscillator();
    const gainNode = context.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(context.destination);
    
    // 根据手势设置不同的音调
    switch(gesture) {
        case "石头":
            oscillator.frequency.value = 261.63; // C4
            break;
        case "剪刀":
            oscillator.frequency.value = 329.63; // E4
            break;
        case "布":
            oscillator.frequency.value = 392.00; // G4
            break;
    }
    
    // 短暂的音效
    gainNode.gain.value = 0.1;
    oscillator.start();
    
    setTimeout(() => {
        oscillator.stop();
    }, 200);
}// 页面元素
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
const eventLogDiv = document.getElementById('event-log');
const clearLogButton = document.getElementById('clear-log-btn');

// 手势置信度元素
const rockConfidence = document.getElementById('rock-confidence');
const paperConfidence = document.getElementById('paper-confidence');
const scissorsConfidence = document.getElementById('scissors-confidence');

// 手势卡片元素
const rockCard = document.getElementById('rock-card');
const paperCard = document.getElementById('paper-card');
const scissorsCard = document.getElementById('scissors-card');

// 全局变量
let hands;
/** 手部模型是否已就绪（与是否正在采集视频分开） */
let handModelReady = false;
/** requestAnimationFrame 驱动检测的句柄（避免使用 Camera 类二次 getUserMedia 覆盖所选设备） */
let videoFrameRafId = null;
let lastFrameTime = 0;
let isRunning = false;
let currentGesture = "未识别";
let gestureConfidence = 0;
let lastDetectedGesture = ""; // 用于记录上一次稳定触发的手势
let pendingGesture = ""; // 等待稳定确认的候选手势
let gestureChangeTimeout = null; // 用于防抖动的超时变量
let gestureSendInFlight = false; // 避免同一时刻叠加多个机械手请求
let queuedCounterGesture = null; // 请求进行中时只保留最新的待发送动作
let deviceConfig = null; // 存储设备配置信息
let baseHost = "http://localhost:7080";
let batchHost = "http://localhost:8899";
const GESTURE_STABLE_DELAY_MS = 300;
const DEBUG_CAN_LOG = false;
const FPS_UPDATE_INTERVAL_MS = 250;
const LANDMARKS_UPDATE_INTERVAL_MS = 200;

let lastFpsUpdate = 0;
let lastLandmarksInfoUpdate = 0;
let lastHandCountText = "";
let lastGestureDisplayText = "";
const RPS_RECOGNIZER = window.RPSGestureRecognition;
const GESTURE_ACCEPT_CONFIDENCE = RPS_RECOGNIZER.ACCEPTED_CONFIDENCE;

// 定义手部连接关系 (MediaPipe Hands模型的21个关键点连接方式)
const HAND_CONNECTIONS = [
    [0, 1], [1, 2], [2, 3], [3, 4],  // 拇指
    [0, 5], [5, 6], [6, 7], [7, 8],  // 食指
    [0, 9], [9, 10], [10, 11], [11, 12],  // 中指
    [0, 13], [13, 14], [14, 15], [15, 16],  // 无名指
    [0, 17], [17, 18], [18, 19], [19, 20],  // 小指
    [5, 9], [9, 13], [13, 17],  // 掌心连接
    [0, 5], [0, 17]  // 手腕连接
];

function setTextIfChanged(element, text) {
    if (element && element.textContent !== text) {
        element.textContent = text;
    }
}

function setCardActive(card, active) {
    if (!card) return;
    if (active && !card.classList.contains('active')) {
        card.classList.add('active');
    } else if (!active && card.classList.contains('active')) {
        card.classList.remove('active');
    }
}

// 设置canvas大小
function setupCanvas() {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
}

// 初始化MediaPipe Hands模型
async function initHandDetection() {
    try {
        handModelReady = false;
        statusDiv.textContent = "正在加载手部检测模型...";
        
        hands = new Hands({
            locateFile: (file) => {
                return `../6.gameplay/libs/mediapipe/hands/${file}`;
                //return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
            }
        });

        // 配置模型
        await hands.setOptions({
            maxNumHands: 1,              // 最多检测2只手
            modelComplexity: 1,          // 模型复杂度 (0, 1)
            minDetectionConfidence: 0.5, // 最小检测置信度
            minTrackingConfidence: 0.5   // 最小跟踪置信度
        });

        // 设置结果回调
        hands.onResults(onResults);

        handModelReady = true;
        statusDiv.textContent = "模型加载完成，请选择摄像头后点击「启动摄像头」";
        updateStartButtonState();

    } catch (error) {
        handModelReady = false;
        statusDiv.textContent = `初始化失败: ${error.message}`;
        console.error("初始化失败:", error);
        updateStartButtonState();
    }
}

// 处理检测结果
function onResults(results) {
    // 计算FPS
    const now = performance.now();
    const elapsed = now - lastFrameTime;
    lastFrameTime = now;
    if (now - lastFpsUpdate >= FPS_UPDATE_INTERVAL_MS) {
        lastFpsUpdate = now;
        setTextIfChanged(fpsCounter, `FPS: ${Math.round(1000 / elapsed)}`);
    }

    // 清除canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 更新检测到的手数量
    const handCount = results.multiHandLandmarks?.length || 0;
    if (`${handCount}` !== lastHandCountText) {
        lastHandCountText = `${handCount}`;
        setTextIfChanged(handCountSpan, lastHandCountText);
    }

    // 如果检测到手
    if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        let bestGesture = null;

        // 绘制手部关键点
        for (let i = 0; i < results.multiHandLandmarks.length; i++) {
            const landmarks = results.multiHandLandmarks[i];
            const handedness = results.multiHandedness[i].label; // 'Left' 或 'Right'
            
            // 绘制连接线和关键点
            drawConnectors(ctx, landmarks, HAND_CONNECTIONS, 
                { color: handedness === 'Left' ? '#00FF00' : '#FF0000', lineWidth: 5 });
            drawLandmarks(ctx, landmarks, 
                { color: handedness === 'Left' ? '#00CC00' : '#CC0000', lineWidth: 2 });
            
            // 在手腕处标示左/右手
            const wrist = landmarks[0];
            ctx.fillStyle = handedness === 'Left' ? '#00FF00' : '#FF0000';
            ctx.font = '16px Arial';
            ctx.fillText(handedness === 'Left' ? '左手' : '右手', 
                         wrist.x * canvas.width, 
                         wrist.y * canvas.height - 10);
            
            // 识别石头剪刀布手势
            const gesture = recognizeRockPaperScissors(landmarks);
            
            // 在手部上方显示识别的手势
            ctx.font = '20px Arial';
            ctx.fillStyle = '#FFFFFF';
            ctx.strokeStyle = '#000000';
            ctx.lineWidth = 3;
            const gestureText = `${gesture.name} (${Math.round(gesture.confidence * 100)}%)`;
            const textX = wrist.x * canvas.width;
            const textY = wrist.y * canvas.height - 30;
            ctx.strokeText(gestureText, textX, textY);
            ctx.fillText(gestureText, textX, textY);
            
            if (!bestGesture || gesture.confidence > bestGesture.confidence) {
                bestGesture = gesture;
            }
        }

        if (bestGesture) {
            updateGestureConfidence(bestGesture.name, bestGesture.confidence);

            if (bestGesture.name !== "未识别" && bestGesture.confidence >= GESTURE_ACCEPT_CONFIDENCE) {
                currentGesture = bestGesture.name;
                gestureConfidence = bestGesture.confidence;
            } else {
                currentGesture = "未识别";
                gestureConfidence = bestGesture.confidence;
            }

            handleGestureChange(bestGesture.name, bestGesture.confidence);
        }

        // 详细调试信息限频刷新，不影响每帧识别与绘制。
        if (now - lastLandmarksInfoUpdate >= LANDMARKS_UPDATE_INTERVAL_MS) {
            lastLandmarksInfoUpdate = now;
            updateLandmarksInfo(results.multiHandLandmarks, results.multiHandedness);
        }
    } else {
        setTextIfChanged(landmarksInfo, "尚未检测到手部");
        currentGesture = "等待手势...";
        gestureConfidence = 0;
        resetGestureConfidence();
        resetGestureTriggerState();
    }
    
    // 更新屏幕上的手势显示
    updateGestureDisplay();
}

// 识别石头剪刀布手势
function recognizeRockPaperScissors(landmarks) {
    return RPS_RECOGNIZER.recognizeGesture(landmarks);
}


// 更新手势置信度显示
function updateGestureConfidence(gesture, confidence) {
    const confidencePercent = Math.round(confidence * 100);
    const isRock = gesture === "石头";
    const isPaper = gesture === "布";
    const isScissors = gesture === "剪刀";

    // 一次性同步三张卡片，避免每帧先清空再激活导致重复 DOM 写入。
    setTextIfChanged(rockConfidence, isRock ? `${confidencePercent}%` : "0%");
    setTextIfChanged(paperConfidence, isPaper ? `${confidencePercent}%` : "0%");
    setTextIfChanged(scissorsConfidence, isScissors ? `${confidencePercent}%` : "0%");

    setCardActive(rockCard, isRock);
    setCardActive(paperCard, isPaper);
    setCardActive(scissorsCard, isScissors);
}

// 重置手势置信度显示
function resetGestureConfidence() {
    setTextIfChanged(rockConfidence, "0%");
    setTextIfChanged(paperConfidence, "0%");
    setTextIfChanged(scissorsConfidence, "0%");
    
    setCardActive(rockCard, false);
    setCardActive(paperCard, false);
    setCardActive(scissorsCard, false);
}

// 更新手势显示
function updateGestureDisplay() {
    let icon = "";
    
    // 根据手势设置图标
    switch(currentGesture) {
        case "石头":
            icon = "👊";
            break;
        case "布":
            icon = "✋";
            break;
        case "剪刀":
            icon = "✌️";
            break;
        default:
            icon = "";
            break;
    }
    
    // 更新显示
    let nextText;
    if (currentGesture === "等待手势...") {
        nextText = currentGesture;
    } else if (currentGesture === "未识别") {
        nextText = `未识别 (${Math.round(gestureConfidence * 100)}%)`;
    } else {
        const confidencePercent = Math.round(gestureConfidence * 100);
        nextText = `${icon} ${currentGesture} ${confidencePercent}%`;
    }
    if (nextText !== lastGestureDisplayText) {
        lastGestureDisplayText = nextText;
        setTextIfChanged(gestureDisplay, nextText);
    }
}

// 更新关键点信息显示
function updateLandmarksInfo(multiHandLandmarks, multiHandedness) {
    let infoText = '';
    
    for (let i = 0; i < multiHandLandmarks.length; i++) {
        const handedness = multiHandedness[i].label;
        const confidence = multiHandedness[i].score.toFixed(2);
        const landmarks = multiHandLandmarks[i];
        
        // 识别手势
        const gesture = recognizeRockPaperScissors(landmarks);
        
        infoText += `手 #${i+1} (${handedness === 'Left' ? '左手' : '右手'}, 置信度: ${confidence})\n`;
        infoText += `检测到的手势: ${gesture.name} (置信度: ${gesture.confidence.toFixed(2)})\n`;

        for (const line of RPS_RECOGNIZER.getDebugLines(gesture)) {
            infoText += `${line}\n`;
        }

        infoText += '\n';
    }
    
    setTextIfChanged(landmarksInfo, infoText || "尚未检测到手部");
}

// 根据模型就绪、是否已选设备、是否在运行，更新「启动」按钮
function updateStartButtonState() {
    const selected = cameraSelect && cameraSelect.value;
    const canStart = Boolean(handModelReady && selected && !isRunning);
    startButton.disabled = !canStart;
}

// 启动摄像头（仅在用户选择设备后由按钮触发）
async function startCamera() {
    const selectedDeviceId = cameraSelect.value;
    if (!selectedDeviceId) {
        statusDiv.textContent = "请先在下拉框中选择摄像头";
        return;
    }
    if (!handModelReady || !hands) {
        statusDiv.textContent = "模型尚未就绪，请稍候";
        return;
    }

    try {
        statusDiv.textContent = "正在启动摄像头...";

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
            "loadedmetadata",
            async () => {
                setupCanvas();
                // 授权后重新枚举，便于显示设备名称（首次加载时 label 常为空）
                try {
                    await loadCameraDevices(selectedDeviceId);
                } catch (e) {
                    console.warn("刷新摄像头列表失败:", e);
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
        console.error("摄像头启动失败:", error);
        updateStartButtonState();
    }
}

// 使用已绑定到 <video> 的 MediaStream 逐帧送检（不再调用 Camera.start 以免再次 getUserMedia）
function startDetection() {
    if (isRunning) return;

    isRunning = true;
    statusDiv.textContent = "正在检测手部...";

    const loop = () => {
        if (!isRunning) {
            return;
        }
        Promise.resolve(hands.send({ image: video })).then(() => {
            videoFrameRafId = requestAnimationFrame(loop);
        }).catch((err) => {
            console.error("hands.send 失败:", err);
            statusDiv.textContent = `检测中断: ${err.message}`;
            stopDetection();
        });
    };
    videoFrameRafId = requestAnimationFrame(loop);
}

// 停止检测
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
        const tracks = video.srcObject.getTracks();
        tracks.forEach((track) => track.stop());
        video.srcObject = null;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    handCountSpan.textContent = "0";
    landmarksInfo.textContent = "尚未检测到手部";
    statusDiv.textContent = "检测已停止";
    currentGesture = "等待手势...";
    gestureConfidence = 0;
    gestureDisplay.textContent = "等待手势...";
    resetGestureConfidence();
    resetGestureTriggerState();

    stopButton.disabled = true;
    if (cameraSelect) {
        cameraSelect.disabled = false;
    }
    updateStartButtonState();
}

// 辅助函数 - 绘制关键点连接线
function drawConnectors(ctx, landmarks, connections, options) {
    const { color = 'white', lineWidth = 1 } = options || {};
    
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    
    for (const connection of connections) {
        const [i, j] = connection;
        const from = landmarks[i];
        const to = landmarks[j];
        
        if (from && to) {
            ctx.beginPath();
            ctx.moveTo(from.x * canvas.width, from.y * canvas.height);
            ctx.lineTo(to.x * canvas.width, to.y * canvas.height);
            ctx.stroke();
        }
    }
}

// 辅助函数 - 绘制关键点
function drawLandmarks(ctx, landmarks, options) {
    const { color = 'red', lineWidth = 2 } = options || {};
    
    ctx.fillStyle = color;
    
    for (const landmark of landmarks) {
        ctx.beginPath();
        ctx.arc(
            landmark.x * canvas.width,
            landmark.y * canvas.height,
            lineWidth * 2,
            0,
            2 * Math.PI
        );
        ctx.fill();
    }
}

// 设置事件监听器
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

// 页面加载完成后初始化
window.addEventListener('load', async () => {
    // 首先加载设备配置信息（只加载一次）
    await loadDeviceConfig();
        // 加载摄像头列表
    await loadCameraDevices();
    
    // 然后初始化手部检测模型
    initHandDetection();
    
    // 添加手势事件监听器
    document.addEventListener('gestureDetected', (event) => {
        const gestureData = event.detail;
        
        // 在页面中显示事件信息
        const messageContainer = document.createElement('div');
        messageContainer.className = 'gesture-message';
        messageContainer.innerHTML = `
            <div class="gesture-message-content">
                <strong>检测到手势:</strong> ${gestureData.gesture} 
                <span class="gesture-message-confidence">置信度: ${Math.round(gestureData.confidence * 100)}%</span>
                <span class="gesture-message-time">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
        
        // 添加到页面
        document.body.appendChild(messageContainer);
        
        // 设置动画
        setTimeout(() => {
            messageContainer.classList.add('show');
        }, 10);
        
        // 2秒后移除消息
        setTimeout(() => {
            messageContainer.classList.remove('show');
            setTimeout(() => {
                document.body.removeChild(messageContainer);
            }, 500);
        }, 2000);
    });
});

/**
 * 枚举视频输入设备并填充下拉框（页面加载时调用；未授权时可能没有 device label）
 * @param {string} [preferredDeviceId] 重建选项后尽量恢复选中项
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

        console.log('检测到摄像头数量:', cameras.length);
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
