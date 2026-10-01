"""Reproduce a known CI failure and verify a predefined patch in a real sandbox.

No LLM is used. The same unmodified regression test runs before and after the
patch, and both command results are saved locally for inspection.
"""

import argparse
import asyncio
import difflib
import json
from pathlib import Path

from fastmcp import Client

SAMPLE = Path(__file__).parent / "sample"


async def run(url, output):
    source = (SAMPLE / "rollout.py").read_text()
    broken = "return available > 0"
    if source.count(broken) != 1:
        raise RuntimeError("Expected exactly one sample bug to patch")
    fixed = source.replace(broken, "return available >= desired")
    report = {"scenario": "incomplete replica rollout", "patch": "".join(
        difflib.unified_diff(source.splitlines(keepends=True), fixed.splitlines(keepends=True),
                             fromfile="before/rollout.py", tofile="after/rollout.py"))}
    async with Client(url, timeout=240) as client:
        created = await client.call_tool("create_sandbox", {
            "warmpool": "python-demo", "namespace": "mcp-demo",
            "sandbox_ready_timeout": 180, "shutdown_after_seconds": 300,
        })
        target = {"sandbox_claim_name": created.structured_content["sandbox_claim_name"],
                  "namespace": "mcp-demo"}
        report["claim"] = target["sandbox_claim_name"]
        print(f"Created sandbox: {report['claim']}", flush=True)
        try:
            for name in ("rollout.py", "test_rollout.py"):
                await client.call_tool("upload_file", {
                    **target, "path": name, "content": (SAMPLE / name).read_text(),
                })
            # -B prevents a stale bytecode cache from obscuring the patched source.
            command = "python -B -m unittest -v test_rollout"
            for stage in ("before", "after"):
                if stage == "after":
                    await client.call_tool("upload_file", {
                        **target, "path": "rollout.py", "content": fixed,
                    })
                result = await client.call_tool("execute_command", {**target, "command": command})
                report[stage] = result.structured_content
                print(f"{stage}: exit_code={report[stage]['exit_code']}", flush=True)
            before, after = report["before"], report["after"]
            if (before["exit_code"] != 1 or "True is not false" not in before["stderr"]
                    or "FAILED (failures=1)" not in before["stderr"]):
                raise RuntimeError("Expected replica-count regression was not reproduced")
            if after["exit_code"] != 0 or "Ran 1 test" not in after["stderr"]:
                raise RuntimeError("Patched source did not pass the same regression test")
            print("PASS: failure reproduced; predefined patch passes the unchanged test", flush=True)
        finally:
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, indent=2) + "\n")
                print(f"Report: {output}", flush=True)
            finally:
                await client.call_tool("delete_sandbox", target)
                print(f"Deleted sandbox: {report['claim']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18000/mcp")
    parser.add_argument("--output", type=Path, default=Path(".state/ci-report.json"))
    args = parser.parse_args()
    asyncio.run(run(args.url, args.output))
