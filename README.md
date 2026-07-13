# testing — L6 灵巧手实验与测试脚本

本目录为个人编写的 **LinkerHand L6 灵巧手** 实验代码，用于在 Windows + PCAN 环境下完成：环境验证、SDK 功能探索、姿势控制、视觉联动、角度标定等工作。

同仓库中的 `linkerbot-python-sdk/` 与 `dexterous/` 为公司官方代码；本目录在其之上搭建实验流程，并通过桥接脚本将 Windows 环境与公司的 Web 手势游戏对接。

---

## 目录结构概览

```
testing/
├── README.md                          ← 本文件
│
├── 【环境与连接】
│   test_install.py / test_env_full.py
│   test1_connect.py / 硬件连接测试.py
│
├── 【SDK 功能测试】test1 ~ test4 系列
│   test2_move.py / test2_move_new.py / test2_move_fail.py
│   test3_read.py / test4_stream.py / test_move_stream.py
│   testing_L6.py / testing_fault.py / test_force_sensor.py
│   test_version.py / test_speed.py / 电流轮询.py
│   只开角度轮询.py / 只开力传感器轮询.py / queue_full_replay.py
│
├── 【姿势控制】
│   pose_common.py + pose_*.py
│   move_open_pose.py / angle_slider.py / angle_monitor.py
│
├── 【视觉联动】
│   realsense_virtual_cam.py
│   hand_tracking_service.py
│   windows_l6_bridge.py
│
├── 【角度标定】角度标定/
│   角度标定_采集.py → 合并 → 拟合 → 画图
│   witmotion_serial.py / witmotion_export.py
│   L6.data/（CSV 标定数据与图表）
│
└── 【操作指南】
    石头剪刀布游戏-Windows完整指南.md
    石头剪刀布游戏-快速启动.md
```

---



## 前置条件


| 项目        | 说明                                            |
| --------- | --------------------------------------------- |
| 操作系统      | Windows（脚本默认 `PCAN_USBBUS1`）                  |
| Python 环境 | `conda activate linkerbot`（含 `linkerbot` SDK） |
| 硬件        | L6 灵巧手 + PEAK PCAN-USB + 24V 电源               |
| 可选硬件      | Intel RealSense D405、WitMotion IMU            |
| 运行前       | 关闭 PCAN-View、RealSense Viewer 等占用程序           |
| 全局配置      | 各脚本顶部 `HAND_SIDE`（`left` / `right`）须与实物一致     |


**关节顺序**（所有脚本统一）：

```
[thumb_flex, thumb_abd, index, middle, ring, pinky]
拇指弯曲 · 拇指侧摆 · 食指 · 中指 · 无名指 · 小指
```

**重要提示**：L6 默认轮询包含力传感器（30Hz），无力传感器机型若不先 `stop_polling()` / `stop_stream()`，容易导致读角超时或 `queue.Full`。本目录多数脚本已处理；`test2_move_fail.py` 与 `queue_full_replay.py` 专门用于复现此问题。

---



## 一、环境与连接验证

从零开始时的推荐顺序：

```
test_install.py  →  test_env_full.py  →  test1_connect.py  →  硬件连接测试.py
  （无需硬件）       （无需硬件）          （基础连接）         （分层诊断）
```


| 脚本                 | 作用                                  |
| ------------------ | ----------------------------------- |
| `test_install.py`  | 检查 `linkerbot` 包是否安装，打印 SDK 版本      |
| `test_env_full.py` | 完整环境检测（SDK + 可选 Pinocchio 机械臂扩展）    |
| `test1_connect.py` | PCAN 通道 + 读角；`HAND_SIDE` 填错时自动试另一只手 |
| `硬件连接测试.py`        | 分层诊断：阶段 1 验 CAN 通道，阶段 2 验读角（两种方式）   |


连接通过后，可继续运行 `test_version.py` 读取设备序列号与固件版本。

---



## 二、SDK 功能测试（test 系列）

