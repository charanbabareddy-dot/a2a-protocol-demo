"""
Shop Assistant: an A2A client agent (Python standard library only)
==================================================================

It talks to the Delivery Agent the A2A v1.0 way:

  1. Discover: read the Agent Card to learn the agent's name, skills and URL
  2. Send:     call SendMessage with a question
  3. Continue: if the task needs input, send more input on the SAME task
  4. Check:    call GetTask to see the task's final state and its artifact
"""

import json
import urllib.request
import uuid

BASE_URL = "http://127.0.0.1:8765"
A2A_VERSION = "1.0"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def rpc(url: str, method: str, params: dict) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "A2A-Version": A2A_VERSION}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        reply = json.loads(resp.read())
    if "error" in reply:
        raise RuntimeError(f"{method} failed: {reply['error']['message']}")
    return reply["result"]


def user_message(text: str, task_id: str | None = None, context_id: str | None = None) -> dict:
    msg = {"messageId": str(uuid.uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        msg["taskId"] = task_id        # continue the same task
    if context_id:
        msg["contextId"] = context_id  # same conversation
    return msg


def reply_text(task: dict) -> str:
    return " ".join(p["text"] for p in task["status"]["message"]["parts"] if "text" in p)


def pick_jsonrpc_url(card: dict) -> str:
    for interface in card["supportedInterfaces"]:
        if interface["protocolBinding"] == "JSONRPC":
            return interface["url"]
    raise RuntimeError("This agent has no JSON-RPC interface")


def main() -> None:
    # 1. Discover
    card = get_json(f"{BASE_URL}/.well-known/agent-card.json")
    print(f"1. Found agent: {card['name']}  |  skills: {[s['name'] for s in card['skills']]}")
    endpoint = pick_jsonrpc_url(card)

    # 2. Send a question without a pincode
    task = rpc(endpoint, "SendMessage", {"message": user_message("When will my books arrive?")})["task"]
    print(f"2. Task {task['id'][:8]}... state = {task['status']['state']}  |  agent says: {reply_text(task)}")

    # 3. The agent needs more input: continue the SAME task
    if task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED":
        task = rpc(endpoint, "SendMessage",
                   {"message": user_message("My pincode is 500081", task["id"], task["contextId"])})["task"]
        print(f"3. Task {task['id'][:8]}... state = {task['status']['state']}  |  agent says: {reply_text(task)}")

    # 4. Check the task and read its artifact (structured result)
    final = rpc(endpoint, "GetTask", {"id": task["id"]})
    data = final["artifacts"][0]["parts"][0]["data"]
    print(f"4. GetTask -> state = {final['status']['state']}  |  artifact data = {data}")
    print(f"   Messages in task history: {len(final['history'])}")


if __name__ == "__main__":
    main()
