"""
test_install.py

【测试目的】
  验证 linkerbot 基础包是否安装成功；可选检测机械臂运动学扩展（Pinocchio + ArmKinetix）。

【前置条件】
  · 已创建并激活 Python 虚拟环境
  · **不需要**连接硬件

【操作步骤】
  1. 执行：python test_install.py

【预期结果】
  · 打印 SDK 版本与「基础包安装成功」
  · 若装了扩展则显示「机械臂运动学扩展安装成功」，否则提示未安装

【实际结果】
  （测试后在此填写）

【说明】
  安装 linkerbot 后的第一步自检；完整环境见 test_env_full.py。
"""

import linkerbot
from importlib.metadata import version

sdk_version = version("linkerbot")
print(f"SDK 版本: {sdk_version}")
print("基础包安装成功")

try:
    import pinocchio
    from linkerbot.arm import ArmKinetix
    print("机械臂运动学扩展安装成功")
except ImportError:
    print("未安装机械臂扩展")