按由浅入深的顺序设计，每个脚本文件头均含【测试目的 / 前置条件 / 操作步骤 / 预期结果】。

### 2.1 运动控制


| 脚本                    | 作用                                      |
| --------------------- | --------------------------------------- |
| `test.py`             | 最简运动片段（早期草稿）：设速后发一个张开指令                 |
| `完整示例.py`             | 官方风格示例：张开 → 握拳 → 阻塞读角度与温度               |
| `test2_move.py`       | 验证 `L6Angle` 与 list 两种传参；5 步动作序列 + 每步读角 |
| `test2_move_new.py`   | 改进版：集中 `POSE_CONFIG`，左右手姿势分开配置          |
| `test2_move_fail.py`  | **对照实验**：故意不 stop 轮询，演示队列堵塞             |
| `test_move_stream.py` | 合并运动 + 流式读角：后台执行动作，主线程 `hand.stream()`  |
| `test_speed.py`       | 演示六关节分别设置不同运动速度                         |




### 2.2 数据读取


| 脚本                | 作用                                              |
| ----------------- | ----------------------------------------------- |
| `test3_read.py`   | 对比三种读角方式：`get_blocking` / `get_snapshot` / 全局快照 |
| `test4_stream.py` | 验证流式读取：开启角度轮询后持续接收 `AngleEvent`                 |
| `只开角度轮询.py`       | 隔离测试：仅 10Hz 角度轮询，30 秒稳定性验证                      |
| `只开力传感器轮询.py`     | 隔离测试：仅力传感器轮询，排查队列影响                             |




### 2.3 传感器与故障模块


| 脚本                     | 作用                                         |
| ---------------------- | ------------------------------------------ |
| `testing_L6.py`        | 批量验证 temperature / current / torque 模块 API |
| `testing_fault.py`     | 验证 fault 模块阻塞读与轮询快照                        |
| `test_force_sensor.py` | 检测硬件是否具备力传感器（预检 + 力数据读取）                   |
| `电流轮询.py`              | 验证 current 模块三种读取方式                        |
| `test_version.py`      | 读取设备版本信息                                   |




### 2.4 队列问题复现


| 脚本                     | 作用                                  |
| ---------------------- | ----------------------------------- |
| `queue_full_replay.py` | 故意复现 `queue.Full`：不 stop 轮询 + 频繁阻塞读 |


> **建议学习路径**：`test2_move.py` → `test3_read.py` → `test4_stream.py` → `test_move_stream.py`

---



## 三、姿势控制



### 3.1 公共模块

`pose_common.py` 为所有 `pose_*.py` 提供：

- `verify_hand_online()` — 在线预检（stop 轮询 → 阻塞读角）
- `resolve_hand_side()` — 自动尝试 left/right
- `exit_if_hand_offline()` — 离线时打印排查指引并退出



### 3.2 预设姿势脚本

每个 `pose_*.py` 定义左右手各自的 `L6Angle` 参数，运行后执行对应手势：


| 脚本                  | 手势                   |
| ------------------- | -------------------- |
| `pose_open.py`      | 全张开（安全复位位，六关节 = 100） |
| `pose_fist.py`      | 握拳                   |
| `pose_peace.py`     | 剪刀手（比耶）              |
| `pose_ok.py`        | OK 手势                |
| `pose_point.py`     | 食指指向                 |
| `move_open_pose.py` | 单独回到全张开安全位           |


这些姿势参数与 `windows_l6_bridge.py` 中石头剪刀布的 `ROCK / PAPER / SCISSORS` 映射一致。

### 3.3 GUI 调试工具


| 脚本                 | 界面          | 功能                            |
| ------------------ | ----------- | ----------------------------- |
| `angle_slider.py`  | Tkinter 滑条  | 6 路关节 0~100 实时控制，拖动即发送，显示反馈角度 |
| `angle_monitor.py` | Tkinter 控制台 | 流式显示角度 + 快捷姿势按钮 + 自定义角度输入     |


---



## 四、视觉联动（与公司 dexterous 对接）

