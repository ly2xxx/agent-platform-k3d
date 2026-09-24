# besa-agent-platform

Helm chart for the BeSA AI agent platform on k3d/Rancher. It is a parameterised port of
the raw manifests in [`../../k8s/`](../../k8s/) — same workloads, same topology, but every
namespace and cross-namespace endpoint is a value, so the whole stack can be installed
more than once on the same cluster without the copies reaching into each other.

The design it implements is [`../../DESIGN.md`](../../DESIGN.md); the manifests it was
derived from stay in place and are still deployed by [`../../PHASED.md`](../../PHASED.md).

## What it deploys

| Namespace | Workloads |
| :-- | :-- |
| `namespaces.platform` | `postgres` (StatefulSet), `milvus`, `litellm`, `langfuse-web` |
| `namespaces.apps` | `mcp-server`, `headless-browser`, `agent-gateway`, `agent-1`, `agent-2`, `webui` |

Plus two NetworkPolicies, up to three Traefik Ingresses, two `local-path` PVCs, and a
`helm test` pod that runs the DESIGN.md §4 health probes.

Only four real images are pulled — `postgres:16-alpine`, `milvusdb/milvus:v2.4.13`,
`ghcr.io/berriai/litellm:main-latest`, `ghcr.io/langfuse/langfuse:2`. The six agent
workloads are stock `python:3.11-slim` running stdlib HTTP servers mounted from
ConfigMaps, sourced from [`files/`](files/). **There is no application image to build.**

## Install

```powershell
cd helm\besa-agent-platform

# 1. Create the namespaces. Rendered from this chart, so they carry the Rancher
#    project annotation and the Helm ownership metadata that lets step 2 adopt them.
helm template besa-dev . -n ai-platform-dev -f values-dev-8086.yaml `
  -s templates/00-namespaces.yaml | kubectl apply -f -

# 2. Install.
helm upgrade --install besa-dev . -n ai-platform-dev -f values-dev-8086.yaml --wait --timeout 12m

# 3. Publish host port 8086 -> nodePort 30086. Helm cannot do this.
#    Recreates the k3d serverlb container, so the Rancher UI on :8443 and the
#    kubectl API on :6550 drop for a few seconds. Additive - 8081/8443 survive,
#    and there is no --port-remove, so undoing it means recreating the cluster.
k3d cluster edit rancher-cluster --port-add "8086:30086@loadbalancer"
docker port k3d-rancher-cluster-serverlb
curl.exe -s http://localhost:8086/healthz
```

### Why step 1 exists

Helm writes the release secret into `.Release.Namespace` **before** it applies any
manifest, so that namespace must already exist — a chart cannot bootstrap the namespace it
is installed into. `--create-namespace` does not help: it creates a bare namespace with no
labels, and the chart's own Namespace object would then fail Helm's ownership check.

So `templates/00-namespaces.yaml` declares the `meta.helm.sh/release-name` and
`meta.helm.sh/release-namespace` annotations Helm would have added anyway. Rendering just
that template and applying it makes both namespaces adoptable, and step 2 takes ownership
cleanly. Set `namespaces.create=false` to install into namespaces you manage yourself.

Note that `helm uninstall` then **deletes both namespaces**, since the release owns them.

## Credentials

Nothing secret lives in `values.yaml`. The Postgres password, LiteLLM's master key and UI
password, and Langfuse's `nextAuthSecret`, `salt` and `encryptionKey` are left empty, and
the chart fills in each one, in this order:

1. a value you pass (`-f my-values.yaml` or `--set`);
2. the value already in the cluster's Secret, so `helm upgrade` never rotates the database
   password or Langfuse's encryption key out from under their data;
3. a new random value, on first install.

Read one when you need it:

```powershell
function Get-BesaSecret($name, $key, $ns = 'ai-platform-dev') {
  [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl get secret $name -n $ns -o jsonpath="{.data.$key}")))
}
Get-BesaSecret litellm-secret UI_PASSWORD          # LiteLLM admin UI, user "admin"
Get-BesaSecret litellm-secret LITELLM_MASTER_KEY   # API calls: Authorization: Bearer <key>
```

The agents read the master key from the `agent-secret` Secret in the apps namespace, not
from the `agent-config` ConfigMap.

`helm template` and a client-side `--dry-run` cannot read the cluster, so they show fresh
random values on every run. That is expected; `install` and `upgrade` read the Secrets.
To confirm an upgrade kept everything, read `Get-BesaSecret postgres-secret POSTGRES_PASSWORD`
before and after: it must not change.

A release installed before credentials were generated still holds the old fixed values,
and rule 2 keeps them. On a throwaway cluster the clean way out is `helm uninstall`, delete
the two PVCs, and install again. To rotate in place instead, pass the new values with
`--set`; for Postgres, change the password inside the database first
(`ALTER USER postgres PASSWORD '...'`), because the Secret only seeds a new volume.

## Wire LiteLLM to Langfuse

A fresh Langfuse has a fresh database, so it issues **new** project keys — the ones in
[`../../docs/langfuse-litellm-integration.md`](../../docs/langfuse-litellm-integration.md)
belong to the original instance and do not work here.

While `platform.langfuse.publicKey`/`secretKey` are empty the chart renders LiteLLM with
**no** langfuse callback at all, so it starts clean instead of erroring on every
completion. To turn tracing on:

1. Open `http://langfuse-dev.localhost:8081`, create an organization and project.
2. Copy the public and secret keys, then:
   ```powershell
   helm upgrade besa-dev . -n ai-platform-dev -f values-dev-8086.yaml `
     --set platform.langfuse.publicKey=pk-lf-... `
     --set platform.langfuse.secretKey=sk-lf-...
   ```

