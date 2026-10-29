# What this sample demonstrates

A deterministic native A2A report Task that runs for two seconds. Request an
immediate Task response, poll until the artifact is ready, or cancel the work.
No model or Azure credentials are needed locally.

## How it works

[main.py](src/report-a2a/main.py) publishes a Task and working state before
awaiting the report operation. `configuration.returnImmediately: true` lets
`SendMessage` return before that operation finishes. `GetTask` polls its state.
`CancelTask` invokes the executor's cancellation hook; the native handler then
cancels the running coroutine. Do not swallow `asyncio.CancelledError` in the
application operation.

Successful output is `Report: quarterly results`. Canceled work reaches
`TASK_STATE_CANCELED` without producing a report artifact. A completed Task
cannot subsequently be canceled.

## Prerequisites

- Python 3.10+ and uv 0.11.7. The manifest deploys Python 3.13.
- For deployment: azd 1.27.1+, its `azure.ai.agents` extension, Azure CLI, and
  a Foundry project supporting native A2A send/get/cancel operations.

> **SDK publication gate:** A2A `1.0.0b1` and Core `2.3.0b3` must be published
> on PyPI, then `uv.lock` must be generated and committed. Frozen installation
> and deployment remain blocked until that happens. Do not bypass the policy.

## Run locally

Clone this repository. From this sample directory, once the publication gate
is satisfied:

```powershell
cd src\report-a2a
uv sync --frozen --python 3.13
uv run --frozen python main.py
```

From a second terminal at the repository root:

```powershell
python .azure-pipelines\scripts\hosted-agents\scripts\invoke_hosted_agent_a2a.py `
  --message "quarterly results" --expected-text "Report: quarterly results" `
  --return-immediately
```

The verifier prints the initial Task and the final completed snapshot. Initial
state can be submitted, working, or completed depending on scheduling. The
report delay makes submitted/working observable in the automated local test.

To exercise cancellation:

```powershell
python .azure-pipelines\scripts\hosted-agents\scripts\invoke_hosted_agent_a2a.py `
  --message "cancel this report" --return-immediately --cancel
```

The verifier checks both the cancellation response and the saved canceled
snapshot. A client timeout is not a cancellation request.

For VS Code debugging, open `src/report-a2a`, select its `.venv` interpreter,
and debug `main.py`. Run the verifier in a second terminal.

## Deploy with azd

From this sample directory, authenticate with `az login` and `azd auth login`,
choose a unique agent name in [azure.yaml](azure.yaml), and run:

```powershell
azd env new a2a-report-demo
azd provision
azd deploy
azd ai agent show --output json
```

No model or Dockerfile is required. Add `--endpoint "<agent_endpoints.a2a>"`
and `--azure-auth` to either verifier command for the deployed agent. Use a
project where the corresponding native public A2A operations are available;
container readiness alone is not public gateway validation.

## Tests and tracing

From the repository root, in an interpreter with the runtime dependencies:

```powershell
python .github\scripts\test\test_a2a_samples.py
python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

Tests use real server processes and HTTP. They verify an initial unfinished
Task, completion by polling, rejection of cancellation after completion, and
that canceled work remains canceled after its original completion time.
The [cloud contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/long-running-tasks/test-spec.yml)
exercises both report completion and cancellation using native A2A.

With an OpenTelemetry exporter configured, correlate A2A operation spans and
Task IDs with `A2A_REPORT_WORKING`, `A2A_REPORT_COMPLETED` and
`A2A_REPORT_CANCELED` logs.

## Execution boundary

The report runs inside one server process. Persisting a Task snapshot does not
resume unfinished report generation after process termination. Business work
that needs execution recovery requires an application-level durable workflow.

## Troubleshooting

- Missing lock or unresolved SDK packages: the publication gate is still open.
- No immediate response: ensure `configuration.returnImmediately` is true.
- Unexpected terminal state or JSON-RPC error: inspect the captured evidence;
  the verifier does not turn failures into successful reports.
- Public method rejected: verify the target project's native A2A support before
  assuming the local endpoint and public gateway expose identical operations.

## Next steps

- [Echo](../echo/README.md)
- [Task persistence](../task-persistence/README.md)
