# Coding Agent Instructions - Native A2A Echo

This Microsoft Foundry sample hosts an official native A2A executor with
`azure-ai-agentserver-a2a`. Keep Echo deterministic and independent of models.

## Deployment mode

Direct code deployment uses `azure.yaml` and `src/echo-a2a/main.py`. No Dockerfile
is needed. Do not commit Toolkit-generated `.vscode` files.

## Dependencies

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`. Runtime inputs are in
`src/echo-a2a/pyproject.toml`. A2A `1.0.0b1` and Core `2.3.0b3` publication is a
merge gate: generate and commit `uv.lock` from PyPI only after both are available.
Never commit local wheels, private-feed configuration or fabricated lock data.

## Development and validation

Follow the README for local setup, native-client invocation and deployment.
Use standard `logging` for runtime diagnostics. The executor-based constructor
owns its default handler/storage; do not replace it with a caller-owned memory
store in the introductory sample.

From the repository root, run:

```powershell
python .github\scripts\test\test_a2a_samples.py
python -m unittest discover -s samples\python\hosted-agents\bring-your-own\a2a\tests -p "test_*.py" -v
```

The sample's public cloud behavior contract is under
`.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/echo/test-spec.yml`.
Keep exact artifact, native-client and Task retrieval checks. Never substitute
another protocol or weaken a shared policy to make an A2A check pass.
