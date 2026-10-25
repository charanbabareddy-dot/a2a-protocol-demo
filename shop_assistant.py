"""
Shop Assistant: an A2A client agent (Python standard library only)
==================================================================

It talks to the Delivery Agent the A2A way:

  1. Discover: read the Agent Card to learn the agent's name, skills and URL
  2. Send:     call message/send with a question
  3. Continue: if the task is "input-required", send more input on the SAME task
  4. Check:    call tasks/get to see the task's final state
"""

import json
import urllib.request
import uuid

BASE_URL = "http://127.0.0.1:8765"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def rpc(url: str, method: str, params: dict) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        reply = json.loads(resp.read())
    if "error" in reply:
        raise RuntimeError(f"{method} failed: {reply['error']['message']}")
    return reply["result"]


def user_message(text: str, task_id: str | None = None, context_id: str | None = None) -> dict:
    msg = {"kind": "message", "role": "user", "messageId": str(uuid.uuid4()),
           "parts": [{"kind": "text", "text": text}]}
    if task_id:
        msg["taskId"] = task_id        # continue the same task
    if context_id:
        msg["contextId"] = context_id  # same conversation
    return msg


def reply_text(task: dict) -> str:
    return " ".join(p["text"] for p in task["status"]["message"]["parts"] if p["kind"] == "text")


def main() -> None:
    # 1. Discover
    card = get_json(f"{BASE_URL}/.well-known/agent-card.json")
    print(f"1. Found agent: {card['name']}  |  skills: {[s['name'] for s in card['skills']]}")
    endpoint = card["url"]

    # 2. Send a question without a pincode
    task = rpc(endpoint, "message/send", {"message": user_message("When will my books arrive?")})
    print(f"2. Task {task['id'][:8]}... state = {task['status']['state']}  |  agent says: {reply_text(task)}")

    # 3. The agent needs more input: continue the SAME task
    if task["status"]["state"] == "input-required":
        task = rpc(endpoint, "message/send",
                   {"message": user_message("My pincode is 500081", task["id"], task["contextId"])})
        print(f"3. Task {task['id'][:8]}... state = {task['status']['state']}  |  agent says: {reply_text(task)}")

    # 4. Check the task and read its artifact (structured result)
    final = rpc(endpoint, "tasks/get", {"id": task["id"]})
    data = final["artifacts"][0]["parts"][0]["data"]
    print(f"4. tasks/get -> state = {final['status']['state']}  |  artifact data = {data}")
    print(f"   Messages in task history: {len(final['history'])}")


if __name__ == "__main__":
    main()