The LiteLLM Deployment carries a `checksum/tracing` annotation, so this rolls the pod
automatically.

## External access

| Route | Path |
| :-- | :-- |
| `http://localhost:8086` | host → k3d serverlb → node:30086 (NodePort) → `svc/webui` → webui:8080 |
| `http://agent-dev.localhost:8081` | shared Traefik → `svc/webui` |
| `http://litellm-dev.localhost:8081` | shared Traefik → `svc/litellm` |
| `http://langfuse-dev.localhost:8081` | shared Traefik → `svc/langfuse-web` |

The NodePort is what satisfies "external facing port 8086". The Ingresses are additive — a
single NodePort cannot reach the Langfuse and LiteLLM admin UIs — and their hostnames are
deliberately distinct from the original stack's `agent`/`litellm`/`langfuse.localhost`.

Ingress `tls:` blocks carry hosts but no `secretName`, so Traefik serves its default
self-signed cert over `:8443` — use `curl -k` there.

## Running under a Rancher project quota

A Rancher project applies a **per-namespace** ResourceQuota by default. For
`ai-development` that is `requests.storage 8Gi`, `limits.cpu 4`, `requests.cpu 2`,
`limits.memory 8Gi`, 25 pods, 5 PVCs. Three things follow, and the chart handles all of
them:

- **Every container must declare requests and limits**, including init containers — a
  quota on a resource makes it mandatory, and there is no LimitRange supplying defaults.
  `initResources` covers the four init containers and the test pod; the raw manifests leave
  these unset, which only works in an unquotaed namespace.
- **`deploymentStrategy: Recreate`.** These are all single-replica workloads. Under a quota
  sized for exactly one copy of the stack, RollingUpdate cannot admit its surge replica and
  the rollout stalls on `exceeded quota` — the Deployment reports `ReplicaFailure` /
  `FailedCreate` and never converges. Recreate trades a few seconds of downtime for
  upgrades that complete. Switch to `RollingUpdate` if your quota has headroom.
- **`values-dev-8086.yaml` trims storage and CPU limits to fit**: `requests.storage`
  15Gi → 7Gi (postgres 5→3, milvus 10→4) and `limits.cpu` 4500m → 3500m (milvus
  2000m → 1000m). `values.yaml` keeps the raw manifests' original sizing. Milvus takes the
  bulk of the cut because it is provisioned and probed but never queried — `MILVUS_URI` is
  only TCP-probed by the init container.

### Migrating an existing release to Recreate

The API server rejects `strategy.type: Recreate` alongside the `rollingUpdate` block it
defaulted onto an existing Deployment, and Helm's merge patch will not drop that block on
its own. Patch the live objects once, then upgrade:

```powershell
kubectl patch deploy <name> -n <ns> --type=merge `
  -p '{\"spec\":{\"strategy\":{\"type\":\"Recreate\",\"rollingUpdate\":null}}}'
```

Fresh installs are unaffected.

## Key values

| Value | Default | Notes |
| :-- | :-- | :-- |
| `namespaces.platform` / `.apps` | `ai-platform-dev` / `agent-apps-dev` | Drive every rendered FQDN |
| `rancher.projectId` / `.projectName` | `""` | `local:p-frmjf` / `p-frmjf` joins the namespaces to a Rancher project |
| `apps.webui.service.nodePort` | `30086` | Must match the `k3d --port-add` mapping |
| `deploymentStrategy` | `Recreate` | See above |
| `initResources` | 25m/32Mi → 100m/128Mi | Required under a quota |
| `workerOnly` | `true` | nodeAffinity `control-plane DoesNotExist`, per DESIGN.md §1 |
| `platform.litellm.ollamaBaseUrl` | `http://host.docker.internal:11434` | Host Ollama |
| `platform.litellm.startupProbe` | enabled, 6 min | See below |
| `platform.postgres.extraDatabases` | `[litellm]` | See below |
| `apps.webui.tier` | `frontend` | See below |
| `<component>.enabled` | `true` | Every component can be switched off individually |

