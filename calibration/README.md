# 角度标定 — L6 灵巧手电机值与真实角度映射

本目录实现 **灵巧手电机控制值（motor_raw，0~255）与 WitMotion IMU 测得的真实关节角度** 之间的标定流水线：采集 → 合并 → 拟合 → 可视化。

标定结果可用于评估各关节的线性度，并为后续「控制值 → 真实角度」的映射提供依据。

---

## 目录结构

```
calibration/
├── README.md                          ← 本文件
│
├── 角度标定_采集.py                   ← ① 控制单关节扫点 + 记录 WitMotion
├── 角度标定_合并witmotion记录.py       ← ② 合并上位机录制文件（方式 B 专用）
├── 角度标定_拟合.py                   ← ③ 单文件线性回归（R²、RMSE）
├── 角度标定_合并指根指尖.py           ← ④ 五指指根/指尖合并 + 第二关节分析
├── 角度标定_画图.py                   ← ⑤ 生成标定曲线图
│
├── witmotion_serial.py                ← WitMotion 串口读取（备用模块）
├── witmotion_export.py                ← 解析 WitMotion 上位机导出文件
├── move_open_pose.py                  ← 标定前回到全张开安全位
├── urdf.md                            ← URDF 建模参考笔记
│
└── data/                              ← 标定数据与图表
    ├── calibration_data_*.csv         ← 各指/各关节原始标定表
    ├── calibration_markers_*.csv      ← 时间标记（方式 B）
    ├── merged_*.csv                   ← 指根+指尖合并结果
    ├── plots/                         ← 拟合曲线 PNG
    └── 指尖/                          ← 指尖标定示意图
```

---



## 标定原理



### 要回答的问题

灵巧手 SDK 下发的角度是 **0~100**（用户层），底层 CAN 原始值为 **0~255**（motor_raw）。我们想知道：

> 给定 motor_raw，手指在物理空间中实际弯了多少度？

WitMotion 惯性传感器固定在手指上，提供 **roll / pitch / yaw**（上位机界面常显示为「角度 X/Y/Z」），作为真实角度的外部测量。

### 单关节标定（基础）

对**一个关节**从 raw=255 每隔 15 递减到 0，在每个点停稳后记录一对数据：

```
motor_raw  ↔  angle_x（WitMotion 读数，度）
```

再对二者做线性回归，得到 `angle_x = m × motor_raw + b`，用 **R²** 衡量线性度（越接近 1 越好）。

### 指根 + 指尖标定（进阶）

四指（及拇指两自由度）的弯曲通常涉及**两个关节**。因此分别在被测位置的**指根**和**指尖**各固定一颗 WitMotion：

```
angle_joint2 = angle_x_tip - angle_x_root    （第二关节弯曲角）
```

拟合时应使用 **指根角度 vs 第二关节角度**，而不是直接用指尖的累积角度。

### 五指编号


| 编号   | 关节   | SDK 字段     |
| ---- | ---- | ---------- |
| `1a` | 拇指弯曲 | thumb_flex |
| `1b` | 拇指侧摆 | thumb_abd  |
| `2`  | 食指   | index      |
| `3`  | 中指   | middle     |
| `4`  | 无名指  | ring       |
| `5`  | 小指   | pinky      |


关节索引（`JOINT_INDEX`）：`[0, 1, 2, 3, 4, 5]` 对应上表从左到右。

---



## 前置条件


| 项目   | 说明                                |
| ---- | --------------------------------- |
| 环境   | `conda activate linkerbot`        |
| 硬件   | L6（或 O6）+ PCAN + 24V 电源           |
| 传感器  | WitMotion IMU，固定在被测手指指根或指尖        |
| 软件   | WitMotion 上位机（方式 B）               |
| 运行目录 | `cd testing/calibration`          |
| 运行前  | 关闭 PCAN-View；确认 `HAND_SIDE` 与实物一致 |


标定前建议先运行：

```powershell
cd ../setup
python test1_connect.py
```

