# Copyright (c) Microsoft. All rights reserved.

"""Native A2A v1 echo agent hosted by Azure AI Agent Server."""

import logging
import os
from asyncio import sleep
from uuid import uuid4

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState

from azure.ai.agentserver.a2a import A2AAgentServerHost

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("a2a-echo-agent")


class EchoAgentExecutor(AgentExecutor):
    """Echo the incoming A2A message as a completed Task artifact."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request did not contain a message")

        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        text = get_message_text(context.message)
        logger.info(
            "A2A_REQUEST_RECEIVED message_id=%s task_id=%s context_id=%s",
            context.message.message_id,
            task.id,
            task.context_id,
        )
        reply = f"Echo: {text}"
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        if dict(context.message.metadata).get("streaming_demo") is True:
            await updater.update_status(
                state=TaskState.TASK_STATE_WORKING,
                message=new_text_message("Streaming the echo one line at a time"),
            )
            lines = reply.splitlines(keepends=True)
            # Bound demo duration even when the input contains many lines.
            batch_size = max(1, (len(lines) + 15) // 16)
            chunks = ["".join(lines[i : i + batch_size]) for i in range(0, len(lines), batch_size)]
            artifact_id = str(uuid4())
            for index, chunk in enumerate(chunks):
                if index:
                    await sleep(0.5)
                await updater.add_artifact(
                    artifact_id=artifact_id,
                    name="streaming-echo",
                    parts=[new_text_part(chunk, media_type="text/plain")],
                    append=index > 0,
                    last_chunk=index == len(chunks) - 1,
                )
                logger.info("A2A_ECHO_CHUNK task_id=%s index=%s total=%s", task.id, index + 1, len(chunks))
        else:
            await updater.add_artifact(parts=[new_text_part(reply, media_type="text/plain")])
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Echo completed"),
        )
        logger.info(
            "A2A_ECHO_COMPLETED task_id=%s context_id=%s",
            task.id,
            task.context_id,
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        del context, event_queue
        raise NotImplementedError("Cancellation is not supported by the echo sample")


agent_url = os.environ.get("A2A_AGENT_URL", "http://localhost:8088/a2a")
card = AgentCard(
    name="Foundry A2A Echo Agent",
    description="Echoes the user's A2A message as a completed Task artifact.",
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            protocol_version="1.0",
            url=agent_url,
        )
    ],
    skills=[
        AgentSkill(
            id="echo",
            name="Echo",
            description="Returns the supplied text with an Echo prefix.",
            input_modes=["text/plain"],
            output_modes=["text/plain"],
            tags=["echo"],
            examples=["hello"],
        )
    ],
)
handler = DefaultRequestHandler(
    agent_executor=EchoAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=card,
)
host = A2AAgentServerHost(agent_card=card, request_handler=handler)

if __name__ == "__main__":
    logger.info("Starting native A2A echo agent")
    host.run()
