# Native A2A hosted-agent samples

These deterministic Python examples use `azure-ai-agentserver-a2a` and the
official `a2a-sdk`. No model is required.

| Sample | Learn |
|---|---|
| [Echo](echo/README.md) | Discover the Card, send a message, read the completed Task |
| [Long-running Tasks](long-running-tasks/README.md) | Return immediately, poll, and cancel a report |
| [Task persistence](task-persistence/README.md) | Read complete Task snapshots after reconstructing the server |

## Release gate

This draft targets the first A2A release `1.0.0b1` and Core `2.3.0b3`. They
are not yet both available on PyPI. Each runtime has a dependency project;
its `uv.lock` must be generated and committed after publication. Do not create
a lock containing private wheel paths or feed configuration.

Once packages are published, use uv 0.11.7 in each runtime directory:

```powershell
uv lock --default-index https://pypi.org/simple
uv sync --frozen
```

Commit all three locks, run the dependency policy with `--resolve`, then run
the native sample workflow before requesting merge.

## Testing during SDK development

Use an isolated environment with the exact A2A and Core wheels under test,
native `a2a-sdk==1.2.3`, and the Echo client's declared dependencies. Supply wheel
paths explicitly when installing; keep them out of committed dependency files.

From the repository root:

```powershell
python .github\scripts\test\test_a2a_samples.py
python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

The first command checks planning, RPC failures, output validation and CI
wiring without an SDK or Azure credentials. The second runs the actual sample
servers over HTTP, including cancellation and a writer/reader process restart.

The cloud pipeline selects `a2a`, uses Card discovery and JSON-RPC, and evaluates
each sample's public behavior contract. It does not invoke `/responses` or
`/invocations` as a substitute. SDK publication and public native A2A/state-store
availability remain separate prerequisites for cloud execution.