或将手回到安全位：

```powershell
python move_open_pose.py
```

---



## 快速流程



### 单关节标定（最常见）

```
角度标定_采集.py  →  角度标定_拟合.py  →  角度标定_画图.py（可选）
```



### 方式 B（上位机录制，推荐）

```
WitMotion 点开始记录
    ↓
角度标定_采集.py  （RECORD_MODE = "witmotion_record"）
    ↓
WitMotion 点结束记录，找到导出文件
    ↓
角度标定_合并witmotion记录.py
    ↓
角度标定_拟合.py
```



### 五指完整标定（指根 + 指尖）

对每个手指的指根、指尖各跑一遍采集（修改 `JOINT_INDEX` 和 `OUTPUT_CSV` 文件名），然后：

```
角度标定_合并指根指尖.py  →  角度标定_画图.py
```

仓库 `data/` 中已包含完整的五指标定数据（`1a`、`1b`、`2`~`5`）及合并结果。

---



## 两种 WitMotion 记录方式

在 `角度标定_采集.py` 顶部设置 `RECORD_MODE`：


| 模式          | 值                    | 说明                                          |
| ----------- | -------------------- | ------------------------------------------- |
| **A 手动**    | `"manual"`           | 每个采样点停稳后，在终端手动输入 WitMotion 读数               |
| **B 上位机录制** | `"witmotion_record"` | 采集前在 WitMotion 软件点「开始记录」，脚本只写时间标记；事后用合并脚本对齐 |


**方式 B 合并原理**：采集脚本在每个采样点停稳时写入 unix 时间戳到 `calibration_markers_*.csv`；合并脚本根据时间差，在 WitMotion 记录文件中取对应时刻的角度平均值。

---



## 脚本说明



### `角度标定_采集.py`

控制**单个关节**按 `255 → 240 → … → 0`（步长 `RAW_STEP`，默认 15）运动，其余关节保持全张开。

**关键配置**（文件顶部）：

```python
HAND_SIDE = "left"
HAND_MODEL = "L6"           # 或 "O6"
JOINT_INDEX = 2             # 0~5，被测关节
RECORD_MODE = "witmotion_record"
WITMOTION_AXIS = "roll"     # 选弯曲时变化最大的轴
OUTPUT_CSV = "data/calibration_data_2.csv"
MARKERS_CSV = "data/calibration_markers_2.csv"
```

**输出 CSV 列**（方式 A 直接生成；方式 B 由合并脚本生成）：


| 列名                        | 含义              |
| ------------------------- | --------------- |
| `motor_raw` / `raw_value` | 底层原始值 0~255     |
| `sdk_value`               | SDK 角度 0~100    |
| `angle_x` / `witmotion_x` | WitMotion 角度（度） |




### `角度标定_合并witmotion记录.py`

将 `calibration_markers_*.csv` 与 WitMotion 导出文件按时间对齐。

**需修改**：

```python
MARKERS_FILE = "data/calibration_markers_2.csv"
WITMOTION_RECORD_FILE = "WitMotion/Record/<日期>/<时间>/data_0.csv"
OUTPUT_CSV = "data/calibration_data_2.csv"
```

若合并结果整体偏早/偏晚，微调 `WITMOTION_TIME_OFFSET_SEC`。

### `角度标定_拟合.py`

对单个 `calibration_data_*.csv` 做线性回归，输出：

- 线性函数 `angle_x = m × motor_raw + b`
- Pearson r、R²、RMSE、最大绝对误差

**判断标准**：R² 接近 1 表示控制值与真实角度近似直线关系，可用于映射。

### `角度标定_合并指根指尖.py`

读取 `data/calibration_data_{指根}.csv` 与 `data/calibration_data_tip_{指}_*.csv`，计算：

```
angle_joint2 = angle_x_tip - angle_x_root
```

输出 `data/merged_{finger_id}.csv` 和 `data/merged_all.csv`，并打印各指的线性/二次拟合 R²。

### `角度标定_画图.py`

