# PHASED Tracking: BeSA Agent Platform on k3d-Rancher

> **Credentials.** No credential below is real or stored in this repo. With the raw
> manifests, `scripts/new-dev-secrets.ps1` creates them before Phase 1's platform apply;
> the Helm chart generates its own. Commands that call LiteLLM expect the master key in
> `$env:LITELLM_KEY`, loaded once per shell:
>
> ```powershell
> $env:LITELLM_KEY = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl get secret litellm-secret -n ai-platform -o jsonpath='{.data.LITELLM_MASTER_KEY}')))
> ```

## Phase 1: Shared Platform Infra & LiteLLM Gateway

- **Status**: Implemented — Pending User Execution & Review
- **Target Manifests Created**:
  - [`k8s/namespaces/00-namespaces.yaml`](k8s/namespaces/00-namespaces.yaml)
  - [`k8s/platform/01-storage-pvcs.yaml`](k8s/platform/01-storage-pvcs.yaml)
  - [`k8s/platform/30-litellm.yaml`](k8s/platform/30-litellm.yaml)
  - [`scripts/verify-phase1.ps1`](scripts/verify-phase1.ps1)
- **Summary of Implemented Business/Infra Logic**:
  - Created isolated dual-namespace architecture (`ai-platform` and `agent-apps`).
  - Pre-provisioned `local-path` PersistentVolumeClaims (`pvc-postgres` 5Gi, `pvc-milvus-data` 10Gi) ready for stateful services.
  - Implemented LiteLLM AI Gateway Deployment, Service, and ConfigMap routing `deepseek-v4-flash:cloud`, `qwen2-5-3b-neuron`, and `default-model` directly to host-level Ollama at `http://host.k3d.internal:11434`.
- **Exact Terminal Deployment & Verification Commands**:
  ```powershell
  # 1. Go to the repo root
  cd agent-platform-k3d

  # 2. Apply Namespaces
  kubectl apply -f k8s/namespaces/00-namespaces.yaml

  # 3. Apply Storage PVCs
  kubectl apply -f k8s/platform/01-storage-pvcs.yaml

  # 4. Apply LiteLLM AI Gateway (with corrected probe & master key)
  kubectl apply -f k8s/platform/30-litellm.yaml

  # 5. Watch it transition cleanly to 1/1 Running
  kubectl rollout status deployment/litellm -n ai-platform

  # 6. Run Synthetic Phase 1 Verification Script
  .\scripts\verify-phase1.ps1

  # 7. Start port-forwarding again (Browser Access)
  kubectl port-forward svc/litellm -n ai-platform 4000:4000
  # Browser URLs & Credentials:
  # - Swagger API Docs: http://localhost:4000/docs (No auth required)
  # - LiteLLM inAdmin UI: http://localhost:4000/ui (Username: admin | Password: `UI_PASSWORD` in `litellm-secret`)
  # - Verified Ingress API Test Commands: See Phase 4, section 6.3 (tested on port 8081)
  ```
- **Review & Approval Gate**:
  - Phase 1: APPROVED by User.

---

## Phase 2: State & Observability Tier (Milvus + Langfuse + Postgres)

- **Status**: Implemented — Pending User Execution & Review
- **Target Manifests Created**:
  - [`k8s/platform/10-postgres.yaml`](k8s/platform/10-postgres.yaml)
  - [`k8s/platform/20-milvus.yaml`](k8s/platform/20-milvus.yaml)
  - [`k8s/platform/40-langfuse.yaml`](k8s/platform/40-langfuse.yaml)
  - [`scripts/verify-phase2.ps1`](scripts/verify-phase2.ps1)
- **Summary of Implemented Business/Infra Logic**:
  - Deployed PostgreSQL 16 StatefulSet backed by `pvc-postgres` with automatic secret provisioning.
  - Deployed Milvus Standalone (v2.4.13) with embedded etcd and local storage mounted on `pvc-milvus-data` exposing port 19530 (gRPC/REST) and 9091 (metrics/health).
  - Deployed Langfuse Web v2 with PostgreSQL dependency init-container, automated migrations, and secret encryption keys for full LLM telemetry.
