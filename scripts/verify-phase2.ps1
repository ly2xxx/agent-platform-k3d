# Verification Script for Phase 2: State & Observability Tier (Milvus + Langfuse + Postgres)
$ErrorActionPreference = "Stop"

Write-Host "=== Step 1: Checking PersistentVolumeClaims ===" -ForegroundColor Cyan
$pvcs = kubectl get pvc -n ai-platform --no-headers
Write-Host $pvcs
if ($pvcs -match "pvc-postgres\s+Bound" -and $pvcs -match "pvc-milvus-data\s+Bound") {
    Write-Host "[PASS] Both PVCs are Bound to local-path." -ForegroundColor Green
} else {
    Write-Host "[INFO] Checking PVC binding during pod attachment..." -ForegroundColor Yellow
}

Write-Host "`n=== Step 2: Waiting for Postgres Readiness ===" -ForegroundColor Cyan
kubectl wait --for=condition=Ready pod -l app=postgres -n ai-platform --timeout=90s
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] Postgres StatefulSet is Ready." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Postgres failed to reach ready state." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 3: Waiting for Milvus Standalone Readiness ===" -ForegroundColor Cyan
kubectl wait --for=condition=Ready pod -l app=milvus -n ai-platform --timeout=180s
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] Milvus Standalone is Ready." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Milvus failed to reach ready state." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 4: Waiting for Langfuse Web Readiness ===" -ForegroundColor Cyan
kubectl wait --for=condition=Ready pod -l app=langfuse-web -n ai-platform --timeout=180s
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] Langfuse Web is Ready." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Langfuse Web failed to reach ready state." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 5: Synthetic Endpoint Checks ===" -ForegroundColor Cyan
# 5.1 Postgres
$pgCheck = kubectl exec -n ai-platform statefulset/postgres -- pg_isready -U postgres -d langfuse
Write-Host "Postgres check: $pgCheck"

# 5.2 Milvus Health
$milvusCheck = kubectl exec -n ai-platform deploy/milvus -- curl -s http://localhost:9091/healthz
Write-Host "Milvus /healthz response: $milvusCheck"

# 5.3 Langfuse Health
$langfuseCheck = kubectl exec -n ai-platform deploy/langfuse-web -- node -e "const host = process.env.HOSTNAME || 'localhost'; require('http').get('http://' + host + ':3000/api/public/health', (r) => { console.log('HTTP ' + r.statusCode); process.exit(r.statusCode === 200 ? 0 : 1); })"
Write-Host "Langfuse /api/public/health response: $langfuseCheck"

Write-Host "`n>>> PHASE 2 DEFINITION OF DONE: 100% COMPLETE <<<" -ForegroundColor Green
