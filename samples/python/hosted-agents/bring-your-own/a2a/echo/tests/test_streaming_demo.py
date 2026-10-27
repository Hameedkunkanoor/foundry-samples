# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for the explicit, opt-in streaming demo."""

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from a2a.helpers import new_text_message
from a2a.types import Role

RUNTIME = Path(__file__).resolve().parents[1] / "src" / "echo-a2a"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, RUNTIME / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with patch("azure.ai.agentserver.a2a.A2AAgentServerHost"):
            self.sample = load("echo_stream_sample", "main.py")

    async def execute(self, text, opt_in):
        message = new_text_message(text, role=Role.ROLE_USER)
        if opt_in:
            message.metadata.update({"streaming_demo": True})
        context = SimpleNamespace(message=message, current_task=None)
        queue, updater = AsyncMock(), AsyncMock()
        with patch.object(self.sample, "TaskUpdater", return_value=updater), patch.object(
            self.sample, "sleep", new_callable=AsyncMock
        ) as pause:
            await self.sample.EchoAgentExecutor().execute(context, queue)
        return updater, pause

    async def test_default_echo_stays_one_artifact_without_delays(self):
        updater, pause = await self.execute("hello\nworld", False)
        self.assertEqual(updater.add_artifact.await_count, 1)
        parts = updater.add_artifact.await_args.kwargs["parts"]
        self.assertEqual(parts[0].text, "Echo: hello\nworld")
        pause.assert_not_awaited()

    async def test_demo_preserves_content_and_artifact_flags(self):
        text = "first line\nsecond line\nthird line"
        updater, pause = await self.execute(text, True)
        calls = updater.add_artifact.await_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual("".join(call.kwargs["parts"][0].text for call in calls), "Echo: " + text)
        self.assertEqual(len({call.kwargs["artifact_id"] for call in calls}), 1)
        self.assertEqual([call.kwargs["append"] for call in calls], [False, True, True])
        self.assertEqual([call.kwargs["last_chunk"] for call in calls], [False, False, True])
        self.assertEqual(pause.await_count, 2)

    async def test_demo_bounds_update_count_and_preserves_unicode(self):
        text = "\n".join(f"line {index}: \u96ea \U0001f680" for index in range(100))
        updater, pause = await self.execute(text, True)
        calls = updater.add_artifact.await_args_list
        self.assertLessEqual(len(calls), 16)
        self.assertEqual("".join(call.kwargs["parts"][0].text for call in calls), "Echo: " + text)
        self.assertEqual(pause.await_count, len(calls) - 1)


class ParserTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = load("echo_stream_client", "streaming_client.py")

    async def test_sse_parser_handles_multiline_data_and_heartbeats(self):
        response = httpx.Response(
            200,
            content=b': heartbeat\n\ndata: {"result":\ndata: {"task": {"id": "task-1"}}}\n\n',
        )
        values = [value async for value in self.client.sse_events(response)]
        self.assertEqual(values, [{"result": {"task": {"id": "task-1"}}}])

    async def test_sse_parser_rejects_truncated_event(self):
        response = httpx.Response(200, content=b'data: {"result": {}}')
        with self.assertRaisesRegex(RuntimeError, "ended before"):
            _ = [value async for value in self.client.sse_events(response)]

    async def test_demo_rejects_unary_fallback(self):
        async def handler(_request):
            return httpx.Response(200, json={"result": {}})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        args = argparse.Namespace(
            endpoint="http://test/a2a",
            message=self.client.DEMO_MESSAGE,
            azure_auth=False,
            session_id=None,
            output=None,
        )
        with patch.object(self.client.httpx, "AsyncClient", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "Expected SSE"):
                await self.client.run(args)

    async def test_demo_rejects_fully_buffered_delivery(self):
        payloads = [
            {"result": {"task": {"id": "task-1", "status": {"state": "TASK_STATE_SUBMITTED"}}}},
            {
                "result": {
                    "artifactUpdate": {
                        "taskId": "task-1",
                        "artifact": {"artifactId": "artifact-1", "parts": [{"text": "Echo: first\n"}]},
                        "append": False,
                        "lastChunk": False,
                    }
                }
            },
            {
                "result": {
                    "artifactUpdate": {
                        "taskId": "task-1",
                        "artifact": {"artifactId": "artifact-1", "parts": [{"text": "second"}]},
                        "append": True,
                        "lastChunk": True,
                    }
                }
            },
            {"result": {"statusUpdate": {"taskId": "task-1", "status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]

        async def handler(_request):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="".join(f"data: {json.dumps(value)}\n\n" for value in payloads).encode(),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        args = argparse.Namespace(
            endpoint="http://test/a2a",
            message="first\nsecond",
            azure_auth=False,
            session_id=None,
            output=None,
        )
        with patch.object(self.client.httpx, "AsyncClient", return_value=client), patch.object(
            self.client.time, "perf_counter", return_value=100
        ):
            with self.assertRaisesRegex(RuntimeError, "Possible buffering"):
                await self.client.run(args)


if __name__ == "__main__":
    unittest.main()
