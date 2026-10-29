# Coding Agent Instructions - Native A2A Report Tasks

This Microsoft Foundry sample hosts a native A2A report executor. Its two-second
asynchronous operation demonstrates immediate Task responses, polling and
cooperative cancellation without models or external application services.

## Deployment mode and key files

- `azure.yaml`: direct Python code deployment, no Dockerfile.
- `src/report-a2a/main.py`: executor and server entry point.
- `src/report-a2a/pyproject.toml`: runtime dependency inputs.
- `README.md`: local, test and deployment instructions.

Do not commit Toolkit-generated `.vscode` files. Use `logging` for diagnostics.

## Dependencies

Follow the shared Python hosted-agent dependency policy. SDK publication is a
merge gate; generate and commit the runtime's `uv.lock` after A2A `1.0.0b1`
and Core `2.3.0b3` are on PyPI. Never commit private wheel/feed references.

## Validation

Run the shared A2A helper and real-HTTP sample tests documented in the README.
Keep cancellation terminal, prevent report artifacts after cancellation, and
do not swallow `asyncio.CancelledError`. The public cloud contract is
`.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/long-running-tasks/test-spec.yml`.
Do not describe Task snapshot persistence as recovery of application work.
