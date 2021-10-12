
{{/* vim: set filetype=mustache: */}}
{{/*
Create inference server name.
*/}}
{{- define "faiss-grpc-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "faiss-grpc-server.fullname" -}}
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
  Create inference server metrics service name and fullname derived from above and
  truncated appropriately.
*/}}
{{- define "faiss-grpc-server-metrics.name" -}}
{{- $basename := include "faiss-grpc-server.name" . -}}
{{- $basename_trimmed := $basename | trunc 55 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics" -}}
{{- end -}}

{{- define "faiss-grpc-server-metrics.fullname" -}}
{{- $basename := include "faiss-grpc-server.fullname" . -}}
{{- $basename_trimmed := $basename | trunc 55 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics" -}}
{{- end -}}

{{/*
  Create inference server metrics monitor name and fullname derived from
  above and truncated appropriately.
*/}}
{{- define "faiss-grpc-server-metrics-monitor.name" -}}
{{- $basename := include "faiss-grpc-server.name" . -}}
{{- $basename_trimmed := $basename | trunc 47 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics-monitor" -}}
{{- end -}}

{{- define "faiss-grpc-server-metrics-monitor.fullname" -}}
{{- $basename := include "faiss-grpc-server.fullname" . -}}
{{- $basename_trimmed := $basename | trunc 47 | trimSuffix "-" -}}
{{- printf "%s-%s" $basename_trimmed "metrics-monitor" -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "faiss-grpc-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}
