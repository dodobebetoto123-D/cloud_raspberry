import time
from YB_Pcb_Car import YB_Pcb_Car

car = YB_Pcb_Car()

try:
    print("1초 동안 저속 전진합니다.", flush=True)
    car.Car_Run(40, 40)
    time.sleep(1)
finally:
    car.Car_Stop()
    print("정지했습니다.", flush=True)
