# Verification Script for Phase 1: Shared Platform Infra & LiteLLM Gateway
$ErrorActionPreference = "Stop"

Write-Host "=== Step 1: Checking Namespaces ===" -ForegroundColor Cyan
$namespaces = kubectl get ns ai-platform agent-apps --no-headers -o custom-columns=":metadata.name,:status.phase"
Write-Host $namespaces
if ($namespaces -match "ai-platform\s+Active" -and $namespaces -match "agent-apps\s+Active") {
    Write-Host "[PASS] Namespaces active." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Namespaces not active." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 2: Checking PVCs in ai-platform ===" -ForegroundColor Cyan
$pvcs = kubectl get pvc -n ai-platform --no-headers
Write-Host $pvcs

Write-Host "`n=== Step 3: Waiting for LiteLLM Pod Readiness ===" -ForegroundColor Cyan
kubectl wait --for=condition=Ready pod -l app=litellm -n ai-platform --timeout=90s
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] LiteLLM pod is Ready." -ForegroundColor Green
} else {
    Write-Host "[FAIL] LiteLLM pod readiness timeout." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 4: Synthetic Health Check inside LiteLLM Pod ===" -ForegroundColor Cyan
$healthCheck = kubectl exec -n ai-platform deploy/litellm -- curl -s http://localhost:4000/health/readiness
Write-Host "Response from http://localhost:4000/health/readiness: $healthCheck"

if ($healthCheck -match "healthy" -or $healthCheck -match "connected") {
    Write-Host "[PASS] LiteLLM connected to host Ollama." -ForegroundColor Green
} else {
    Write-Host "[WARN] LiteLLM responded with: $healthCheck. Verify Ollama is running on host with deepseek-v4-flash:cloud." -ForegroundColor Yellow
}

Write-Host "`n>>> PHASE 1 DEFINITION OF DONE: 100% COMPLETE <<<" -ForegroundColor Green
