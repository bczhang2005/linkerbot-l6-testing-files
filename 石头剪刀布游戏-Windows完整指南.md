# 石头剪刀布游戏 · Windows 完整指南

本文档说明在 **Windows + PCAN + L6 灵巧手 + Intel RealSense D405** 环境下，从搭建环境到使用虚拟摄像头运行石头剪刀布竞技模式的完整流程。

> 文中所有 `cd` 命令均相对于**项目根目录**（包含 `testing/`、`dexterous/` 等子文件夹的目录）。请先将终端切换到你本机上的项目根目录。

---

## 目录

1. [系统架构](#1-系统架构)
2. [硬件清单与接线](#2-硬件清单与接线)
3. [软件安装（一次性）](#3-软件安装一次性)
4. [硬件连接验证](#4-硬件连接验证)
5. [日常启动流程](#5-日常启动流程)
6. [游戏操作说明](#6-游戏操作说明)
7. [常见问题排查](#7-常见问题排查)
8. [目录与脚本说明](#8-目录与脚本说明)
9. [简化方案](#9-简化方案)

---

## 1. 系统架构

Windows 上无法直接使用 Linux 版 `can-bridge`，因此采用 **linkerbot + 自研桥接脚本** 控制灵巧手；D405 的彩色画面通过 **RealSense SDK → 虚拟摄像头** 提供给浏览器。

```
┌─────────────────────────────────────────────────────────────────┐
│  浏览器  http://localhost:8899/6.gameplay/                       │
│    · 摄像头：OBS Virtual Camera（RealSense D405 彩色）           │
│    · GET :7080/api/hand/devices                                  │
└────────────┬───────────────────────────────┬────────────────────┘
             │ POST /api/gesture/batch        │
┌────────────▼───────────────────────────────┐│
│  dexterous-hand-rps (Go)  :8899            ││
│  路径：dexterous/dexterous-hand-rps/        ││
└────────────┬───────────────────────────────┘│
             │ POST :5260/api/can             │
┌────────────▼───────────────────────────────┐│
│  windows_l6_bridge.py  :5260 + :7080         ││
│  路径：testing/                              ││
│  linkerbot → PCAN_USBBUS1 → L6 左手          ││
└──────────────────────────────────────────────┘│
                                                │
┌───────────────────────────────────────────────▼──────────────────┐
│  realsense_virtual_cam.py  →  OBS Virtual Camera                   │
│  pyrealsense2 读 D405 Color → pyvirtualcam 输出                   │
└────────────────────────────────────────────────────────────────────┘
```

| 服务 | 端口 | 作用 |
|------|------|------|
| 设备配置 + CAN 桥接 | 7080 / 5260 | 告诉游戏有 L6 左手；把手势指令发给灵巧手 |
| 游戏 Web 服务 | 8899 | 网页 + 手势识别 + 转发 CAN |
| RealSense 虚拟摄像头 | （系统设备） | 把 D405 彩色流提供给浏览器 |
| OBS 虚拟摄像头 | （系统设备） | Windows 上 pyvirtualcam 的输出通道 |

---

## 2. 硬件清单与接线

### 2.1 清单

| 设备 | 说明 |
|------|------|
| LinkerHand L6 灵巧手 | 本指南以 **左手** 为例 |
| PEAK PCAN-USB 适配器 | 脚本默认 `PCAN_USBBUS1` |
| CAN 连接线 | 适配器 ↔ 灵巧手 |
| 24V 电源 | 灵巧手专用电源 |
| Intel RealSense D405 | 外置深度相机（本指南用于彩色手势识别） |
| USB 3.0 口 | D405 与 PCAN 建议接 USB 3.0 |

### 2.2 接线顺序

1. PCAN 适配器插入电脑 USB
2. CAN 线连接 PCAN 与灵巧手
3. 灵巧手接通 24V 电源并上电
4. D405 插入 USB 3.0 口（先插相机再插电脑更稳）

### 2.3 运行前检查

- [ ] 灵巧手电源指示灯正常
- [ ] 设备管理器中 PCAN 设备无感叹号
- [ ] **关闭 PCAN-View** 及一切占用 PCAN 的程序
- [ ] **关闭 RealSense Viewer / Depth Quality Tool**（运行虚拟摄像头脚本前）

---

## 3. 软件安装（一次性）

### 3.1 Go（游戏 Web 服务）

1. 安装 [Go 1.21+](https://go.dev/dl/)
2. 新开 PowerShell 验证：

```powershell
go version
```

### 3.2 PEAK PCAN 驱动

1. 安装 PEAK 官方 **PCAN 驱动** 与 **PCAN-Basic**
2. 设备管理器中确认适配器正常

### 3.3 linkerbot 环境（控灵巧手）

```powershell
conda activate linkerbot
pip install linkerbot
```

验证（在 `testing` 目录）：

```powershell
cd testing
python test_env_full.py
```

应看到 linkerbot SDK 可用。

### 3.4 Intel RealSense SDK（D405）

1. 安装 [Intel RealSense SDK 2.0](https://github.com/IntelRealSense/librealsense/releases)（含 Viewer）
2. 打开 **Intel RealSense Viewer**，确认 D405 的 **Color** 流为正常彩色
3. D405 的 Color 在 Viewer 里位于 **Stereo Module** 下（不是独立 RGB 模块）

### 3.5 OBS Studio（虚拟摄像头）

1. 安装 [OBS Studio](https://obsproject.com/)（建议 26+，当前常用 32.x）
2. 虚拟摄像头入口（OBS 30+）：
   - **不在「工具」菜单**
   - 在窗口 **右下角「控制按钮」**
   - 点击 **「开始虚拟摄像机」**（若显示「停止虚拟摄像机」表示已在运行）

### 3.6 Python 依赖

#### RealSense → 虚拟摄像头

```powershell
cd testing
pip install -r realsense_virtual_cam_requirements.txt
```

依赖：`pyrealsense2`、`pyvirtualcam`、`opencv-python`、`numpy`

#### L6 桥接（使用 linkerbot 环境）

```powershell
conda activate linkerbot
# linkerbot 已含 L6 控制，无需额外安装
```

### 3.7 克隆 / 获取游戏项目

游戏代码位于：

```
dexterous/dexterous-hand-rps/
```

首次运行会自动编译，无需单独 `go build`。

---

## 4. 硬件连接验证

在启动游戏前，确认 PCAN + L6 通信正常（**测完退出，释放 PCAN**）：

```powershell
conda activate linkerbot
cd testing
python test1_connect.py
```

确认脚本内配置：

```python
HAND_SIDE = "left"
INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
```

**预期结果：** `PCAN ✅  灵巧手 ✅`

若失败，可先运行：

```powershell
python 硬件连接测试.py
```

---

## 5. 日常启动流程

完整体验（**D405 彩色 + L6 动手**）需要 **4 个窗口 + 浏览器**，按以下顺序启动。

### 步骤 0：关闭冲突程序

- 关闭 PCAN-View、RealSense Viewer、其他 linkerbot 测试脚本

### 步骤 1：OBS 虚拟摄像头

1. 打开 **OBS Studio**
2. 右下角 **控制按钮** → **开始虚拟摄像机**
3. OBS 预览区可以是黑的，不影响后续脚本推流

### 步骤 2：RealSense 彩色 → 虚拟摄像头

**终端 A**（PowerShell）：

```powershell
cd testing
python realsense_virtual_cam.py
```

**预期输出：**

```text
RealSense 已启动 Color 流: 640x480 @ 30fps
虚拟摄像头已就绪: OBS Virtual Camera
```

保持此窗口运行，不要关闭。

> 若报 OBS 相关错误：回到步骤 1，确认 OBS 虚拟摄像机已启动。

### 步骤 3：L6 灵巧手桥接（7080 + 5260）

**终端 B**（PowerShell）：

```powershell
conda activate linkerbot
cd testing
python windows_l6_bridge.py
```

**预期输出：**

```text
[init] L6 已连接
Windows L6 桥接已启动
  设备配置: http://localhost:7080/api/hand/devices
  CAN 转发: http://localhost:5260/api/can
```

保持运行。若 `HAND_SIDE` 或 `INTERFACE` 与实物不符，编辑 `windows_l6_bridge.py` 顶部配置。

### 步骤 4：游戏 Web 服务（8899）

**终端 C**（PowerShell）：

```powershell
cd dexterous\dexterous-hand-rps
go run server.go -port 8899 -model l6
```

**预期输出：**

```text
🚀 灵巧手剪刀石头布游戏服务器启动
📡 监听地址: http://localhost:8899
```

### 步骤 5（可选）：快速验证灵巧手能否动作

**终端 D** 或复用终端 C 所在机器：

```powershell
$body = @{
  models = @{
    "O6/L6" = @{
      interface = @("can0")
      id        = @(40)
      data      = @(@(1,65,170,25,25,25,25))
    }
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8899/api/gesture/batch" -Method POST -Body $body -ContentType "application/json"
```

L6 应 **握拳**（石头）。`success: 1` 表示链路正常。

### 步骤 6：浏览器打开游戏

1. 打开 Chrome 或 Edge
2. 访问：**http://localhost:8899/6.gameplay/**
3. 摄像头下拉框选择 **「OBS Virtual Camera」**
   - ✅ 选 OBS Virtual Camera
   - ❌ 不要选 `Intel RealSense Depth Camera 405 Depth`（那是深度流，黑白且无法识别手势）
   - 内置 `Integrated Camera` 也可用于识别，但本指南目标是 D405 彩色
4. 点击 **启动摄像头** → 允许浏览器使用摄像头
5. 确认画面为 **彩色**，且「检测到的手」在举手时为 **1**
6. 点击 **开始游戏**

### 启动顺序一览

| 顺序 | 终端 | 命令 | 端口/设备 |
|------|------|------|-----------|
| 1 | OBS | 开始虚拟摄像机 | OBS Virtual Camera |
| 2 | A | `python realsense_virtual_cam.py` | RealSense → 虚拟摄像头 |
| 3 | B | `python windows_l6_bridge.py` | 7080 + 5260 |
| 4 | C | `go run server.go -port 8899 -model l6` | 8899 |
| 5 | 浏览器 | 打开 6.gameplay，选 OBS Virtual Camera | — |

---

## 6. 游戏操作说明

### 6.1 竞技模式界面

地址：http://localhost:8899/6.gameplay/

| 操作 | 说明 |
|------|------|
| 启动摄像头 | 需先在下拉框选择 OBS Virtual Camera |
| 开始游戏 | 需摄像头已启动 |
| 暂停 / 结束 | 结束会清零比分 |

### 6.2 单局流程

1. 倒计时 **3 → 2 → 1 → 出招！**
2. 倒计时到 1 时，机器人随机出招，**L6 做对应动作**
3. 你在 **5 秒内** 对摄像头出石头 / 剪刀 / 布
4. 显示胜负并更新比分，约 1 秒后自动下一局

### 6.3 手势识别提示

- 使用 **食指、中指、无名指、小指**（拇指不参与判定）
- **石头**：四指握拢
- **布**：四指张开
- **剪刀**：食指 + 中指伸，无名指 + 小指弯
- 手置于画面中央，光线充足
- 展开页面底部 **「详细检测信息」** 可调试识别分数

### 6.4 其他模式

| 模式 | 地址 |
|------|------|
| 主页 | http://localhost:8899/ |
| 必胜模式 | http://localhost:8899/5.always-win/ |
| 跟随模式 | http://localhost:8899/4.follow-me/ |
| 纯识别调试 | http://localhost:8899/2.detect-hand-rps/ |

竞技与必胜模式与本文档的 L6 桥接配置相同；跟随模式需额外高频 CAN，默认桥接脚本未覆盖。

---

## 7. 常见问题排查

### 7.1 RealSense 画面黑白 / 检测不到手

| 原因 | 处理 |
|------|------|
| 选了 Depth 设备 | 改选 **OBS Virtual Camera** |
| 未运行虚拟摄像头脚本 | 运行 `realsense_virtual_cam.py` |
| RealSense Viewer 占用相机 | 关闭 Viewer 后重跑脚本 |

### 7.2 浏览器里没有 OBS Virtual Camera

1. OBS 是否已 **开始虚拟摄像机**
2. 刷新游戏页面或重启浏览器
3. 确认 `realsense_virtual_cam.py` 在运行且无报错

### 7.3 Console：加载设备配置失败

- 终端 B 的 `windows_l6_bridge.py` 是否在运行
- 访问 http://localhost:7080/api/hand/devices 是否返回 JSON

### 7.4 识别正常但 L6 不动

- 终端 B、C 是否都在运行
- 终端 B 是否有 `[can] id=40 -> ROCK/PAPER/SCISSORS` 日志
- PCAN 是否被 PCAN-View 或其他脚本占用
- `windows_l6_bridge.py` 中 `HAND_SIDE` 是否为 `left`

### 7.5 桥接 / PCAN 启动失败

```powershell
conda activate linkerbot
python test1_connect.py
```

确认 PCAN ✅ 灵巧手 ✅ 后再启动 `windows_l6_bridge.py`。

### 7.6 端口被占用

```powershell
netstat -ano | findstr :8899
netstat -ano | findstr :7080
netstat -ano | findstr :5260
```

游戏服务可换端口：

```powershell
go run server.go -port 8090 -model l6
# 浏览器访问 http://localhost:8090/6.gameplay/
```

### 7.7 realsense_virtual_cam 启动失败

- D405 插 USB 3.0
- 关闭 RealSense Viewer
- 尝试：`python realsense_virtual_cam.py --width 640 --height 480 --fps 30`

---

## 8. 目录与脚本说明

```
<项目根目录>/
├── 环境.txt                               ← conda 环境备忘
├── testing/
│   ├── 石头剪刀布游戏-Windows完整指南.md    ← 本文档
│   ├── realsense_virtual_cam.py         ← D405 Color → OBS 虚拟摄像头
│   ├── realsense_virtual_cam_requirements.txt
│   ├── windows_l6_bridge.py             ← L6 PCAN 桥接（7080 + 5260）
│   ├── test1_connect.py                   ← PCAN + L6 连接测试
│   ├── 硬件连接测试.py
│   └── pose_*.py                          ← 单姿势测试脚本
└── dexterous/
    └── dexterous-hand-rps/                ← 游戏主项目
        ├── server.go                      ← Go Web 服务（默认 :8899）
        ├── 6.gameplay/                    ← 竞技模式
        ├── 5.always-win/                  ← 必胜模式
        └── shared/rps-recognition.js      ← 手势识别算法
```

### 关键配置（按需修改）

**windows_l6_bridge.py** 顶部：

```python
INTERFACE = "PCAN_USBBUS1"
HAND_SIDE = "left"          # 左手 / right 右手
LOGICAL_INTERFACE = "can0"  # 与 Go 侧一致，无需改为 PCAN 名
```

---

## 9. 简化方案

### 9.1 只要手势识别，不要灵巧手动

只需 **终端 C + 浏览器**，摄像头用内置或 OBS Virtual Camera：

```powershell
cd dexterous\dexterous-hand-rps
go run server.go
```

打开 http://localhost:8899/6.gameplay/ 或 http://localhost:8899/2.detect-hand-rps/

### 9.2 只要灵巧手动，不用 D405

- 跳过步骤 1、2（OBS + realsense_virtual_cam）
- 摄像头选 **Integrated Camera**
- 仍需要步骤 3、4（桥接 + Go 服务）

### 9.3 使用内置摄像头 + L6 完整对战

| 终端 | 命令 |
|------|------|
| B | `python windows_l6_bridge.py` |
| C | `go run server.go -model l6` |
| 浏览器 | 选 Integrated Camera |

无需 OBS 与 RealSense 脚本。

---

## 附录：停止服务

按 **Ctrl+C** 依次关闭：

1. 浏览器标签页
2. 终端 C（Go 服务）
3. 终端 B（L6 桥接，会释放 PCAN）
4. 终端 A（RealSense 虚拟摄像头）

OBS 虚拟摄像机可在 OBS 中点击 **停止虚拟摄像机**。

---

*文档版本：2026-07-06 · 适用环境：Windows 10/11 + PCAN + L6 左手 + RealSense D405*
