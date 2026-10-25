"""
Delivery Agent built with the official A2A Python SDK
=====================================================

Same agent as ../delivery_agent.py, but the SDK writes the JSON-RPC for us.
The 6 building blocks of every SDK agent:

  1. AgentSkill + AgentCard      -> the visiting card
  2. Business logic              -> estimate_delivery()
  3. AgentExecutor.execute()     -> reads the message, runs the logic, sends events
  4. DefaultRequestHandler       -> handles JSON-RPC and stores tasks (InMemoryTaskStore)
  5. Routes + Starlette app      -> Agent Card route + JSON-RPC route
  6. uvicorn                     -> runs the web server

Run:  python delivery_agent_sdk.py
"""

import re

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_data_part, new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Part

HOST, PORT = "127.0.0.1", 9999

# 1. Skill + Agent Card
skill = AgentSkill(
    id="estimate_delivery",
    name="Estimate delivery",
    description="Give a 6 digit pincode and get the expected delivery days.",
    tags=["delivery", "pincode"],
    examples=["How many days to deliver to 500081?"],
)
agent_card = AgentCard(
    name="Delivery Agent",
    description="Estimates delivery days for an Indian pincode.",
    version="1.0.0",
    supported_interfaces=[AgentInterface(url=f"http://{HOST}:{PORT}", protocol_binding="JSONRPC", protocol_version="1.0")],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain", "application/json"],
    skills=[skill],
)


# 2. Business logic (plain Python, no A2A here)
def estimate_delivery(pincode: str) -> dict:
    days = {"5": 2, "6": 3}.get(pincode[0], 5)
    return {"pincode": pincode, "days": days}


# 3. Executor: the bridge between A2A and the business logic
class DeliveryExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:                                   # first message: create a new task
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        match = re.search(r"\b(\d{6})\b", context.get_user_input())
        if not match:                                      # ask for more input, task stays open
            await updater.requires_input(
                message=updater.new_agent_message([Part(text="Please share a 6 digit pincode.")]))
            return

        result = estimate_delivery(match.group(1))
        await updater.add_artifact([new_data_part(result)], name="delivery_estimate")
        await updater.complete(message=updater.new_agent_message(
            [Part(text=f"Delivery to {result['pincode']} takes about {result['days']} days.")]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancel is not supported")


# 4. Request handler + 5. app with routes
handler = DefaultRequestHandler(agent_executor=DeliveryExecutor(), task_store=InMemoryTaskStore(), agent_card=agent_card)
app = Starlette(routes=[*create_agent_card_routes(agent_card), *create_jsonrpc_routes(handler, "/")])

# 6. Run
if __name__ == "__main__":
    print(f"SDK Delivery Agent at http://{HOST}:{PORT}  (Agent Card: /.well-known/agent-card.json)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
