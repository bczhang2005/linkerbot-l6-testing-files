# URDF 与机器人建模

URDF（Unified Robot Description Format）是 ROS 生态里描述机器人本体的事实标准。它把一台机器人抽象成一棵由 link（连杆）和 joint（关节）构成的运动树，每个 link 携带自己的可视几何、碰撞几何与惯性参数。这套模型直接决定了正运动学、动力学求解、以及碰撞检测能不能给出正确的结果。

本章不重复 URDF 语法手册的内容，而是集中讲清楚**做建模决策时真正需要知道的理论与工程约定**：坐标系与角度、惯量参数、mimic 关节与等式约束、碰撞几何、以及自碰撞策略。整章以 URDF 为主视角，跨界到 MJCF 的地方给出对照，方便在两种格式之间一致地维护同一台机器人。

关于坐标变换与位姿表示的更底层内容，请参考 [第一章 正运动学](../../robot-arm-theory-and-guides/robotics/forward-kinematics)。关于碰撞体几何的更底层内容，请参考 [仿真环境中的碰撞体](../theoretical-foundations/collision-bodies)。

## 1 URDF 的模型结构

### 1.1 URDF 是一棵运动树

URDF 在拓扑上是一棵**有根的有向树**：

- **节点**：link，代表一段刚体。
- **边**：joint，从父 link 指向子 link，定义两者之间的相对位姿以及自由度类型。
- **根**：树上唯一没有父关节的 link，称为 `base_link` 或类似命名。

每个 link 有且仅有一个父关节（除了根），这条约束是 URDF 能表示为一棵树的前提。真实机器人如果存在**闭链**结构（例如四杆机构、并联手指），URDF 无法直接表达，只能借助 `<mimic>` 或者交由仿真器的等式约束模拟。

运动树带来的好处是：正运动学可以写成一串齐次变换矩阵的连乘

$$
T_{\text{root} \to \text{leaf}} = T_1 T_2 \cdots T_n
$$

其中每个 $T_i$ 由对应关节的类型（固定 / 旋转 / 移动）和当前关节角决定。这一性质在 [正运动学](../../robot-arm-theory-and-guides/robotics/forward-kinematics) 中已经详细讨论，此处不再展开。

### 1.2 URDF 的语法组成

一个最简单的可用 URDF 通常包含以下几类元素：

- `<link>`：定义一段刚体，可选地携带 `<visual>`、`<collision>`、`<inertial>` 三个子元素。
- `<joint>`：定义两个 link 之间的相对位姿、关节类型、关节轴、限位、以及可选的 `<mimic>`。
- `<transmission>`：把关节和执行器（actuator）关联起来，ROS 控制器用。仿真场景里往往被 MJCF 的 actuator / Isaac 的 Articulation Drive 替代。
- `<material>`、`<mesh>`、`<geometry>`：视觉与碰撞的具体表示。

一个典型的连杆定义大致长这样：

```xml
<link name="link_1">
  <visual>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <geometry><mesh filename="meshes/link_1_visual.STL"/></geometry>
  </visual>
  <collision>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <geometry><mesh filename="meshes/link_1_collision.obj"/></geometry>
  </collision>
  <inertial>
    <origin xyz="0.01 0 0.05" rpy="0 0 0"/>
    <mass value="0.8"/>
    <inertia ixx="0.0021" ixy="0" ixz="0" iyy="0.0021" iyz="0" izz="0.0004"/>
  </inertial>
</link>
```

后面的几节会分别拆开 `<origin rpy>`、`<inertia>`、`<collision>` 三块讲。

### 1.3 URDF 的能力边界

URDF 的设计目标是简洁与广泛兼容，代价是**动力学与接触建模的表达力偏弱**：

- 关节约束只支持 `<mimic>` 一种，且限定为线性。
- 没有原生的接触对排除机制（`<contact><exclude/>` 是 MJCF 才有的）。
- 没有 default 类、没有 site、传感器只有占位符。
- 没有惯量的物理有效性检查，非法惯量能被解析器接受。

