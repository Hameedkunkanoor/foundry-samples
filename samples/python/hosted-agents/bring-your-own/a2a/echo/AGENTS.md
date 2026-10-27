# Coding Agent Instructions - A2A Echo

This sample is a **Microsoft Foundry hosted agent** that implements a native
A2A v1 echo agent with `a2a-sdk` and hosts it through
`azure-ai-agentserver-a2a`. It runs in
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents).

## Deployment mode

- **Direct code deployment:** `codeConfiguration` declares the Python runtime
  and entry point. A Dockerfile is not required.

## Key files

- `azure.yaml` - Foundry project and native A2A hosted-agent declaration
- `src/echo-a2a/main.py` - native A2A echo executor and server entry point
- `src/echo-a2a/test_client.py` - dedicated local or hosted A2A v1 client
- `src/echo-a2a/streaming_client.py` - explicit SSE client with live timings and wire evidence
- `src/echo-a2a/requirements.txt` - five direct, pinned dependencies
- `src/echo-a2a/requirements.lock.txt` - generated, fully resolved dependencies
- `README.md` - local, deployment, and E2E instructions

Do not commit Toolkit-generated `.vscode` files.

## Dependency workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`.

This is a reference-only alpha sample with a short direct-dependency list, as
requested by its author. Keep exact published pins in `requirements.txt` and
regenerate the full graph in `requirements.lock.txt`. This layout does not meet
the shared canonical artifact policy; do not disable or broaden shared checks.
Keep Echo independent of model clients and model configuration. LLM behavior
belongs in a separate sample and is not included in this reference PR.

## Development workflow

```powershell
cd src\echo-a2a
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
.\.venv\Scripts\python main.py
```

In another terminal:

```powershell
cd src\echo-a2a
.\.venv\Scripts\python test_client.py --message "hello"
```

The generic hosted-agent cloud runner does not yet support A2A Agent Card
discovery and JSON-RPC Task handling. Use `test_client.py` for local and hosted
E2E validation.

For streaming proof, use `streaming_client.py`. Its opt-in message metadata
enables paced Echo updates; ordinary messages retain their existing behavior.
Never count a unary fallback as a successful streaming test. The public
Foundry Card can suppress streaming discovery even when the explicit SSE path
works. Keep `.stream-results` output out of source control.

## Microsoft Foundry Skill

Install the Microsoft Foundry Skill for guided deployment and troubleshooting:

```bash
npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
```

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [A2A protocol](https://a2a-protocol.org/)
