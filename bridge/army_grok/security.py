from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid


def signed_webhook_headers(body: bytes, secret: str, *, webhook_id: str | None = None, timestamp: int | None = None) -> dict[str, str]:
    delivery_id = webhook_id or f"msg_{uuid.uuid4().hex}"
    unix_time = str(int(time.time()) if timestamp is None else timestamp)
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed_content = f"{delivery_id}.{unix_time}.".encode() + body
    signature = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()
    return {
        "content-type": "application/json",
        "webhook-id": delivery_id,
        "webhook-timestamp": unix_time,
        "webhook-signature": f"v1,{signature}",
    }