这些正是**为什么很多项目会同时维护 URDF 与 MJCF 两份文件**：URDF 作为**真相之源**（与 CAD 一致、与厂家沟通、与 ROS 兼容），MJCF 作为**仿真契约**（补齐 URDF 没写但仿真需要的接触参数、mimic 展开、self-collision 排除、default 类等）。两份文件必须一致，一致性通过 [FK 一致性校验](../validation/fk-parity) 与 [惯量一致性校验](../validation/inertia-parity-eigenvalues) 自动断言。

## 2 坐标系与角度约定

### 2.1 单位与手性

URDF 强制**国际单位制 + 右手坐标系**：

- 长度：米（m）
- 质量：千克（kg）
- 角度：**弧度**（rad），不是度
- 时间：秒（s）
- 坐标系：右手系，与 ROS REP-103 一致

MJCF 的默认值和 URDF 是**不一样**的：`<compiler>` 默认 `angle="degree"`。这是最常见的角度陷阱来源之一——把 URDF 里的 `1.5708` 直接拷进 MJCF 会得到 1.6° 的旋转，而不是 90°。手写 MJCF 时应当在编译器指令里显式声明：

```xml
<compiler angle="radian" eulerseq="XYZ" autolimits="true" discardvisual="false"/>
```

### 2.2 `<origin>` 元素与齐次变换

URDF 里的每一次坐标变换（joint 的父到子、link 的 inertial/visual/collision 相对于 link 原点）都由一个 `<origin>` 元素描述：

```xml
<origin xyz="x y z" rpy="phi theta psi"/>
```

从数学上看，这就是一个齐次变换矩阵：

$$
T =
\begin{bmatrix}
R(\phi, \theta, \psi) & \mathbf{p} \\
\mathbf{0}^T & 1
\end{bmatrix},
\quad
\mathbf{p} =
\begin{bmatrix} x \\ y \\ z \end{bmatrix}
$$

其中 $R(\phi, \theta, \psi)$ 是由 `rpy` 三个角度按 URDF 约定构造出来的旋转矩阵——这个约定是下一节的重点。

### 2.3 rpy 的语义：固定轴外旋 XYZ

URDF 的 `rpy` 是**绕固定轴（世界系）依次做 X → Y → Z 三次旋转**，也称为**外旋 XYZ**：

$$
R(\phi, \theta, \psi) = R_z(\psi)\, R_y(\theta)\, R_x(\phi)
$$

注意矩阵乘法顺序**从右向左**读，恰好对应"先绕 X 转 $\phi$、再绕 Y 转 $\theta$、再绕 Z 转 $\psi$"这一物理动作。

> **外旋（extrinsic）与内旋（intrinsic）**
> - **外旋**：每一次旋转都相对于**世界系**的固定坐标轴进行。URDF 采用的就是这种。
> - **内旋**：每一次旋转都相对于**上一步已经转过的**局部坐标轴进行。
>
> 两者在单轴旋转下结果一致；在多轴旋转下会得到**不同**的最终姿态。数学上二者互为顺序反转：绕世界 X→Y→Z 的外旋等价于绕局部 Z→Y→X 的内旋。

MJCF 默认 `eulerseq="xyz"`（**小写**）是**内旋 XYZ**，与 URDF 的**外旋 XYZ** 不同。只有把 `eulerseq` 显式设为大写 `"XYZ"` 才能对齐 URDF。

这个约定差异带来的最阴险的 bug 是：**单轴 rpy 情况下两种约定结果一致，测试样例常常只涉及单轴，导致错误在多轴场景下才暴露**。校验方式详见 [FK 一致性校验](../validation/fk-parity)。

### 2.4 四元数分量顺序

URDF 本身不写四元数，但在与真机 SDK、SLAM、可视化工具打交道时经常需要在 rpy、旋转矩阵、四元数之间互转。这里最常见的陷阱是**分量顺序不一致**：

