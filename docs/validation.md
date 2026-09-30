# 실행 검증 기록

검증일: 2026-09-30. 이 기록은 실제 로컬 실행 결과입니다.

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
