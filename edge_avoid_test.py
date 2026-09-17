"""BottleSumo edge-avoidance test using only verified R-Avoid sensors X1 and X4.

Verified wiring: X1 -> BCM GPIO22 (left sensor), X4 -> BCM GPIO4 (right sensor).
The default assumes an active-low sensor and enables the Pi's internal pull-up.
"""

import argparse
import time

import lgpio

from YB_Pcb_Car import YB_Pcb_Car


X1_GPIO = 22
X4_GPIO = 4


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the BottleSumo two-sensor edge-avoidance test."
    )
    state = parser.add_mutually_exclusive_group()
    state.add_argument(
        "--active-low",
        dest="active_high",
        action="store_false",
        help="Sensors assert low (default); use the internal pull-up.",
    )
    state.add_argument(
        "--active-high",
        dest="active_high",
        action="store_true",
        help="Sensors assert high; use the internal pull-down.",
    )
    parser.set_defaults(active_high=False)
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Read and print both sensors without driving the motors.",
    )
    parser.add_argument(
        "--max-runtime",
        type=float,
        default=30.0,
        help="Maximum test duration in seconds (default: 30).",
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=40,
        help="Forward/reverse motor speed, 0-255 (default: 40).",
    )
    parser.add_argument(
        "--reverse-time",
        type=float,
        default=0.25,
        help="Seconds to reverse after an edge detection (default: 0.25).",
    )
    parser.add_argument(
        "--turn-time",
        type=float,
        default=0.35,
        help="Seconds to turn toward the table center (default: 0.35).",
    )
    args = parser.parse_args()
    if args.max_runtime <= 0 or args.reverse_time < 0 or args.turn_time < 0:
        parser.error("runtime must be positive and action durations cannot be negative")
    if not 0 <= args.speed <= 255:
        parser.error("speed must be between 0 and 255")
    return args


def read_sensors(chip, active_high):
    left_value = lgpio.gpio_read(chip, X1_GPIO)
    right_value = lgpio.gpio_read(chip, X4_GPIO)
    if left_value not in (0, 1) or right_value not in (0, 1):
        raise RuntimeError(
            f"Unexpected sensor value: X1={left_value}, X4={right_value}"
        )
    active_level = 1 if active_high else 0
    return (
        left_value,
        right_value,
        left_value == active_level,
        right_value == active_level,
    )


def avoid_edge(
    car,
    chip,
    active_high,
    speed,
    reverse_time,
    turn_time,
):
    _, _, left_detected, right_detected = read_sensors(chip, active_high)
    if not (left_detected or right_detected):
        return False

    # Stop before changing direction so an edge detection cannot be carried
    # through into a reverse command.
    car.Car_Stop()
    print(
        "Edge detected by "
        + ("X1" if left_detected else "")
        + (" and " if left_detected and right_detected else "")
        + ("X4" if right_detected else "")
        + "; reversing.",
        flush=True,
    )
    car.Car_Back(speed, speed)
    time.sleep(reverse_time)
    car.Car_Stop()

    # Turn away from the triggering edge, toward the center of the table.
    if left_detected:
        car.Car_Right(speed, speed)
    else:
        car.Car_Left(speed, speed)
    time.sleep(turn_time)
    car.Car_Stop()
    return True


def claim_sensors(chip, active_high):
    pull = lgpio.SET_PULL_DOWN if active_high else lgpio.SET_PULL_UP
    lgpio.gpio_claim_input(chip, X1_GPIO, pull)
    lgpio.gpio_claim_input(chip, X4_GPIO, pull)


def main():
    args = parse_args()
    car = None
    chip = None

    try:
        car = YB_Pcb_Car()
        chip = lgpio.gpiochip_open(0)
        claim_sensors(chip, args.active_high)
        initial = read_sensors(chip, args.active_high)
        print(
            f"Initial sensors: X1={initial[0]} "
            f"({'EDGE' if initial[2] else 'clear'}), "
            f"X4={initial[1]} "
            f"({'EDGE' if initial[3] else 'clear'}).",
            flush=True,
        )
        if args.diagnose:
            print("Diagnostic mode: motors are disabled.", flush=True)
            deadline = time.monotonic() + args.max_runtime
            while time.monotonic() < deadline:
                values = read_sensors(chip, args.active_high)
                print(
                    f"X1={values[0]} ({'EDGE' if values[2] else 'clear'}), "
                    f"X4={values[1]} ({'EDGE' if values[3] else 'clear'})",
                    flush=True,
                )
                time.sleep(0.25)
            return
        if initial[2] or initial[3]:
            raise RuntimeError(
                "A sensor is already detecting an edge; refusing to drive."
            )
        print(
            "Running edge avoidance for "
            f"{args.max_runtime:.1f}s; X1=GPIO22, X4=GPIO4, "
            f"active={'high' if args.active_high else 'low'}. Ctrl+C to stop.",
            flush=True,
        )
        deadline = time.monotonic() + args.max_runtime
        while time.monotonic() < deadline:
            if not avoid_edge(
                car,
                chip,
                args.active_high,
                args.speed,
                args.reverse_time,
                args.turn_time,
            ):
                car.Car_Run(args.speed, args.speed)
            time.sleep(0.01)
    finally:
        if car is not None:
            car.Car_Stop()
        if chip is not None:
            lgpio.gpiochip_close(chip)
        print("Car stopped; edge sensors released.", flush=True)


if __name__ == "__main__":
    main()