| 环境                                | 分量顺序           |
|-------------------------------------|--------------------|
| MJCF `quat`                         | `[w, x, y, z]`     |
| ROS `geometry_msgs/Quaternion`      | `[x, y, z, w]`     |
| `scipy.spatial.transform.Rotation`  | `[x, y, z, w]`     |
| Eigen `Quaternion` 构造函数         | `(w, x, y, z)`     |
| Eigen `Quaternion` 内存布局         | `[x, y, z, w]`     |

不同库的约定不同，转换写反是**静默失败**——旋转看起来"不对劲"但没有报错。工程上的推荐做法是**在数据结构层面严格标注顺序**，例如在函数注释里显式写"expects [w, x, y, z]"。

### 2.5 网格缩放

URDF 中网格缩放写在每个 `<visual>` / `<collision>` 的 `<mesh scale="sx sy sz"/>` 上，MJCF 则是 `<asset><mesh scale="..."/>` 只声明一次。同一个网格在两份文件中的 scale 必须一致，否则同一 STL 在 URDF 侧和 MJCF 侧代表的其实是不同大小的物体。

## 3 惯量与质量参数

### 3.1 刚体惯量张量的定义

对于一个具有质量分布 $\rho(\mathbf{r})$ 的刚体，惯量张量定义为

$$
\mathbf{I} = \int_V \rho(\mathbf{r}) \left(\mathbf{r}^T\mathbf{r}\, \mathbf{E} - \mathbf{r}\mathbf{r}^T\right) dV
$$

其中 $\mathbf{r}$ 是从**质心**出发的位置向量，$\mathbf{E}$ 是三阶单位矩阵。展开成分量：

$$
\mathbf{I} =
\begin{bmatrix}
I_{xx} & -I_{xy} & -I_{xz} \\
-I_{xy} & I_{yy} & -I_{yz} \\
-I_{xz} & -I_{yz} & I_{zz}
\end{bmatrix}
$$

具体来说：

$$
I_{xx} = \int \rho (y^2 + z^2)\, dV, \quad
I_{xy} = \int \rho \, xy\, dV, \quad \text{（其余类推）}
$$

对角元 $I_{xx}, I_{yy}, I_{zz}$ 描述绕对应坐标轴的转动惯量，非对角元 $I_{xy}, I_{xz}, I_{yz}$ 描述惯量耦合项。张量是**对称**且**半正定**的。

### 3.2 URDF 与 MJCF 的字段顺序

URDF `<inertial>` 元素：

```xml
<inertial>
  <origin xyz="cx cy cz" rpy="0 0 0"/>
  <mass value="m"/>
  <inertia ixx="..." ixy="..." ixz="..." iyy="..." iyz="..." izz="..."/>
</inertial>
```

MJCF `<inertial>` 元素：

```xml
<inertial pos="cx cy cz" mass="m" fullinertia="ixx iyy izz ixy ixz iyz"/>
```

两者**字段顺序不同**：

- URDF：`ixx, ixy, ixz, iyy, iyz, izz`（交错排列，先行后列）
- MJCF `fullinertia`：`ixx, iyy, izz, ixy, ixz, iyz`（先对角、后非对角）

这是 URDF↔MJCF 迁移里最常见的 copy-paste 出错源。工程上的推荐做法是在人工写 MJCF 时**总是从 URDF 的字段名重新排布**，不要从数字序列直接搬。

`<origin xyz>` 表示的是**质心位置**（相对于 link 原点），惯量张量则默认表示在**通过质心、与 link 原点轴对齐**的坐标系里。如果 `<origin rpy>` 非零，还多一层旋转，实际使用中很少这么写。

### 3.3 平行轴定理

惯量张量依赖于参考点。如果质心处的张量为 $\mathbf{I}_c$，那么在偏移 $\mathbf{d}$ 的另一点处的张量为

$$
\mathbf{I}_p = \mathbf{I}_c + m\left(\mathbf{d}^T\mathbf{d}\, \mathbf{E} - \mathbf{d}\mathbf{d}^T\right)
$$

URDF 与 MJCF 都规定 `<inertial>` 里的张量**表达在质心处**，`<origin xyz>` / `pos` 只告诉引擎质心在哪。所以工程上不需要手动做平行轴变换——只需保证从 CAD 导出时选中"表达于质心"的选项即可。

