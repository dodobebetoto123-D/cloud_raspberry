"""RoboFest BottleSumo 타임 트라이얼 자율 주행 프로그램.

규칙(2027 국내예선 규정집 기준):
- 시작 후 3초 대기 필수, 완전 자율 주행 (원격 조종 금지)
- 타임 트라이얼: 테이블 위 병을 밀어내기 (시드 결정용)
- 토너먼트: 병 없이 1대1 헤드투헤드 (이 프로그램은 타임 트라이얼용)
- 게임 제한 2분, 20초간 진전 없으면 무승부
- 밀어낸 뒤 3초 이상 테이블 위에 생존해야 함
- Junior Unlimited: 30x30x30cm, 2.5kg / Pi 기반은 Unlimited 디비전

전략:
1. 3초 대기 후 시작 (룰 필수)
2. 저속 직진하며 전방 초음파 센서로 병 탐색 (제자리 탐색 회전 없음)
3. 병이 감지되면 돌진해서 밀기 (엣지 감시 병행)
4. 엣지 감지 시 정지, 짧게 후진 후 회전. 감지가 지속되면 정지 상태로 정상 복귀 대기
5. 밀기 동작 후에는 중앙 쪽으로 후퇴 (3초 생존 확보)
6. --max-runtime(기본 115초)이 되면 정지 후 종료

하드웨어:
- 모터: YB_Pcb_Car (I2C 0x16, Yahboom Raspbot)
- 엣지 센서: X1=BCM GPIO22(왼쪽), X4=BCM GPIO4(오른쪽), 기본 active-low
- 초음파: echo=BCM24, trig=BCM23
"""

import argparse
import statistics
import time

import lgpio
from gpiozero import DistanceSensor

from YB_Pcb_Car import YB_Pcb_Car


# --- 배선 (edge_avoid_test.py / ultrasonic_test.py와 동일) ---
X1_GPIO = 22
X4_GPIO = 4
ECHO_GPIO = 24
TRIG_GPIO = 23

# --- 대회 규칙 상수 ---
START_DELAY_SECONDS = 3.0   # 시작 후 3초 대기 (필수)
TIME_LIMIT_SECONDS = 120.0  # 타임 트라이얼 제한 시간

# --- 전략 파라미터 (실제 테이블에서 튜닝할 것) ---
SEARCH_SPEED = 25
PUSH_SPEED = 55
TURN_SPEED = 30
PUSH_TIMEOUT_SECONDS = 2.0
REVERSE_SECONDS = 0.4
EDGE_REVERSE_SPEED = 35
EDGE_REVERSE_SECONDS = 1.0  # 후진 시간: 실제 후진 거리를 측정해 보정
RECOVER_TURN_SECONDS = 0.5
REPOSITION_SECONDS = 0.6
BOTTLE_DETECT_CM = 70.0     # 이 거리 안에 병이 있으면 돌진
ULTRASONIC_SAMPLES = 3
EDGE_POLL_SECONDS = 0.05


def parse_args():
    parser = argparse.ArgumentParser(description="BottleSumo 타임 트라이얼 자율 주행")
    state = parser.add_mutually_exclusive_group()
    state.add_argument("--active-low", dest="active_high", action="store_false",
                       help="엣지 센서가 감지 시 LOW 출력 (기본값)")
    state.add_argument("--active-high", dest="active_high", action="store_true",
                       help="엣지 센서가 감지 시 HIGH 출력")
    parser.set_defaults(active_high=False)
    parser.add_argument("--diagnose", action="store_true",
                        help="모터 없이 센서만 읽어서 출력")
    parser.add_argument("--max-runtime", type=float, default=115.0,
                        help="최대 실행 시간(초). 120초 제한 안에 끝나야 함 (기본: 115)")
    parser.add_argument("--search-speed", type=int, default=SEARCH_SPEED)
    parser.add_argument("--push-speed", type=int, default=PUSH_SPEED)
    parser.add_argument("--start-gpio", type=int, default=None,
                        help="물리 시작 버튼 GPIO 번호 (지정하면 버튼 입력 대기 후 3초 대기)")
    args = parser.parse_args()
    if not 0 < args.max_runtime <= TIME_LIMIT_SECONDS:
        parser.error("max-runtime은 0보다 크고 120 이하여야 합니다.")
    for name in ("search_speed", "push_speed"):
        if not 0 <= getattr(args, name) <= 255:
            parser.error(f"{name}는 0-255 사이여야 합니다.")
    return args


