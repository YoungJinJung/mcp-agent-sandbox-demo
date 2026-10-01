# 실행 검증 기록

검증일: kind 2026-09-30, Floci 2026-10-01. 이 기록은 실제 로컬 실행 결과입니다.

## Floci EKS / DevTools 검증 (2026-10-01)

macOS arm64 / OrbStack에서 Floci `2.1.0`의 real EKS 모드로 실제 k3s
`v1.35.8+k3s1` 노드를 만들었습니다. 컨트롤러·SDK·MCP 버전은 아래 kind 기록과 같습니다.
이미지 digest와 구성은 `compose.floci.yaml`에 고정했습니다.

- AWS CLI로 로컬 Floci의 IAM 사용자·키와 EKS 클러스터를 생성했습니다.
- `aws eks update-kubeconfig` 및 exec 방식 `aws eks get-token`으로 노드 Ready를 확인했습니다.
- 잘못된 AWS 프로필·키를 부모 환경변수에 넣어도 전용 kubeconfig의 실습용 키로 접속했습니다.
- `make floci-demo`: MCP 도구 탐색, Pod 실행, 파일 왕복, 종료 코드 보존,
  다른 세션 접근 거부 등 기존 7개 검증을 통과했습니다.
- `make floci-ci`: 샘플의 예상 assertion 실패(종료 코드 1)를 재현하고,
  소스만 수정한 뒤 동일한 테스트의 통과(종료 코드 0)를 확인했습니다.
- CI 클라이언트가 실패한 실행에서도 `finally`의 claim 삭제가 이뤄졌습니다.
- 실습 키와 kubeconfig의 파일 권한은 `0600`이며 git에서 제외됩니다.
- 최종 설정으로 새 Floci 클러스터 생성 → 두 데모 실행 → 삭제를 연속 검증했습니다.
  삭제 후 전용 컨테이너·데이터 볼륨·네트워크가 남지 않았습니다.
- 공통 실행 스크립트 변경 후 기존 kind의 `make demo`도 7개 검증을 통과했습니다.

CI 실행 예시:

```text
Created sandbox: sandbox-claim-612169e6
before: exit_code=1
after: exit_code=0
PASS: failure reproduced; predefined patch passes the unchanged test
Deleted sandbox: sandbox-claim-612169e6
PASS: MCP round trip completed; no demo claims remain.
```

실행 로그와 diff는 `.state/floci/ci-report.json`에 저장됩니다.
이는 의도적으로 실패하는 작은 Python 샘플과 미리 정한 패치를 검증한 것이며,
임의의 CI 재현이나 LLM의 자동 수정 기능을 검증한 것은 아닙니다.

구성 중 확인한 사항:

- k3s Docker 이미지의 이미지 적재는 `k3s ctr` 대신 별도 `ctr` 바이너리로 실행했습니다.
- EKS `ACTIVE`와 노드 등록 사이에 간격이 있어, 노드가 생긴 뒤 Ready를 기다립니다.
- upstream 런타임은 명령을 `shlex.split` 후 직접 실행합니다. `cd ... && ...` 같은
  셸 구문 대신 `/workspace` 작업 디렉터리에서 Python을 직접 실행합니다.
- 이 실습은 이미지를 직접 적재하므로 ECR 레지스트리 자동 생성과 mirror를 껐습니다.
  전용 EKS 클러스터 삭제 시 데이터 볼륨도 정리하도록 설정했습니다.
- k3s API의 Docker 포트 바인딩은 모든 인터페이스입니다. 이 구성을 인터넷에 노출하지 않습니다.

AWS 관리형 EKS, VPC 네트워킹, IAM 권한 경계 및 운영 보안과의 동일성은 검증 범위 밖입니다.

## 환경

