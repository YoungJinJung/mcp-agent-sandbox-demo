"""Provision only the dedicated local Floci EKS cluster; never call AWS endpoints."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state" / "floci"
ENDPOINT = "http://127.0.0.1:14566"
CLUSTER = "mcp-agent-sandbox-demo"
CONTEXT = "floci-mcp-agent-sandbox-demo"
REGION = "us-east-1"

# Child processes must not inherit a real AWS profile or temporary credentials.
env = os.environ.copy()
for key in list(env):
    if key.startswith("AWS_"):
        del env[key]
env.update({
    "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION,
    "AWS_ENDPOINT_URL": ENDPOINT, "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_CONFIG_FILE": str(STATE / "aws-config"),
    "AWS_SHARED_CREDENTIALS_FILE": os.devnull, "AWS_PAGER": "",
})


def aws(*args):
    result = subprocess.run(
        ["aws", "--endpoint-url", ENDPOINT, "--region", REGION,
         "--output", "json", *args], env=env, check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def k(*args):
    return subprocess.run(
        ["kubectl", "--kubeconfig", str(STATE / "kubeconfig"), *args],
        env=env, check=True, capture_output=True, text=True,
    )


def up():
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "aws-config").write_text("[default]\nregion = us-east-1\n")
    for _ in range(90):
        try:
            with urllib.request.urlopen(ENDPOINT + "/_localstack/health", timeout=2):
                break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
    else:
        raise RuntimeError("Floci did not become ready on localhost:14566")

    credentials = STATE / "credentials.json"
    if not credentials.exists():
        if "mcp-demo-admin" not in [u["UserName"] for u in aws("iam", "list-users")["Users"]]:
            aws("iam", "create-user", "--user-name", "mcp-demo-admin")
        key = aws("iam", "create-access-key", "--user-name", "mcp-demo-admin")["AccessKey"]
        with open(credentials, "w", opener=lambda p, f: os.open(p, f, 0o600)) as out:
            json.dump(key, out)
    key = json.loads(credentials.read_text())
    env.update(AWS_ACCESS_KEY_ID=key["AccessKeyId"], AWS_SECRET_ACCESS_KEY=key["SecretAccessKey"])

    if CLUSTER not in aws("eks", "list-clusters")["clusters"]:
        aws("eks", "create-cluster", "--name", CLUSTER,
            "--role-arn", "arn:aws:iam::000000000000:role/mcp-demo-eks",
            "--resources-vpc-config", '{"subnetIds":[],"securityGroupIds":[]}',
            "--kubernetes-version", "1.35")
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        cluster = aws("eks", "describe-cluster", "--name", CLUSTER)["cluster"]
        if cluster["status"] == "ACTIVE":
            break
        if cluster["status"] == "FAILED":
            raise RuntimeError("Floci EKS failed; inspect docker logs mcp-demo-floci")
        time.sleep(3)
    else:
        raise RuntimeError("Floci EKS did not become ACTIVE within 300 seconds")
    endpoint = cluster["endpoint"]
    if endpoint not in {"https://localhost:16650", "https://127.0.0.1:16650"}:
        raise RuntimeError(f"Refusing unexpected Kubernetes endpoint: {endpoint}")

    subprocess.run([
        "aws", "--endpoint-url", ENDPOINT, "--region", REGION,
        "eks", "update-kubeconfig", "--name", CLUSTER,
        "--kubeconfig", str(STATE / "kubeconfig"), "--alias", CONTEXT,
        "--user-alias", "floci-demo-admin",
    ], env=env, check=True, capture_output=True)
    # Persist only locally generated emulator credentials, never the user's AWS keys.
    exec_env = {key: value for key, value in env.items() if key.startswith("AWS_")}
    exec_env.update(AWS_PROFILE="default", AWS_SESSION_TOKEN="", AWS_SECURITY_TOKEN="")
    k("config", "set-credentials", "floci-demo-admin",
      *[f"--exec-env={key}={value}" for key, value in exec_env.items()])
    (STATE / "kubeconfig").chmod(0o600)
    for _ in range(60):
        nodes = json.loads(k("--context", CONTEXT, "get", "nodes", "-o", "json").stdout)
        if nodes["items"]:
            break
        time.sleep(2)
    else:
        raise RuntimeError("No Kubernetes node registered")
    k("--context", CONTEXT, "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=180s")
    print(f"Floci EKS ACTIVE: {endpoint}; Kubernetes nodes Ready", flush=True)


def down():
    if CLUSTER in aws("eks", "list-clusters")["clusters"]:
        aws("eks", "delete-cluster", "--name", CLUSTER)
    deadline = time.monotonic() + 90
    while CLUSTER in aws("eks", "list-clusters")["clusters"]:
        if time.monotonic() > deadline:
            raise RuntimeError("Floci EKS deletion timed out")
        time.sleep(2)
    print("Deleted dedicated Floci EKS cluster")


if __name__ == "__main__":
    try:
        {"up": up, "down": down}[sys.argv[1]]()
    except subprocess.CalledProcessError as exc:
        # AWS errors carry diagnostics, but successful IAM responses contain keys.
        print(exc.stderr or "Local provisioning command failed", file=sys.stderr)
        raise SystemExit(1)
