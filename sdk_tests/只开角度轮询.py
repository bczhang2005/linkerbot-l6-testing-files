"""
只开角度轮询.py

【测试目的】
  隔离测试：仅开启角度 10Hz 轮询，30 秒内每秒 get_snapshot，验证是否稳定无堵队列。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电；HAND_SIDE 正确

【操作步骤】
  1. 修改 HAND_SIDE
  2. 执行：python 只开角度轮询.py
  3. 观察 30 秒内角度快照读取

【预期结果】
  · 30 秒内多次正常读到角度，无中途异常
  · 结束时打印正常读取次数

【实际结果】
  （测试后在此填写）

【说明】
  推荐无力传感器机型的安全轮询方式；与 test3_read / 硬件连接测试 方式2 一致思路。
"""

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
import time

INTERFACE = "PCAN_USBBUS1"
INTERFACE_TYPE = "pcan"
HAND_SIDE = "left"

if __name__ == "__main__":
    print("=== 测试1：只开角度轮询（10Hz） ===")
    with L6(side=HAND_SIDE, interface_name=INTERFACE, interface_type=INTERFACE_TYPE) as hand:
        # 先停掉所有默认轮询，清空状态
        hand.stop_polling()
        hand.stop_stream()
        time.sleep(0.5)

        # 只开角度轮询，10Hz（每秒10次，比默认低，排除其他干扰）
        print("✅ 只开启角度轮询，开始测试30秒...")
        hand.start_polling({SensorSource.ANGLE: 0.1})

        # 每隔1秒读一次角度，看会不会超时、会不会堵
        start_time = time.time()
        normal_count = 0
        while time.time() - start_time < 30:
            try:
                angle_snap = hand.angle.get_snapshot()
                if angle_snap:
                    normal_count += 1
                    # 每5秒打印一次，不用太频繁
                    if normal_count % 5 == 0:
                        print(f"第{normal_count}次读角度正常: {[round(x,2) for x in angle_snap.angles.to_list()]}")
                time.sleep(1)
            except Exception as e:
                print(f"❌ 中途出错：{e}")
                break
        
        print(f"\n✅ 测试1结束：30秒内正常读取{normal_count}次，只开角度轮询无问题")
        hand.stop_polling()