<#
.SYNOPSIS
  Creates the Secrets the raw manifests in k8s/ need, with random values.

.DESCRIPTION
  The Helm chart generates its own credentials. The raw manifests don't, so run this
  once after applying k8s/namespaces/ and before the rest of k8s/.

  Values already in the cluster are kept, so re-running is safe: it never rotates a
  database password or Langfuse's encryption key out from under existing data.
  Secret values are never printed and never passed on a command line; each Secret is
  written as YAML to `kubectl apply` on stdin.

    postgres-secret   (platform)  POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    litellm-secret    (platform)  LITELLM_MASTER_KEY, UI_PASSWORD, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
    langfuse-secret   (platform)  NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY
    agent-secret      (apps)      LITELLM_API_KEY (the LiteLLM master key)

.EXAMPLE
  kubectl apply -f k8s/namespaces/
  .\scripts\new-dev-secrets.ps1
  kubectl apply -R -f k8s/

.EXAMPLE
  # After creating a project in Langfuse, turn LiteLLM tracing on:
  .\scripts\new-dev-secrets.ps1 -LangfusePublicKey pk-lf-... -LangfuseSecretKey sk-lf-...
  kubectl rollout restart deploy/litellm -n ai-platform

.EXAMPLE
  # A cluster that ran the old manifests used "sk-admin". Keep it so models you added
  # in the LiteLLM UI (encrypted with the master key) stay readable:
  .\scripts\new-dev-secrets.ps1 -LiteLLMMasterKey sk-admin
#>
[CmdletBinding()]
param(
    [string]$PlatformNamespace = 'ai-platform',
    [string]$AppsNamespace = 'agent-apps',
    [string]$LangfusePublicKey,
    [string]$LangfuseSecretKey,
    [string]$LiteLLMMasterKey
)

$Alphanumeric = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'

function Get-RandomBytes([int]$Count) {
    $bytes = New-Object byte[] $Count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ,$bytes
}

function New-RandomString([int]$Length) {
    # Rejection sampling: 248 is the largest multiple of 62 below 256, so every
    # character is equally likely. Alphanumeric only, so values are safe inside URLs.
    $out = New-Object System.Text.StringBuilder
    while ($out.Length -lt $Length) {
        foreach ($b in (Get-RandomBytes 64)) {
            if ($b -lt 248 -and $out.Length -lt $Length) { [void]$out.Append($Alphanumeric[$b % 62]) }
        }
    }
    return $out.ToString()
}

function New-HexKey {
    # Langfuse's ENCRYPTION_KEY: 32 random bytes as 64 hex characters.
    return -join ((Get-RandomBytes 32) | ForEach-Object { $_.ToString('x2') })
}

function Get-ExistingValue([string]$Namespace, [string]$Name, [string]$Key) {
    $b64 = & kubectl get secret $Name -n $Namespace -o "jsonpath={.data.$Key}" 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($b64)) { return $null }
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("$b64".Trim()))
}

$script:report = New-Object System.Collections.Generic.List[string]

function Resolve-Value([string]$Namespace, [string]$Name, [string]$Key, [string]$Explicit, [scriptblock]$Generate) {
    if ($Explicit) { $script:report.Add("  $Name/$Key : set from parameter"); return $Explicit }
    $existing = Get-ExistingValue $Namespace $Name $Key
    if ($null -ne $existing) { $script:report.Add("  $Name/$Key : kept"); return $existing }
    $value = & $Generate
    if ($value) { $script:report.Add("  $Name/$Key : generated") } else { $script:report.Add("  $Name/$Key : not set") }
    return $value
}

function Set-Secret([string]$Namespace, [string]$Name, [System.Collections.Specialized.OrderedDictionary]$Data) {
    $lines = @(
        'apiVersion: v1', 'kind: Secret', 'metadata:', "  name: $Name", "  namespace: $Namespace",
        '  labels:', '    app.kubernetes.io/part-of: besa-ai-platform',
        '    app.kubernetes.io/managed-by: new-dev-secrets', 'type: Opaque', 'data:'
    )
    foreach ($key in $Data.Keys) {
        $b64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes([string]$Data[$key]))
        $lines += "  ${key}: `"$b64`""
    }
    ($lines -join "`n") | & kubectl apply -f - | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "kubectl could not apply Secret $Namespace/$Name." }
}

foreach ($ns in @($PlatformNamespace, $AppsNamespace)) {
    & kubectl get namespace $ns 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Namespace '$ns' does not exist. Run 'kubectl apply -f k8s/namespaces/' first, then re-run this script."
        exit 1
    }
}

if ($LiteLLMMasterKey -and -not $LiteLLMMasterKey.StartsWith('sk-')) {
    Write-Error "LiteLLM master keys must start with 'sk-'."
    exit 1
}

try {
    $p = $PlatformNamespace
    $pgPassword = Resolve-Value $p 'postgres-secret' 'POSTGRES_PASSWORD' $null { New-RandomString 24 }
    $masterKey  = Resolve-Value $p 'litellm-secret' 'LITELLM_MASTER_KEY' $LiteLLMMasterKey { 'sk-' + (New-RandomString 32) }
    $uiPassword = Resolve-Value $p 'litellm-secret' 'UI_PASSWORD' $null { New-RandomString 20 }
    $lfPublic   = Resolve-Value $p 'litellm-secret' 'LANGFUSE_PUBLIC_KEY' $LangfusePublicKey { '' }
    $lfSecret   = Resolve-Value $p 'litellm-secret' 'LANGFUSE_SECRET_KEY' $LangfuseSecretKey { '' }
    $nextAuth   = Resolve-Value $p 'langfuse-secret' 'NEXTAUTH_SECRET' $null { New-RandomString 32 }
    $salt       = Resolve-Value $p 'langfuse-secret' 'SALT' $null { New-RandomString 32 }
    $encKey     = Resolve-Value $p 'langfuse-secret' 'ENCRYPTION_KEY' $null { New-HexKey }

    Set-Secret $p 'postgres-secret' ([ordered]@{ POSTGRES_DB = 'langfuse'; POSTGRES_USER = 'postgres'; POSTGRES_PASSWORD = $pgPassword })
    Set-Secret $p 'litellm-secret' ([ordered]@{ LITELLM_MASTER_KEY = $masterKey; UI_PASSWORD = $uiPassword; LANGFUSE_PUBLIC_KEY = $lfPublic; LANGFUSE_SECRET_KEY = $lfSecret })
    Set-Secret $p 'langfuse-secret' ([ordered]@{ NEXTAUTH_SECRET = $nextAuth; SALT = $salt; ENCRYPTION_KEY = $encKey })
    Set-Secret $AppsNamespace 'agent-secret' ([ordered]@{ LITELLM_API_KEY = $masterKey })
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}

Write-Host "Secrets are in place:"
$script:report | ForEach-Object { Write-Host $_ }
Write-Host "  agent-secret/LITELLM_API_KEY : same as litellm-secret/LITELLM_MASTER_KEY"
if (-not $lfPublic) {
    Write-Host "`nLiteLLM tracing to Langfuse is off until you re-run with -LangfusePublicKey and -LangfuseSecretKey."
}
Write-Host "`nRead a value when you need it, for example the LiteLLM UI password:"
Write-Host "  [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl get secret litellm-secret -n $p -o jsonpath='{.data.UI_PASSWORD}')))"
