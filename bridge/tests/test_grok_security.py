from __future__ import annotations

import base64
import hashlib
import hmac

from army_grok.security import signed_webhook_headers


def test_standard_webhook_signature() -> None:
    key = b"test-key"
    secret = "whsec_" + base64.b64encode(key).decode()
    body = b'{"event":"matrix.message"}'
    headers = signed_webhook_headers(body, secret, webhook_id="msg_test", timestamp=1234567890)
    expected = base64.b64encode(hmac.new(key, b"msg_test.1234567890." + body, hashlib.sha256).digest()).decode()
    assert headers == {
        "content-type": "application/json",
        "webhook-id": "msg_test",
        "webhook-timestamp": "1234567890",
        "webhook-signature": f"v1,{expected}",
    }
