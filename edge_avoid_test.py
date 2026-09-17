"""BottleSumo edge-avoidance test using only verified R-Avoid sensors X1 and X4.

Verified wiring: X1 -> BCM GPIO22 (left sensor), X4 -> BCM GPIO4 (right sensor).
The default assumes an active-low sensor. The board's existing pull configuration
is preserved; this script does not request an active_state.
"""

import argparse
import time

from gpiozero import DigitalInputDevice

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


def avoid_edge(
    car,
    left_edge,
    right_edge,
    active_high,
    speed,
    reverse_time,
    turn_time,
):
    active_level = 1 if active_high else 0
    left_detected = left_edge.value == active_level
    right_detected = right_edge.value == active_level
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


def make_sensor(gpio):
    try:
        # None preserves a pull configured by the board or external wiring.
        return DigitalInputDevice(gpio, pull_up=None)
    except TypeError:
        # Older gpiozero releases may not accept pull_up=None.
        return DigitalInputDevice(gpio)


def main():
    args = parse_args()
    car = YB_Pcb_Car()
    left_edge = None
    right_edge = None

    try:
        # Leave pull configuration to the board/external wiring. In particular,
        # do not combine an existing pull with gpiozero's active_state setting.
        left_edge = make_sensor(X1_GPIO)
        right_edge = make_sensor(X4_GPIO)
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
                left_edge,
                right_edge,
                args.active_high,
                args.speed,
                args.reverse_time,
                args.turn_time,
            ):
                car.Car_Run(args.speed, args.speed)
            time.sleep(0.01)
    finally:
        car.Car_Stop()
        if left_edge is not None:
            left_edge.close()
        if right_edge is not None:
            right_edge.close()
        print("Car stopped; edge sensors released.", flush=True)


if __name__ == "__main__":
    main()
