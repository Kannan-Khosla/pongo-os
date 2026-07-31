from __future__ import annotations

import json
import logging
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def send_operations_alert(settings, event: str, message: str, **details) -> bool:
    url = str(getattr(settings, "operations_alert_webhook_url", "") or "").strip()
    if not url:
        return False
    payload = json.dumps({"event": event, "message": message[:1000], "details": details}).encode()
    try:
        with urlopen(Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST"), timeout=5) as response:
            return 200 <= response.status < 300
    except Exception:
        logger.exception("Operations alert delivery failed for event %s.", event)
        return False