def read_edge(chip, active_high):
    """(왼쪽 감지, 오른쪽 감지) 반환."""
    left_value = lgpio.gpio_read(chip, X1_GPIO)
    right_value = lgpio.gpio_read(chip, X4_GPIO)
    if left_value not in (0, 1) or right_value not in (0, 1):
        raise RuntimeError(f"엣지 센서 값 오류: X1={left_value}, X4={right_value}")
    active_level = 1 if active_high else 0
    return left_value == active_level, right_value == active_level


def read_distance_cm(sensor):
    """초음파 거리(cm). gpiozero의 distance는 이미 미터 단위이므로 *100으로 cm 환산."""
    samples = []
    for _ in range(ULTRASONIC_SAMPLES):
        samples.append(sensor.distance * 100.0)
        time.sleep(0.02)
    return statistics.median(samples)


def wait_for_clear(car, chip, active_high, deadline):
    """모터 정지 상태에서 두 센서가 정상으로 돌아올 때까지 대기한다."""
    car.Car_Stop()
    if not any(read_edge(chip, active_high)):
        return time.monotonic() < deadline
    print("엣지 감지 지속: 모터 정지, 바닥 감지 복귀 대기", flush=True)
    while time.monotonic() < deadline:
        if not any(read_edge(chip, active_high)):
            print("바닥 감지 정상 복귀", flush=True)
            return True
        time.sleep(EDGE_POLL_SECONDS)
    return False


def avoid_edge(car, chip, active_high, deadline, detected=None):
    """엣지 감지 시 정지, 약 10cm 후진 후 중앙을 향해 회전."""
    left, right = detected if detected is not None else read_edge(chip, active_high)
    if not (left or right):
        return False
    print(f"엣지 감지 (X1={'EDGE' if left else 'clear'}, "
          f"X4={'EDGE' if right else 'clear'}): 약 10cm 후퇴 후 회전", flush=True)
    car.Car_Stop()
    time.sleep(0.2)  # 전진 정지 후 방향 전환 대기
    if time.monotonic() >= deadline:
        return True
    car.Car_Back(EDGE_REVERSE_SPEED, EDGE_REVERSE_SPEED)
    time.sleep(min(EDGE_REVERSE_SECONDS, max(0, deadline - time.monotonic())))
    car.Car_Stop()

    if not wait_for_clear(car, chip, active_high, deadline):
        return True

    if right and not left:
        car.Car_Left(TURN_SPEED, TURN_SPEED)
    else:
        car.Car_Right(TURN_SPEED, TURN_SPEED)
    time.sleep(RECOVER_TURN_SECONDS)
    car.Car_Stop()
    return True


def scan_for_bottle(sensor, chip, active_high, deadline):
    """전방 초음파로만 물통을 확인한다. 탐색 회전은 하지 않는다."""
    if time.monotonic() >= deadline or any(read_edge(chip, active_high)):
        return False
    distance = read_distance_cm(sensor)
    if time.monotonic() >= deadline or any(read_edge(chip, active_high)):
        return False
    return distance < BOTTLE_DETECT_CM


def push_bottle(car, chip, active_high, push_speed, deadline):
    """병을 밀다가 엣지를 감지하면 감지 상태를 반환하고, 그 외에는 None을 반환."""
    car.Car_Stop()
    started = time.monotonic()
    while time.monotonic() - started < PUSH_TIMEOUT_SECONDS:
        if time.monotonic() >= deadline:
            break
        left, right = read_edge(chip, active_high)
        if left or right:
            print("밀기 중 엣지 감지: 중단", flush=True)
            car.Car_Stop()
            return left, right
        car.Car_Run(push_speed, push_speed)
        time.sleep(EDGE_POLL_SECONDS)
    car.Car_Stop()
    return None