Windows 无法直接使用 Linux 版 `can-bridge`，本目录提供三个自研脚本，将 RealSense 相机与 L6 灵巧手接入公司的 `dexterous-hand-rps` Web 游戏。

### 4.1 系统架构

```
浏览器 (localhost:8899/6.gameplay/)
    │ 摄像头：OBS Virtual Camera
    │ GET :7080/api/hand/devices
    ▼
dexterous-hand-rps (Go, :8899)          ← 公司代码
    │ POST :5260/api/can
    ▼
windows_l6_bridge.py (:5260 + :7080)     ← 本目录
    │ linkerbot → PCAN → L6
    ▼
realsense_virtual_cam.py                 ← 本目录
    RealSense D405 Color → OBS Virtual Camera
```



### 4.2 脚本说明


| 脚本                         | 端口/输出               | 作用                                                                    |
| -------------------------- | ------------------- | --------------------------------------------------------------------- |
| `realsense_virtual_cam.py` | OBS Virtual Camera  | D405 彩色流 → 虚拟摄像头（浏览器可选）                                               |
| `windows_l6_bridge.py`     | :7080 / :5260       | PCAN 桥接：设备发现 API + CAN 指令转发；支持竞技手势与跟随模式                               |
| `hand_tracking_service.py` | ws://localhost:8765 | RealSense Color+Depth → 21 点 3D 手系 → WebSocket（供 `7.follow-me-3d` 页面） |


**依赖文件**：

- `realsense_virtual_cam_requirements.txt` — `pyrealsense2`、`pyvirtualcam` 等
- `hand_tracking_requirements.txt` — `pyrealsense2`、`mediapipe`、`websockets` 等
- `hand_landmarker.task` — MediaPipe 手部检测模型

**操作指南**（已编写）：

- `石头剪刀布游戏-Windows完整指南.md` — 从环境搭建到日常启动的完整流程
- `石头剪刀布游戏-快速启动.md` — 环境就绪后的 4 步快速启动

---



## 五、角度标定（`角度标定/` 子目录）

研究 **电机原始值（0~255）与真实关节角度（WitMotion IMU）** 之间的线性映射关系。

### 5.1 标定流程

```
角度标定_采集.py
    │  控制单关节 255→0 递减，同步记录 WitMotion 角度
    │  输出 calibration_markers_*.csv / calibration_data_*.csv
    ▼
角度标定_合并witmotion记录.py   （方式 B：上位机录制时）
    │  合并 WitMotion 导出文件与时间标记
    ▼
角度标定_合并指根指尖.py         （多关节标定）
    │  计算第二关节角 = 指尖角度 - 指根角度
    ▼
角度标定_拟合.py
    │  线性回归：motor_raw vs angle_x，输出 R²、RMSE
    ▼
角度标定_画图.py
    生成标定曲线图（保存至 data/plots/）
```



### 5.2 三种采集模式（`角度标定_采集.py`）


| 模式      | `RECORD_MODE`        | 说明                                      |
| ------- | -------------------- | --------------------------------------- |
| A 手动输入  | `"manual"`           | 停稳后手动输入 WitMotion 读数                    |
| B 上位机录制 | `"witmotion_record"` | WitMotion 软件「开始记录」+ 脚本写时间标记，事后合并        |
| C 串口自动  | `"serial"`           | Type-C 直连，通过 `witmotion_serial.py` 自动读取 |




### 5.3 支撑模块


| 文件                    | 作用                                   |
| --------------------- | ------------------------------------ |
| `witmotion_serial.py` | 解析 WitMotion 串口数据包（0x55 0x53）        |
| `witmotion_export.py` | 解析 WitMotion 上位机导出文件（Data.tsv / csv） |
| `move_open_pose.py`   | 标定前将手回到全张开位                          |
| `urdf.md`             | URDF 建模参考笔记（关节/连杆理论）                 |




### 5.4 标定数据（`data/`）

已采集五指（含拇指弯曲 1a、侧摆 1b）的标定数据，包括：

