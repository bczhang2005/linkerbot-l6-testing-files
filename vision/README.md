# vision/ — RealSense D405 视觉与 L6 桥接

本目录存放 **RealSense D405** 相关 Python 脚本，以及连接 **L6 灵巧手** 的 PCAN 桥接。

> 本目录同时包含 **2D（浏览器）** 与 **3D（深度跟手）** 两条路线，外加 **2D/3D 共用** 的桥接服务。

---

## 文件一览


| 文件                                       | 路线     | 作用                                             |
| ---------------------------------------- | ------ | ---------------------------------------------- |
| `hand_tracking_service.py`               | **3D** | D405 Color + Depth → 手部 3D → WebSocket `:8765` |
| `hand_tracking_requirements.txt`         | 3D     | 上列脚本依赖（含 mediapipe、websockets）                 |
| `realsense_virtual_cam.py`               | **2D** | D405 彩色流 → OBS 虚拟摄像头（供浏览器 `getUserMedia`）      |
| `realsense_virtual_cam_requirements.txt` | 2D     | 上列脚本依赖（含 pyvirtualcam）                         |
| `windows_l6_bridge.py`                   | **共用** | PCAN 桥接：`:7080` 设备发现 + `:5260` CAN → L6        |
| `README.md`                              | —      | 本说明                                            |


---



## 两条视觉路线

```text
┌─────────────────────────────────────────────────────────────────┐
│                    RealSense D405                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
  【2D 路线】                              【3D 路线】
  realsense_virtual_cam.py                hand_tracking_service.py
         │                                       │
         ▼                                       ▼
  OBS 虚拟摄像头                          WebSocket :8765
         │                                       │
         ▼                                       ▼
  浏览器 MediaPipe（2D）                  /7.follow-me-3d/ 页面
  /4.follow-me/ 或 /6.gameplay/                  │
         │                                       │
         └───────────────────┬───────────────────┘
                             ▼
              windows_l6_bridge.py + server.go :8899
                             ▼
                         L6 灵巧手
```


| 功能             | 用到的本目录脚本                                            | 浏览器页面              |
| -------------- | --------------------------------------------------- | ------------------ |
| 石头剪刀布（D405 彩色） | `realsense_virtual_cam.py` + `windows_l6_bridge.py` | `/6.gameplay/`     |
| 2D 手势跟随        | 同上（或不用 D405，直接本机摄像头）                                | `/4.follow-me/`    |
| **3D 关节跟随**    | `hand_tracking_service.py` + `windows_l6_bridge.py` | `/7.follow-me-3d/` |


**3D 跟手时请勿同时运行** `realsense_virtual_cam.py` 或占用 D405 的 RealSense Viewer / OBS 虚拟摄像头。

---



## 3D 路线：原理摘要

D405 不是「左右拼接宽图」的双目 UVC，而是：

1. **Color 流** — MediaPipe 在彩色图上检测 21 个 2D 关键点
2. **Depth 流** — 对每个 2D 点采样距离（米）
3. **反投影** — 得到真实 3D 坐标，再算 10 关节角
4. **WebSocket** — 推给 `dexterous-hand-rps/7.follow-me-3d/`
5. **浏览器** — `hand-retarget.js` 组 7 字节 CAN → `server.go` → 本目录桥接 → L6

页面上 **厘米深度、深度着色、XYZ 表** 仅 3D 路线有；2D 页面没有。

更完整说明见项目根下 `testing/docs/石头剪刀布游戏-快速启动.md` 文末「D405 真 3D 跟随」。

---



## 环境

```powershell
conda activate linkerbot
cd testing/vision
```

- 已安装 **Intel RealSense SDK 2.0**（含 D405 驱动）  
- L6 **24V 上电**，PCAN 正常  
- 玩 2D 游戏且用 OBS 时：OBS 已安装，并会点「开始虚拟摄像机」

---



## 快速启动



### A. 3D 关节跟随（三终端 + 浏览器）

**终端 1 — 3D 跟踪**

```powershell
conda activate linkerbot
cd testing/vision
pip install -r hand_tracking_requirements.txt
python hand_tracking_service.py
```

看到 `WebSocket: ws://localhost:8765` 后保持运行。

**终端 2 — L6 桥接**

```powershell
conda activate linkerbot
cd testing/vision
python windows_l6_bridge.py
```

**终端 3 — Go 服务**

```powershell
cd testing/dexterous/dexterous-hand-rps
go run server.go -port 8899 -model l6
```

**浏览器：** `http://localhost:8899/7.follow-me-3d/` → 连接 3D 跟踪。

---



### B. 2D 石头剪刀布（需 OBS）

1. OBS 开启「虚拟摄像机」
2. 终端运行 `python realsense_virtual_cam.py`
3. 终端运行 `python windows_l6_bridge.py`
4. 终端运行 `go run server.go -port 8899 -model l6`
5. 浏览器 `/6.gameplay/`，摄像头选 **OBS Virtual Camera**

详见 `testing/docs/石头剪刀布游戏-快速启动.md`。

---



## `windows_l6_bridge.py` 说明（共用）

- `:7080` — `GET /api/hand/devices`，浏览器读取 L6 左右手、型号  
- `:5260` — 接收 `server.go` 转发的 CAN  
- 支持 **石头剪刀布** 固定三姿态（ROCK/PAPER/SCISSORS）  
- 支持 **跟随模式** 7 字节动态帧（`[1,拇屈,拇展,食,中,无,小]`）

2D 与 3D 跟随都依赖此桥接；区别只在「谁算关节角」——浏览器 2D 或 `hand_tracking_service` 3D。

---



## 常见问题


| 现象                                     | 处理                                              |
| -------------------------------------- | ----------------------------------------------- |
| `hand_tracking_service` 报 mediapipe 缺失 | `pip install -r hand_tracking_requirements.txt` |
| 3D 页 WebSocket 连不上                     | 确认终端 1 在跑；地址 `ws://localhost:8765`              |
| L6 不动                                  | 检查桥接 + Go；桥接日志应有 `[follow]`                     |
| 2D 画面黑白                                | 勿选 RealSense Depth；选 OBS Virtual Camera         |
| 3D 与 2D 同时开摄像头冲突                       | 只跑一条路线，关掉另一路的 D405 脚本                           |


---



## 相关仓库路径

```text
testing/vision/              ← 本目录
testing/dexterous/dexterous-hand-rps/
  ├── 7.follow-me-3d/        ← 3D 浏览器页
  ├── 4.follow-me/           ← 2D 跟随页
  ├── 6.gameplay/            ← 石头剪刀布
  └── shared/hand-retarget.js
testing/docs/                ← 快速启动、完整指南
```

---

*最后更新：与 D405 3D 跟随（*`hand_tracking_service` *+* `7.follow-me-3d`*）落地版本一致。*