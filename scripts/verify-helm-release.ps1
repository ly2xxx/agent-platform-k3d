# Verification script for the besa-agent-platform Helm release.
#
# Parameterised on the namespaces so it can validate any release of the chart.
# The original verify-phase1..4.ps1 scripts hardcode ai-platform/agent-apps and
# still validate the raw-manifest deployment.
#
#   .\scripts\verify-helm-release.ps1 `
#       -PlatformNamespace ai-platform-dev -AppsNamespace agent-apps-dev -HostPort 8086

param(
    [string]$ReleaseName       = "besa-dev",
    [string]$PlatformNamespace = "ai-platform-dev",
    [string]$AppsNamespace     = "agent-apps-dev",
    [int]   $HostPort          = 8086,
    [string]$ProjectId         = "local:p-frmjf"
)

$ErrorActionPreference = "Continue"
$script:Failures = 0

function Assert-Pass($Ok, $Message, $Detail = "") {
    if ($Ok) {
        Write-Host "[PASS] $Message" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Message" -ForegroundColor Red
        if ($Detail) { Write-Host "       $Detail" -ForegroundColor DarkGray }
        $script:Failures++
    }
}

Write-Host "=== Step 1: Namespaces exist and are in the Rancher project ===" -ForegroundColor Cyan
foreach ($ns in @($PlatformNamespace, $AppsNamespace)) {
    $actual = kubectl get ns $ns -o jsonpath='{.metadata.annotations.field\.cattle\.io/projectId}' 2>$null
    Assert-Pass ($LASTEXITCODE -eq 0) "Namespace $ns exists."
    if ($ProjectId) {
        Assert-Pass ($actual -eq $ProjectId) "Namespace $ns is in project $ProjectId." "got '$actual'"
    }
}

Write-Host "`n=== Step 2: Platform tier rollout ===" -ForegroundColor Cyan
kubectl rollout status statefulset/postgres -n $PlatformNamespace --timeout=180s
Assert-Pass ($LASTEXITCODE -eq 0) "postgres StatefulSet rolled out."
foreach ($d in @("milvus", "litellm", "langfuse-web")) {
    kubectl rollout status deployment/$d -n $PlatformNamespace --timeout=180s
    Assert-Pass ($LASTEXITCODE -eq 0) "$d Deployment rolled out."
}

Write-Host "`n=== Step 3: Agent tier rollout ===" -ForegroundColor Cyan
foreach ($d in @("mcp-server", "headless-browser", "agent-gateway", "agent-1", "agent-2", "webui")) {
    kubectl rollout status deployment/$d -n $AppsNamespace --timeout=180s
    Assert-Pass ($LASTEXITCODE -eq 0) "$d Deployment rolled out."
}

Write-Host "`n=== Step 4: Workloads scheduled off the control plane ===" -ForegroundColor Cyan
foreach ($ns in @($PlatformNamespace, $AppsNamespace)) {
    $nodes = kubectl get pods -n $ns -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' 2>$null
    $bad = @($nodes -split "`n" | Where-Object { $_ -match "server-0" })
    Assert-Pass ($bad.Count -eq 0) "No $ns pods on the control-plane node." "$($bad.Count) pod(s) on a server node"
}

Write-Host "`n=== Step 5: Cross-namespace wiring points at THIS release ===" -ForegroundColor Cyan
$litellmUrl = kubectl get cm agent-config -n $AppsNamespace -o jsonpath='{.data.LITELLM_BASE_URL}' 2>$null
$expected = "http://litellm.$PlatformNamespace.svc.cluster.local:4000"
Assert-Pass ($litellmUrl -eq $expected) "agent-config LITELLM_BASE_URL targets $PlatformNamespace." "got '$litellmUrl'"

kubectl exec -n $AppsNamespace deploy/agent-1 -- python -c "import os,urllib.request;r=urllib.request.urlopen(os.environ['LITELLM_BASE_URL']+'/health/liveliness',timeout=10);print(r.status)"
Assert-Pass ($LASTEXITCODE -eq 0) "agent-1 can reach LiteLLM across namespaces (NetworkPolicy allows it)."