读取 `merged_*.csv`，生成：


| 图表                        | 文件                                   |
| ------------------------- | ------------------------------------ |
| 指根角度 vs 第二关节角度            | `data/plots/root_vs_joint2.png`      |
| 角度分解（root + joint2 = tip） | `data/plots/angle_decomposition.png` |


需要 `matplotlib`（`pip install matplotlib`）。

### 支撑模块


| 文件                    | 作用                             |
| --------------------- | ------------------------------ |
| `witmotion_serial.py` | 解析 WitMotion 串口包（0x55 0x53），备用 |
| `witmotion_export.py` | 解析上位机导出的 Data.tsv / csv，供合并脚本  |
| `move_open_pose.py`   | 六个关节回到 100（全张开安全位）             |
| `urdf.md`             | 关节/连杆建模理论参考，与标定实验互补            |


---



## 数据文件命名约定


| 模式   | 文件名示例                          | 含义               |
| ---- | ------------------------------ | ---------------- |
| 指根标定 | `calibration_data_2.csv`       | 食指指根，关节 index=2  |
| 拇指弯曲 | `calibration_data_1a.csv`      | 拇指弯曲（thumb_flex） |
| 拇指侧摆 | `calibration_data_1b.csv`      | 拇指侧摆（thumb_abd）  |
| 指尖标定 | `calibration_data_tip_2.1.csv` | 食指指尖，第 1 次采集     |
| 时间标记 | `calibration_markers_2.csv`    | 方式 B 的时间戳        |
| 合并结果 | `merged_2.csv`                 | 食指指根+指尖合并        |
| 全指汇总 | `merged_all.csv`               | 五指合并             |


---



## 操作示例：标定食指（指根）

```powershell
conda activate linkerbot
cd testing/calibration
```

1. 将 WitMotion 固定在**食指指根**
2. 编辑 `角度标定_采集.py`：

```python
JOINT_INDEX = 2
RECORD_MODE = "witmotion_record"
OUTPUT_CSV = "data/calibration_data_2.csv"
MARKERS_CSV = "data/calibration_markers_2.csv"
```

1. WitMotion 上位机点「开始记录」
2. `python 角度标定_采集.py`
3. 上位机点「结束记录」，找到 `data_0.csv`
4. 编辑 `角度标定_合并witmotion记录.py` 中的 `WITMOTION_RECORD_FILE`
5. `python 角度标定_合并witmotion记录.py`
6. `python 角度标定_拟合.py`

---



## 常见问题


| 现象                  | 处理                                                  |
| ------------------- | --------------------------------------------------- |
| 采集时读角超时             | 检查 PCAN 连接；关闭 PCAN-View；确认 `HAND_SIDE`              |
| 合并后角度全为 0 或乱跳       | 检查 WitMotion 是否全程在录制；调整 `WITMOTION_TIME_OFFSET_SEC` |
| `WITMOTION_AXIS` 选错 | 在 WitMotion 界面观察弯曲时变化最大的轴，改为 `roll`/`pitch`/`yaw`   |
| 拟合 R² 很低            | 传感器未固定牢、运动未停稳、或该关节本身非线性较强                           |
| 画图失败                | `pip install matplotlib`                            |


---



## 与仓库其他模块的关系


| 模块                           | 关系                                                     |
| ---------------------------- | ------------------------------------------------------ |
| `../setup/test1_connect.py`  | 标定前验证 PCAN 通信                                          |
| `../poses/pose_common.py`    | 采集脚本用于在线预检                                             |
| `../poses/move_open_pose.py` | 与 `calibration/move_open_pose.py` 功能相同，标定目录内保留一份方便就地使用 |
| WitMotion 上位机                | 方式 B 的记录与导出（不在本仓库中）                                    |


---



## 已有标定成果

`data/` 目录已包含五指（含拇指 `1a`/`1b`）的完整标定数据、合并 CSV 及拟合图表（`plots/`），可直接用于查阅或复现分析流程。