- **Exact Terminal Deployment & Verification Commands**:
  ```powershell
  # 1. Apply PostgreSQL (Database for Langfuse)
  kubectl apply -f k8s/platform/10-postgres.yaml

  # 2. Apply Milvus Standalone (Vector Store)
  kubectl apply -f k8s/platform/20-milvus.yaml

  # 3. Apply Langfuse Web (Observability)
  kubectl apply -f k8s/platform/40-langfuse.yaml

  # 4. Wait for Rollouts
  kubectl rollout status statefulset/postgres -n ai-platform
  kubectl rollout status deployment/milvus -n ai-platform
  kubectl rollout status deployment/langfuse-web -n ai-platform

  # 5. Run Synthetic Phase 2 Verification Script
  .\scripts\verify-phase2.ps1

  # 6. Access Langfuse UI from Local Browser
  kubectl port-forward svc/langfuse-web -n ai-platform 3000:3000
  # Browser URL: http://localhost:3000
  # Note: Use an Incognito/Private window or clear localhost:3000 cookies if an /error redirect occurs from prior local apps.
  # Sign-up Instructions:
  # - Click the "Sign Up" tab (no default credentials on a fresh installation).
  # - Enter any dummy email (e.g., admin@local.test) and password; real email/SMTP is not required.
  # - The first registered user automatically becomes the instance Admin/Owner.
  ```
- **Review & Approval Gate**:
  - Phase 2: APPROVED by User.

---

## Phase 3: Agent & Tooling Tier (MCP + Sandbox + Gateway + Agents)

- **Status**: Implemented — Pending User Execution & Review
- **Target Manifests Created**:
  - [`k8s/apps/50-mcp.yaml`](k8s/apps/50-mcp.yaml)
  - [`k8s/apps/60-sandbox.yaml`](k8s/apps/60-sandbox.yaml)
  - [`k8s/apps/70-gateway.yaml`](k8s/apps/70-gateway.yaml)
  - [`k8s/apps/80-agents.yaml`](k8s/apps/80-agents.yaml)
  - [`scripts/verify-phase3.ps1`](scripts/verify-phase3.ps1)
- **Summary of Implemented Business/Infra Logic**:
  - Deployed `mcp-server` providing mock business APIs (Orders, Inventory, Returns) with health checks on port 8000.
  - Deployed `headless-browser` Playwright sandbox on port 9222 exposing `/json/version` and CDP debugging interface.
  - Deployed `agent-gateway` proxy and routing engine on port 8000 handling inter-agent delegation (`/a2a/route`) and tool proxying (`/mcp/*`).
  - Deployed `agent-1` (Customer Agent) and `agent-2` (Specialist Agent) on port 8080 with dependency `initContainers` gating startup on LiteLLM and Milvus readiness.
  - All Phase 3 workloads enforce strict `nodeAffinity` targeting worker nodes (`node-role.kubernetes.io/control-plane DoesNotExist`).
- **Exact Terminal Deployment & Verification Commands**:
  ```powershell
  # 1. Apply MCP Tool Server
  kubectl apply -f k8s/apps/50-mcp.yaml

  # 2. Apply Headless Browser Sandbox
  kubectl apply -f k8s/apps/60-sandbox.yaml

  # 3. Apply Agent Gateway
  kubectl apply -f k8s/apps/70-gateway.yaml

  # 4. Apply Agent 1 & Agent 2
  kubectl apply -f k8s/apps/80-agents.yaml

  # 5. Wait for all Agent Runtime deployments to roll out
  kubectl rollout status deployment/mcp-server -n agent-apps
  kubectl rollout status deployment/headless-browser -n agent-apps
  kubectl rollout status deployment/agent-gateway -n agent-apps
  kubectl rollout status deployment/agent-1 -n agent-apps
  kubectl rollout status deployment/agent-2 -n agent-apps

  # 6. Run Synthetic Phase 3 Verification Script
  .\scripts\verify-phase3.ps1
  ```
