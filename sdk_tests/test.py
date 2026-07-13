"""
test.py

【测试目的】
  最简运动片段：设置低速后发一个 open_pose 指令，无读角、无 stop 轮询（早期草稿/片段）。

【前置条件】
  · linkerbot 环境；PCAN 已连接，灵巧手已上电

【操作步骤】
  1. 修改 HAND_SIDE、open_pose 参数
  2. 执行：python test.py

【预期结果】
  · 手指移动到 open_pose 指定角度

【实际结果】
  （测试后在此填写）

【说明】
  未含 stop_polling，完整测试请用 test2_move.py 或 test_move_new.py。
"""

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle
import time

INTERFACE = "PCAN_USBBUS1"   
INTERFACE_TYPE = "pcan"     
HAND_SIDE = "left"

if __name__ == "__main__":
    with L6(
        side=HAND_SIDE,
        interface_name=INTERFACE,
        interface_type=INTERFACE_TYPE
    ) as hand:
        # 设置低速，保证安全
        hand.speed.set_speeds([20, 20, 20, 20, 20, 20])
        print("已设置低速模式")
        
        open_pose = L6Angle(
            thumb_flex=0,  
            thumb_abd=50,    
            index=100,        
            middle=100,      
            ring=100,       
            pinky=100       
        )
        
        print("\n--- 回到全张开安全位 ---")
        hand.angle.set_angles(open_pose)  
        time.sleep(2)  
