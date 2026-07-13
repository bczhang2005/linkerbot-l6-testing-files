"""
test_env_full.py

【测试目的】
  验证 Python 环境：linkerbot SDK、Pinocchio、（可选）机械臂运动学扩展 ArmKinetix。

【前置条件】
  · 已激活 linkerbot 虚拟环境
  · **不需要**连接 PCAN 或灵巧手硬件
  · 机械臂扩展为可选项，仅使用 L6 灵巧手时可不安装

【操作步骤】
  1. 激活 linkerbot 虚拟环境
  2. 执行：python test_env_full.py

【预期结果】
  · linkerbot SDK、Pinocchio 均显示 ✅
  · 仅灵巧手：ArmKinetix 显示「未安装（可选）」，仍提示灵巧手环境可用
  · 机械臂用户：需 pip install linkerbot[kinetix]，ArmKinetix 也应 ✅

【实际结果】
  （测试后在此填写）

【说明】
  linkerbot 基础包面向灵巧手；ArmKinetix 属于 A7/A7 Lite 机械臂扩展，需额外安装 kinetix。
  Windows 下 Pinocchio 通常用 conda install pinocchio -c conda-forge。
"""

from importlib.metadata import version

hand_ok = False
arm_ok = False

# 1. 验证基础 SDK（灵巧手必需）
try:
    import linkerbot  # noqa: F401
    sdk_ver = version("linkerbot")
    print(f"✅ linkerbot SDK 版本: {sdk_ver}")
    hand_ok = True
except Exception as e:
    print(f"❌ linkerbot SDK 不可用: {e}")

# 2. 验证 Pinocchio（机械臂扩展依赖；灵巧手基础功能不强制要求）
try:
    import pinocchio
    print(f"✅ Pinocchio 版本: {pinocchio.__version__}")
except ImportError:
    print("ℹ️  Pinocchio 未安装（仅做 L6 灵巧手可不装；机械臂扩展需要）")

# 3. 验证机械臂运动学扩展（可选）
try:
    from linkerbot.arm import ArmKinetix  # noqa: F401
    print("✅ 机械臂运动学扩展（ArmKinetix）加载成功")
    arm_ok = True
except ImportError as e:
    print(f"ℹ️  机械臂扩展未就绪: {e}")
    print("   仅使用 L6 灵巧手可忽略；机械臂用户请执行: pip install linkerbot[kinetix]")

print()
if hand_ok and arm_ok:
    print("🎉 整套环境全部验证通过（灵巧手 + 机械臂）")
elif hand_ok:
    print("✅ 灵巧手开发环境可用（linkerbot SDK 正常）")
    print("   当前未检测到机械臂扩展 ArmKinetix，这不影响 L6 灵巧手脚本。")
else:
    print("❌ 环境不完整，请先安装 linkerbot: pip install linkerbot")
