import threading
import time
import base64
import os

import cv2
from gpiozero import DistanceSensor
from flask import Flask, Response, jsonify, render_template_string
from groq import Groq
from picamera2 import Picamera2

from YB_Pcb_Car import YB_Pcb_Car


app = Flask(__name__)
car = YB_Pcb_Car()
car_lock = threading.Lock()
last_command_at = time.monotonic()
current_command = "stop"

COMMAND_TIMEOUT_SECONDS = 1.0
MOTOR_SPEED = 40
CAMERA_FPS = 30
VISION_INTERVAL_SECONDS = 2.0
VISION_MODEL = "qwen/qwen3.8-27b"
APPROACH_STOP_DISTANCE_CM = 20
APPROACH_MAX_SECONDS = 10
APPROACH_SPEED = 30

camera = Picamera2()
camera.configure(
    camera.create_video_configuration(
        main={"size": (640, 480), "format": "RGB888"},
        controls={"FrameRate": CAMERA_FPS},
    )
)
camera.start()
distance_sensor = DistanceSensor(echo=24, trigger=23, max_distance=4)
camera_lock = threading.Lock()
approach_lock = threading.Lock()
approach_active = False
latest_jpeg = None
latest_frame = None
latest_objects = "인식 대기 중"

PAGE = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>라즈베리파이 자동차 조종</title>
  <style>
    body { font-family: sans-serif; text-align: center; margin: 2rem auto; max-width: 42rem; }
    .camera { width: 100%; background: #111; }
    .objects { min-height: 1.5rem; margin: .7rem; font-weight: bold; }
    .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; margin-top: 2rem; }
    button { min-height: 4.5rem; font-size: 1.4rem; touch-action: none; user-select: none; }
    #stop { background: #d33; color: white; border: 0; }
    #approach { background: #1769aa; color: white; border: 0; grid-column: span 3; }
    #status { margin-top: 1.5rem; font-weight: bold; }
  </style>
</head>
<body>
  <h1>자동차 조종</h1>
  <img class="camera" src="/video_feed" alt="자동차 카메라">
  <div class="objects" id="objects">인식 대기 중</div>
  <p>방향 버튼을 누르면 이동하고, 정지 버튼으로 멈춥니다.</p>
  <div class="pad">
    <span></span>
    <button data-command="forward">전진</button>
    <span></span>
    <button data-command="left">좌회전</button>
    <button id="stop" data-command="stop">정지</button>
    <button data-command="right">우회전</button>
    <span></span>
    <button data-command="backward">후진</button>
    <span></span>
    <button id="approach">종이컵 접근</button>
  </div>
  <div id="status">정지</div>
  <script>
    const status = document.getElementById("status");
    const objects = document.getElementById("objects");
    let timer = null;

    async function send(command) {
      const response = await fetch("/api/move/" + command, { method: "POST" });
      const result = await response.json();
      status.textContent = result.command;
    }

    async function refreshObjects() {
      const response = await fetch("/api/objects");
      const result = await response.json();
      objects.textContent = "인식 결과: " + result.objects;
    }

    function start(command) {
      if (timer) clearInterval(timer);
      send(command);
      timer = setInterval(() => send(command), 300);
    }

    function stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      send("stop");
    }

    async function approach() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      const response = await fetch("/api/approach", { method: "POST" });
      const result = await response.json();
      status.textContent = result.status;
    }

    document.querySelectorAll("[data-command]").forEach((button) => {
      const command = button.dataset.command;
      if (command === "stop") {
        button.addEventListener("click", stop);
        return;
      }
      button.addEventListener("click", () => start(command));
    });
    document.getElementById("approach").addEventListener("click", approach);

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop();
    });
    setInterval(refreshObjects, 1000);
    refreshObjects();
  </script>
