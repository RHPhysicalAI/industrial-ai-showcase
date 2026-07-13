{{/*
This project was developed with assistance from AI tools.

Helm template helpers for vllm-agent-brain chart
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "vllm-agent-brain.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "vllm-agent-brain.fullname" -}}
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
{{- define "vllm-agent-brain.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "vllm-agent-brain.labels" -}}
helm.sh/chart: {{ include "vllm-agent-brain.chart" . }}
{{ include "vllm-agent-brain.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "vllm-agent-brain.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vllm-agent-brain.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
vLLM command arguments
Builds the vLLM CLI args from values.yaml
*/}}
{{- define "vllm-agent-brain.args" -}}
- "--model={{ .Values.model.name }}"
- "--dtype={{ .Values.model.dtype }}"
- "--max-model-len={{ .Values.model.maxModelLen }}"
- "--gpu-memory-utilization={{ .Values.model.gpuMemoryUtilization }}"
{{- if .Values.model.disableFrontendMultiprocessing }}
- "--disable-frontend-multiprocessing"
{{- end }}
{{- if .Values.model.enableAutoToolChoice }}
- "--enable-auto-tool-choice"
{{- end }}
{{- if .Values.model.toolCallParser }}
- "--tool-call-parser={{ .Values.model.toolCallParser }}"
{{- end }}
- "--port=8000"
{{- end }}