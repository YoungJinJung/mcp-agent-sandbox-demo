"""Exercise the upstream MCP server over one Streamable HTTP session.

This script is also the integration check: it verifies actual pod execution,
file round trips, command failures, and session ownership without an LLM key.
"""

import argparse
import asyncio
import json

from fastmcp import Client
from fastmcp.exceptions import ToolError

NAMESPACE = "mcp-demo"
PROGRAM = '''import json
import socket
from pathlib import Path

numbers = [2, 3, 5, 7, 11]
result = {"numbers": numbers, "sum": sum(numbers), "hostname": socket.gethostname()}
Path("result.json").write_text(json.dumps(result))
print(json.dumps(result))
'''


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


async def run(url):
    async with Client(url, timeout=240) as client:
        tools = {tool.name for tool in await client.list_tools()}
        required = {"create_sandbox", "get_sandbox_status", "upload_file",
                    "execute_command", "download_file", "delete_sandbox"}
        check(required <= tools, f"Missing tools: {required - tools}")
        print(f"[1/7] Connected: {len(tools)} MCP tools", flush=True)
        created = await client.call_tool("create_sandbox", {
            "warmpool": "python-demo", "namespace": NAMESPACE,
            "sandbox_ready_timeout": 180, "shutdown_after_seconds": 300,
        })
        claim = created.structured_content["sandbox_claim_name"]
        target = {"sandbox_claim_name": claim, "namespace": NAMESPACE}
        print(f"[2/7] Created claim: {claim}", flush=True)
        try:
            status = await client.call_tool("get_sandbox_status", target)
            check(status.structured_content["ready"], f"Sandbox not ready: {status.structured_content}")
            uploaded = await client.call_tool("upload_file", {
                **target, "path": "calculate.py", "content": PROGRAM,
            })
            check(uploaded.structured_content["bytes_written"] == len(PROGRAM.encode()),
                  "Upload byte count differs")
            print("[3/7] Uploaded calculate.py", flush=True)
            executed = await client.call_tool("execute_command", {
                **target, "command": "python /workspace/calculate.py",
            })
            check(executed.structured_content["exit_code"] == 0, str(executed.structured_content))
            result = json.loads(executed.structured_content["stdout"])
            check(result["sum"] == 28 and bool(result["hostname"]),
                  f"Unexpected calculation result: {result}")
            print(f"[4/7] Python ran inside pod: {json.dumps(result)}", flush=True)
            downloaded = await client.call_tool("download_file", {
                **target, "path": "result.json",
            })
            check(json.loads(downloaded.structured_content["content"]) == result,
                  "Downloaded file differs from stdout")
            print("[5/7] Downloaded result.json: matches stdout", flush=True)
            failed = await client.call_tool("execute_command", {
                **target, "command": 'python -c "raise SystemExit(7)"',
            })
            check(failed.structured_content["exit_code"] == 7, "Command failure was not preserved")
            # A separate MCP session must not be able to adopt this claim.
            async with Client(url, timeout=30) as other:
                try:
                    await other.call_tool("get_sandbox_status", target)
                except ToolError as exc:
                    expected = f"Sandbox claim '{claim}' is not found in namespace '{NAMESPACE}'."
                    check(expected in str(exc), f"Unexpected second-session error: {exc}")
                else:
                    raise RuntimeError("Another session accessed the claim")
            print("[6/7] Exit code 7 preserved; other session denied", flush=True)
        finally:
            # Keep the original session alive until its claim is deleted.
            await client.call_tool("delete_sandbox", target)
            print(f"[7/7] Deleted claim: {claim}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18000/mcp")
    args = parser.parse_args()
    asyncio.run(run(args.url))
