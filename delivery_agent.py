"""
Delivery Agent: a tiny A2A server (Python standard library only)
=================================================================

It does two things, like every A2A agent:

  1. Publishes an Agent Card at  GET /.well-known/agent-card.json
     (who it is, what it can do, where to send messages)
  2. Accepts JSON-RPC 2.0 requests at  POST /
     - SendMessage : start or continue a task
     - GetTask     : check a task's current state

Skill: estimate delivery days for an Indian pincode.
If the pincode is missing, the task goes to TASK_STATE_INPUT_REQUIRED and waits for more input.

This is a learning sample written by hand so you can SEE the JSON.
It follows the A2A v1.0 JSON-RPC format. For real projects, use the official A2A SDK.
"""

import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 8765
BASE_URL = f"http://{HOST}:{PORT}"
A2A_VERSION = "1.0"

AGENT_CARD = {
    "name": "Delivery Agent",
    "description": "Estimates delivery days for an Indian pincode.",
    "version": "1.0.0",
    # Where to reach the agent, which binding and which protocol version
    "supportedInterfaces": [
        {"url": BASE_URL, "protocolBinding": "JSONRPC", "protocolVersion": A2A_VERSION}
    ],
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "estimate_delivery",
            "name": "Estimate delivery",
            "description": "Give a 6 digit pincode and get the expected delivery days.",
            "tags": ["delivery", "pincode"],
            "examples": ["How many days to deliver to 500081?"],
        }
    ],
}

# Made-up rule: the first digit of the pincode decides the region
REGION_DAYS = {"5": ("South (Telangana, Andhra Pradesh, Karnataka)", 2), "6": ("South (Tamil Nadu, Kerala)", 3)}
DEFAULT_DAYS = ("Other regions", 5)

TASKS: dict[str, dict] = {}   # in-memory task store (lost when the server stops)

# JSON-RPC error codes (the -32001 and -32009 codes are defined by A2A)
PARSE_ERROR, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32601, -32602
TASK_NOT_FOUND, VERSION_NOT_SUPPORTED = -32001, -32009


def text_of(message: dict) -> str:
    return " ".join(p["text"] for p in message.get("parts", []) if "text" in p)


def agent_message(text: str, task_id: str, context_id: str) -> dict:
    return {"messageId": str(uuid.uuid4()), "contextId": context_id, "taskId": task_id,
            "role": "ROLE_AGENT", "parts": [{"text": text}]}


def handle_send_message(params: dict) -> dict:
    message = params["message"]
    task_id = message.get("taskId") or str(uuid.uuid4())      # continue a task, or start a new one
    context_id = message.get("contextId") or str(uuid.uuid4())
    task = TASKS.setdefault(task_id, {"id": task_id, "contextId": context_id, "history": []})
    task["history"].append({**message, "taskId": task_id, "contextId": context_id})

    match = re.search(r"\b(\d{6})\b", text_of(message))
    if not match:
        reply = agent_message("Please share a 6 digit pincode.", task_id, context_id)
        task["status"] = {"state": "TASK_STATE_INPUT_REQUIRED", "message": reply}
    else:
        pincode = match.group(1)
        region, days = REGION_DAYS.get(pincode[0], DEFAULT_DAYS)
        reply = agent_message(f"Delivery to {pincode} takes about {days} days.", task_id, context_id)
        task["status"] = {"state": "TASK_STATE_COMPLETED", "message": reply}
        task["artifacts"] = [{
            "artifactId": str(uuid.uuid4()),
            "name": "delivery_estimate",
            "parts": [{"data": {"pincode": pincode, "region": region, "days": days}}],
        }]
    task["history"].append(reply)
    return {"task": task}          # SendMessage returns either {"task": ...} or {"message": ...}


def error(rpc_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def handle_rpc(request: dict, version: str) -> dict:
    rpc_id, method, params = request.get("id"), request.get("method"), request.get("params", {})
    if version != A2A_VERSION:
        return error(rpc_id, VERSION_NOT_SUPPORTED, f"A2A version '{version}' is not supported. Expected '{A2A_VERSION}'.")
    try:
        if method == "SendMessage":
            return {"jsonrpc": "2.0", "id": rpc_id, "result": handle_send_message(params)}
        if method == "GetTask":
            task = TASKS.get(params.get("id"))
            if task is None:
                return error(rpc_id, TASK_NOT_FOUND, "Task not found")
            return {"jsonrpc": "2.0", "id": rpc_id, "result": task}
        return error(rpc_id, METHOD_NOT_FOUND, "Method not found")
    except (KeyError, TypeError) as exc:
        return error(rpc_id, INVALID_PARAMS, f"Invalid params: {exc}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/.well-known/agent-card.json":
            self._send(200, AGENT_CARD)
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._send(200, error(None, PARSE_ERROR, "Parse error"))
            return
        # The client says which protocol version it speaks. No header means the old 0.3.
        version = self.headers.get("A2A-Version", "0.3")
        self._send(200, handle_rpc(request, version))

    def log_message(self, *args):   # keep the console quiet
        pass


def make_server() -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, PORT), Handler)


if __name__ == "__main__":
    print(f"Delivery Agent running at {BASE_URL}  (Agent Card: {BASE_URL}/.well-known/agent-card.json)")
    make_server().serve_forever()