</body>
</html>
"""


def apply_command(command):
    global current_command, last_command_at, approach_active

    with car_lock:
        approach_active = False
        if command == "forward":
            car.Car_Run(MOTOR_SPEED, MOTOR_SPEED)
        elif command == "backward":
            car.Car_Back(MOTOR_SPEED, MOTOR_SPEED)
        elif command == "left":
            car.Car_Left(MOTOR_SPEED, MOTOR_SPEED)
        elif command == "right":
            car.Car_Right(MOTOR_SPEED, MOTOR_SPEED)
        elif command == "stop":
            car.Car_Stop()
        else:
            raise ValueError("알 수 없는 명령입니다.")

        current_command = command
        last_command_at = time.monotonic()


def stop_if_command_is_old():
    global current_command, approach_active

    while True:
        time.sleep(0.2)
        with car_lock:
            if (
                current_command != "stop"
                and time.monotonic() - last_command_at > COMMAND_TIMEOUT_SECONDS
            ):
                car.Car_Stop()
                current_command = "stop"
                approach_active = False


def approach_to_cup():
    global approach_active, current_command, last_command_at

    with approach_lock:
        with car_lock:
            approach_active = True
            started_at = time.monotonic()

        while time.monotonic() - started_at < APPROACH_MAX_SECONDS:
            with car_lock:
                if not approach_active:
                    return

                distance_cm = distance_sensor.distance * 100
                if distance_cm <= APPROACH_STOP_DISTANCE_CM:
                    car.Car_Stop()
                    current_command = "stop"
                    approach_active = False
                    return

                car.Car_Run(APPROACH_SPEED, APPROACH_SPEED)
                current_command = "approach"
                last_command_at = time.monotonic()

            time.sleep(0.1)

        with car_lock:
            car.Car_Stop()
            current_command = "stop"
            approach_active = False


def encode_for_vision(frame):
    success, encoded = cv2.imencode(".jpg", frame)
    if not success:
        raise RuntimeError("카메라 프레임을 JPEG로 변환하지 못했습니다.")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def recognize_objects(client, frame):
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "사진에서 보이는 주요 사물을 최대 5개까지 찾아라. "
                        "특히 종이컵이 있으면 반드시 '종이컵'이라고 표시하라. "
                        "사물 이름과 개수만 한국어로 짧게 답하라."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64," + encode_for_vision(frame)
                    },
                },
            ],
        }],
        temperature=0,
        max_completion_tokens=100,
    )
    return response.choices[0].message.content.strip()


def camera_worker():
    global latest_jpeg, latest_frame

    while True:
        frame = camera.capture_array()
        with camera_lock:
            latest_frame = frame.copy()

        if latest_objects:
            cv2.putText(
                frame,
                latest_objects[:70],
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        success, encoded = cv2.imencode(".jpg", frame)
        if success:
            with camera_lock:
                latest_jpeg = encoded.tobytes()


def vision_worker():
    global latest_objects

    if not os.environ.get("GROQ_API_KEY"):
        latest_objects = "GROQ_API_KEY가 설정되지 않음"
        return

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    while True:
        time.sleep(VISION_INTERVAL_SECONDS)
        with camera_lock:
            frame = None if latest_frame is None else latest_frame.copy()
        if frame is None:
            continue
        try:
            latest_objects = recognize_objects(client, frame)
        except Exception as error:
            latest_objects = f"분석 오류: {type(error).__name__}"


def mjpeg_stream():
    while True:
        with camera_lock:
            frame = latest_jpeg
        if frame is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame
                + b"\r\n"
            )
        time.sleep(1 / CAMERA_FPS)


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.post("/api/move/<command>")
def move(command):
    try:
        apply_command(command)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"command": command})


@app.post("/api/approach")
def approach():
    with approach_lock:
        if approach_active:
            return jsonify({"status": "이미 접근 중입니다."}), 409
        worker = threading.Thread(target=approach_to_cup, daemon=True)
        worker.start()
    return jsonify({
        "status": "접근 시작",
        "stop_distance_cm": APPROACH_STOP_DISTANCE_CM,
    })


@app.get("/video_feed")
def video_feed():
    return Response(
        mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/objects")
def objects():
    return jsonify({"objects": latest_objects})


def main():
    watchdog = threading.Thread(target=stop_if_command_is_old, daemon=True)
    camera_thread = threading.Thread(target=camera_worker, daemon=True)
    vision_thread = threading.Thread(target=vision_worker, daemon=True)
    watchdog.start()
    camera_thread.start()
    vision_thread.start()
    try:
        app.run(host="0.0.0.0", port=5000)
    finally:
        car.Car_Stop()
        camera.stop()
        distance_sensor.close()


if __name__ == "__main__":
    main()
