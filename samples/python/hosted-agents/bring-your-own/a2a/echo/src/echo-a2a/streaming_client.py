# Copyright (c) Microsoft. All rights reserved.

"""Explicit native A2A SSE demo: print live events and optionally save wire evidence."""

import argparse
import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path

import httpx

DEMO_MESSAGE = (
    "Step 1: Receive the request.\n"
    "Step 2: Start the A2A Task.\n"
    "Step 3: Prepare the response.\n"
    "Step 4: Send this line immediately.\n"
    "Step 5: Keep the connection open.\n"
    "Step 6: Append more text to the same artifact.\n"
    "Step 7: Check the assembled response.\n"
    "Step 8: Complete the Task."
)


async def sse_events(response):
    data = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif not line and data:
            yield json.loads("\n".join(data))
            data.clear()
    if data:
        raise RuntimeError("The SSE stream ended before the final event separator")


async def run(args):
    trace_id, parent_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
    request = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "SendStreamingMessage",
        "params": {
            "message": {
                "messageId": uuid.uuid4().hex,
                "role": "ROLE_USER",
                "parts": [{"text": args.message}],
                "metadata": {"streaming_demo": True},
            }
        },
    }
    headers = {
        "Accept": "text/event-stream",
        "A2A-Version": "1.0",
        "traceparent": f"00-{trace_id}-{parent_id}-01",
    }
    if args.azure_auth:
        from azure.identity import AzureDeveloperCliCredential

        with AzureDeveloperCliCredential() as credential:
            token = credential.get_token("https://ai.azure.com/.default")
        headers["Authorization"] = "Bearer " + token.token
    if args.session_id:
        headers["x-agent-session-id"] = args.session_id

    evidence = {
        "endpoint": args.endpoint,
        "trace_id": trace_id,
        "parent_id": parent_id,
        "request": request,
        "events": [],
    }
    print("SENT " + json.dumps(request, ensure_ascii=False), flush=True)
    started = time.perf_counter()
    evidence["started_ns"] = time.time_ns()
    chunks, arrivals, task_ids, artifact_ids, states = [], [], set(), set(), []
    last_chunk = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=30)) as client:
            async with client.stream("POST", args.endpoint, headers=headers, json=request) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                evidence["content_type"] = content_type
                if not content_type.startswith("text/event-stream"):
                    raise RuntimeError(f"Expected SSE; received {content_type!r}. Unary fallback is not accepted.")
                async for event in sse_events(response):
                    elapsed = round((time.perf_counter() - started) * 1000, 2)
                    evidence["events"].append({"received_ms": elapsed, "payload": event})
                    if "error" in event:
                        raise RuntimeError(f"A2A protocol error: {event['error']}")
                    result = event.get("result", {})
                    for field, id_key in (("task", "id"), ("statusUpdate", "taskId"), ("artifactUpdate", "taskId")):
                        value = result.get(field)
                        if not isinstance(value, dict):
                            continue
                        task_ids.add(value[id_key])
                        if field == "artifactUpdate":
                            artifact = value["artifact"]
                            artifact_ids.add(artifact["artifactId"])
                            if last_chunk or bool(value.get("append", False)) != bool(chunks):
                                raise RuntimeError("Unexpected artifact append/final-chunk ordering")
                            text = "".join(part.get("text", "") for part in artifact.get("parts", []))
                            chunks.append(text)
                            arrivals.append(elapsed)
                            last_chunk = bool(value.get("lastChunk", False))
                            print(f"RECEIVED +{elapsed:8.2f}ms CHUNK {len(chunks):02d}: {text!r}", flush=True)
                        else:
                            state = value.get("status", {}).get("state")
                            if state:
                                states.append(state)
                                print(f"RECEIVED +{elapsed:8.2f}ms {state}", flush=True)

            expected = f"Echo: {args.message}"
            assembled = "".join(chunks)
            if len(task_ids) != 1 or len(artifact_ids) != 1:
                raise RuntimeError("Expected one Task and one incrementally updated artifact")
            if assembled != expected or not last_chunk or not states or states[-1] != "TASK_STATE_COMPLETED":
                raise RuntimeError("The stream did not produce the exact expected completed response")
            if len(chunks) < 2:
                raise RuntimeError("Use a multiline message so the demo can demonstrate incremental delivery")
            spread = arrivals[-1] - arrivals[0]
            if spread < (len(chunks) - 1) * 250:
                raise RuntimeError(f"Possible buffering: {len(chunks)} chunks arrived within only {spread:.2f}ms")
            check = await client.post(
                args.endpoint,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": uuid.uuid4().hex,
                    "method": "GetTask",
                    "params": {"id": next(iter(task_ids))},
                },
            )
            check.raise_for_status()
            task = check.json().get("result", {})
            stored = "".join(
                part.get("text", "") for artifact in task.get("artifacts", []) for part in artifact.get("parts", [])
            )
            if task.get("status", {}).get("state") != "TASK_STATE_COMPLETED" or stored != expected:
                raise RuntimeError("GetTask did not return the same completed artifact")
        evidence.update(
            {
                "outcome": "PASS",
                "task_id": next(iter(task_ids)),
                "chunks": len(chunks),
                "first_chunk_ms": arrivals[0],
                "last_chunk_ms": arrivals[-1],
                "delivery_spread_ms": round(spread, 2),
                "assembled_output": assembled,
                "sha256": hashlib.sha256(assembled.encode("utf-8")).hexdigest(),
                "get_task_verified": True,
            }
        )
        print("FINAL OUTPUT:\n" + assembled, flush=True)
        print(
            f"PASS: {len(chunks)} live chunks over {spread / 1000:.2f}s; exact output and GetTask verified.", flush=True
        )
        print(f"TRACE ID: {trace_id}", flush=True)
    except Exception as error:
        evidence.update({"outcome": "FAIL", "error": str(error)})
        raise
    finally:
        evidence["finished_ns"] = time.time_ns()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default="http://localhost:8088/a2a", help="Full JSON-RPC endpoint, including query parameters"
    )
    parser.add_argument("--azure-auth", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--message", default=DEMO_MESSAGE)
    parser.add_argument("--output", type=Path, help="Save exact sent JSON, received events and measured timings")
    asyncio.run(run(parser.parse_args()))