### 3.4 惯量的物理有效性

要让一个惯量张量对应到某种真实的质量分布，仅有对称与半正定还不够——它的**主惯量**（也就是特征值） $I_1, I_2, I_3$ 还必须满足**三角不等式**：

$$
I_1 + I_2 \ge I_3, \quad I_2 + I_3 \ge I_1, \quad I_1 + I_3 \ge I_2
$$

违反三角不等式的张量在数学上是有效的（对称半正定矩阵），但在物理上找不到任何一个真实物体能产生这样的惯量分布。常见的违反来源：

- CAD 导出 bug：某些格式用"半张量"约定（把非对角项加了 1/2 系数）。
- 手算简单几何体时公式记错。
- 从厂家 URDF 抄写时把非对角项符号搞反。

**MuJoCo 的 `<compiler balanceinertia="true"/>` 就是为了绕过这个门槛而存在的**——它在检测到非法惯量时会**悄悄编造一个对角张量**去替换，让模型能加载。这是一个静默的正确性陷阱：仿真跑得动，但对应的动力学早已与真实物体无关。**永远不要开启这个选项**，让加载在非法张量上直接失败，然后回到源头（CAD / 数据表）修正。

### 3.5 为什么用特征值做一致性校验

MuJoCo 在编译期会做两件事：

1. 对每个 body 的惯量张量做**主轴对角化**，得到该 body 的主惯量方向。
2. 把 body 的旋转调整到与主轴对齐，编译后的 `body_inertia` 只存三个对角元。

结果就是：**编译后的 MJCF 惯量张量**与 URDF 的**书写坐标系下的惯量张量**在数值上**不完全相等**——它们相差一个旋转。如果直接逐元素比对，一定会误报失败。

正确的校验方式是比较**排序后的主惯量（也就是特征值）**：

$$
\text{eigsorted}(\mathbf{I}_{\text{URDF}}) \stackrel{?}{=} \text{eigsorted}(\mathbf{I}_{\text{MJCF}})
$$

特征值是**旋转不变量**——不依赖坐标系怎么选，只取决于质量分布本身。工程上取相对误差 0.1% 作为容差是可达且足够灵敏的阈值。这套检查能覆盖：轴交换、非对角项符号错误、URDF↔MJCF 字段顺序抄错等常见 bug。

需要同时校验的三项：质量、质心位置、主惯量特征值。缺一都可能漏掉一类错误。

### 3.6 零质量链接的处理

URDF 里 `<mass value="0"/>` 是合法的写法，通常用于**占位坐标系**——例如末端 TCP、传感器安装原点、纯粹为了挂载 mount frame 而存在的中间 link。这类 link 没有几何、没有惯性，仅作为一个 frame 存在。

MuJoCo 编译器对零质量 body 的处理是**焊接**（weld）到父 body：不分配关节自由度，不参与动力学。**这是预期行为**，与作者的意图一致。

但同一机制也会**吞掉一类错误**：作者本意让 link 是动态体，但因为 CAD 导出漏算 / 手写抄成 0，MuJoCo 就默默把它焊死。这时候：

- 仿真里"看得见"这段 link，因为几何还在。
- 关节看起来"能动"，因为父 link 的自由度还在。
- 但这段 link 的质量、惯量对整机动力学没有任何贡献。

校验策略：[惯量一致性校验](../validation/inertia-parity-eigenvalues) 应**跳过** `mass < 10^{-9}` 的 link（视为合法占位），但对 `mass = 10^{-6}` 这种"微小但合法"的 link 仍然做比对，防止把真正的动态 link 误当作占位 frame。

## 4 Mimic 关节与等式约束

### 4.1 关节类型与自由度

URDF 定义的关节类型：

| 类型         | 自由度 | 说明                             |
|--------------|--------|----------------------------------|
| `fixed`      | 0      | 刚性连接，用于组件装配、mount    |
| `revolute`   | 1      | 有限位的旋转关节                 |
| `continuous` | 1      | 无限位的旋转关节（旋转编码器）   |
| `prismatic`  | 1      | 有限位的平移关节                 |
| `floating`   | 6      | 完全自由的 6-DoF（很少正确使用） |
| `planar`     | 2      | 平面内两平移（很少见）           |

