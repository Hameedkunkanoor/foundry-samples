# Copyright (c) Microsoft. All rights reserved.
"""Invoke the local coordinator with an ordinary native A2A client."""

import argparse
import asyncio
import json

import httpx2 as httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import GetTaskRequest, Role, SendMessageRequest, TaskState


async def run(endpoint: str, message: str) -> None:
    async with httpx.AsyncClient(headers={"A2A-Version": "1.0"}, timeout=240) as http:
        card = await A2ACardResolver(http, endpoint).get_agent_card(
            relative_card_path="a2a/.well-known/agent-card.json"
        )
        client = await create_client(
            card, ClientConfig(streaming=False, httpx_client=http)
        )
        try:
            tasks = [
                response.task
                async for response in client.send_message(
                    SendMessageRequest(
                        message=new_text_message(message, role=Role.ROLE_USER)
                    )
                )
                if response.HasField("task")
            ]
            if (
                len(tasks) != 1
                or tasks[0].status.state != TaskState.TASK_STATE_COMPLETED
            ):
                raise RuntimeError("Coordinator did not return one completed Task")
            task = tasks[0]
            if len(task.artifacts) != 1:
                raise ValueError("Expected one structured result artifact")
            result = json.loads(get_artifact_text(task.artifacts[0]))
            delegations = result.get("delegations", [])
            if (
                result.get("delegation_verified") is not True
                or not result.get("plan")
                or [item.get("role") for item in delegations] != ["scope", "risk"]
                or len({item.get("task_id") for item in delegations}) != 2
                or any(
                    not item.get("task_id") or not item.get("execution_id")
                    for item in delegations
                )
                or any(
                    item.get("run_id") != result.get("run_id") for item in delegations
                )
            ):
                raise ValueError("Missing or inconsistent remote delegation evidence")
            if await client.get_task(GetTaskRequest(id=task.id)) != task:
                raise RuntimeError(
                    "Coordinator Task retrieval did not preserve the result"
                )
            print(f"Coordinator Task: {task.id}")
            for item in delegations:
                print(f"{item['role']} Task: {item['task_id']}")
            print(result["plan"])
        finally:
            await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8088")
    parser.add_argument(
        "--message",
        default="Plan a staged release of search filters for 20 internal testers. Include tests and rollback. Budget is undecided.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.endpoint, args.message))
