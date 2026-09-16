"""Local JSONL object recognition log server for Raspberry Pi 3 B+."""

import argparse
import json
import logging
import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, request


app = Flask(__name__)
LOGGER = logging.getLogger(__name__)
LOG_PATH = os.environ.get("OBJECT_LOG_FILE", "object_logs.jsonl")
MAX_RETURNED_RECORDS = 100
_file_lock = threading.Lock()


PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>객체 인식 로그</title>
  <style>
    body { font-family: sans-serif; margin: 2rem auto; max-width: 48rem; padding: 0 1rem; }
    li { border-bottom: 1px solid #ddd; padding: .7rem 0; white-space: pre-wrap; }
    time { color: #666; margin-right: 1rem; }
  </style>
</head>
<body>
  <h1>객체 인식 로그</h1>
  <p>최근 인식 결과가 5초마다 갱신됩니다.</p>
  <ul id="logs"><li>불러오는 중...</li></ul>
  <script>
    const list = document.getElementById("logs");
    async function refresh() {
      try {
        const response = await fetch("/api/logs?limit=50");
        if (!response.ok) throw new Error("HTTP " + response.status);
        const entries = await response.json();
        list.replaceChildren(...entries.map((entry) => {
          const item = document.createElement("li");
          const time = document.createElement("time");
          time.textContent = entry.timestamp || "시간 없음";
          item.append(time, document.createTextNode(JSON.stringify(entry.objects)));
          return item;
        }));
        if (!entries.length) list.textContent = "기록이 없습니다.";
      } catch (error) {
        list.textContent = "로그를 불러오지 못했습니다.";
      }
    }
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_limit():
    raw_limit = request.args.get("limit", str(MAX_RETURNED_RECORDS))
    try:
        limit = int(raw_limit)
    except ValueError as error:
        raise ValueError("limit은 정수여야 합니다.") from error
    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")
    return min(limit, MAX_RETURNED_RECORDS)


def _validate_payload(payload):
    if not isinstance(payload, dict) or "objects" not in payload:
        raise ValueError("JSON 객체와 objects 필드가 필요합니다.")
    objects = payload["objects"]
    if not isinstance(objects, (str, list, dict)):
        raise ValueError("objects는 문자열, 배열 또는 객체여야 합니다.")
    timestamp = payload.get("timestamp", _now())
    if not isinstance(timestamp, str):
        raise ValueError("timestamp는 문자열이어야 합니다.")
    return {"timestamp": timestamp, "objects": objects}


def _read_recent(limit):
    if not os.path.exists(LOG_PATH):
        return []
    entries = []
    with _file_lock:
        with open(LOG_PATH, "r", encoding="utf-8") as log_file:
            for line in log_file:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    LOGGER.warning("Skipping malformed JSONL record")
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    return entries[-limit:][::-1]


@app.post("/api/log")
def create_log():
    if not request.is_json:
        return jsonify({"error": "Content-Type: application/json이 필요합니다."}), 400
    try:
        entry = _validate_payload(request.get_json(silent=False))
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _file_lock:
            with open(LOG_PATH, "a", encoding="utf-8") as log_file:
                log_file.write(line)
                log_file.flush()
                os.fsync(log_file.fileno())
    except (ValueError, json.JSONDecodeError) as error:
        return jsonify({"error": str(error)}), 400
    except OSError:
        LOGGER.exception("Unable to persist object log")
        return jsonify({"error": "로그를 저장하지 못했습니다."}), 500
    return jsonify(entry), 201


@app.get("/api/logs")
def get_logs():
    try:
        limit = _parse_limit()
        return jsonify(_read_recent(limit))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except OSError:
        LOGGER.exception("Unable to read object logs")
        return jsonify({"error": "로그를 읽지 못했습니다."}), 500


@app.get("/")
def index():
    return PAGE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
