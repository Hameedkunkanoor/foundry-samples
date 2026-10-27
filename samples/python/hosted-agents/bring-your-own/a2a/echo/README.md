<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A minimal native **A2A v1 echo agent** using the Bring Your Own approach in
Python. The native `a2a-sdk` owns the Agent Card, JSON-RPC, Task, artifact, and
executor behavior. `azure-ai-agentserver-a2a` adds Foundry's canonical routes,
request context, readiness, telemetry, and lifecycle.

The sample disables the native SDK's generic OpenTelemetry instrumentation
before importing `a2a`. The Agent Server host emits one semantic `SERVER` span
per A2A operation instead, including task, conversation, Agent Card, streaming,
and JSON-RPC error attributes. These attributes follow the development-stage
[OpenTelemetry A2A proposal](https://github.com/open-telemetry/semantic-conventions-genai/pull/195).

## How it works

The executor creates an A2A Task, adds `Echo: <input>` as an artifact, and
completes the Task. It does not import a model client, call an LLM, or require
model configuration. This PR keeps model-backed examples separate. The host exposes:

```text
POST /a2a
GET  /a2a/.well-known/agent-card.json
GET  /readiness
```

[`test_client.py`](src/echo-a2a/test_client.py) resolves the Agent Card and uses
native A2A streaming when the Card advertises it. The public gateway Card may
select unary `SendMessage` instead. Both paths verify the exact echo artifact
and a completed Task.

> [!NOTE]
> `InMemoryTaskStore` is used only for this deterministic echo sample. Use a
> durable native A2A `TaskStore` for production workloads that must survive
> container restarts, suspension, or replica movement.

## Prerequisites

1. Python 3.13.
2. Azure Developer CLI 1.27.1 or later with the `azure.ai.agents` extension.
3. Azure Developer CLI authentication for hosted E2E validation.

No model deployment, model quota, or model-access role is needed for Echo.
Its `azure.yaml` declares only the Foundry project and the hosted echo agent.

## Dependencies

[`requirements.txt`](src/echo-a2a/requirements.txt) is the five-package direct
dependency list. It pins the published alpha pair:

- `azure-ai-agentserver-a2a==1.0.0a20261026004`
- `azure-ai-agentserver-core==2.2.1a20261026004`

These versions were published by [pipeline run 20261026.4](https://dev.azure.com/azure-sdk/internal/_build/results?buildId=6999953)
from SDK commit `38cb2ae9a4`. Native `a2a-sdk` is pinned to `1.2.3`,
matching the validated runtime. This alpha includes the hosted tracing fix;
it does not include the pending automatic Foundry task-store integration.

[`requirements.lock.txt`](src/echo-a2a/requirements.lock.txt) contains the
generated full graph for reproducible installs. Edit `requirements.txt`, then
regenerate the separate lock. Neither file declares Azure AI Projects or the
OpenAI model client.

> [!IMPORTANT]
> This is a reference-only alpha layout. The short `requirements.txt` and
> separately named lock do not satisfy the repository's
> [canonical dependency-artifact policy](../../../DEPENDENCY_POLICY.md).
> The alphas are also unavailable to its PyPI-only resolution check. Do not
> merge this layout or relax shared checks to accommodate it.

These alphas are on the public Azure SDK development feed, not PyPI. Configure
the feed in the installation shell as shown below; registry configuration is
deliberately kept out of the portable dependency files.

## Run and test locally

```powershell
cd src\echo-a2a
python -m venv .venv
$env:PIP_INDEX_URL = "https://pkgs.dev.azure.com/azure-sdk/public/_packaging/azure-sdk-for-python/pypi/simple/"
$env:PIP_EXTRA_INDEX_URL = "https://pypi.org/simple/"
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
.\.venv\Scripts\python main.py
```

In another terminal:

```powershell
cd src\echo-a2a
.\.venv\Scripts\python test_client.py --message "hello"
```

Successful output includes:

```text
Echo: hello
```

Echo is always deterministic; there is no LLM toggle. The client checks the
exact echo artifact and completed Task state. If overriding the listening port,
set `A2A_AGENT_URL` to the same host and port so the Card advertises a reachable
`/a2a` URL.

### Prove streaming with visible, paced chunks

The optional demo sends eight lines as updates to one artifact, with a 500 ms
pause between updates. Normal Echo requests keep their existing one-artifact,
no-delay behavior. The opt-in is the message metadata `streaming_demo: true`;
the final text remains exactly `Echo: <input>`.

With the server running, use this client instead of the discovery-based client:

```powershell
cd src\echo-a2a
.\.venv\Scripts\python streaming_client.py --output .stream-results\local.json
```

For the deployed agent, from the same directory:

```powershell
$endpoint = "<project-endpoint>/agents/echo-a2a/endpoint/protocols/a2a?api-version=v1"
.\.venv\Scripts\python streaming_client.py --endpoint $endpoint --azure-auth `
  --session-id "<session-bound-to-the-updated-version>" `
  --output .stream-results\hosted.json
```

This client explicitly sends `SendStreamingMessage` and reads the HTTP response
incrementally. It prints each received chunk with its arrival time, saves the
exact request and JSON events when `--output` is supplied, checks append/final
flags and exact reconstructed text, and fetches the completed Task to verify
the stored artifact. It rejects non-SSE responses and delivery compressed into
less than 250 ms per expected chunk gap rather than silently accepting unary
fallback or a fully buffered stream.

The public Foundry Agent Card may currently advertise `streaming: false`, even
when the container card declares streaming and the explicit SSE path works.
Consequently, a discovery-based client with `streaming=True` can choose unary
`SendMessage`. This demo tests the explicit streaming path; it does not change
the public card or establish platform-wide support for reconnection/replay.

To run the demo regressions, from this sample root:

```powershell
.\src\echo-a2a\.venv\Scripts\python -m unittest discover -s tests -p test_streaming_demo.py
```

### Regenerate the dependency lock

From `src\echo-a2a`, with the same feed variables set:

```powershell
.\.venv\Scripts\python -m pip install "pip-tools==7.6.2"
.\.venv\Scripts\python -m piptools compile requirements.txt `
  --output-file requirements.lock.txt --no-annotate --no-emit-options --strip-extras
```

Commit the authoring list and regenerated lock together. The compact export
omits per-package dependency annotations and registry options.

## Deploy to Microsoft Foundry

The cloud dependency builder must also be configured to use the Azure SDK
development feed for these alpha versions. Local `PIP_*` variables do not
configure the remote build. A PyPI-only cloud build cannot install this alpha
pair; keep any deployment-only feed settings separate from the portable lock.

For a new project, from this sample directory:

```powershell
azd env new echo-a2a-dev
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION <supported-region>
azd provision
azd deploy
```

For an existing initialized project, skip provisioning and run
`azd deploy echo-a2a --no-prompt`. No model is provisioned by the Echo manifest.

For alpha smoke deployments, use a private build copy with the SDK feed as
`--index-url`, PyPI as `--extra-index-url`, and
`--constraint requirements.lock.txt` prepended to that copy's `requirements.txt`.
Keep those build-only options out of the source dependency list. This is the
same feed used for local installation, not a locally built SDK substitution.

After deployment, get the project endpoint:

```powershell
$projectEndpoint = azd env get-value AZURE_AI_PROJECT_ENDPOINT
$endpoint = "$projectEndpoint/agents/echo-a2a/endpoint/protocols/a2a?api-version=v1"
```

Run the dedicated hosted E2E client:

```powershell
cd src\echo-a2a
.\.venv\Scripts\python test_client.py `
  --endpoint $endpoint `
  --card-path agentCard/v1.0 `
  --azure-auth `
  --message "hosted hello"
```

The generic `azd ai agent invoke` and hosted-agent cloud test runner do not yet
implement A2A Agent Card discovery and JSON-RPC Task handling, so this sample
uses its dedicated native client.

## Observe the end-to-end trace

When the Foundry project has an Application Insights connection, Agent Server
uses the platform-provided connection string to export spans and logs. A
successful request produces:

1. An `invoke_agent echo-a2a` parent span with the Foundry deployment name and
   version, containing an A2A `SendMessage` or `SendStreamingMessage` server span.
   The child retains the native Agent Card name/version.
2. Log records for request receipt and `A2A_ECHO_COMPLETED`.
3. The returned Task ID on both spans, including when the request has no Task ID.
   Request-supplied `contextId` values provide conversation correlation; tracing
   does not harvest response-only context IDs or task states.

Both spans cover the full streaming response. HTTP and unary JSON-RPC errors
mark both spans failed; JSON-RPC error events inside HTTP-200 SSE streams are
not inspected for error classification. An LLM call or native implementation
spans are not required for hosted trace discovery. The portal also requires the
appropriate telemetry-read permissions.

There are no model spans or model calls in this sample. Hosted invocation
discovery and explicit streaming do not require a model call.

## Troubleshooting

- **`JSON-RPC Error -32099: The requested A2A operation is not supported for
  this hosted-agent target`** — the project or subscription has not been
  enabled for native hosted-agent A2A passthrough. Agent Card discovery may
  still work through the A2A Head, but `SendMessage` will not reach the native
  container. The Vienna code references
  `AgentsPlatform.A2A.EnablePassthrough`, but its reviewed threat model requires
  passthrough to remain disabled pending a separate security/privacy review.
  This is a service-side ECS rollout controlled by the Foundry Agents team, not
  a flag customers can enable on their Azure subscription.
- **HTTP 400 `endpoint-protocol-not-enabled` / missing `responses`** — keep both
  entries under `agentEndpoint.protocols` in `azure.yaml`. In the hosted test on
  2026-10-22, `azd deploy` accepted an A2A-only endpoint and readback confirmed
  only `a2a`, but public Agent Card discovery failed with:
  "Both 'a2a' and 'responses' protocols must be enabled on the endpoint."
  This is a Foundry gateway requirement, not an A2A SDK requirement. The
  container remains native A2A and does not implement a Responses route.
- **Agent Card is not defined** — keep the deployment-time `agentCard` metadata
  in `azure.yaml`; the native container card remains available at the canonical
  container route for passthrough.

## Next steps

- Replace `InMemoryTaskStore` with a durable native A2A `TaskStore`.
- Add skills and artifacts using native `a2a-sdk` types.
- Add another Agent Server protocol host to run multiple protocol paths in the
  same process.
