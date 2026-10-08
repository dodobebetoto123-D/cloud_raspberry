import time

from gpiozero import DistanceSensor


# Raspbot 공식 문서의 BOARD 핀:
# ECHO = 물리 핀 18 = BCM GPIO24
# TRIG = 물리 핀 16 = BCM GPIO23
sensor = DistanceSensor(
    echo=24,
    trigger=23,
    max_distance=4,
)


try:
    print("초음파 측정을 시작합니다. 종료: Ctrl+C", flush=True)

    while True:
        # gpiozero의 distance는 이미 미터 단위이므로 *100으로 cm 환산
        distance_cm = sensor.distance * 100
        print(f"거리: {distance_cm:.1f} cm", flush=True)
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n종료합니다.", flush=True)

finally:
    sensor.close()
