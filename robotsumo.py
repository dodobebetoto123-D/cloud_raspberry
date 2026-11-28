"""1대1 로봇 스모 전용 자율주행. bottlesumo.py의 하드웨어/엣지 회피 함수를 공유한다."""

import argparse
import time

import lgpio
from gpiozero import DistanceSensor

from YB_Pcb_Car import YB_Pcb_Car
from bottlesumo import (
    X1_GPIO, X4_GPIO, ECHO_GPIO, TRIG_GPIO,
    START_DELAY_SECONDS, TIME_LIMIT_SECONDS,
    SEARCH_SPEED, PUSH_SPEED, TURN_SPEED, EDGE_POLL_SECONDS,
    read_edge, read_distance_cm, wait_for_clear, avoid_edge,
    wait_for_start_button,
)

OPPONENT_DETECT_CM = 70.0
SCAN_SECONDS = 3.6  # 탐색 회전 시간: 실제 회전 각도에 맞춰 보정
FORWARD_SECONDS = 0.6


def parse_args():
    parser = argparse.ArgumentParser(description="1대1 로봇 스모 자율주행")
    state = parser.add_mutually_exclusive_group()
    state.add_argument("--active-low", dest="active_high", action="store_false")
    state.add_argument("--active-high", dest="active_high", action="store_true")
    parser.set_defaults(active_high=False)
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--max-runtime", type=float, default=115.0)
    parser.add_argument("--search-speed", type=int, default=SEARCH_SPEED)
    parser.add_argument("--push-speed", type=int, default=PUSH_SPEED)
    parser.add_argument("--scan-turn-time", type=float, default=SCAN_SECONDS)
    parser.add_argument("--start-gpio", type=int, default=None)
    args = parser.parse_args()
    if not 0 < args.max_runtime <= TIME_LIMIT_SECONDS:
        parser.error("max-runtime은 0보다 크고 120 이하여야 합니다.")
    if not 0 < args.scan_turn_time <= TIME_LIMIT_SECONDS:
        parser.error("scan-turn-time은 0보다 크고 120 이하여야 합니다.")
    if not all(0 <= speed <= 255 for speed in (args.search_speed, args.push_speed)):
        parser.error("모터 출력은 0~255 사이여야 합니다.")
    return args


def search_opponent(car, sensor, chip, active_high, deadline, scan_seconds):
    """정면 확인 후 제자리 회전 탐색. 엣지가 감지되면 즉시 정지한다."""
    scan_deadline = min(deadline, time.monotonic() + scan_seconds)
    try:
        while time.monotonic() < scan_deadline:
            if any(read_edge(chip, active_high)):
                return False
            distance = read_distance_cm(sensor)
            if time.monotonic() >= scan_deadline or any(read_edge(chip, active_high)):
                return False
            if distance < OPPONENT_DETECT_CM:
                print(f"상대 감지: {distance:.1f}cm", flush=True)
                return True
            car.Car_Right(TURN_SPEED, TURN_SPEED)
        return False
    finally:
        car.Car_Stop()


def push_opponent(car, chip, active_high, push_speed, deadline):
    """상대를 놓쳐도 전진 유지. 엣지 또는 전체 시간 제한에서 정지한다."""
    try:
        while time.monotonic() < deadline:
            detected = read_edge(chip, active_high)
            if any(detected):
                return detected
            car.Car_Run(push_speed, push_speed)
            time.sleep(min(EDGE_POLL_SECONDS, max(0, deadline - time.monotonic())))
        return None
    finally:
        car.Car_Stop()


def advance(car, chip, active_high, speed, deadline):
    """탐색 위치를 조금 옮긴다."""
    move_deadline = min(deadline, time.monotonic() + FORWARD_SECONDS)
    try:
        while time.monotonic() < move_deadline:
            if any(read_edge(chip, active_high)):
                return
            car.Car_Run(speed, speed)
            time.sleep(min(EDGE_POLL_SECONDS, max(0, move_deadline - time.monotonic())))
    finally:
        car.Car_Stop()


def main():
    args = parse_args()
    car = chip = sensor = None
    try:
        car = YB_Pcb_Car()
        car.Car_Stop()
        chip = lgpio.gpiochip_open(0)
        pull = lgpio.SET_PULL_DOWN if args.active_high else lgpio.SET_PULL_UP
        lgpio.gpio_claim_input(chip, X1_GPIO, pull)
        lgpio.gpio_claim_input(chip, X4_GPIO, pull)
        sensor = DistanceSensor(echo=ECHO_GPIO, trigger=TRIG_GPIO, max_distance=4)

        if args.diagnose:
            deadline = time.monotonic() + args.max_runtime
            while time.monotonic() < deadline:
                left, right = read_edge(chip, args.active_high)
                distance = read_distance_cm(sensor)
                print(f"X1={'EDGE' if left else 'clear'} "
                      f"X4={'EDGE' if right else 'clear'} 거리={distance:.1f}cm", flush=True)
                time.sleep(0.5)
            return

        if args.start_gpio is not None:
            wait_for_start_button(chip, args.start_gpio)
        print("RobotSumo 시작 전 3초 대기", flush=True)
        time.sleep(START_DELAY_SECONDS)
        deadline = time.monotonic() + args.max_runtime
        if not wait_for_clear(car, chip, args.active_high, deadline):
            return

        while time.monotonic() < deadline:
            if avoid_edge(car, chip, args.active_high, deadline):
                continue
            if search_opponent(car, sensor, chip, args.active_high,
                               deadline, args.scan_turn_time):
                detected = push_opponent(car, chip, args.active_high, args.push_speed, deadline)
                if detected is not None:
                    avoid_edge(car, chip, args.active_high, deadline, detected)
            else:
                advance(car, chip, args.active_high, args.search_speed, deadline)
    finally:
        try:
            if car is not None:
                car.Car_Stop()
        finally:
            try:
                if sensor is not None:
                    sensor.close()
            finally:
                if chip is not None:
                    lgpio.gpiochip_close(chip)
        print("RobotSumo 종료: 모터 정지", flush=True)


if __name__ == "__main__":
    main()
