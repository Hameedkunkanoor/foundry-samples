# Native A2A hosted-agent samples

These deterministic Python examples use `azure-ai-agentserver-a2a` and the
official `a2a-sdk`. No model is required.

| Sample | Learn |
|---|---|
| [Echo](echo/README.md) | Discover the Card, send a message, read the completed Task |
| [Long-running Tasks](long-running-tasks/README.md) | Return immediately, poll, and cancel a report |
| [Task persistence](task-persistence/README.md) | Read complete Task snapshots after reconstructing the server |

## Run without separate dependency setup

Install Python 3.10+ and uv 0.11.7 or later, then open a sample's runtime
directory and run:

```powershell
uv run --frozen python main.py
```

uv creates the environment and installs the committed lock automatically.
No separate `pip install`, `uv sync`, package-index flag, or feed environment
variable is needed. The first run needs internet access to download packages.

All three projects pin:

- `azure-ai-agentserver-a2a==1.0.0a20261029006`
- `azure-ai-agentserver-core==2.3.1a20261029006`
- Native `a2a-sdk==1.2.3`

Their `pyproject.toml` files map only the two AgentServer packages to the
public Azure SDK dev feed. Other packages come from PyPI. The lock keeps
compatible third-party versions, including native A2A's HTTPX dependency.
Do not enable prereleases globally with `--pre` or `--prerelease allow`.

No Azure credentials or model deployment are needed locally. Azure sign-in,
permissions and a Foundry project remain prerequisites for cloud deployment.

## Tests

From the repository root, the same uv workflow runs all seven real-HTTP tests:

```powershell
uv run --frozen --project samples\python\hosted-agents\bring-your-own\a2a\echo\src\echo-a2a `
  python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

Tests copy each runtime without its `.venv`, use an empty temporary uv cache,
and launch it with `uv run --frozen`. No feed flags or feed environment
variables are supplied. They verify Echo, cancellation, and complete Task
retrieval from a newly started process. CI separately checks native planning,
RPC failures, package-source configuration and lock contents.

The cloud pipeline selects `a2a`, uses Card discovery and JSON-RPC, and evaluates
each sample's public behavior contract. It does not invoke `/responses` or
`/invocations` as a substitute. Public native A2A/state-store availability is a
separate prerequisite for cloud execution.

## Repository dependency policy

These alphas are available on the dev feed, not PyPI. The shared repository
check still reports `PYREQ009` for those two package sources in each runtime.
Do not disable that check or add an unapproved exception. When the SDK is
published to PyPI, replace the alpha pins, remove the dev-feed source mappings,
and regenerate all three locks with uv 0.11.7.
