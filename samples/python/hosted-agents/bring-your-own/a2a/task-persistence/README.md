# What this sample demonstrates

Persist a complete native A2A Task, stop the server process, and retrieve the
same Task from a newly started process. Status, history and artifacts survive;
the executor does not run again to answer the read.

## How it works

[main.py](src/persistent-a2a/main.py) uses the host's default agent-scoped,
caller-isolated Foundry store when hosted. Locally it explicitly supplies a
`FoundryTaskStore`, backed by Core's file storage. The sample closes that
caller-owned local store during shutdown.

`AGENTSERVER_STATE_ROOT` selects the local data directory. Keep this directory
and the sample namespace unchanged when restarting. A2A Task IDs and context
IDs are opaque; neither is a Foundry session ID.

## Prerequisites

- Python 3.10+ and uv 0.11.7. Deployment uses Python 3.13.
- A writable local data directory; no Azure account is needed for local tests.
- For deployment: azd 1.27.1+, its `azure.ai.agents` extension, Azure CLI and
  a Foundry project with native A2A and managed state-store support.

> **SDK publication gate:** Publish A2A `1.0.0b1` and Core `2.3.0b3` on PyPI,
> then generate and commit `uv.lock`. Frozen installation and deployment are
> blocked until the lock and public dependency checks pass.

## Run locally and verify a restart

Clone this repository. From this sample directory, after the publication gate
is satisfied:

```powershell
cd src\persistent-a2a
uv sync --frozen --python 3.13
$env:AGENTSERVER_STATE_ROOT = Join-Path $PWD ".task-state"
uv run --frozen python main.py
```

From another terminal at the repository root:

```powershell
python .azure-pipelines\scripts\hosted-agents\scripts\invoke_hosted_agent_a2a.py `
  --message "remember this result" --expected-text "Persisted: remember this result" `
  --list-tasks
```

Copy the printed Task ID. Stop the server with Ctrl+C, start it again from the
same terminal and data directory, then run:

```powershell
python .azure-pipelines\scripts\hosted-agents\scripts\invoke_hosted_agent_a2a.py `
  --task-id "<task-id>"
```

Expected state is `TASK_STATE_COMPLETED`, with the exact artifact
`Persisted: remember this result`. This last command sends only `GetTask`;
it does not repeat `SendMessage`.

For VS Code debugging, open `src/persistent-a2a`, select its `.venv`
interpreter and set `AGENTSERVER_STATE_ROOT` in the debug environment. Use the
same directory for each debug run.

## Deploy with azd

From this sample directory, authenticate with `az login` and `azd auth login`,
choose a unique agent name in [azure.yaml](azure.yaml), and run:

```powershell
azd env new a2a-persistence-demo
azd provision
azd deploy
azd ai agent show --output json
```

No model or Dockerfile is required. For public verification, add
`--endpoint "<agent_endpoints.a2a>" --azure-auth` to the verifier commands.
The public gateway must support the requested send/get/list methods.

Hosted storage uses the platform's authenticated caller context. Do not
replace it with user-supplied identity headers. Reads must use the same
authenticated principal and agent storage namespace as the write. Another
caller must not obtain the saved Task.

The automated local restart test proves file-backed persistence across
independent processes. The cloud contract proves managed save/get/list; it
does not forcibly restart a hosted container or prove execution recovery.

## Tests and tracing

From the repository root, using an interpreter with the runtime dependencies:

```powershell
python .github\scripts\test\test_a2a_samples.py
python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

Tests compare full native Task snapshots after stopping the writer and starting
a reader. They also verify listing, missing-store reads without creation, and
local simulated-caller separation. The latter is not a cloud authentication test.
The [cloud contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/task-persistence/test-spec.yml)
uses native A2A save/get/list assertions.

With an OpenTelemetry exporter configured, inspect the A2A operation spans and
the `A2A_PERSISTED` log. Restart reads must not produce that executor log.

## Troubleshooting

- Task missing after local restart: check the data directory, namespace and
  caller context. Do not send a new message as a retrieval workaround.
- Storage authorization error: check the hosted identity/state-store setup.
- Public method rejected: check native A2A availability on the target project.
- Missing lock or unresolved dependencies: the SDK publication gate is open.

## Next steps

- [Echo](../echo/README.md)
- [Long-running Tasks](../long-running-tasks/README.md)