- `calibration_data_*.csv` — 电机值与 WitMotion 角度对应表
- `calibration_markers_*.csv` — 采样点时间标记
- `merged_*.csv` — 指根/指尖合并后的数据
- `plots/` — 标定曲线图（motor vs angles、transmission ratio 等）
- `analysis_output.txt` / `analysis_joint2.txt` — 拟合分析结果

---



## 六、推荐工作流

> 以下 `cd` 命令均相对于**项目根目录**（包含 `testing/`、`dexterous/` 等子文件夹的目录）。



### 首次上手

```
1. conda activate linkerbot
2. python test_install.py
3. python test_env_full.py
4. 接好 PCAN + 上电 → python test1_connect.py
5. python test2_move.py
6. python angle_slider.py          # 交互式体验
```



### 运行石头剪刀布游戏

详见 `石头剪刀布游戏-快速启动.md`，简要步骤：

```
1. OBS 开启虚拟摄像头
2. python realsense_virtual_cam.py
3. python windows_l6_bridge.py
4. 启动 dexterous-hand-rps Go 服务
5. 浏览器打开 localhost:8899/6.gameplay/
```



### 角度标定实验

```
1. cd testing/角度标定
2. WitMotion 固定在被测手指 → python 角度标定_采集.py
3. python 角度标定_拟合.py
4. python 角度标定_画图.py
```

---



## 七、文件索引（按类别）



### 环境与连接（4）

`test_install.py` · `test_env_full.py` · `test1_connect.py` · `硬件连接测试.py`

### SDK 测试（16）

`test.py` · `完整示例.py` · `test2_move.py` · `test2_move_new.py` · `test2_move_fail.py` · `test3_read.py` · `test4_stream.py` · `test_move_stream.py` · `test_speed.py` · `testing_L6.py` · `testing_fault.py` · `test_force_sensor.py` · `test_version.py` · `电流轮询.py` · `只开角度轮询.py` · `只开力传感器轮询.py` · `queue_full_replay.py`

### 姿势与 GUI（9）

`pose_common.py` · `pose_open.py` · `pose_fist.py` · `pose_peace.py` · `pose_ok.py` · `pose_point.py` · `move_open_pose.py` · `angle_slider.py` · `angle_monitor.py`

### 视觉联动（5）

`realsense_virtual_cam.py` · `realsense_virtual_cam_requirements.txt` · `hand_tracking_service.py` · `hand_tracking_requirements.txt` · `windows_l6_bridge.py`

### 角度标定（8 + data）

`角度标定_采集.py` · `角度标定_合并witmotion记录.py` · `角度标定_合并指根指尖.py` · `角度标定_拟合.py` · `角度标定_画图.py` · `witmotion_serial.py` · `witmotion_export.py` · `urdf.md`

### 文档（3）

`README.md`（本文件）· `石头剪刀布游戏-Windows完整指南.md` · `石头剪刀布游戏-快速启动.md`

---



## 八、与公司代码的关系


| 公司代码                           | 本目录如何使用                                                                                                                       |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `linkerbot-python-sdk`         | 所有硬件控制脚本通过 `from linkerbot import L6` 调用 SDK                                                                                  |
| `dexterous/dexterous-hand-rps` | `windows_l6_bridge.py` 桥接其 HTTP API；`realsense_virtual_cam.py` 为其提供摄像头画面；`hand_tracking_service.py` 为其 3D 跟随页面提供 WebSocket 数据 |
| `stereo-3d-follow/`            | 平行的双目 3D 跟随方案（不在本目录，但思路相近）                                                                                                    |


---



## 九、其他说明

- `__pycache__/`：Python 自动生成的字节码缓存，可安全删除，不影响功能。
- **脚本风格**：每个测试脚本顶部有配置区（`HAND_SIDE`、`INTERFACE` 等）和完整的文档字符串，便于逐个运行和记录实验结果。
- **安全位**：多数运动脚本在 `finally` 块中回到全张开（`[100, 100, 100, 100, 100, 100]`），避免实验结束后手指处于非安全姿态。

