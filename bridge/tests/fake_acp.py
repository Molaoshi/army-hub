import json
import sys

sessions = 0
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {})
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {}}
    elif method == "session/new":
        sessions += 1
        result = {"sessionId": f"session-{sessions}"}
    elif method == "session/load":
        result = {"sessionId": params["sessionId"]}
    elif method == "session/prompt":
        session_id = params["sessionId"]
        text = params["prompt"][0]["text"]
        notification = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": f"ack:{text}"},
                },
            },
        }
        print(json.dumps(notification), flush=True)
        result = {"stopReason": "end_turn"}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)
