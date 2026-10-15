{{- define "platform.image" -}}
{{- $digest := .Values.image.digest | default "" -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $digest) -}}
{{- fail "image.digest must be sha256 followed by 64 lowercase hex characters" -}}
{{- end -}}
{{- printf "%s@%s" .Values.image.repository $digest -}}
{{- else -}}
{{- $tag := required "Set image.tag to a tested commit SHA or set image.digest" .Values.image.tag -}}
{{- if not (regexMatch "^[a-f0-9]{40}$" $tag) -}}
{{- fail "image.tag must be a full 40-character commit SHA" -}}
{{- end -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}
{{- end -}}
