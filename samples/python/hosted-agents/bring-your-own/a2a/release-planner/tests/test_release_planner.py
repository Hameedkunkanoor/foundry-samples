"""Contract checks and real three-server native A2A collaboration."""

import asyncio
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.request import urlopen

import httpx2 as httpx
from a2a.helpers import new_text_message
from a2a.types import Role

RUNTIME = Path(__file__).resolve().parents[1] / "src" / "release-planner-a2a"
SPEC = importlib.util.spec_from_file_location("release_planner", RUNTIME / "main.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
PROJECT = "https://example.services.ai.azure.com/api/projects/test"


def specialist_card(role: str, endpoint: str) -> dict:
    return {
        "skills": [{"id": role}],
        "supportedInterfaces": [
            {"protocolBinding": "JSONRPC", "protocolVersion": "1.0", "url": endpoint}
        ],
    }


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_advertised_query_is_authoritative_and_transport_cannot_change(self):
        source = PROJECT + "/agents/discovery/endpoint/protocols/a2a?api-version=v1"
        target = (
            PROJECT
            + "/agents/worker/endpoint/protocols/a2a?api-version=v2&custom=value"
        )
        self.assertEqual(
            target,
            module.select_interface(
                specialist_card("scope", target), source, PROJECT, False
            ),
        )
        with self.assertRaisesRegex(ValueError, "transport"):
            module.select_interface(
                specialist_card("scope", target),
                "http://127.0.0.1:8089/a2a",
                PROJECT,
                False,
            )

    async def test_invokes_advertised_interface_and_preserves_api_version(self):
        configured = PROJECT + "/agents/discovery/endpoint/protocols/a2a?api-version=v1"
        advertised = PROJECT + "/agents/worker/endpoint/protocols/a2a"
        services = module.Services(PROJECT, "test-model", False)
        services.headers = AsyncMock(return_value={"Authorization": "test-auth"})
        requests = []

        def respond(request):
            requests.append(request)
            if request.method == "GET":
                card = specialist_card("scope", advertised)
                card["supportedInterfaces"].insert(
                    0,
                    {
                        "protocolBinding": "GRPC",
                        "protocolVersion": "1.0",
                        "url": "https://untrusted.invalid",
                    },
                )
                return httpx.Response(200, json=card)
            rpc = json.loads(request.content)
            artifact = {
                "role": "scope",
                "run_id": "run",
                "input_sha256": hashlib.sha256(b"test").hexdigest(),
                "execution_id": "execution-1",
                "analysis": "scope assessment",
            }
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": rpc["id"],
                    "result": {
                        "task": {
                            "id": "remote-task-1",
                            "status": {"state": "TASK_STATE_COMPLETED"},
                            "artifacts": [{"parts": [{"text": json.dumps(artifact)}]}],
                        }
                    },
                },
            )

        await services.http.aclose()
        services.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            result = await services.specialist(configured, "scope", "test", "run")
            self.assertEqual("remote-task-1", result["task_id"])
            self.assertEqual(
                configured.replace("/a2a?", "/a2a/agentCard/v1.0?"),
                str(requests[0].url),
            )
            self.assertEqual(advertised + "?api-version=v1", str(requests[1].url))
            self.assertNotEqual(configured, str(requests[1].url))
        finally:
            await services.close()

    async def test_invalid_advertised_interfaces_never_receive_a_post(self):
        configured = PROJECT + "/agents/discovery/endpoint/protocols/a2a?api-version=v1"
        cases = [
            {},
            {"supportedInterfaces": []},
            {
                "supportedInterfaces": [
                    {
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "0.3",
                        "url": configured,
                    }
                ]
            },
            specialist_card("scope", "https://untrusted.invalid/a2a"),
            specialist_card(
                "scope", PROJECT + "-other/agents/worker/endpoint/protocols/a2a"
            ),
            specialist_card(
                "scope",
                PROJECT + "/agents/../other/agents/worker/endpoint/protocols/a2a",
            ),
            specialist_card("scope", PROJECT + "/agents/%2e%2e/endpoint/protocols/a2a"),
            specialist_card("scope", "http://127.0.0.1:8089/a2a"),
            specialist_card("scope", ""),
            specialist_card("scope", 42),
        ]
        for card in cases:
            card["skills"] = [{"id": "scope"}]
            with self.subTest(card=card):
                services = module.Services(PROJECT, "test-model", False)
                services.headers = AsyncMock(
                    return_value={"Authorization": "test-auth"}
                )
                requests = []

                def respond(request):
                    requests.append(request)
                    return httpx.Response(200, json=card)

                await services.http.aclose()
                services.http = httpx.AsyncClient(
                    transport=httpx.MockTransport(respond)
                )
                try:
                    with self.assertRaises(ValueError):
                        await services.specialist(configured, "scope", "test", "run")
                    self.assertEqual(["GET"], [request.method for request in requests])
                finally:
                    await services.close()

    async def test_hosted_a2a_headers_use_the_agent_credential(self):
        with patch.dict(
            os.environ,
            {
                "FOUNDRY_AGENT_INSTANCE_CLIENT_ID": "11111111-1111-1111-1111-111111111111"
            },
        ):
            services = module.Services(PROJECT, "test-model", True)
        default = services.credential
        agent = services.agent_credential
        services.credential = SimpleNamespace(
            get_token=AsyncMock(return_value=SimpleNamespace(token="model-token")),
            close=AsyncMock(),
        )
        services.agent_credential = SimpleNamespace(
            get_token=AsyncMock(return_value=SimpleNamespace(token="agent-token")),
            close=AsyncMock(),
        )
        try:
            headers = await services.headers(True, agent_identity=True)
            self.assertEqual("Bearer agent-token", headers["Authorization"])
            services.credential.get_token.assert_not_awaited()
        finally:
            await services.close()
            await default.close()
            await agent.close()

    async def test_coordinator_never_synthesizes_when_a_specialist_fails(self):
        services = SimpleNamespace(
            specialist=AsyncMock(side_effect=RuntimeError("remote agent unavailable")),
            model_reply=AsyncMock(),
        )
        executor = module.ReleaseExecutor(
            "coordinator",
            services,
            {"scope": "http://127.0.0.1:8089/a2a", "risk": "http://127.0.0.1:8090/a2a"},
        )
        context = SimpleNamespace(
            message=new_text_message("Plan a test release", role=Role.ROLE_USER)
        )
        with self.assertLogs("a2a.release_planner", level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "Release planning failed"):
                await executor.execute(
                    context, SimpleNamespace(enqueue_event=AsyncMock())
                )
        services.model_reply.assert_not_awaited()

    async def test_wrong_card_skill_fails_before_message_dispatch(self):
        services = module.Services(PROJECT, "test-model", False)
        services.headers = AsyncMock(return_value={})
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"skills": [{"id": "risk"}]})

        await services.http.aclose()
        services.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with self.assertRaisesRegex(ValueError, "does not advertise"):
                await services.specialist(
                    "http://127.0.0.1:8089/a2a", "scope", "test", "run"
                )
            self.assertEqual(["GET"], [request.method for request in requests])
        finally:
            await services.close()

    async def test_hosted_endpoint_rejects_other_projects_and_credentials(self):
        module.check_endpoint(
            PROJECT + "/agents/scope/endpoint/protocols/a2a", PROJECT, True
        )
        for endpoint in (
            "http://127.0.0.1:8089/a2a",
            "https://other.example/agents/scope/endpoint/protocols/a2a",
            PROJECT + "-other/agents/scope/endpoint/protocols/a2a",
            "https://user:secret@example.services.ai.azure.com/api/projects/test/agents/scope/endpoint/protocols/a2a",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                module.check_endpoint(endpoint, PROJECT, True)

    async def test_specialist_protocol_error_does_not_become_a_success(self):
        services = module.Services(PROJECT, "test-model", False)
        services.headers = AsyncMock(return_value={})

        def respond(request):
            if request.method == "GET":
                return httpx.Response(
                    200, json=specialist_card("scope", "http://127.0.0.1:8089/a2a")
                )
            rpc = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": rpc["id"],
                    "error": {"code": -32000, "message": "test failure"},
                },
            )

        await services.http.aclose()
        services.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with self.assertRaisesRegex(RuntimeError, "Specialist scope failed"):
                await services.specialist(
                    "http://127.0.0.1:8089/a2a", "scope", "test", "run"
                )
        finally:
            await services.close()

    async def test_incomplete_model_response_is_rejected(self):
        services = module.Services(PROJECT, "test-model", False)
        services.headers = AsyncMock(return_value={})
        await services.http.aclose()
        services.http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"status": "incomplete", "output": []}
                )
            )
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "not complete"):
                await services.model_reply("scope", "test")
        finally:
            await services.close()