在实际机器人建模里，几乎所有出现的关节都是 `fixed`、`revolute` 或 `prismatic`。`continuous` 用于连续旋转的轮子/电机；`floating` / `planar` 更多是数学上的完整性，实际中被基座 `fixed` + 自由的浮动关节替代（后者由仿真器提供）。

### 4.2 Mimic 的数学表达

URDF 的 `<mimic>` 声明了一个**follower** 关节的角度必须严格跟随另一个 **driver** 关节：

```xml
<joint name="follower" type="revolute">
  <parent link="a"/> <child link="b"/>
  <axis xyz="0 0 1"/>
  <limit lower="-1" upper="1" effort="10" velocity="1"/>
  <mimic joint="driver" multiplier="k" offset="c"/>
</joint>
```

它表达的约束是

$$
q_{\text{follower}} = k \cdot q_{\text{driver}} + c
$$

数学上，这是一条**线性完整约束**（linear holonomic constraint）。它把系统的自由度从 $n$ 减到 $n - 1$；进入动力学方程时表现为一个 Lagrange 乘子，仿真器求解时把 follower 的自由度消掉。

从工程上说，mimic **描述真实机器人上的机械耦合**：齿轮组、腱驱、四杆机构、指关节联动。真机上这些耦合是**硬件强制**的，仿真里如果不实现，那么"模拟机器人"和"真实机器人"在同样的电机指令下会呈现不同的手指姿态。**这是必须仿真出来的**，而不是可选优化。

### 4.3 URDF `<mimic>` 与 MJCF `<equality>` 对照

URDF 的 mimic 表达能力很受限：只能线性、一对一。MJCF 提供更一般的 `<equality>` 约束：

```xml
<equality>
  <joint joint1="follower" joint2="driver" polycoef="c0 c1 c2 c3 c4"/>
</equality>
```

`polycoef` 是一个 5 元系数向量，定义了 follower 相对于 driver 的多项式关系：

$$
q_{\text{follower}} = c_0 + c_1\, q_{\text{driver}} + c_2\, q_{\text{driver}}^2 + c_3\, q_{\text{driver}}^3 + c_4\, q_{\text{driver}}^4
$$

对应 URDF `<mimic joint="driver" multiplier="k" offset="c"/>` 的线性形式，MJCF 里写作：

```xml
<joint joint1="follower" joint2="driver" polycoef="c k 0 0 0"/>
```

三个常见迁移陷阱：

1. **多项式系数必须恰好 5 个**。写 6 个（例如厂家 URDF 里嵌入的 `<mujoco>` 块里常见的 `"0 1.125676 0 0 0 0"`）会被 MuJoCo 拒绝，或者某些版本静默丢弃多余项，导致约束行为错乱。迁移时需要主动删掉尾部的多余零。
2. **常数项与系数项的位置**：URDF 的 `offset` 是常数项，`multiplier` 是一次项系数——对应 MJCF 的 `c0` 与 `c1`。顺序容易记反。
3. **符号方向**：URDF `multiplier` 允许负值（follower 与 driver 反向联动），迁移到 MJCF 时 `c1` 直接取相同符号，不要在坐标系变换里把符号丢掉。

### 4.4 多驱动、组合复用与命名前缀

**多个 follower 共用一个 driver**：URDF 与 MJCF 都支持，但要**逐条**写出，不能"打包"。每一条 `<mimic>` 或 `<equality>` 都是一条独立约束。

**组合复用时的重命名**：当组件（component）被 workstation composer 装配成完整机器人时，每个关节名会被加上**角色前缀**（例如 `arm_left_L1_joint`），避免左右两份同型号机械臂的关节重名。这时候 mimic / equality 里的 `joint=` / `joint1=` / `joint2=` 引用也**必须同步重写**，否则加载时找不到关节。这一步由 composer 自动完成，作者不需要手动改。

## 5 碰撞几何设计