## Deviations from the raw manifests

Five deliberate changes; everything else is a faithful port.

- **`platform.postgres.extraDatabases: [litellm]`.** LiteLLM's `DATABASE_URL` points at a
  `litellm` database that `POSTGRES_DB=langfuse` never creates. A fresh volume means the
  initdb hook actually runs, so the fix is free here. Set to `[]` for strict parity.
- **`startupProbe` on litellm and langfuse.** Consequence of the above: once the database
  really exists, LiteLLM runs Prisma migrations on first boot (86 tables). That takes far
  longer than the liveness probe's 15s delay, so the pod was SIGKILLed mid-migration
  (exit 137) in a restart loop. A startupProbe holds liveness off until boot completes.
- **`deploymentStrategy` and `initResources`**, for the quota reasons above.
- **`webui-config` split into `webui-env` + `webui-code`.** The raw manifest used one
  ConfigMap for both `envFrom` and the volume, injecting `server.py` and the curl shim into
  the pod environment as multi-line env vars.
- **One curl shim.** The five in-tree copies had already drifted — `60-sandbox.yaml` used
  an older single-token `-d` parser. `files/shared/curl` is the version the other four
  agreed on, and all five ConfigMaps now reference it.

The embedded Python is byte-identical to the originals apart from `gateway.py` and
`wait_for_platform.py`, whose hardcoded FQDN constants became `os.environ.get(...)` lookups
so the gateway and the readiness gate follow the release's own namespaces. The stale
old-namespace *fallback* defaults in `agent1_server.py`, `agent2_server.py` and
`webui/server.py` were changed to bare service names, so a missing env var fails fast
instead of silently resolving against the other stack.

Carried over unchanged, and worth knowing:

- **The NetworkPolicies are not enforced on this cluster.** They are created exactly as in
  the raw manifests, but postgres is reachable from the agent tier in `agent-apps-dev` —
  and equally in the original `agent-apps`, so this is a property of the k3d/WSL2 CNI, not
  of the chart. Do not rely on `isolate-data-tier` for isolation here.
- `apps.webui.tier` defaults to `frontend`, matching the original. That means
  `allow-agents-to-platform` (which selects `tier: agent-runtime`) does not select the
  webui pod. Set it to `agent-runtime` to bring it under the policy.
- Postgres uses a pre-created PVC rather than `volumeClaimTemplates`, mounted at PGDATA
  with no `subPath`.
- Credentials are generated per install (see [Credentials](#credentials)) rather than fixed.
  They are still ordinary Kubernetes Secrets, which are base64-encoded, not encrypted, unless
  the cluster enables encryption at rest. Anywhere real, back them with an external secret store.

## Verify

```powershell
helm lint . -f values-dev-8086.yaml
helm template besa-dev . -n ai-platform-dev -f values-dev-8086.yaml | kubectl apply --dry-run=client -f -
helm test besa-dev -n ai-platform-dev

# Namespaces really are in the Rancher project
kubectl get ns ai-platform-dev agent-apps-dev `
  -o custom-columns='NAME:.metadata.name,PROJECT:.metadata.annotations.field\.cattle\.io/projectId'

# Nothing points back at the original stack
helm template besa-dev . -n ai-platform-dev -f values-dev-8086.yaml | `
  Select-String 'ai-platform\.svc|agent-apps\.svc'    # must return nothing

# End to end
curl.exe -s http://localhost:8086/healthz
curl.exe -s -X POST http://localhost:8086/chat -H "Content-Type: application/json" `
  -d '{\"query\": \"Where is order ORD-12345?\"}'
```

A server-side dry run (`--dry-run=server`) reports `namespaces ... not found` for every
object until the namespaces exist; use `--dry-run=client` before the first install.

`..\..\scripts\verify-helm-release.ps1 -PlatformNamespace ai-platform-dev -AppsNamespace agent-apps-dev`
runs the fuller phase-by-phase assertions. The original `verify-phase1..4.ps1` scripts
hardcode `ai-platform`/`agent-apps` and still validate the raw-manifest deployment.

## Uninstall

```powershell
helm uninstall besa-dev -n ai-platform-dev   # also deletes both namespaces
```

The `8086` k3d mapping can only be removed by recreating the cluster — there is no
`--port-remove` — but an unused published port is harmless.


## TODO
```powershell
 k3d cluster edit rancher-cluster --port-add "8086:30086@loadbalancer" 
 http://localhost:8086/healthz
 k3d cluster edit rancher-cluster --port-delete "8086:30086@loadbalancer"
```