class ThreeServerTests(unittest.TestCase):
    def test_native_delegation_requires_both_remote_completed_tasks(self):
        processes = []
        logs = []
        ports = []
        for _ in range(3):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ports.append(sock.getsockname()[1])
        wrapper = (
            "import sys; sys.path.insert(0,sys.argv[1]); import main; "
            "exec('async def fixture_reply(self, role, material):\\n"
            ' return role + " fixture assessment: " + material[:100]\\n\'); '
            "main.Services.model_reply=fixture_reply; main.main()"
        )
        with tempfile.TemporaryDirectory() as state:
            try:
                for role, port in zip(("scope", "risk", "coordinator"), ports):
                    environment = {
                        key: value
                        for key, value in os.environ.items()
                        if not key.startswith(
                            ("FOUNDRY_", "APPLICATIONINSIGHTS_", "OTEL_")
                        )
                    }
                    environment.update(
                        AGENT_ROLE=role,
                        PORT=str(port),
                        FOUNDRY_PROJECT_ENDPOINT=PROJECT,
                        AZURE_AI_MODEL_DEPLOYMENT_NAME="test-model",
                        AGENTSERVER_STATE_ROOT=state,
                        SCOPE_AGENT_ENDPOINT=f"http://127.0.0.1:{ports[0]}/a2a",
                        RISK_AGENT_ENDPOINT=f"http://127.0.0.1:{ports[1]}/a2a",
                    )
                    log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
                    logs.append(log)
                    process = subprocess.Popen(
                        [sys.executable, "-c", wrapper, str(RUNTIME)],
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(process)
                    deadline = time.monotonic() + 40
                    while True:
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            self.fail(log.read())
                        try:
                            with urlopen(
                                f"http://127.0.0.1:{port}/readiness", timeout=1
                            ) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            time.sleep(0.05)

                async def invoke():
                    async with httpx.AsyncClient(timeout=30) as client:
                        response = await client.post(
                            f"http://127.0.0.1:{ports[2]}/a2a",
                            headers={"A2A-Version": "1.0"},
                            json={
                                "jsonrpc": "2.0",
                                "id": "test-1",
                                "method": "SendMessage",
                                "params": {
                                    "message": {
                                        "messageId": "message-1",
                                        "role": "ROLE_USER",
                                        "parts": [
                                            {
                                                "text": "Release a search feature to 20 testers."
                                            }
                                        ],
                                    },
                                    "configuration": {"returnImmediately": False},
                                },
                            },
                        )
                        response.raise_for_status()
                        return response.json()

                response = asyncio.run(invoke())
                self.assertNotIn("error", response, response)
                task = response["result"]["task"]
                self.assertEqual("TASK_STATE_COMPLETED", task["status"]["state"])
                result = json.loads(task["artifacts"][0]["parts"][0]["text"])
                self.assertTrue(result["delegation_verified"])
                self.assertEqual(
                    ["scope", "risk"], [item["role"] for item in result["delegations"]]
                )
                self.assertEqual(
                    2, len({item["task_id"] for item in result["delegations"]})
                )
                self.assertEqual(
                    2, len({item["execution_id"] for item in result["delegations"]})
                )
                self.assertTrue(result["plan"])
                native = subprocess.run(
                    [
                        sys.executable,
                        str(RUNTIME / "test_client.py"),
                        "--endpoint",
                        f"http://127.0.0.1:{ports[2]}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(0, native.returncode, native.stdout + native.stderr)
                self.assertIn("scope Task:", native.stdout)
                self.assertIn("risk Task:", native.stdout)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                for log in logs:
                    log.close()


if __name__ == "__main__":
    unittest.main()
