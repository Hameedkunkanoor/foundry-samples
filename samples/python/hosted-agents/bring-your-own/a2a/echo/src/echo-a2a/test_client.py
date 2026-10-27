# Copyright (c) Microsoft. All rights reserved.

"""Dedicated local or hosted E2E client for the native A2A echo sample."""

import argparse
import asyncio
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://localhost:8088")
    parser.add_argument(
        "--card-path",
        default="a2a/.well-known/agent-card.json",
    )
    parser.add_argument("--message", default="hello")
    parser.add_argument("--azure-auth", action="store_true")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    headers: dict[str, str] = {}
    if args.azure_auth:
        from azure.identity import AzureDeveloperCliCredential

        token = AzureDeveloperCliCredential().get_token("https://ai.azure.com/.default")
        headers["Authorization"] = f"Bearer {token.token}"

    endpoint = urlsplit(args.endpoint)
    base_url = urlunsplit((endpoint.scheme, endpoint.netloc, endpoint.path, "", ""))
    query = dict(parse_qsl(endpoint.query))

    async with httpx.AsyncClient(
        headers=headers,
        params=query,
        timeout=60.0,
    ) as http_client:
        card = await A2ACardResolver(http_client, base_url).get_agent_card(
            relative_card_path=args.card_path,
        )
        http_client.headers["A2A-Version"] = "1.0"
        client = await create_client(
            card,
            ClientConfig(streaming=True, httpx_client=http_client),
        )
        request = SendMessageRequest(message=new_text_message(args.message, role=Role.ROLE_USER))

        outputs: list[str] = []
        completed = False
        async for response in client.send_message(request):
            if response.HasField("message"):
                outputs.append(get_message_text(response.message))
            elif response.HasField("task"):
                outputs.extend(get_artifact_text(artifact) for artifact in response.task.artifacts)
                completed = response.task.status.state == TaskState.TASK_STATE_COMPLETED
            elif response.HasField("artifact_update"):
                outputs.append(get_artifact_text(response.artifact_update.artifact))
            elif response.HasField("status_update"):
                completed = response.status_update.status.state == TaskState.TASK_STATE_COMPLETED

        expected = f"Echo: {args.message}"
        if outputs != [expected]:
            raise RuntimeError(f"Expected one artifact {expected!r}, received {outputs!r}")
        if not completed:
            raise RuntimeError("Expected a completed A2A streaming status update")
        print(expected, flush=True)


if __name__ == "__main__":
    asyncio.run(_run(_parse_args()))