### 5.1 视觉与碰撞的分离

URDF 把每个 link 的几何清晰分成两类：

- `<visual>`：给渲染器用。可以任意复杂——CAD 导出的高精度网格、带材质与贴图、上百万三角面。物理引擎不看这一块。
- `<collision>`：给物理引擎用。用来做碰撞检测、距离查询、接触点生成。物理引擎的性能与稳定性直接依赖这一块。

两者**可以共用**同一个网格文件，也**应当分开**。共用的做法在小项目里很普遍（"反正是同一个物体"），但这会带来两类问题：

- **性能塌方**：视觉网格通常有几万到几十万三角面，物理引擎每一步都要在这些面上做碰撞查询。
- **凸性问题**：视觉网格通常是**非凸**的（有凹槽、螺孔、内部空腔），下一节会看到，PhysX 等主流物理引擎不接受动态刚体上的非凸网格作为碰撞体。

MJCF 通过 `contype` / `conaffinity` / `group` 分离两者：可视 geom 用 `contype="0" conaffinity="0" group="1"`，碰撞 geom 用 `contype="1" conaffinity="1" group="3"`——这样默认视图只显示可视组，接触计算只走碰撞组。

### 5.2 三类碰撞几何

关于碰撞几何的一般理论（凸集、凸包、GJK 等）请见 [仿真环境中的碰撞体](../theoretical-foundations/collision-bodies)。这里只讨论 URDF 中的表达。

URDF 支持的碰撞几何原语：

| 表示           | URDF 元素                     | 说明                                       |
|----------------|-------------------------------|--------------------------------------------|
| 基本体         | `<box>` / `<cylinder>` / `<sphere>` | 最快、最稳定，粗糙但足够多数场景 |
| 网格           | `<mesh filename="..."/>`       | 具体形状由文件决定，可以是凸包、凸分解、或完整网格 |

MJCF 额外支持胶囊体（`capsule`）、椭球（`ellipsoid`）、平面（`plane`）等原语，这也是 MJCF 在接触建模上比 URDF 强的一个体现。

三种常见做法各自的取舍：

- **基本体组合**：用若干个盒体、圆柱、胶囊拼近似形状。运行时最快，接触行为最稳。代价是需要建模时间，对薄壁、凹腔、复杂曲面欠拟合。参考实现：`dex-urdf/robots/hands/inspire_hand` 的手掌就是 1 圆柱 + 6-7 个盒体的组合。
- **凸包（convex hull）**：从源网格顶点一次性求最小凸多面体。保证凸性，PhysX 接受。缺点是**空心或细长形状**的凸包**体积膨胀严重**——例如 Linker Hand 掌心的体积/凸包比是 0.16~0.31，凸包体积是真实体积的 3~6 倍，接触时手掌"变胖"了。
- **完整网格**：直接用视觉网格。仅 MuJoCo 对动态体支持（它内部会 fallback 到凸包），PhysX 直接拒绝。

### 5.3 凸性假设与 PhysX 的拒绝

大多数主流物理引擎（Bullet、PhysX、ODE）在窄相碰撞检测（narrow phase）里使用 **GJK 算法（Gilbert-Johnson-Keerthi）**。GJK 只对**凸集**成立——它依赖凸集的**支撑函数**（support function）来迭代找出最近点对或穿透方向。

对于非凸形状，物理引擎有三种选择：

1. **离线凸分解**：作者在建模阶段就把非凸网格拆成若干个凸块（V-HACD 等算法），运行时对每个凸块单独跑 GJK。
2. **凸包近似**：加载时把整个网格用凸包代替，接受形状失真。MuJoCo 走这条路。
3. **直接拒绝**：不允许把非凸网格用作动态刚体的碰撞体。PhysX 走这条路。

于是同一份 URDF 拿到两种仿真器里：

- **MuJoCo**：加载成功，仿真跑得动，但接触形状是**凸包**而不是原始网格。你以为你在仿真"带凹腔的手掌"，实际上在仿真"实心块"。
- **PhysX（Isaac）**：直接报错拒绝，或者 fallback 到某种简化，接触无法信任。

