{{- define "platform.image" -}}
{{- if and .Values.autoscaling.enabled (lt (int .Values.autoscaling.maxReplicas) (int .Values.autoscaling.minReplicas)) -}}
{{- fail "autoscaling.maxReplicas must be at least autoscaling.minReplicas" -}}
{{- end -}}
{{- $minimum := ternary (int .Values.autoscaling.minReplicas) (int .Values.replicaCount) .Values.autoscaling.enabled -}}
{{- if gt (int .Values.pdb.minAvailable) $minimum -}}
{{- fail "pdb.minAvailable cannot exceed the minimum replica count" -}}
{{- end -}}
{{- $digest := .Values.image.digest | default "" -}}
{{- if and .Values.production (not $digest) -}}
{{- fail "Production deployments require image.digest" -}}
{{- end -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $digest) -}}
{{- fail "image.digest must be sha256 followed by 64 lowercase hex characters" -}}
{{- end -}}
{{- printf "%s@%s" .Values.image.repository $digest -}}
{{- else -}}
{{- $tag := required "Set image.tag to a full commit SHA or set image.digest" .Values.image.tag -}}
{{- if not (regexMatch "^[a-f0-9]{40}$" $tag) -}}
{{- fail "image.tag must be a full 40-character commit SHA" -}}
{{- end -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}
{{- end -}}
