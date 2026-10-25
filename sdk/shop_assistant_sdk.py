"""
Shop Assistant built with the official A2A Python SDK
=====================================================

Start the agent first:   python delivery_agent_sdk.py
Then in a new terminal:  python shop_assistant_sdk.py
"""

import asyncio
import uuid

from a2a.client import ClientFactory
from a2a.helpers import get_data_parts
from a2a.types import GetTaskRequest, Message, Part, Role, SendMessageRequest, TaskState

AGENT_URL = "http://127.0.0.1:9999"


def user_message(text: str, task_id: str = "", context_id: str = "") -> Message:
    return Message(message_id=str(uuid.uuid4()), role=Role.ROLE_USER, parts=[Part(text=text)],
                   task_id=task_id, context_id=context_id)


async def send(client, message: Message):
    task = None
    async for response in client.send_message(SendMessageRequest(message=message)):
        if response.HasField("task"):
            task = response.task
    return task


async def main() -> None:
    # 1. Discover: the factory reads the Agent Card and builds the right client
    client = await ClientFactory().create_from_url(AGENT_URL)
    print("1. Connected to the Delivery Agent")

    # 2. Send a question without a pincode
    task = await send(client, user_message("When will my books arrive?"))
    print(f"2. state = {TaskState.Name(task.status.state)}  |  agent: {task.status.message.parts[0].text}")

    # 3. Continue the SAME task with the missing input
    if task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
        task = await send(client, user_message("My pincode is 500081", task.id, task.context_id))
        print(f"3. state = {TaskState.Name(task.status.state)}  |  agent: {task.status.message.parts[0].text}")

    # 4. Check the task and read the artifact
    final = await client.get_task(GetTaskRequest(id=task.id))
    print(f"4. GetTask -> {TaskState.Name(final.status.state)}  |  artifact data = {get_data_parts(final.artifacts[0].parts)}")


if __name__ == "__main__":
    asyncio.run(main())
