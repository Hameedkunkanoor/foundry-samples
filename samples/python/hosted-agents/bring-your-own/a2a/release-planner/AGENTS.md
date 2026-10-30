# Coding Agent Instructions - Native A2A Release Planner

Follow the Python hosted-agent README and dependency templates.
This sample has three services sharing one runtime: coordinator, scope and risk.
Keep both remote native A2A calls mandatory. Never replace a failed delegation
with a model-only success or copy inbound credentials to remote endpoints.

Use the committed project/lock. The two AgentServer alpha sources remain subject
to the existing repository policy; do not weaken shared checks.
Do not commit credentials, local environments or deployment state.

Validate actual remote Task IDs, completion, run correlation and artifact shape.
Fixture-model tests exercise native HTTP delegation but are not proof of real
LLM or Azure execution. Report those separately.
Follow the shared template for the README; keep commands participant-facing.
