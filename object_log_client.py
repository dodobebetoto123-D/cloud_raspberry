"""Non-blocking client for the Raspberry Pi object log service."""

import json
import logging
import os
import threading
import urllib.error
import urllib.request


LOGGER = logging.getLogger(__name__)
OBJECT_LOG_URL = "OBJECT_LOG_URL"
REQUEST_TIMEOUT_SECONDS = 3


def log_objects(objects, timestamp=None):
    """Post an object recognition result in a daemon thread when configured."""
    url = os.environ.get(OBJECT_LOG_URL)
    if not url:
        return

    payload = {"objects": objects}
    if timestamp is not None:
        payload["timestamp"] = timestamp

    worker = threading.Thread(
        target=_send,
        args=(url, payload),
        name="object-log-post",
        daemon=True,
    )
    worker.start()


def _send(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status < 200 or response.status >= 300:
                LOGGER.warning("Object log server returned HTTP %s", response.status)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        LOGGER.warning("Object log delivery failed: %s", error)
