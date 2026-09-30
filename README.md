# MCP × Kubernetes Agent Sandbox

**MCP로 Kubernetes 샌드박스를 만들고, Python 코드를 실행하고, 결과를 가져오는 로컬 실습.**

A reproducible, Korean-first tutorial for creating Kubernetes sandboxes through
MCP, running Python, retrieving files, and cleaning up. Uses the upstream
[agent-sandbox MCP server](https://github.com/kubernetes-sigs/agent-sandbox/tree/87a4695e620f6057fef3f6b0c0251f2986b1c36f/clients/integrations/mcp-server).
No model API key is required: a deterministic Python MCP client makes real
Streamable HTTP tool calls against a real Kubernetes cluster.

## 무엇을 배우나요?

- MCP의 `tools/list`, `tools/call`이 실제 인프라 작업으로 연결되는 과정
- `SandboxTemplate` → `SandboxWarmPool` → `SandboxClaim`의 관계
- 하나의 MCP 세션에서 생성한 샌드박스에 파일을 올리고 코드를 실행하는 방법
- 명령 실패 처리, 세션별 소유권 검사, 작업 후 리소스 정리

이 데모는 모델의 도구 선택을 구현하지 않습니다. 도구 호출 순서를 고정해 프로토콜과
실행 환경을 먼저 확인합니다. 따라서 LLM 서비스 가입이나 유료 API 호출 없이 실행할 수 있습니다.

## 구조

```mermaid
sequenceDiagram
    participant C as demo.py (MCP client)
    participant M as Upstream MCP server (Pod)
    participant K as Kubernetes / agent-sandbox
    participant P as Python runtime (Pod)
    C->>M: tools/list
    C->>M: create_sandbox
    M->>K: Create SandboxClaim
    K-->>M: Warm pool sandbox assigned and ready
    C->>M: upload_file(calculate.py)
    M->>P: Write file over runtime HTTP API
    C->>M: execute_command(python ...)
    M->>P: Run Python
    P-->>C: stdout / stderr / exit_code via MCP server
    C->>M: download_file(result.json)
    C->>M: delete_sandbox
    M->>K: Delete claim; controller cleans up sandbox
```

MCP는 **도구 호출을 주고받는 프로토콜**입니다. 샌드박스의 생성·준비·삭제는 Kubernetes의
agent-sandbox 컨트롤러가 맡고, 실제 Python 실행은 별도 런타임 Pod에서 일어납니다.
이 데모의 MCP 서버와 Python 런타임은 같은 빌드 이미지를 서로 다른 명령으로 실행합니다.
두 서버 모두 upstream 코드를 그대로 사용합니다. MCP 서버는 Sandbox 상태의 Pod IP를
읽어 런타임에 직접 연결합니다. 별도 sandbox-router는 필요하지 않습니다.

## 준비물

macOS 또는 Linux에서 다음 명령이 필요합니다.

- 로컬 Docker 엔진: Docker Desktop, OrbStack 등. `docker info`가 성공해야 합니다.
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/): 검증 버전 `v0.33.0`
- `kubectl` 1.35.x 권장, `make`, Bash, `curl`, Python 3
- [uv](https://docs.astral.sh/uv/getting-started/installation/): 데모 클라이언트의 Python 3.12 환경 관리

macOS에서 빠져 있는 도구만 설치하는 예:

```bash
brew install kind kubectl uv
```

최초 실행에는 Kubernetes·Python 이미지와 Python 패키지를 내려받을 네트워크 및 디스크 공간이
필요합니다. 로컬 Docker VM에는 여유 메모리 약 4 GB 이상을 권장합니다.

## 빠른 실행

```bash
git clone https://github.com/YoungJinJung/mcp-agent-sandbox-demo.git
cd mcp-agent-sandbox-demo
make up
make demo
make status
```

Dockerfile이나 의존성을 변경한 뒤에는 `make down` 후 `make up`으로 다시 배포합니다.

`make up`은 다음을 수행합니다.

1. `mcp-agent-sandbox-demo`라는 전용 kind 클러스터를 생성합니다.
2. agent-sandbox `v1.0.4` 컨트롤러와 확장 CRD를 설치합니다.
3. 고정된 upstream 커밋으로 MCP 서버·런타임 이미지를 빌드해 kind에 적재합니다.
4. `mcp-demo` 네임스페이스에 MCP 서버, 템플릿, 준비된 샌드박스 1개를 유지하는 warm pool을 배포합니다.

별도의 `.state/kubeconfig`를 사용합니다. 스크립트는 사용자의 기본 kubeconfig를 수정하지 않으며,
모든 `kubectl` 명령에 전용 파일과 `kind-mcp-agent-sandbox-demo` 컨텍스트를 명시합니다.
같은 이름의 기존 kind 클러스터가 있으면 재사용하므로 이 이름은 실습용으로만 사용하세요.

`make demo`는 일시적으로 **127.0.0.1:18000**에 MCP 서버를 포워딩하고, 실행이 끝나면
포트포워딩을 종료합니다. MCP는 클러스터 외부에 LoadBalancer나 Ingress로 노출하지 않습니다.

출력 예시 — claim과 hostname은 실행마다 달라집니다:

```text
[1/7] Connected: 8 MCP tools
[2/7] Created claim: sandbox-claim-...
[3/7] Uploaded calculate.py
[4/7] Python ran inside pod: {"numbers": [2, 3, 5, 7, 11], "sum": 28, "hostname": "..."}
[5/7] Downloaded result.json: matches stdout
[6/7] Exit code 7 preserved; other session denied
[7/7] Deleted claim: sandbox-claim-...
PASS: MCP round trip completed; no demo claims remain.
```

## 코드 따라가기

실습의 핵심은 [demo.py](demo.py)에 있습니다.

```python
async with Client("http://127.0.0.1:18000/mcp") as client:
    created = await client.call_tool("create_sandbox", {
        "warmpool": "python-demo",
        "namespace": "mcp-demo",
    })
    # Use this same client/session for upload, execute, download, and delete.
```

- **템플릿**은 런타임 이미지, CPU·메모리, 읽기 전용 루트 파일시스템과 작업 볼륨을 정의합니다.
- **Warm pool**은 요청 전에 준비된 샌드박스를 유지해 시작 지연을 줄입니다.
- **Claim**은 사용자가 샌드박스를 요청하는 리소스입니다. 클라이언트는 할당이 준비될 때까지 기다립니다.
- **MCP 세션**은 도구 호출의 소유권 범위입니다. 새 클라이언트 세션에서 기존 claim 이름만 전달하면
  upstream 서버의 소유권 검사에서 거부됩니다. 이 검사는 사용자 인증을 대체하지 않습니다.
- 실행 결과 파일은 샌드박스의 `/workspace`에 저장합니다. `download_file`로 읽은 JSON이
  `execute_command`의 stdout과 같은지 확인합니다.
- 중간 검증이 실패해도 `finally`에서 같은 세션으로 claim 삭제를 요청합니다.

고의로 종료 코드 `7`을 반환하는 명령도 실행합니다. MCP 도구 호출 성공과 샌드박스 안 명령의
성공은 별개이므로, 클라이언트가 `exit_code`를 검사해야 한다는 점을 보여줍니다.

## 검증

```bash
make check  # Shell/Python 구문 검사
make demo   # 실제 MCP → Kubernetes → 런타임 왕복 검증
```

`make demo`는 다음 중 하나라도 실패하면 0이 아닌 종료 코드를 반환합니다.

- 필요한 MCP 도구 발견 및 샌드박스 Ready 상태
- 업로드 바이트 수, Python 계산 결과 `28`, 결과 파일 왕복 일치
- 명령의 실패 코드 보존, 다른 세션의 claim 접근 거부
- 실행 후 demo claim 삭제 확인

가장 최근 실행의 표준 출력은 `.state/last-run.log`에 저장합니다.
실제 검증 환경과 결과는 [docs/validation.md](docs/validation.md)에 기록합니다.

## 정리

```bash
make down
```

전용 kind 클러스터 전체를 삭제합니다. `make demo` 이후 warm pool Pod 하나가 남는 것은 정상입니다.
풀의 목표 수량이 1이므로 컨트롤러가 새 대기 샌드박스를 준비하기 때문입니다.
`make down` 이후에도 로컬 Docker 이미지, `.venv`, `.state` 파일은 재실행을 위해 남습니다.

프로세스를 강제 종료하거나 MCP 연결이 끊기면 `finally`의 삭제 요청이 완료되지 않을 수 있습니다.
claim에는 5분 후 종료하도록 lifecycle을 설정하지만, 실습 종료 시 전체 정리는 `make down`으로
확인하세요. 샌드박스의 `emptyDir` 파일은 Pod 삭제 시 사라집니다.

## 문제 해결

리소스와 이벤트 확인:

```bash
make status
kubectl --kubeconfig .state/kubeconfig --context kind-mcp-agent-sandbox-demo \
  -n mcp-demo get events --sort-by=.lastTimestamp
kubectl --kubeconfig .state/kubeconfig --context kind-mcp-agent-sandbox-demo \
  -n mcp-demo logs deployment/mcp-server
```

- **`kind: command not found`**: kind를 설치하고 PATH에 추가합니다.
- **이미지 다운로드 실패**: Docker의 네트워크·프록시 설정을 확인하고 `make up`을 재실행합니다.
- **`ErrImageNeverPull`**: 이 데모는 로컬 빌드 이미지만 사용합니다. `make up`으로 kind에 다시 적재합니다.
- **18000 포트 사용 중**: `.state/port-forward.log`에서 원인을 확인하고 해당 포트를 비운 뒤 재실행합니다.
- **`Sandbox ... not found` / 세션 변경**: 생성부터 삭제까지 같은 `Client` 컨텍스트를 유지합니다.
- **Pod가 Pending / OOMKilled**: Docker VM의 가용 메모리와 Pod 이벤트를 확인합니다.
- **매니페스트 체크섬 불일치**: 다운로드 내용을 확인합니다. 검증 코드를 제거해 우회하지 마세요.

## 범위와 보안

이 저장소는 **신뢰할 수 있는 자신의 코드를 실행하는 로컬 교육용 데모**입니다.
MCP 서버와 런타임 HTTP API에는 인증이 없습니다. MCP 서버의 ServiceAccount 권한은
`mcp-demo` 네임스페이스의 claim 생성·삭제와 sandbox 조회로 제한했습니다.
런타임 Pod에는 ServiceAccount 토큰을 마운트하지 않습니다.

다만 Pod는 호스트 커널을 공유하며, 이 설정에는 네트워크 격리나 gVisor/Kata 같은 추가 런타임
격리가 없습니다. 다른 Pod는 런타임 API에 접근할 수 있고, 실행 코드는 네트워크에 접근할 수 있습니다.
운영 클러스터나 다중 사용자 서비스, 신뢰할 수 없는 코드 실행에 이 설정을 그대로 사용하지 마세요.

## 고정한 버전과 출처

| 구성 | 버전 |
|---|---|
| agent-sandbox 컨트롤러 | `v1.0.4` — 다운로드 매니페스트 SHA-256 확인 |
| MCP 서버 / Python 런타임 소스 | `87a4695e620f6057fef3f6b0c0251f2986b1c36f` — 소스 아카이브 SHA-256 확인 |
| Python SDK | `k8s-agent-sandbox==0.5.6` |
| FastMCP | `3.4.4` |
| 컨테이너 Python | `3.12-slim` — Dockerfile에서 이미지 digest 고정 |
| kind 노드 | Kubernetes `v1.35.8` — 노드 이미지 digest 고정 |

Python 의존성은 [requirements.lock](requirements.lock)에 버전과 해시를 고정했습니다.
업데이트할 때는 [requirements.in](requirements.in)을 변경하고 다음 명령으로 다시 생성한 뒤
실제 데모를 검증합니다.

```bash
uv pip compile --universal --python-version 3.12 --generate-hashes --no-annotate --no-header \
  requirements.in -o requirements.lock
```

- [Upstream MCP 서버](https://github.com/kubernetes-sigs/agent-sandbox/tree/87a4695e620f6057fef3f6b0c0251f2986b1c36f/clients/integrations/mcp-server)
- [Upstream Python 런타임](https://github.com/kubernetes-sigs/agent-sandbox/blob/87a4695e620f6057fef3f6b0c0251f2986b1c36f/examples/python-runtime-sandbox/main.py)
- [MCP 공식 문서](https://modelcontextprotocol.io/docs/getting-started/intro)
- [FastMCP 클라이언트](https://gofastmcp.com/clients/client)

Apache-2.0 라이선스입니다. 재사용하는 upstream 소스의 저작권 헤더와 라이선스를 이미지에 보존합니다.