**这是一个跨仿真器的静默差异**：同一份资产在两边跑出不同结果，作者未必知道。工程上的正确姿态是**在建模阶段就把碰撞几何做成凸的**，让两个仿真器看到的是同一份可信几何。

### 5.4 凸包生成的工程实践

对于必须用网格描述的复杂形状，从视觉网格到可用的凸碰撞几何有几种路径：

- **直接凸包**：`trimesh.load(stl).convex_hull` 一行代码。适合本来就近似凸的形状。三角面数与源顶点数相关，通常几百到几千。
- **凸分解（V-HACD）**：把非凸网格分成多个凸块。保留凹结构信息，但每个 link 会产生若干个 collision geom，配置复杂。
- **体素量化凸包**：先把顶点按 1-5 mm 网格量化去重，再求凸包。既保留极值点（形状不塌陷），又控制三角面数，又保证凸性。工程上简单可靠。

关键规则：

- **不能对凸包做 `simplify_quadric_decimation`**。四边形误差最小化会在凸包表面引入亚毫米的凹陷，PhysX 因此拒绝。
- **不能"先精简源网格再求凸包"**。精简会随机丢顶点，导致凸包比源形状**更小**——视觉上就是碰撞体嵌进了视觉网格里，看起来穿透了。
- **只有"体素量化 + 凸包"这条路径同时满足**：控制三角面数、保留原始形状包络、保证凸性、结果可重复。

三角面预算的工程参考：单手 5-10k 碰撞三角面通常足够仿真级别的接触；参考仓库 `dex-urdf` 的 inspire_hand 约 25k、`sharpa-urdf-usd-xml` 约 28k。超过 100k 的 collision mesh 几乎一定会拖慢仿真。

## 6 自碰撞策略

### 6.1 自碰撞的物理来源

自碰撞（self-collision）指同一个机器人（同一个 articulation）内部两个 link 的碰撞几何之间发生接触。真实机器人上，自碰撞被机械限位和结构设计避免；仿真器不知道这些，默认会把所有 link 对儿都算接触。

自碰撞在仿真里通常**不是我们想要的**：

- 关节限位应当在**关节层面**约束（`<limit lower upper>`），而不是让 link 撞在一起来阻止。
- link 之间"应当碰撞"的极少数场景（例如夹爪两指夹到一起）应当显式建模。

因此工程上的默认姿态是**关闭大多数自碰撞对**，只保留明确需要的那些。

### 6.2 相邻连杆的必然穿插

一个反直觉但普遍存在的现象：**用完整网格作碰撞几何时，相邻 link 在关节轴附近几乎一定会互相穿插**。

原因很直接：joint 位于两 link 的物理接触面附近，两个 link 的碰撞网格在关节轴半径 1-5 mm 范围内几乎必然重叠。真实机器人靠机械间隙避免了这个问题，仿真里没有这个间隙。

于是仿真启动瞬间（qpos=0）就产生了活跃的接触对，接触摩擦力反向作用在关节方向上：

```
执行器输出 = 位置目标 - 当前位置 × Kp
反向摩擦力 = 与关节运动方向相反
关节 = 摩擦锁死
```

用户看到的现象是：拖动 viewer 里的关节滑块能"手动"移动关节（因为滑块直接改 qpos），但执行器下了同一个位置指令**跟不到位**。诊断方式详见 [相邻连杆夹住执行器](../pitfalls/adjacent-link-clamping)。

### 6.3 排除策略

**URDF 本身没有原生的自碰撞排除机制**。这一决策必须交给仿真器：

- **MJCF**：`<contact><exclude body1="..." body2="..."/>`，或者反向的 `<contact><pair/>` 白名单模式。
- **Isaac / PhysX**：由 URDF loader 配置生成 collision filter matrix。
- **通用 URDF loader**（例如 `srdf`）：另一份 `.srdf` 文件描述排除对，与 URDF 并行维护。

排除对应当按**三层**组织：