Write-Host "`n=== Step 6: In-cluster health probes ===" -ForegroundColor Cyan
$probes = @(
    @{ ns = $PlatformNamespace; target = "deploy/litellm";      url = "http://localhost:4000/health/readiness" },
    @{ ns = $PlatformNamespace; target = "deploy/langfuse-web"; url = "http://localhost:3000/api/public/health" },
    @{ ns = $PlatformNamespace; target = "deploy/milvus";       url = "http://localhost:9091/healthz" },
    @{ ns = $AppsNamespace;     target = "deploy/mcp-server";   url = "http://localhost:8000/healthz" },
    @{ ns = $AppsNamespace;     target = "deploy/agent-gateway";url = "http://localhost:8000/healthz" },
    @{ ns = $AppsNamespace;     target = "deploy/agent-1";      url = "http://localhost:8080/healthz" },
    @{ ns = $AppsNamespace;     target = "deploy/agent-2";      url = "http://localhost:8080/healthz" },
    @{ ns = $AppsNamespace;     target = "deploy/webui";        url = "http://localhost:8080/healthz" }
)
foreach ($p in $probes) {
    kubectl exec -n $p.ns $p.target -- curl -s $p.url | Out-Null
    Assert-Pass ($LASTEXITCODE -eq 0) "$($p.target) $($p.url)"
}

Write-Host "`n=== Step 7: Postgres reachable and databases present ===" -ForegroundColor Cyan
kubectl exec -n $PlatformNamespace statefulset/postgres -- pg_isready -U postgres | Out-Null
Assert-Pass ($LASTEXITCODE -eq 0) "postgres accepts connections."
$dbs = kubectl exec -n $PlatformNamespace statefulset/postgres -- psql -U postgres -tAc "SELECT datname FROM pg_database" 2>$null
foreach ($db in @("langfuse", "litellm")) {
    Assert-Pass ($dbs -match $db) "database '$db' exists."
}

Write-Host "`n=== Step 8: External access on host port $HostPort ===" -ForegroundColor Cyan
$nodePort = kubectl get svc webui -n $AppsNamespace -o jsonpath='{.spec.ports[0].nodePort}' 2>$null
Assert-Pass ($nodePort) "webui Service exposes nodePort $nodePort."

$published = docker port k3d-rancher-cluster-serverlb 2>$null
if ($published -match ":$HostPort`$" -or $published -match ":$HostPort\s") {
    Write-Host "[INFO] k3d serverlb publishes $HostPort." -ForegroundColor DarkGray
} else {
    Write-Host "[WARN] k3d serverlb does not publish $HostPort. Run:" -ForegroundColor Yellow
    Write-Host "       k3d cluster edit rancher-cluster --port-add `"$HostPort`:$nodePort@loadbalancer`"" -ForegroundColor Yellow
}

$code = curl.exe -s -o NUL -w "%{http_code}" "http://localhost:$HostPort/healthz" 2>$null
Assert-Pass ($code -eq "200") "http://localhost:$HostPort/healthz returned 200." "got HTTP $code"

Write-Host "`n=== Step 9: End-to-end chat through the WebUI ===" -ForegroundColor Cyan
$body = '{\"query\": \"Where is order ORD-12345?\"}'
$resp = curl.exe -s -X POST "http://localhost:$HostPort/chat" -H "Content-Type: application/json" -d $body 2>$null
Assert-Pass ($resp -match "trace_id") "WebUI /chat returned a trace." "got: $resp"
if ($resp) { Write-Host "       $resp" -ForegroundColor DarkGray }

Write-Host "`n=== Step 10: The original stack is untouched ===" -ForegroundColor Cyan
foreach ($ns in @("ai-platform", "agent-apps")) {
    $notReady = kubectl get pods -n $ns --no-headers 2>$null | Where-Object { $_ -notmatch "Running" -and $_ -notmatch "Completed" }
    Assert-Pass ($null -eq $notReady) "All pods in the original $ns namespace are still Running."
}

Write-Host ""
if ($script:Failures -eq 0) {
    Write-Host "All checks passed for release '$ReleaseName'." -ForegroundColor Green
    exit 0
} else {
    Write-Host "$script:Failures check(s) failed for release '$ReleaseName'." -ForegroundColor Red
    exit 1
}