- **Review & Approval Gate**:
  - Phase 3: APPROVED by User.

---

## Phase 4: Ingress, WebUI & End-to-End Validation

- **Status**: Implemented — Pending User Execution & Review
- **Target Manifests Created**:
  - [`k8s/apps/90-webui.yaml`](k8s/apps/90-webui.yaml)
  - [`k8s/ingress/traefik-routes.yaml`](k8s/ingress/traefik-routes.yaml)
  - [`k8s/policies/network-policies.yaml`](k8s/policies/network-policies.yaml)
  - [`scripts/verify-phase4.ps1`](scripts/verify-phase4.ps1)
- **Summary of Implemented Business/Infra Logic**:
  - Deployed `webui` frontend on port 8080 with topological `initContainers` gating startup until `agent-1` is Ready.
  - Implemented Traefik Ingress routes exposing:
    - WebUI on `agent.localhost:8443`
    - LiteLLM on `litellm.localhost:8443`
    - Langfuse on `langfuse.localhost:8443`
  - Enforced zero-trust `NetworkPolicy` rules:
    - `isolate-data-tier`: Strictly blocks PostgreSQL direct access from `agent-apps` namespace.
    - `allow-agents-to-platform`: Authorizes agent egress only to LiteLLM (4000), Milvus (19530), Langfuse (3000), and CoreDNS (53).
- **Exact Terminal Deployment & Verification Commands**:
  ```powershell
  # 1. Apply WebUI frontend
  kubectl apply -f k8s/apps/90-webui.yaml

  # 2. Apply Traefik Ingress routes
  kubectl apply -f k8s/ingress/traefik-routes.yaml

  # 3. Apply NetworkPolicies (Zero-Trust Security)
  kubectl apply -f k8s/policies/network-policies.yaml

  # 4. Wait for WebUI rollout
  kubectl rollout status deployment/webui -n agent-apps

  # 5. Run Synthetic Phase 4 End-to-End Verification Script
  .\scripts\verify-phase4.ps1

  # 6. Access Services Directly via Traefik Ingress (No port-forwarding needed!)
  # 6.1 WebUI Frontend:
  #     Primary Browser URL: https://agent.localhost:8443
  #     Plain HTTP URL:      http://agent.localhost:8081
  # 6.2 Langfuse Observability Dashboard: (admin@workshop.local/admin@local.test)
  #     Primary Browser URL: https://ocallangfuse.localhost:8443
  #     Plain HTTP URL:      http://langfuse.localhost:8081
  # 6.3 LiteLLM AI Gateway: (admin)
  #     Swagger API Docs:    https://litellm.localhost:8443/docs
  #     Admin UI:            https://litellm.localhost:8443/ui (Username: admin | Password: `UI_PASSWORD` in `litellm-secret`)
  #     Health Readiness:    https://litellm.localhost:8443/health/readiness
  #
  #     Proved Working LiteLLM API Test Commands (HTTP :8081):
  #     1) curl list models:
  curl.exe -H "Host: litellm.localhost" -H "Authorization: Bearer $env:LITELLM_KEY" http://litellm.localhost:8081/v1/models

  #     2) curl chat completion:
  curl.exe -s -H "Host: litellm.localhost" -H "Authorization: Bearer $env:LITELLM_KEY" `
    --json '{\"model\": \"deepseek-v4-flash:cloud\", \"messages\": [{\"role\": \"user\", \"content\": \"Say hello in one sentence.\"}]}' `
    http://litellm.localhost:8081/chat/completions

  #     3) PowerShell one-liner chat completion:
  (Invoke-RestMethod -Uri "http://127.0.0.1:8081/chat/completions" `
    -Headers @{ "Host" = "litellm.localhost"; "Authorization" = "Bearer $env:LITELLM_KEY" } `
    -Method Post -ContentType "application/json" `
    -Body '{"model": "deepseek-v4-flash:cloud", "messages": [{"role": "user", "content": "Say hello in one sentence."}]}').choices[0].message.content

  #     4) PowerShell structured payload chat completion:
  $body = @{
      model    = "deepseek-v4-flash:cloud"
      messages = @(
          @{ role = "user"; content = "Say hello in one sentence." }
      )
  } | ConvertTo-Json

  $response = Invoke-RestMethod -Uri "http://127.0.0.1:8081/chat/completions" `
    -Headers @{ "Host" = "litellm.localhost"; "Authorization" = "Bearer $env:LITELLM_KEY" } `
    -Method Post -ContentType "application/json" `
    -Body $body

  $response.choices[0].message.content

  # 7. Understanding Edge Port Mappings & Ingress Routing
  # Inspect how host ports map to cluster edge via k3d load balancer:
  docker port k3d-rancher-cluster-serverlb
  # Output:
  #   443/tcp -> 0.0.0.0:8443   (Host 8443 routes to Traefik HTTPS 443)
  #   80/tcp  -> 0.0.0.0:8081   (Host 8081 routes to Traefik HTTP 80)
  #
  # Inspect Traefik Ingress Controller service inside Kubernetes:
  kubectl get svc traefik -n kube-system
  # Output:
  #   PORT(S): 80:31033/TCP, 443:31966/TCP
  #
  # Important Networking Notes:
  # - Do NOT use internal container IPs (e.g. 172.21.0.3) or cluster IPs (e.g. 10.43.188.197); they are not routable from Windows.
  # - Always use the domain name 'agent.localhost' so Traefik's Host-header rule routes traffic to webui:8080.
  ```
