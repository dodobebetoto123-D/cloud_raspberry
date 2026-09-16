import threading
import time

from flask import Flask, jsonify, render_template_string

from YB_Pcb_Car import YB_Pcb_Car


app = Flask(__name__)
car = YB_Pcb_Car()
car_lock = threading.Lock()
last_command_at = time.monotonic()
current_command = "stop"

COMMAND_TIMEOUT_SECONDS = 1.0
MOTOR_SPEED = 40

PAGE = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>라즈베리파이 자동차 조종</title>
  <style>
    body { font-family: sans-serif; text-align: center; margin: 2rem auto; max-width: 28rem; }
    .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; margin-top: 2rem; }
    button { min-height: 4.5rem; font-size: 1.4rem; touch-action: none; user-select: none; }
    #stop { background: #d33; color: white; border: 0; }
    #status { margin-top: 1.5rem; font-weight: bold; }
  </style>
</head>
<body>
  <h1>자동차 조종</h1>
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
  </div>
  <div id="status">정지</div>
  <script>
    const status = document.getElementById("status");
    let timer = null;

    async function send(command) {
      const response = await fetch("/api/move/" + command, { method: "POST" });
      const result = await response.json();
      status.textContent = result.command;
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

    document.querySelectorAll("[data-command]").forEach((button) => {
      const command = button.dataset.command;
      if (command === "stop") {
        button.addEventListener("click", stop);
        return;
      }
      button.addEventListener("click", () => start(command));
    });

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop();
    });
  </script>
</body>
</html>
"""


def apply_command(command):
    global current_command, last_command_at

    with car_lock:
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
    global current_command

    while True:
        time.sleep(0.2)
        with car_lock:
            if (
                current_command != "stop"
                and time.monotonic() - last_command_at > COMMAND_TIMEOUT_SECONDS
            ):
                car.Car_Stop()
                current_command = "stop"


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


def main():
    watchdog = threading.Thread(target=stop_if_command_is_old, daemon=True)
    watchdog.start()
    try:
        app.run(host="0.0.0.0", port=5000)
    finally:
        car.Car_Stop()


if __name__ == "__main__":
    main()