| 구성 | 검증 값 |
|---|---|
| 호스트 | macOS / Apple Silicon (arm64) |
| 컨테이너 엔진 | OrbStack, Docker Engine 29.4.0 |
| kind | v0.33.0 |
| Kubernetes 노드 | v1.35.8 / linux-arm64 |
| kubectl | v1.35.8 |
| uv | 0.12.1 |
| 로컬 MCP 클라이언트 Python | 3.12.13 |
| agent-sandbox controller | v1.0.4 |
| k8s-agent-sandbox SDK | 0.5.6 |
| FastMCP | 3.4.4 |

컨트롤러 매니페스트, upstream 소스 아카이브, 컨테이너 베이스 이미지, 노드 이미지 및
Python 패키지를 고정했습니다. 정확한 SHA-256은 Dockerfile, scripts/demo.sh,
requirements.lock을 참조하세요.

## 통과한 검증

- `make check`: Bash와 Python 구문 검사
- `make up`: 실제 kind 클러스터, CRD, 컨트롤러, MCP 서버와 warm pool 배포
- `make demo`: 실제 Streamable HTTP 세션에서 8개 도구 탐색
- SandboxClaim 생성 및 Sandbox Ready 확인
- Python 파일 업로드, 계산 실행, stdout의 합계 `28` 확인
- 결과 JSON 다운로드 및 stdout과의 일치 확인
- 실패하는 명령의 종료 코드 `7` 보존
- 별도 MCP 세션에서 같은 claim 접근 시 정확한 소유권 오류 확인
- 정상 종료 후 claim 0개 및 포트 18000의 포워딩 프로세스 종료 확인
- MCP ServiceAccount의 다른 네임스페이스 claim 생성 권한 거부 확인
- 개발 중 실행 취소(SIGINT) 시 claim과 포트포워딩 정리 확인
- `make down`: 전용 kind 클러스터 삭제
- 최종 설정으로 `make down` → `make up` → `make demo`를 연속 실행해 새 클러스터에서도 통과

## 실제 출력 예시

```text
[1/7] Connected: 8 MCP tools
[2/7] Created claim: sandbox-claim-1d7c4900
[3/7] Uploaded calculate.py
[4/7] Python ran inside pod: {"numbers": [2, 3, 5, 7, 11], "sum": 28, "hostname": "python-demo-fm5m4"}
[5/7] Downloaded result.json: matches stdout
[6/7] Exit code 7 preserved; other session denied
[7/7] Deleted claim: sandbox-claim-1d7c4900
PASS: MCP round trip completed; no demo claims remain.
```

## 설정에 반영한 확인 사항

1. **Python SDK 패치 버전도 중요합니다.** `0.5.0`에는 MCP 서버의
   `get_sandbox_status`가 사용하는 `AsyncSandbox.status()`가 없습니다.
   upstream의 `~=0.5.0` 범위에 속하며 해당 메서드를 포함하는 `0.5.6`을 고정했습니다.
2. **샌드박스 생성과 네트워크 연결은 별개입니다.** 이 구성은 샌드박스별 Service 생성에
   의존하지 않습니다. `K8S_SANDBOX_CONNECTION__USE_POD_IP=true`로 Sandbox 상태의
   `podIPs`를 읽어 런타임에 연결합니다.
3. **macOS 잠금 파일을 그대로 Linux에 적용하면 패키지가 빠질 수 있습니다.**
   `uv pip compile --universal`로 플랫폼별 의존성과 해시를 함께 기록했습니다.
4. **FastMCP의 `.data`는 동적 Python 모델일 수 있습니다.** 데모는 딕셔너리 형태의
   MCP 구조화 결과인 `.structured_content`를 읽습니다.

## 검증 범위

이 기록은 macOS arm64 호스트와 Linux arm64 컨테이너에서의 로컬 실습입니다.
Linux 호스트, amd64, Windows 및 운영용 다중 사용자 환경은 별도로 검증하지 않았습니다.
로그의 hostname은 실제 런타임 Pod 이름이며, claim과 Pod 이름은 실행마다 달라집니다.

이 테스트는 Pod를 강한 보안 격리 경계로 검증한 것이 아닙니다.
네트워크 정책 시행, 악성 코드 차단, 사용자 인증 또는 모델의 도구 선택 정확도는 범위 밖입니다.
