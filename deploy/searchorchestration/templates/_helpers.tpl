
{{/* vim: set filetype=mustache: */}}
{{/*
Create search orchestration name.
*/}}
{{- define "search-orchestration.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "search-orchestration.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "search-orchestration.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
  Create orchestration metrics service name and fullname derived from above and
  truncated appropriately.
*/}}
{{- define "search-orchestration-metrics.name" -}}
{{- $basename := include "search-orchestration.name" . -}}
{{- $basename_trimmed := $basename | trunc 55 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics" -}}
{{- end -}}

{{- define "search-orchestration-metrics.fullname" -}}
{{- $basename := include "search-orchestration.fullname" . -}}
{{- $basename_trimmed := $basename | trunc 55 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics" -}}
{{- end -}}

{{/*
  Create orchestration metrics monitor name and fullname derived from
  above and truncated appropriately.
*/}}
{{- define "search-orchestration-metrics-monitor.name" -}}
{{- $basename := include "search-orchestration.name" . -}}
{{- $basename_trimmed := $basename | trunc 47 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics-monitor" -}}
{{- end -}}

{{- define "search-orchestration-metrics-monitor.fullname" -}}
{{- $basename := include "search-orchestration.fullname" . -}}
{{- $basename_trimmed := $basename | trunc 47 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics-monitor" -}}
{{- end -}}

