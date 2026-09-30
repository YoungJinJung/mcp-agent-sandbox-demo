# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS upstream
ADD --checksum=sha256:c3e3655ad9c95d7b84b401e4c0fbe1138cb7eeaaed0a9d1becd35830042ab1e9 https://codeload.github.com/kubernetes-sigs/agent-sandbox/tar.gz/87a4695e620f6057fef3f6b0c0251f2986b1c36f /tmp/upstream.tar.gz
RUN mkdir /src && tar -xzf /tmp/upstream.tar.gz --strip-components=1 -C /src

FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY --from=upstream /src/clients/integrations/mcp-server/k8s_agent_sandbox_mcp_server ./k8s_agent_sandbox_mcp_server
COPY --from=upstream /src/examples/python-runtime-sandbox/main.py ./runtime.py
COPY --from=upstream /src/LICENSE ./UPSTREAM-LICENSE
USER 1000:1000
CMD ["uvicorn", "k8s_agent_sandbox_mcp_server.app:app", "--host", "0.0.0.0", "--port", "8000"]
