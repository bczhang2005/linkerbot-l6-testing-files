# testing — L6 灵巧手实验与测试脚本

本目录为个人编写的 **LinkerBot L6 灵巧手** 实验代码，用于在 Windows + PCAN 环境下完成：环境验证、SDK 功能探索、姿势控制、视觉联动、角度标定等工作。

> 依赖公司的 `linkerbot` SDK；改编版 `dexterous-hand-rps` Web 游戏位于本目录下 `dexterous/` 中（基于公司原版，含 3D 跟随等自创功能）。

---

## 目录结构

```
testing/
├── README.md                 ← 本文件
├── 环境.txt                  ← conda 环境备忘
│
├── setup/                    ← 环境与连接验证
├── sdk_tests/                ← SDK 功能测试（test 系列）
├── poses/                    ← 预设姿势与 GUI 调试
├── vision/                   ← RealSense D405：2D 虚拟摄像头、3D 跟踪、L6 桥接（见 vision/README.md）
├── calibration/              ← 角度标定流水线与数据
├── dexterous/                ← 改编版 dexterous-hand-rps Web 游戏（含 3D 跟随等自创功能）
└── docs/                     ← 操作指南
```


| 子目录            | 内容                     | 典型入口                              |
| -------------- | ---------------------- | --------------------------------- |
| `setup/`       | 环境检测、PCAN 连接测试         | `test1_connect.py`                |
| `sdk_tests/`   | 运动/读取/传感器/队列复现         | `test2_move.py` → `test3_read.py` |
| `poses/`       | `pose_*.py`、滑条/监控 GUI  | `angle_slider.py`                 |
| `vision/`      | D405 2D/3D 视觉脚本、L6 桥接  | `vision/README.md` → 按路线选脚本       |
| `calibration/` | WitMotion 标定采集→拟合→画图   | `角度标定_采集.py`                      |
| `dexterous/`   | 改编版 Web 游戏（Go，含 3D 跟随） | `dexterous-hand-rps/server.go`    |
| `docs/`        | 石头剪刀布游戏 Windows 指南     | 快速启动 / 完整指南                       |


---



## 前置条件


| 项目        | 说明                                  |
| --------- | ----------------------------------- |
| 操作系统      | Windows（脚本默认 `PCAN_USBBUS1`）        |
| Python 环境 | `conda activate linkerbot`          |
| 硬件        | L6 灵巧手 + PEAK PCAN-USB + 24V 电源     |
| 运行前       | 关闭 PCAN-View、RealSense Viewer 等占用程序 |
| 全局配置      | 各脚本顶部 `HAND_SIDE` 须与实物一致            |


**关节顺序**：`[thumb_flex, thumb_abd, index, middle, ring, pinky]`

**重要**：无力传感器机型须先 `stop_polling()`，否则易 `queue.Full`。见 `sdk_tests/queue_full_replay.py`。

---



## 快速开始

> 以下 `cd` 均相对于**仓库根目录**（即 `testing/` 所在的目录）。



### 首次上手

```powershell
conda activate linkerbot
cd testing/setup
python test_install.py
python test_env_full.py
python test1_connect.py
```



### 运行石头剪刀布游戏

详见 `docs/石头剪刀布游戏-快速启动.md`。简要步骤：

```powershell
cd testing/vision
python realsense_virtual_cam.py          # 终端 A
python windows_l6_bridge.py            # 终端 B（另开窗口）
cd ../dexterous/dexterous-hand-rps      # 终端 C
go run server.go -port 8899 -model l6
```

浏览器打开 `http://localhost:8899/6.gameplay/`，摄像头选 **OBS Virtual Camera**。

### D405 3D 关节跟随

与上节 **2D 游戏路线不同**：不需 OBS，改用 `hand_tracking_service.py`。步骤见 `vision/README.md` 与 `docs/石头剪刀布游戏-快速启动.md` 文末附节。

```powershell
cd testing/vision
python hand_tracking_service.py          # 终端 A
python windows_l6_bridge.py            # 终端 B
cd ../dexterous/dexterous-hand-rps      # 终端 C
go run server.go -port 8899 -model l6
```

浏览器：`http://localhost:8899/7.follow-me-3d/` → 连接 3D 跟踪。

> **勿同时**运行 `realsense_virtual_cam.py` 与 `hand_tracking_service.py`（会抢 D405）。



### 角度标定

完整说明见 `calibration/README.md`。

```powershell
cd testing/calibration
python 角度标定_采集.py
python 角度标定_拟合.py
python 角度标定_画图.py
```

标定数据保存在 `calibration/data/`。

---



## 各模块说明



### setup/ — 环境与连接


| 脚本                 | 作用                   |
| ------------------ | -------------------- |
| `test_install.py`  | 检查 linkerbot 包是否安装   |
| `test_env_full.py` | 完整环境检测（无需硬件）         |
| `test1_connect.py` | PCAN + 读角基础连接测试      |
| `硬件连接测试.py`        | 分层诊断，自动尝试 left/right |




### sdk_tests/ — SDK 功能测试

