"""
testing_L6.py

【测试目的】
  批量验证 temperature / current / torque 模块是否具备 get_blocking、get_snapshot API。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确
  · 脚本会先 stop 默认轮询

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python testing_L6.py
  3. 查看各模块两种读法的成功/失败/方法不存在信息

【预期结果】
  · 各模块打印 API 是否存在及调用结果
  · 不支持的模块会显示方法不存在或调用失败

【实际结果】
  （测试后在此填写）

【说明】
  进阶 API 一致性探测；部分模块可能因硬件不支持而无数据。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

if __name__ == "__main__":
    print("=== 进阶模块API一致性测试 ===")
    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        # 先关默认轮询，避免堵队列
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)
        print("✅ 连接成功，开始测试各模块\n")

        # 要测的模块列表
        modules_to_test = [
            ("温度 temperature", hand.temperature),
            ("电流 current", hand.current),
            ("扭矩 torque", hand.torque),
        ]

        for name, module in modules_to_test:
            print(f"---------- 测试 {name} ----------")
            
            # 1. 测有没有get_blocking方法
            print(f"1. 测试 get_blocking():")
            try:
                data = module.get_blocking(timeout_ms=2000)
                print(f"   ✅ 成功，数据: {data}")
            except AttributeError as e:
                print(f"   ❌ 方法不存在: {e}")
                # 打印这个模块的所有方法，看看它到底有什么
                print(f"   该模块实际方法: {[m for m in dir(module) if not m.startswith('_')]}")
            except Exception as e:
                print(f"   ⚠️  调用失败: {type(e).__name__}: {e}")

            # 2. 测有没有get_snapshot方法
            print(f"2. 测试 get_snapshot():")
            try:
                data = module.get_snapshot()
                if data:
                    print(f"   ✅ 成功，数据: {data}")
                else:
                    print(f"   ⚠️  成功但无数据（缓存为空）")
            except AttributeError as e:
                print(f"   ❌ 方法不存在: {e}")
            except Exception as e:
                print(f"   ⚠️  调用失败: {type(e).__name__}: {e}")
            
            print()

        print("=== 测试完成 ===")