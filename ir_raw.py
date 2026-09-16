import time
import lgpio

GPIO = 16
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(chip, GPIO, lgpio.SET_PULL_UP)

last_time = None
count = 0


def callback(chip, gpio, level, tick):
    global last_time, count

    now = time.monotonic_ns() // 1_000_000
    if last_time is not None:
        duration = now - last_time
        if duration > 2:
            print(
                f"edge={count:03d} level={level} "
                f"duration={duration}ms",
                flush=True,
            )
            count += 1

    last_time = now


handle = lgpio.callback(
    chip,
    GPIO,
    lgpio.BOTH_EDGES,
    callback,
)

print("GPIO16 IR 신호 대기 중입니다. 리모컨 버튼을 눌러 보세요.")
print("종료: Ctrl+C")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    handle.cancel()
    lgpio.gpiochip_close(chip)
