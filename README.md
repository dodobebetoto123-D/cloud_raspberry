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
