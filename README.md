# cloud_raspberry

## 객체 인식 로그 서버

Pi 3 B+에서 Flask와 `object_log_server.py`를 실행하면 객체 인식 결과를
`object_logs.jsonl`에 한 줄씩 저장하고 브라우저에서 확인할 수 있습니다.

```bash
pip install flask
python3 object_log_server.py
```

기본 포트는 `5001`이며 `http://<pi3-ip>:5001/`에서 최근 로그를 봅니다.
저장 경로는 `OBJECT_LOG_FILE=/path/to/object_logs.jsonl`로 변경할 수 있습니다.

카메라/제어 Pi에서 서버의 API 주소를 설정하면 인식 결과가 비동기로 전송됩니다.
설정하지 않으면 기존 동작을 유지합니다.

```bash
export OBJECT_LOG_URL=http://<pi3-tailscale-ip>:5001/api/log
export GROQ_API_KEY=...
python3 web_control.py
# 또는 python3 stream_vision_oled.py
```

로그 API는 `POST /api/log`에 `{"objects": "종이컵 1개"}` 또는 구조화된
`objects` 배열/객체를 받고, `GET /api/logs?limit=50`으로 최근 기록을 반환합니다.

## BottleSumo 엣지 회피 테스트

`edge_avoid_test.py`는 검증된 R-Avoid 센서만 사용합니다: X1은 BCM GPIO22
(왼쪽), X4는 BCM GPIO4 (오른쪽)입니다. 기본 입력 논리는 센서가 감지할 때
LOW인 active-low이며, 스크립트는 보드/외부 회로의 기존 pull 상태를 그대로
사용하지 않고 `lgpio`로 직접 설정합니다: `SET_PULL_UP`을 적용하고
`gpio_read(...) == 0`을 감지로 처리합니다. 센서가 HIGH를 출력하면
`--active-high`로 `SET_PULL_DOWN`과 `gpio_read(...) == 1`을 사용합니다.
X2/X3는 연결하거나 사용하지 않습니다. `lgpio`는 Raspberry Pi OS의
Python 패키지로 설치되어 있어야 합니다.

```bash
python3 edge_avoid_test.py --max-runtime 30
# active-high 센서:
python3 edge_avoid_test.py --active-high --max-runtime 30
```

감지하면 즉시 정지한 뒤 잠시 후진하고, X1이면 우회전/X4이면 좌회전하여
중앙을 향합니다. 기본 최대 실행 시간은 30초이며 Ctrl+C, 오류, 시간 만료
모두 모터를 정지시킵니다. GPIO 입력은 3.3V 논리와 공통 GND로 연결하세요.
