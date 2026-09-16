import time
from YB_Pcb_Car import YB_Pcb_Car

car = YB_Pcb_Car()

try:
    print("1초 동안 우회전합니다.", flush=True)
    car.Car_Right(40, 40)
    time.sleep(1)
finally:
    car.Car_Stop()
    print("정지했습니다.", flush=True)
