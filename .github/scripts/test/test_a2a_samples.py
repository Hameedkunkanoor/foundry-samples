"""Credential-free regressions for native A2A planning, invocation and CI wiring."""

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import hosted_agent_test_spec as spec
import check_hosted_agent_contracts as contracts

HELPER = (
    ROOT / ".azure-pipelines/scripts/hosted-agents/scripts/invoke_hosted_agent_a2a.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("a2a_helper", HELPER)
helper = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(helper)
CARD = {
    "name": "sample",
    "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
}
TASK = {
    "id": "task-1",
    "contextId": "context-1",
    "status": {"state": "TASK_STATE_COMPLETED"},
    "artifacts": [{"parts": [{"text": "Echo: hello"}]}],
}
SCENARIO = {"message": "hello", "expected_text": "Echo: hello"}


class A2AHelperTests(unittest.TestCase):
    def test_cloud_success_captures_native_exchanges_without_credentials(self):
        requests = []

        def transport(request, timeout):
            requests.append(request)
            if request.data is None:
                body = CARD
            else:
                payload = json.loads(request.data)
                result = {"task": TASK} if payload["method"] == "SendMessage" else TASK
                body = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
            response = io.BytesIO(json.dumps(body).encode("utf-8"))
            response.status = 200
            return response

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            source.write_text(json.dumps(SCENARIO), encoding="utf-8")
            environment = {
                "AGENT_A2A_URL": "https://example.test/endpoint/protocols/a2a?api-version=preview",
                "AAD_TOKEN": "private-test-token",
                "DEPLOYED_AGENT_VERSION": "3",
                "CI_AGENT_SESSION_ID": "abc",
            }
            with patch.object(helper, "urlopen", side_effect=transport):
                result = helper.invoke_turn(
                    1, source, root, 1, environment=environment, temp_dir=root
                )
            self.assertEqual(0, result["turn_exit"])
            self.assertEqual("200", result["http_code"])
            self.assertEqual(3, len(requests))
            for request in requests:
                self.assertIn("api-version=preview", request.full_url)
                self.assertIn("agent_session_id=abc", request.full_url)
                headers = {key.lower(): value for key, value in request.header_items()}
                self.assertEqual("1.0", headers["a2a-version"])
                self.assertEqual("3", headers["x-agent-version-override"])
            exchanges = json.loads((root / "turn-1-attempt-1-a2a.json").read_text())
            self.assertEqual(
                ["SendMessage", "GetTask"],
                [exchange["request"]["method"] for exchange in exchanges[1:]],
            )
            for path in root.glob("*"):
                self.assertNotIn("private-test-token", path.read_text(encoding="utf-8"))

    def test_polling_timeout_is_a_failure(self):
        client = helper.A2AClient("https://example.test/a2a", timeout=0)
        working = {**TASK, "status": {"state": "TASK_STATE_WORKING"}}
        with patch.object(client, "discover", return_value=CARD), patch.object(
            client, "rpc", side_effect=[{"task": working}, working]
        ):
            with self.assertRaises(TimeoutError):
                helper.run_scenario(client, SCENARIO)

    def test_cancellation_requires_a_canceled_response(self):
        client = helper.A2AClient("https://example.test/a2a")
        with patch.object(client, "discover", return_value=CARD), patch.object(
            client, "rpc", side_effect=[{"task": TASK}, TASK]
        ):
            with self.assertRaisesRegex(ValueError, "TASK_STATE_CANCELED"):
                helper.run_scenario(
                    client,
                    {**SCENARIO, "return_immediately": True, "cancel": True},
                )

    def test_rpc_rejects_errors_bad_ids_and_missing_results(self):
        client = helper.A2AClient("https://example.test/a2a")
        for invalid in (
            lambda request: {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32001, "message": "not found"},
            },
            lambda request: {"jsonrpc": "2.0", "id": "wrong", "result": TASK},
            lambda request: {"jsonrpc": "2.0", "id": request["id"]},
        ):
            with self.subTest(response=invalid), patch.object(
                client, "_request", side_effect=lambda url, request: invalid(request)
            ):
                with self.assertRaises((ValueError, RuntimeError)):
                    client.rpc("GetTask", {"id": "task-1"})

    def test_discovery_preserves_session_and_uses_correct_card_route(self):
        for endpoint, expected in (
            (
                "http://localhost:8088/a2a?agent_session_id=abc",
                "/a2a/.well-known/agent-card.json?agent_session_id=abc",
            ),
            (
                "https://example.test/agents/sample/endpoint/protocols/a2a?agent_session_id=abc",
                "/agents/sample/endpoint/protocols/a2a/agentCard/v1.0?agent_session_id=abc",
            ),
        ):
            client = helper.A2AClient(endpoint)
            with patch.object(client, "_request", return_value=CARD) as request:
                self.assertEqual(CARD, client.discover())
                self.assertTrue(request.call_args.args[0].endswith(expected))

    def test_discovery_rejects_non_native_or_unsupported_cards(self):
        client = helper.A2AClient("https://example.test/a2a")
        for card in ({}, {"name": "wrong", "supportedInterfaces": []}):
            with self.subTest(card=card), patch.object(
                client, "_request", return_value=card
            ):
                with self.assertRaises(ValueError):
                    client.discover()

    def test_wrong_output_does_not_pass_for_http_success(self):
        client = helper.A2AClient("https://example.test/a2a")
        with patch.object(client, "discover", return_value=CARD), patch.object(
            client, "rpc", side_effect=[{"task": TASK}, TASK]
        ):
            with self.assertRaisesRegex(ValueError, "Expected artifact"):
                helper.run_scenario(client, {**SCENARIO, "expected_text": "different"})

    def test_task_identity_and_failed_state_are_checked(self):
        for task in (
            {**TASK, "id": "another-task"},
            {**TASK, "status": {"state": "TASK_STATE_FAILED"}},
        ):
            client = helper.A2AClient("https://example.test/a2a")
            with self.subTest(task=task), patch.object(
                client, "discover", return_value=CARD
            ), patch.object(client, "rpc", side_effect=[{"task": TASK}, task]):
                with self.assertRaises(ValueError):
                    helper.run_scenario(client, SCENARIO)

    def test_missing_listing_entry_does_not_pass(self):
        client = helper.A2AClient("https://example.test/a2a")
        with patch.object(client, "discover", return_value=CARD), patch.object(
            client, "rpc", side_effect=[{"task": TASK}, TASK, {"tasks": []}]
        ):
            with self.assertRaisesRegex(ValueError, "absent from ListTasks"):
                helper.run_scenario(client, {**SCENARIO, "list_tasks": True})

    def test_cloud_failure_writes_explicit_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            source.write_text(json.dumps(SCENARIO), encoding="utf-8")
            environment = {
                "AGENT_A2A_URL": "https://example.test/endpoint/protocols/a2a",
                "AAD_TOKEN": "private-test-token",
                "DEPLOYED_AGENT_VERSION": "3",
                "CI_AGENT_SESSION_ID": "abc",
            }
            with patch.object(
                helper.A2AClient, "discover", side_effect=ValueError("bad card")
            ):
                result = helper.invoke_turn(
                    1, source, root, 1, environment=environment, temp_dir=root
                )
            self.assertEqual(1, result["turn_exit"])
            self.assertIn("bad card", (root / "invoke-out-1.txt").read_text())
            for path in root.glob("*"):
                self.assertNotIn("private-test-token", path.read_text(encoding="utf-8"))


