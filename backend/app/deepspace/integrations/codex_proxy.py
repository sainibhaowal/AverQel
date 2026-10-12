from __future__ import annotations

CODEX_REQUEST_PREFIX = "averqel:codex-runtime:request:"
CODEX_RESPONSE_PREFIX = "averqel:codex-runtime:response:"
CODEX_ONLINE_PREFIX = "averqel:codex-runtime:online:"
CODEX_ONLINE_TTL_SECONDS = 30
CODEX_STREAM_TTL_SECONDS = 600
CODEX_MAX_PENDING_REQUESTS = 128

CODEX_ENQUEUE_REQUEST_SCRIPT = """
if redis.call('exists', KEYS[1]) == 0 then
  return 0
end
if redis.call('llen', KEYS[2]) >= tonumber(ARGV[3]) then
  return -1
end
redis.call('rpush', KEYS[2], ARGV[1])
redis.call('expire', KEYS[2], ARGV[2])
return 1
"""

CODEX_ENQUEUE_CANCEL_SCRIPT = """
if redis.call('exists', KEYS[1]) == 0 then
  return 0
end
redis.call('rpush', KEYS[2], ARGV[1])
redis.call('expire', KEYS[2], ARGV[2])
return 1
"""


def codex_request_key(tenant_id: str, user_id: str) -> str:
    return f"{CODEX_REQUEST_PREFIX}{tenant_id}:{user_id}"


def codex_online_key(tenant_id: str, user_id: str) -> str:
    return f"{CODEX_ONLINE_PREFIX}{tenant_id}:{user_id}"


def codex_response_key(request_id: str) -> str:
    return f"{CODEX_RESPONSE_PREFIX}{request_id}"
