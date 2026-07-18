#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/.env.vps}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

require_nonempty() {
  local key="$1"
  if ! grep -Eq "^${key}=.+" "$ENV_FILE"; then
    echo "FAIL: missing $key" >&2
    return 1
  fi
  return 0
}

check_permissions() {
  local mode
  mode="$(stat -c '%a' "$ENV_FILE")"
  if [[ "$mode" =~ ^[0-6][0-6][0-6]$ ]]; then
    local owner="${mode:0:1}"
    local group="${mode:1:1}"
    local other="${mode:2:1}"
    if (( other > 0 || group > 4 || owner > 6 )); then
      echo "FAIL: env file permissions are too open ($mode); use chmod 600 $ENV_FILE" >&2
      return 1
    fi
  fi
  echo "OK: env file permissions are restricted"
  return 0
}

get_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

status=0

check_permissions || status=1

for key in \
  AKS_ENV \
  AKS_DATABASE_URL \
  AKS_REDIS_URL \
  AKS_JWT_SECRET \
  AKS_REFRESH_TOKEN_HASH_SECRET \
  AKS_PROVIDER_SECRET_BACKEND \
  AKS_ADMIN_BREAK_GLASS_ENABLED
do
  require_nonempty "$key" || status=1
done

provider_backend="$(get_value AKS_PROVIDER_SECRET_BACKEND)"
break_glass_enabled="$(get_value AKS_ADMIN_BREAK_GLASS_ENABLED)"

if [[ "$provider_backend" == "aws_kms" ]]; then
  for key in AKS_PROVIDER_SECRET_AWS_KMS_KEY_ID AKS_PROVIDER_SECRET_AWS_KMS_REGION; do
    require_nonempty "$key" || status=1
  done
  echo "OK: provider secrets configured for AWS KMS"
else
  require_nonempty AKS_PROVIDER_SECRET_ACTIVE_KID || status=1
  require_nonempty AKS_PROVIDER_SECRET_KEYRING_JSON || status=1
  echo "OK: provider secrets configured for env-managed AES keyring"
fi

if [[ "$break_glass_enabled" != "false" ]]; then
  echo "WARN: AKS_ADMIN_BREAK_GLASS_ENABLED is not false"
  status=1
else
  echo "OK: break-glass is disabled by default"
fi

for key in AKS_JWT_SECRET AKS_REFRESH_TOKEN_HASH_SECRET; do
  value="$(get_value "$key")"
  if [[ "$value" == *change-me* || ${#value} -lt 32 ]]; then
    echo "FAIL: $key is weak or default-like"
    status=1
  fi
done

for key in AVERQEL_POSTGRES_PASSWORD AVERQEL_REDIS_PASSWORD AVERQEL_MINIO_ROOT_PASSWORD; do
  value="$(get_value "$key")"
  if [[ -z "$value" || "$value" == *change-me* || ${#value} -lt 24 ]]; then
    echo "FAIL: $key is weak or missing"
    status=1
  fi
done

if [[ "$(get_value AKS_PROVIDER_SECRET_AUDIT_READS)" != "true" ]]; then
  echo "FAIL: AKS_PROVIDER_SECRET_AUDIT_READS must stay true in production"
  status=1
else
  echo "OK: provider secret access auditing is enabled"
fi

if [[ "$(get_value AKS_ENV)" != "production" ]]; then
  echo "FAIL: AKS_ENV is not production"
  status=1
else
  echo "OK: AKS_ENV=production"
fi

public_origin="$(get_value AVERQEL_PUBLIC_ORIGIN)"
if [[ -n "$public_origin" ]]; then
  if [[ "$public_origin" != https://* ]]; then
    echo "FAIL: AVERQEL_PUBLIC_ORIGIN must use https in production"
    status=1
  else
    echo "OK: AVERQEL_PUBLIC_ORIGIN is https"
  fi
fi

connector_redirect_uri="$(get_value AKS_CONNECTOR_OAUTH_REDIRECT_URI)"
connector_frontend_redirect_uri="$(get_value AKS_CONNECTOR_OAUTH_FRONTEND_REDIRECT_URI)"
derived_connector_redirect_uri=""
derived_connector_frontend_redirect_uri=""
if [[ -n "$public_origin" ]]; then
  derived_connector_redirect_uri="${public_origin%/}/api/v1/integrations/connectors/oauth/callback"
  derived_connector_frontend_redirect_uri="${public_origin%/}/dashboard/connectors"
fi

if [[ -n "$connector_redirect_uri" ]]; then
  if [[ "$connector_redirect_uri" != https://* || "$connector_redirect_uri" != *"/api/v1/integrations/connectors/oauth/callback" ]]; then
    echo "FAIL: AKS_CONNECTOR_OAUTH_REDIRECT_URI must be an https callback URL ending in /api/v1/integrations/connectors/oauth/callback"
    status=1
  elif [[ -n "$derived_connector_redirect_uri" && "$connector_redirect_uri" != "$derived_connector_redirect_uri" ]]; then
    echo "FAIL: AKS_CONNECTOR_OAUTH_REDIRECT_URI must match the URL derived from AVERQEL_PUBLIC_ORIGIN ($derived_connector_redirect_uri)"
    status=1
  else
    echo "OK: connector OAuth callback URL is valid"
  fi
elif [[ -n "$derived_connector_redirect_uri" ]]; then
  echo "OK: connector OAuth callback URL will be derived from AVERQEL_PUBLIC_ORIGIN"
else
  echo "FAIL: AVERQEL_PUBLIC_ORIGIN or AKS_CONNECTOR_OAUTH_REDIRECT_URI must be configured"
  status=1
fi

if [[ -n "$connector_frontend_redirect_uri" ]]; then
  if [[ "$connector_frontend_redirect_uri" != https://* || "$connector_frontend_redirect_uri" != *"/dashboard/connectors" ]]; then
    echo "FAIL: AKS_CONNECTOR_OAUTH_FRONTEND_REDIRECT_URI must be an https frontend URL ending in /dashboard/connectors"
    status=1
  elif [[ -n "$derived_connector_frontend_redirect_uri" && "$connector_frontend_redirect_uri" != "$derived_connector_frontend_redirect_uri" ]]; then
    echo "FAIL: AKS_CONNECTOR_OAUTH_FRONTEND_REDIRECT_URI must match the URL derived from AVERQEL_PUBLIC_ORIGIN ($derived_connector_frontend_redirect_uri)"
    status=1
  else
    echo "OK: connector OAuth frontend redirect URL is valid"
  fi
elif [[ -n "$derived_connector_frontend_redirect_uri" ]]; then
  echo "OK: connector OAuth frontend redirect URL will be derived from AVERQEL_PUBLIC_ORIGIN"
else
  echo "FAIL: AVERQEL_PUBLIC_ORIGIN or AKS_CONNECTOR_OAUTH_FRONTEND_REDIRECT_URI must be configured"
  status=1
fi

exit "$status"
