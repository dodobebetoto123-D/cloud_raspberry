import json
import time

import lgpio
from PIL import ImageFont
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306


IR_GPIO = 16
OLED_ADDRESS = 0x3C

font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
font = ImageFont.truetype(font_path, 10)

serial = i2c(port=1, address=OLED_ADDRESS)
oled = ssd1306(serial, width=128, height=32)

chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(chip, IR_GPIO, lgpio.SET_PULL_UP)

last_edge = None
edges = []


def edge_callback(chip, gpio, level, timestamp):
    global last_edge, edges

    now = time.monotonic_ns() / 1_000_000
    if last_edge is not None:
        edges.append(now - last_edge)
    last_edge = now


callback = lgpio.callback(
    chip,
    IR_GPIO,
    lgpio.BOTH_EDGES,
    edge_callback,
)


def decode_nec(pulses):
    # NEC 신호: 약 9ms + 4.5ms 시작 펄스
    if len(pulses) < 65:
        return None

    start_index = None

    for index in range(len(pulses) - 1):
        if 7_000 < pulses[index] < 11_000:
            if 3_000 < pulses[index + 1] < 6_000:
                start_index = index + 2
                break

    if start_index is None:
        return None

    bits = []

    for index in range(start_index, min(start_index + 64, len(pulses) - 1), 2):
        high_time = pulses[index + 1]

        if 300 < high_time < 800:
            bits.append(0)
        elif 1_200 < high_time < 2_000:
            bits.append(1)
        else:
            break

    if len(bits) != 32:
        return None

    value = 0
    for index, bit in enumerate(bits):
        value |= bit << index

    address = value & 0xFF
    address_inverse = (value >> 8) & 0xFF
    command = (value >> 16) & 0xFF
    command_inverse = (value >> 24) & 0xFF

    if (command ^ command_inverse) != 0xFF:
        return None

    return {
        "address": address,
        "command": command,
    }


try:
    with canvas(oled) as draw:
        draw.text((0, 0), "IR 대기 중", font=font, fill=255)
        draw.text((0, 16), "리모컨을 누르세요", font=font, fill=255)

    print("IR 수신 대기 중입니다. 리모컨의 1번을 누르세요.")

    while True:
        time.sleep(0.05)

        if not edges:
            continue

        if last_edge is not None:
            idle_time = time.monotonic_ns() / 1_000_000 - last_edge

            if idle_time < 30:
                continue

        pulses = edges[:]
        edges.clear()

        result = decode_nec(pulses)

        if result is None:
            continue

        command = result["command"]

        print(
            json.dumps(result, ensure_ascii=False),
            flush=True,
        )

        with canvas(oled) as draw:
            draw.text((0, 0), "IR 버튼 수신", font=font, fill=255)
            draw.text(
                (0, 16),
                f"코드: 0x{command:02X}",
                font=font,
                fill=255,
            )

except KeyboardInterrupt:
    print("\n종료합니다.")

finally:
    callback.cancel()
    lgpio.gpiochip_close(chip)
    oled.clear()
