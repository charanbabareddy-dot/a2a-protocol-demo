"""
Delivery Agent: a tiny A2A server (Python standard library only)
=================================================================

It does two things, like every A2A agent:

  1. Publishes an Agent Card at  GET /.well-known/agent-card.json
     (who it is, what it can do, where to send messages)
  2. Accepts JSON-RPC 2.0 requests at  POST /
     - message/send : start or continue a task
     - tasks/get    : check a task's current state

Skill: estimate delivery days for an Indian pincode.
If the pincode is missing, the task goes to "input-required" and waits for more input.

This is a learning sample that follows the A2A v0.3 message shape.
For real projects, use the official A2A SDK.
"""

import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 8765
BASE_URL = f"http://{HOST}:{PORT}"

AGENT_CARD = {
    "name": "Delivery Agent",
    "description": "Estimates delivery days for an Indian pincode.",
    "url": f"{BASE_URL}/",
    "version": "1.0.0",
    "protocolVersion": "0.3.0",
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "estimate_delivery",
            "name": "Estimate delivery",
            "description": "Give a 6 digit pincode and get the expected delivery days.",
            "examples": ["How many days to deliver to 500081?"],
        }
    ],
}

# Made-up rule: the first digit of the pincode decides the region
REGION_DAYS = {"5": ("South (Telangana, Andhra Pradesh, Karnataka)", 2), "6": ("South (Tamil Nadu, Kerala)", 3)}
DEFAULT_DAYS = ("Other regions", 5)

TASKS: dict[str, dict] = {}   # in-memory task store (lost when the server stops)


def text_of(message: dict) -> str:
    return " ".join(p.get("text", "") for p in message.get("parts", []) if p.get("kind") == "text")


def agent_message(text: str, task_id: str, context_id: str) -> dict:
    return {"kind": "message", "role": "agent", "messageId": str(uuid.uuid4()),
            "taskId": task_id, "contextId": context_id, "parts": [{"kind": "text", "text": text}]}


def handle_message_send(params: dict) -> dict:
    message = params["message"]
    task_id = message.get("taskId") or str(uuid.uuid4())      # continue a task, or start a new one
    context_id = message.get("contextId") or str(uuid.uuid4())
    task = TASKS.setdefault(task_id, {"kind": "task", "id": task_id, "contextId": context_id,
                                      "history": [], "artifacts": []})
    task["history"].append(message)

    match = re.search(r"\b(\d{6})\b", text_of(message))
    if not match:
        reply = agent_message("Please share a 6 digit pincode.", task_id, context_id)
        task["status"] = {"state": "input-required", "message": reply}
    else:
        pincode = match.group(1)
        region, days = REGION_DAYS.get(pincode[0], DEFAULT_DAYS)
        reply = agent_message(f"Delivery to {pincode} takes about {days} days.", task_id, context_id)
        task["status"] = {"state": "completed", "message": reply}
        task["artifacts"] = [{
            "artifactId": str(uuid.uuid4()),
            "name": "delivery_estimate",
            "parts": [{"kind": "data", "data": {"pincode": pincode, "region": region, "days": days}}],
        }]
    task["history"].append(reply)
    return task


def handle_rpc(request: dict) -> dict:
    rpc_id, method, params = request.get("id"), request.get("method"), request.get("params", {})
    try:
        if method == "message/send":
            return {"jsonrpc": "2.0", "id": rpc_id, "result": handle_message_send(params)}
        if method == "tasks/get":
            task = TASKS.get(params.get("id"))
            if task is None:
                return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32001, "message": "Task not found"}}
            return {"jsonrpc": "2.0", "id": rpc_id, "result": task}
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except (KeyError, TypeError) as exc:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": f"Invalid params: {exc}"}}


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
            self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        self._send(200, handle_rpc(request))

    def log_message(self, *args):   # keep the console quiet
        pass


def make_server() -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, PORT), Handler)


if __name__ == "__main__":
    print(f"Delivery Agent running at {BASE_URL}  (Agent Card: {BASE_URL}/.well-known/agent-card.json)")
    make_server().serve_forever()
