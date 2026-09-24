{{/*
Expand the name of the chart.
*/}}
{{- define "besa.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "besa.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "besa.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels. `partOf` and `component` are passed in by each template via a dict:
  {{- include "besa.labels" (dict "ctx" . "component" "litellm" "partOf" "besa-ai-platform" "tier" "data-observability") }}
*/}}
{{- define "besa.labels" -}}
helm.sh/chart: {{ include "besa.chart" .ctx }}
app.kubernetes.io/name: {{ include "besa.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
{{- if .ctx.Chart.AppVersion }}
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
{{- end }}
{{- with .component }}
app.kubernetes.io/component: {{ . }}
{{- end }}
{{- with .partOf }}
app.kubernetes.io/part-of: {{ . }}
{{- end }}
{{- end }}

{{/*
Selector labels. Deliberately narrow: `app` plus the release, so two releases of this
chart in different namespaces never select each other's pods.
*/}}
{{- define "besa.selectorLabels" -}}
app: {{ .name }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
{{- end }}

{{/*
Namespaces.
*/}}
{{- define "besa.platformNs" -}}{{ .Values.namespaces.platform }}{{- end }}
{{- define "besa.appsNs"     -}}{{ .Values.namespaces.apps }}{{- end }}

{{/*
Cross-namespace service FQDNs. These are the single source of truth that makes the
stack relocatable - every embedded script and env var derives its endpoints from here,
so nothing can silently reach back into another release's namespaces.
*/}}
{{- define "besa.postgresHost" -}}postgres.{{ .Values.namespaces.platform }}.svc.cluster.local{{- end }}
{{- define "besa.postgresUrl" -}}
{{- $p := .Values.platform.postgres -}}
postgresql://{{ $p.username }}:{{ $p.password }}@{{ include "besa.postgresHost" . }}:5432
{{- end }}
{{- define "besa.litellmUrl"  -}}http://litellm.{{ .Values.namespaces.platform }}.svc.cluster.local:{{ .Values.platform.litellm.port }}{{- end }}
{{- define "besa.milvusUri"   -}}http://milvus.{{ .Values.namespaces.platform }}.svc.cluster.local:{{ .Values.platform.milvus.port }}{{- end }}
{{- define "besa.langfuseUrl" -}}http://langfuse-web.{{ .Values.namespaces.platform }}.svc.cluster.local:{{ .Values.platform.langfuse.port }}{{- end }}
{{- define "besa.gatewayUrl"  -}}http://agent-gateway.{{ .Values.namespaces.apps }}.svc.cluster.local:{{ .Values.apps.gateway.port }}{{- end }}
{{- define "besa.mcpUrl"      -}}http://mcp-server.{{ .Values.namespaces.apps }}.svc.cluster.local:{{ .Values.apps.mcp.port }}{{- end }}
{{- define "besa.agent1Url"   -}}http://agent-1.{{ .Values.namespaces.apps }}.svc.cluster.local:{{ .Values.apps.agents.port }}{{- end }}
{{- define "besa.agent2Url"   -}}http://agent-2.{{ .Values.namespaces.apps }}.svc.cluster.local:{{ .Values.apps.agents.port }}{{- end }}
{{- define "besa.browserWs"   -}}ws://headless-browser.{{ .Values.namespaces.apps }}.svc.cluster.local:{{ .Values.apps.sandbox.port }}{{- end }}

{{/*
Keep AI workloads off the k3s control plane, per DESIGN.md section 1.
*/}}
{{- define "besa.affinity" -}}
{{- if .Values.workerOnly }}
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: node-role.kubernetes.io/control-plane
              operator: DoesNotExist
{{- end }}
{{- end }}

{{/*
The shared curl shim, mounted into every python:3.11-slim pod because the image has no
curl and the verify scripts shell out to it.
*/}}
{{- define "besa.curlShim" -}}
curl: |
{{ .Files.Get "files/shared/curl" | indent 2 }}
{{- end }}

{{/*
Pod template labels: the common labels plus the selector's `app` label. Not
besa.labels + besa.selectorLabels together - both emit app.kubernetes.io/instance,
and a mapping with a repeated key is invalid YAML that strict parsers reject.
*/}}
{{- define "besa.podLabels" -}}
{{ include "besa.labels" (dict "ctx" .ctx "component" .component "partOf" .partOf) }}
app: {{ .name }}
{{- end }}

{{/*
The value already stored under `key` in Secret `name`, or `new` when there is none.
`lookup` returns nothing under `helm template` and client-side dry runs, so those
always get `new`.
*/}}
{{- define "besa.existingOr" -}}
{{- $s := lookup "v1" "Secret" .ns .name -}}
{{- if and $s $s.data (hasKey $s.data .key) -}}
{{- index $s.data .key | b64dec -}}
{{- else -}}
{{- .new -}}
{{- end -}}
{{- end }}

{{/*
Fill in every generated credential that values.yaml leaves empty, in this order:
  1. a value you set (values file or --set) - used as-is;
  2. the value already in the cluster's Secret - so `helm upgrade` never rotates a
     live database password or Langfuse's encryption key out from under its data;
  3. a new random value.
Writes the result back into .Values so every template, and besa.postgresUrl, sees the
same value within one render. Idempotent: include it at the top of any template that
reads a credential. Generated values are alphanumeric, so they are safe inside URLs.
*/}}
{{- define "besa.resolveSecrets" -}}
{{- $ns := include "besa.platformNs" . -}}
{{- $pg := .Values.platform.postgres -}}
{{- if not $pg.password -}}
{{- $_ := set $pg "password" (include "besa.existingOr" (dict "ns" $ns "name" "postgres-secret" "key" "POSTGRES_PASSWORD" "new" (randAlphaNum 24))) -}}
{{- end -}}
{{- $l := .Values.platform.litellm -}}
{{- if not $l.masterKey -}}
{{- /* LiteLLM requires master keys to start with sk- */ -}}
{{- $_ := set $l "masterKey" (include "besa.existingOr" (dict "ns" $ns "name" "litellm-secret" "key" "LITELLM_MASTER_KEY" "new" (printf "sk-%s" (randAlphaNum 32)))) -}}
{{- end -}}
{{- if not $l.uiPassword -}}
{{- $_ := set $l "uiPassword" (include "besa.existingOr" (dict "ns" $ns "name" "litellm-secret" "key" "UI_PASSWORD" "new" (randAlphaNum 20))) -}}
{{- end -}}
{{- $lf := .Values.platform.langfuse -}}
{{- if not $lf.nextAuthSecret -}}
{{- $_ := set $lf "nextAuthSecret" (include "besa.existingOr" (dict "ns" $ns "name" "langfuse-secret" "key" "NEXTAUTH_SECRET" "new" (randAlphaNum 32))) -}}
{{- end -}}
{{- if not $lf.salt -}}
{{- $_ := set $lf "salt" (include "besa.existingOr" (dict "ns" $ns "name" "langfuse-secret" "key" "SALT" "new" (randAlphaNum 32))) -}}
{{- end -}}
{{- if not $lf.encryptionKey -}}
{{- /* Langfuse wants exactly 64 hex characters; a sha256 digest is that */ -}}
{{- $_ := set $lf "encryptionKey" (include "besa.existingOr" (dict "ns" $ns "name" "langfuse-secret" "key" "ENCRYPTION_KEY" "new" (randAlphaNum 32 | sha256sum))) -}}
{{- end -}}
{{- end }}