class A2AContractTests(unittest.TestCase):
    def test_manifests_are_selected_as_native_a2a(self):
        for name in ("echo", "long-running-tasks", "task-persistence"):
            manifest = (
                ROOT
                / "samples/python/hosted-agents/bring-your-own/a2a"
                / name
                / "azure.yaml"
            )
            with self.subTest(name=name):
                self.assertEqual("a2a", contracts._selected_protocol(manifest))

    def test_every_sample_has_a_valid_native_contract(self):
        for name in ("echo", "long-running-tasks", "task-persistence"):
            with self.subTest(name=name):
                path = (
                    ROOT
                    / ".azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a"
                    / name
                    / "test-spec.yml"
                )
                plan = spec.build_plan(spec.load_spec(path), protocol="a2a")
                self.assertGreater(plan["turn_count"], 0)
                self.assertEqual("hkunkanoor", plan["sample"]["owner"])

    def test_invalid_scenario_inputs_fail_before_execution(self):
        for scenario in (
            "hello",
            {},
            {**SCENARIO, "message": ""},
            {**SCENARIO, "cancel": "yes"},
            {**SCENARIO, "return_immediately": 1},
            {**SCENARIO, "cancel": True},
            {**SCENARIO, "unknown": True},
        ):
            with self.subTest(scenario=scenario), self.assertRaises(spec.SpecError):
                spec.validate_a2a_input(scenario)

    def test_native_contracts_cannot_use_responses_assertions(self):
        path = (
            ROOT
            / ".azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/echo/test-spec.yml"
        )
        document = copy.deepcopy(spec.load_spec(path))
        document["tests"][0]["turns"][0]["assertions"][0]["source"] = "assistant_text"
        with self.assertRaisesRegex(spec.SpecError, "Responses protocol"):
            spec.build_plan(document, protocol="a2a")

    def test_a2a_is_wired_to_its_own_runner_without_a_sample_skip(self):
        runner = (
            ROOT / ".azure-pipelines/scripts/hosted-agents/run-hosted-agent.sh"
        ).read_text(encoding="utf-8")
        discovery = (
            ROOT / ".azure-pipelines/scripts/hosted-agents/discover-samples.sh"
        ).read_text(encoding="utf-8")
        skiplist = (
            ROOT / ".azure-pipelines/scripts/hosted-agent-samples-ci-skiplist"
        ).read_text(encoding="utf-8")
        self.assertIn("invoke_hosted_agent_a2a.py", runner)
        self.assertIn(".agent_endpoints.a2a", runner)
        self.assertEqual(2, discovery.count('protocol="a2a"'))
        for name in ("echo", "long-running-tasks", "task-persistence"):
            self.assertNotIn(
                f"samples/python/hosted-agents/bring-your-own/a2a/{name}\n", skiplist
            )


if __name__ == "__main__":
    unittest.main()