- **Review & Approval Gate**:
  - Phase 4: APPROVED by User (End-to-end multi-agent flow + LiteLLM integration confirmed working).

---

## Phase 5: LangGraph Assistant Integration (Streamlit App via LiteLLM)

- **Status**: Planned — Pending User Review & Comments
- **Architecture Overview**:

  ```mermaid
  graph TD
      Ingress["Traefik Ingress Controller<br/>(Host Edge :8081 / :8443)"]
      Ingress -->|agent.localhost| WebUI["WebUI Frontend :8080<br/>(agent-apps)"]
      Ingress -->|langgraph.localhost| LangGraph["langgraph-assistant :8501<br/>Streamlit Multi-Agent App<br/>(agent-apps)"]

      WebUI --> Agent1["Customer Agent (agent-1 :8080)<br/>(agent-apps)"]
      Agent1 -->|A2A Route| Gateway["Agent Gateway :8000<br/>(agent-apps)"]
      Gateway --> Agent2["Specialist Agent (agent-2 :8080)<br/>(agent-apps)"]

      Agent1 -->|TCP 4000 /chat/completions| LiteLLM["LiteLLM AI Gateway :4000<br/>(ai-platform)"]
      Agent2 -->|TCP 4000 /chat/completions| LiteLLM
      LangGraph -->|TCP 4000 /v1/chat/completions| LiteLLM

      LiteLLM -->|http://host.k3d.internal:11434| Ollama["Host Ollama Engine<br/>(deepseek-v4-flash:cloud)"]
  ```
  ```text
                          [ Traefik Ingress Controller ]
                                        │
              ┌─────────────────────────┴─────────────────────────┐
              ▼ (agent.localhost:8081)                            ▼ (langgraph.localhost:8081)
     [ webui :8080 ]                                   [ langgraph-assistant :8501 ]
   (Existing BeSA UI)                                 (Streamlit Multi-Agent App)
              │                                                   │
              │                                                   │
              ▼                                                   ▼
  [ agent-1 / agent-2 ] (agent-apps)                 [ LangGraph StateGraph ] (agent-apps)
              │                                                   │
              └─────────────────────────┬─────────────────────────┘
                                        │ (Cluster DNS: TCP 4000)
                                        ▼
                          [ LiteLLM AI Gateway ] (ai-platform)
                                        │
                                        ▼
                          [ Host Ollama Engine ] (11434)
  ```
