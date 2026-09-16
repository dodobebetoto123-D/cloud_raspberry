import base64
import json
import os
import time

from groq import Groq
from picamera2 import Picamera2
from PIL import ImageFont
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306

from object_log_client import log_objects


MODEL = "qwen/qwen3.6-27b"
INTERVAL_SECONDS = 5
IMAGE_PATH = "/tmp/groq_camera.jpg"


def encode_image(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("ascii")


def extract_json(text):
    text = text.strip()

    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON을 찾지 못했습니다.")

    return json.loads(text[start:end + 1])


def analyze_image(client):
    image_data = encode_image(IMAGE_PATH)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "사진 속 주요 물체를 최대 4개까지 찾아라. "
                            "물체 이름과 개수를 한국어 JSON으로만 출력하라. "
                            "생각 과정과 설명은 출력하지 마라. "
                            '형식: {"objects":[{"name":"사람","count":1}]}'
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64," + image_data
                        },
                    },
                ],
            }
        ],
        temperature=0,
        max_completion_tokens=400,
    )

    return extract_json(response.choices[0].message.content)


def display_result(device, font, result):
    objects = result.get("objects", [])
    labels = []

    for item in objects[:4]:
        name = str(item.get("name", "알 수 없음"))
        count = item.get("count", 0)
        labels.append(f"{name} {count}")

    line1 = " ".join(labels[:2])[:20]
    line2 = " ".join(labels[2:4])[:20]

    if not line1:
        line1 = "인식 결과"
    if not line2:
        line2 = "없음"

    with canvas(device) as draw:
        draw.text((0, 0), line1, font=font, fill=255)
        draw.text((0, 16), line2, font=font, fill=255)


def main():
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY가 설정되지 않았습니다.")

    serial = i2c(port=1, address=0x3C)
    device = ssd1306(serial, width=128, height=32)

    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    font = ImageFont.truetype(font_path, 10)

    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    camera = Picamera2()
    camera.configure(
        camera.create_still_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
    )
    camera.start()
    time.sleep(2)

    print("Groq 객체 인식을 시작합니다. 종료: Ctrl+C", flush=True)

    try:
        while True:
            started_at = time.monotonic()

            try:
                camera.capture_file(IMAGE_PATH)
                result = analyze_image(client)

                print(
                    json.dumps(result, ensure_ascii=False),
                    flush=True,
                )
                log_objects(result)

                display_result(device, font, result)

            except Exception as error:
                print(
                    f"분석 오류: {type(error).__name__}: {error}",
                    flush=True,
                )

                with canvas(device) as draw:
                    draw.text((0, 0), "분석 오류", font=font, fill=255)
                    draw.text((0, 16), "다시 시도 중", font=font, fill=255)

            elapsed = time.monotonic() - started_at
            time.sleep(max(0, INTERVAL_SECONDS - elapsed))

    except KeyboardInterrupt:
        print("\n종료합니다.", flush=True)

    finally:
        camera.stop()
        device.clear()


if __name__ == "__main__":
    main()