1. **相邻父-子对**：只要使用了完整网格或粗凸包，几乎一定要排除。这是自碰撞的第一大来源。
2. **短连杆祖-孙对**：中间 link 太短、外层网格仍然相交时也需排除。这类需要在校验中主动发现。
3. **跨组件祖先-后代对**：workstation 层面装配时，机械臂末端 link 与机械手第一段、机械臂底座与桌面这类"沿着装配链固定连接"的对儿，应由 composer 自动排除。

**不要排除的对儿**：

- **兄弟组件之间**（左臂 vs 右臂）：这些应当保留正常碰撞——真实双臂能撞在一起，仿真也要能反映出来。
- **末端 vs 环境**：末端和桌面、末端和抓取物之间正是任务本身要感知的接触，绝对不能排除。

### 6.4 组件层与场景层的职责分离

**不要在组件（component）层强行关闭自碰撞**——组件可能被多个 workstation 复用，自碰撞策略是**场景层**的决定。组件层只需要负责：

- 内部 link 之间必须排除的对儿（相邻 mesh 穿插这种）
- 通过 mount frame 与外部装配，不预设装配后的排除

场景层（workstation）在装配时：

- 遍历所有组件对儿，对沿装配链的祖先-后代自动加 exclude。
- 保留兄弟对儿的接触。
- 允许用户在 recipe 里显式追加或移除排除对儿。

### 6.5 静态自接触校验

自碰撞策略配置对不对，靠**静态自接触校验**（self-contact at rest）来断言：

1. 编译工作站模型（URDF → MuJoCo / PhysX 内部表示）。
2. 设置 qpos 到某个已知的"静止"配置——通常是关节零位。
3. 前进 1 步物理，读取当前活跃接触列表。
4. 任何 `dist ≤ 0` 的接触对都视为 bug。

校验器输出应当是**具体的 body 对儿列表**，而不是布尔通过/失败。这样定位者可以直接把配对拷进 `<exclude>` 或者去修碰撞几何。

详见 [静态自接触检查](../validation/self-contact-at-rest)。

## 7 工程实践小结

把整章的关键决策浓缩成一份可以在项目起步阶段就参照的清单：

**建模阶段**

- URDF 是真相之源；MJCF 是仿真契约。两份都进 git，保持一致。
- 单位：米、千克、弧度、右手系。MJCF 显式声明 `angle="radian" eulerseq="XYZ"`。
- `rpy` 语义是外旋 XYZ；不要复用 MJCF 默认的内旋 xyz。
- 惯量填对字段顺序（URDF 交错，MJCF fullinertia 先对角）。
- 惯量必须物理有效——`balanceinertia` 永远不开。
- 零质量 link 仅作占位坐标系使用，动态 link 必须有正质量。

**几何阶段**

- 视觉与碰撞分离，绝不共用完整网格作碰撞。
- 碰撞几何优先基本体，其次凸分解、体素量化凸包，最后才是完整网格。
- 单个 link 碰撞三角面控制在 5-10k 量级。

**约束阶段**

- 真实机械耦合必须建模为 mimic / equality，不能省略。
- `polycoef` 恰好 5 个元素。
- 组件重命名后 mimic 引用必须同步。

**校验阶段（必须自动化）**

- FK 一致性（URDF vs MJCF）——最强的几何正确性检查。
- 惯量一致性（基于特征值）。
- 静态自接触在 qpos=0 处无活跃接触。
- 重力保持下漂移在数值噪声内。

以上任何一项手工检查都不够——**仿真器不会主动告诉你模型是错的**，它会"尽力跑出一些数"，所以校验必须由代码断言。

## 参考

- ROS REP-103: Standard Units of Measure and Coordinate Conventions.
- Featherstone, R. *Rigid Body Dynamics Algorithms*, Springer, 2008.
- MuJoCo Documentation: XML Reference, [https://mujoco.readthedocs.io/en/stable/XMLreference.html](https://mujoco.readthedocs.io/en/stable/XMLreference.html).
- Todorov, E. *Convex and analytically-invertible dynamics with contacts and constraints*, ICRA 2014.
- Ericson, C. *Real-Time Collision Detection*, Morgan Kaufmann, 2004.
