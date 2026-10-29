# What this sample demonstrates

A native A2A 1.0 Echo agent hosted by `azure-ai-agentserver-a2a`. Discover its
Agent Card, send `hello`, and retrieve a completed Task containing `Echo: hello`.
Local execution needs no model, subscription, or credentials.

## How it works

The official `a2a-sdk` supplies Agent Cards, executors, Tasks and artifacts.
[main.py](src/echo-a2a/main.py) passes an executor to `A2AAgentServerHost`.
The host selects memory locally and caller-isolated Foundry storage when hosted.

| Local route | Purpose |
|---|---|
| `GET /readiness` | Container readiness |
| `GET /a2a/.well-known/agent-card.json` | Native Agent Card |
| `POST /a2a` | A2A JSON-RPC, with `A2A-Version: 1.0` |

## Prerequisites

- Python 3.10+; the deployment manifest selects Python 3.13.
- uv 0.11.7 for the frozen dependency workflow.
- For deployment only: Azure CLI, azd 1.27.1+ with the `azure.ai.agents`
  extension, and access to a Foundry project in a supported hosted-agent region.

> **SDK publication gate:** This sample targets A2A `1.0.0b1` and Core `2.3.0b3`.
> Both must be available on PyPI before generating and committing `uv.lock`.
> Until then, frozen installation and deployment are blocked. The PR stays
> draft; do not substitute a private feed or bypass dependency validation.

## Run locally

Clone this repository and open this sample directory. Once the publication gate
is satisfied:

```powershell
cd src\echo-a2a
uv sync --frozen --python 3.13
uv run --frozen python main.py
```

In another terminal, from the same runtime directory:

```powershell
uv run --frozen python test_client.py --message "hello"
```

The [client](src/echo-a2a/test_client.py) uses the official A2A client, checks the
exact artifact and completed state, then verifies `GetTask` returns the same
Task. Output includes `task_id=...` and `Echo: hello`.

To debug, open `src/echo-a2a` in VS Code, install the Python extension, select
its `.venv` interpreter, and debug `main.py` as a Python file. Run the native
client in another terminal. No Inspector integration is required.

## Deploy with azd

From this sample directory, authenticate using `az login` and `azd auth login`.
Choose a unique agent name in [azure.yaml](azure.yaml), then run:

```powershell
azd env new a2a-echo-demo
azd provision
azd deploy
azd ai agent show --output json
```

The manifest uses direct code deployment; no Dockerfile or model deployment is
required. Public invocation requires native A2A availability on the target
Foundry project, including Task retrieval. A deployed container alone does not
prove public gateway availability.

From the repository root, copy `agent_endpoints.a2a` from the last command and
run the shared native verifier:

```powershell
python .azure-pipelines\scripts\hosted-agents\scripts\invoke_hosted_agent_a2a.py `
  --endpoint "<agent_endpoints.a2a>" --azure-auth `
  --message "hello" --expected-text "Echo: hello"
```

It discovers the versioned public Card, sends a native JSON-RPC request and
retrieves the resulting Task. HTTP errors, JSON-RPC errors and incorrect
artifacts fail explicitly.

## Tests and tracing

From the repository root, using an interpreter containing the sample dependencies:

```powershell
python .github\scripts\test\test_a2a_samples.py
python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

The credential-free GitHub workflow runs helper/contract tests and real-HTTP
sample tests. Its frozen dependency job deliberately fails until the publication
gate is satisfied. The cloud pipeline uses the sample's
[native behavior contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/echo/test-spec.yml).
No A2A sample exclusion is required.

The host supplies semantic A2A tracing. When an OpenTelemetry exporter is
configured, inspect `SendMessage` and `GetTask` spans and correlate the Task ID
with the `A2A_ECHO_COMPLETED` application log. Do not enable message-content
capture unless appropriate for the data.

## Troubleshooting

- Missing `uv.lock` or unresolved SDK pins: the publication gate is not satisfied.
- Local discovery failure: use `/a2a/.well-known/agent-card.json`, not the
  Foundry public Card path.
- Version error: send `A2A-Version: 1.0`.
- Public lookup/authorization failure: check the project, deployment and native
  A2A availability. Do not add a different protocol as an invocation fallback.

## Next steps

- [Long-running Tasks](../long-running-tasks/README.md)
- [Task persistence](../task-persistence/README.md)