按推荐顺序：`test2_move.py` → `test3_read.py` → `test4_stream.py` → `test_move_stream.py`


| 类别   | 脚本                                                                                                       |
| ---- | -------------------------------------------------------------------------------------------------------- |
| 运动控制 | `test2_move.py`、`test2_move_new.py`、`test2_move_fail.py`、`test_move_stream.py`、`test_speed.py`、`完整示例.py` |
| 数据读取 | `test3_read.py`、`test4_stream.py`、`只开角度轮询.py`、`只开力传感器轮询.py`                                              |
| 传感器  | `testing_L6.py`、`testing_fault.py`、`test_force_sensor.py`、`电流轮询.py`、`test_version.py`                    |
| 队列复现 | `queue_full_replay.py`                                                                                   |




### poses/ — 姿势控制

- `pose_common.py` — 在线预检公共模块
- `pose_open/fist/peace/ok/point.py` — 预设手势
- `move_open_pose.py` — 回到全张开安全位
- `angle_slider.py` / `angle_monitor.py` — Tkinter 调试 GUI

姿势参数与 `vision/windows_l6_bridge.py` 中石头剪刀布映射一致。

### vision/ — 视觉联动

> 含 2D（OBS 虚拟摄像头）、3D（深度跟手）、共用桥接三条线。文件对照与原理见 **[vision/README.md](vision/README.md)**。


| 脚本                         | 路线  | 作用                                                         |
| -------------------------- | --- | ---------------------------------------------------------- |
| `realsense_virtual_cam.py` | 2D  | D405 彩色流 → OBS 虚拟摄像头（`/6.gameplay/`、`/4.follow-me/`）       |
| `hand_tracking_service.py` | 3D  | D405 Color + Depth → WebSocket `:8765`（`/7.follow-me-3d/`） |
| `windows_l6_bridge.py`     | 共用  | PCAN 桥接（`:7080` 设备发现 + `:5260` CAN 转发）                     |


依赖：`realsense_virtual_cam_requirements.txt`（2D）、`hand_tracking_requirements.txt`（3D）。

### dexterous/ — 灵巧手 Web 游戏（改编版）

基于公司开源项目 [zhuzx17/dexterous-hand-rps](https://github.com/zhuzx17/dexterous-hand-rps) 改编，代码位于 `dexterous/dexterous-hand-rps/`。原版提供浏览器端手势识别与石头剪刀布等页面；本仓库在其基础上增加了与 L6 + D405 实验配套的**新增功能**。

**主要新增 / 改动：**


| 路径                        | 说明                                                                      |
| ------------------------- | ----------------------------------------------------------------------- |
| `7.follow-me-3d/`         | **3D 关节跟随页面**（新增），消费 `vision/hand_tracking_service.py` 的 WebSocket 深度数据 |
| `shared/hand-retarget.js` | **3D 手部重定向**（新增），将 21 点 3D 手系映射为 7 字节 CAN 帧                             |
| `server.go`               | 适配 `-model l6` 启动参数，配合 `windows_l6_bridge.py` 转发 CAN                    |
| `index.html`              | 主页增加 3D 跟随入口                                                            |
| `4.follow-me/app.js`      | 2D 跟随逻辑微调，配合 Windows 桥接                                                 |


**常用页面：**


| 地址                 | 用途                                        |
| ------------------ | ----------------------------------------- |
| `/6.gameplay/`     | 石头剪刀布竞技（2D，需 OBS 虚拟摄像头）                   |
| `/4.follow-me/`    | 2D 手势跟随                                   |
| `/7.follow-me-3d/` | **3D 关节跟随**（需 `hand_tracking_service.py`） |


启动方式见上文「运行石头剪刀布游戏」与「D405 3D 关节跟随」；与 `vision/` 中的 Python 桥接脚本配合使用。

### calibration/ — 角度标定

研究 **电机原始值（0~255）与 WitMotion 真实角度** 的映射关系。完整说明见 **[calibration/README.md](calibration/README.md)**。

```
角度标定_采集.py → 合并 → 拟合 → 画图
```

- `witmotion_serial.py` / `witmotion_export.py` — WitMotion 数据读取
- `data/` — CSV 标定数据、PNG 图表



### docs/ — 操作指南

- `石头剪刀布游戏-Windows完整指南.md`
- `石头剪刀布游戏-快速启动.md`（含 2D 游戏与 3D 跟随启动）

---



## 与公司代码的关系


| 公司代码                 | 本仓库如何使用                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `linkerbot` SDK      | 所有脚本通过 `from linkerbot import L6` 控制硬件                                                                                    |
| `dexterous-hand-rps` | 改编版已纳入本仓库 `dexterous/`；`vision/windows_l6_bridge.py` 桥接其 HTTP API；页面 `/4.follow-me/`、`/6.gameplay/`、自创 `/7.follow-me-3d/` |


---



## 其他说明

- `__pycache__/` 为 Python 缓存，可安全删除
- 每个脚本顶部有配置区和文档字符串，便于逐个运行
- 多数运动脚本在结束时回到全张开安全位

