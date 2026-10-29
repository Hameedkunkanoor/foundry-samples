# Coding Agent Instructions - Native A2A Task Persistence

This Microsoft Foundry sample preserves complete A2A Task snapshots. Local
storage is file-backed; hosted storage uses authenticated Foundry caller context.

## Deployment mode and key files

- `azure.yaml`: direct Python code deployment, no Dockerfile.
- `src/persistent-a2a/main.py`: executor, explicit local store and its shutdown.
- `src/persistent-a2a/pyproject.toml`: runtime dependency inputs.
- `README.md`: restart walkthrough, testing and deployment.

Do not commit Toolkit-generated `.vscode` files. Use `logging` for diagnostics.

## Dependencies

Follow the shared dependency policy. A2A `1.0.0b1` and Core `2.3.0b3` publication
is a merge gate. Generate and commit `uv.lock` from PyPI after publication;
never commit private wheel/feed references or fabricated locks.

## Validation

Keep the real-process writer/restart/reader test and full native Task comparison.
The reader must not send another message or rerun the executor. Preserve missing
store read behavior and caller isolation. Do not trust caller-supplied identity
headers in hosted code. Local simulated identities are not cloud authentication
proof. The cloud save/get/list contract is
`.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/task-persistence/test-spec.yml`.

Persistent snapshots do not recover unfinished executor work.