- **Target Manifests & Code Changes**:

  - Code Adaptations:
    - [`langgraph_ollama/app.py`](https://github.com/ly2xxx/langgraph_ollama/blob/main/app.py) (Add `ChatOpenAI` provider seam for LiteLLM wire compatibility)
    - [`langgraph_ollama/coding_agent/models.py`](https://github.com/ly2xxx/langgraph_ollama/blob/main/coding_agent/models.py) (Add `openai` / `litellm` provider branch)
  - Container Image:
    - [`langgraph_ollama/docker/Dockerfile`](https://github.com/ly2xxx/langgraph_ollama/blob/main/docker/Dockerfile) (Multi-stage `uv` build for Streamlit)
  - Kubernetes Manifests:
    - [`k8s/apps/95-langgraph.yaml`](k8s/apps/95-langgraph.yaml) (Deployment & Service in `agent-apps` with `tier: agent-runtime`)
    - [`k8s/ingress/traefik-routes.yaml`](k8s/ingress/traefik-routes.yaml) (Add `langgraph.localhost` Ingress rule)
  - Verification Script:
    - [`scripts/verify-phase5.ps1`](scripts/verify-phase5.ps1)
- **Summary of Implemented Business/Infra Logic**:

  - Containerize the multi-agent Streamlit application from `langgraph_ollama` using the optimized multi-stage `docker/Dockerfile`.
  - Import the image into the local `rancher-cluster` k3d cluster nodes via `k3d image import`.
  - Deploy `langgraph-assistant` into namespace `agent-apps` with `tier: agent-runtime` so the existing zero-trust `NetworkPolicy` allows cross-namespace egress to LiteLLM on port 4000.
  - Wire LLM calls directly to cluster LiteLLM at `http://litellm.ai-platform.svc.cluster.local:4000/v1` using model `deepseek-v4-flash:cloud` and the LiteLLM master key from `litellm-secret`.
  - Expose the Streamlit UI at `http://langgraph.localhost:8081` (and HTTPS `:8443`) via Traefik Ingress.
- **Exact Terminal Deployment & Verification Commands**:

  ```powershell
  # 1. Build Docker Image from langgraph_ollama directory
  cd ..\langgraph_ollama   # a clone of github.com/ly2xxx/langgraph_ollama
  docker build -f docker/Dockerfile -t langgraph-assistant:latest .

  # 2. Import Docker Image into k3d rancher-cluster
  k3d image import langgraph-assistant:latest -c rancher-cluster

  # 3. Return to this repo
  cd agent-platform-k3d   # repo root

  # 4. Apply Kubernetes Deployment & Service
  kubectl apply -f k8s/apps/95-langgraph.yaml

  # 5. Apply updated Traefik Ingress routes
  kubectl apply -f k8s/ingress/traefik-routes.yaml

  # 6. Wait for rollout
  kubectl rollout status deployment/langgraph-assistant -n agent-apps

  # 7. Verification Commands
  # 7.1 Automated health check
  .\scripts\verify-phase5.ps1

  # 7.2 Ingress endpoint check (Port 8081)
  curl.exe -s -H "Host: langgraph.localhost" http://127.0.0.1:8081/_stcore/health

  # 7.3 Direct in-cluster model test via LiteLLM Gateway
  kubectl exec -n agent-apps deploy/langgraph-assistant -- python -c "from langchain_community.chat_models import ChatOpenAI; llm = ChatOpenAI(base_url='http://litellm.ai-platform.svc.cluster.local:4000/v1', api_key='$env:LITELLM_KEY', model='deepseek-v4-flash:cloud'); print(llm.invoke('ping').content)"

  # 8. Browser Access URLs:
  # - LangGraph Streamlit UI: http://langgraph.localhost:8081 (or https://langgraph.localhost:8443)
  # - LiteLLM Admin UI Logs:  http://litellm.localhost:8081/ui/logs/
  ```
- **Review & Approval Gate**:

  - Phase 5: Pending User Review & Comments.