def recover_to_center(car, search_speed):
    """밀기 후 중앙 쪽으로 후퇴 (병 낙하 뒤 3초 생존 확보용)."""
    car.Car_Back(search_speed, search_speed)
    time.sleep(REVERSE_SECONDS)
    car.Car_Stop()
    car.Car_Right(TURN_SPEED, TURN_SPEED)
    time.sleep(RECOVER_TURN_SECONDS)
    car.Car_Stop()


def wait_for_start_button(chip, gpio):
    lgpio.gpio_claim_input(chip, gpio, lgpio.SET_PULL_UP)
    print(f"GPIO{gpio} 버튼 입력을 기다립니다...", flush=True)
    while lgpio.gpio_read(chip, gpio) != 0:
        time.sleep(0.05)
    print("버튼 입력 확인", flush=True)


def main():
    args = parse_args()
    car = None
    chip = None
    sensor = None
    try:
        car = YB_Pcb_Car()
        chip = lgpio.gpiochip_open(0)
        pull = lgpio.SET_PULL_DOWN if args.active_high else lgpio.SET_PULL_UP
        lgpio.gpio_claim_input(chip, X1_GPIO, pull)
        lgpio.gpio_claim_input(chip, X4_GPIO, pull)
        sensor = DistanceSensor(echo=ECHO_GPIO, trigger=TRIG_GPIO, max_distance=4)

        if args.diagnose:
            print("진단 모드: 모터를 구동하지 않습니다.", flush=True)
            deadline = time.monotonic() + args.max_runtime
            while time.monotonic() < deadline:
                left, right = read_edge(chip, args.active_high)
                dist = read_distance_cm(sensor)
                print(f"X1={'EDGE' if left else 'clear'} "
                      f"X4={'EDGE' if right else 'clear'} "
                      f"거리={dist:.1f}cm", flush=True)
                time.sleep(0.5)
            return

        if args.start_gpio is not None:
            wait_for_start_button(chip, args.start_gpio)

        # 룰 필수: 시작 후 3초 대기 (이 동안 모터 구동 금지)
        print(f"시작 {START_DELAY_SECONDS}초 대기 중...", flush=True)
        time.sleep(START_DELAY_SECONDS)

        deadline = time.monotonic() + args.max_runtime
        if not wait_for_clear(car, chip, args.active_high, deadline):
            return
        print(f"주행 시작 (최대 {args.max_runtime:.0f}초)", flush=True)
        while time.monotonic() < deadline:
            if avoid_edge(car, chip, args.active_high, deadline):
                continue
            if scan_for_bottle(sensor, chip, args.active_high, deadline):
                detected = push_bottle(car, chip, args.active_high,
                                       args.push_speed, deadline)
                if detected is not None:
                    avoid_edge(car, chip, args.active_high, deadline, detected)
                else:
                    recover_to_center(car, args.search_speed)
            else:
                # 물통이 없으면 짧게 직진하며 엣지를 계속 확인
                if time.monotonic() >= deadline:
                    break
                left, right = read_edge(chip, args.active_high)
                if left or right:
                    continue
                car.Car_Run(args.search_speed, args.search_speed)
                move_deadline = min(deadline, time.monotonic() + REPOSITION_SECONDS)
                try:
                    while time.monotonic() < move_deadline:
                        if any(read_edge(chip, args.active_high)):
                            break
                        time.sleep(EDGE_POLL_SECONDS)
                finally:
                    car.Car_Stop()
    finally:
        if car is not None:
            car.Car_Stop()
        if sensor is not None:
            sensor.close()
        if chip is not None:
            lgpio.gpiochip_close(chip)
        print("종료: 모터 정지, 센서 해제", flush=True)


if __name__ == "__main__":
    main()
