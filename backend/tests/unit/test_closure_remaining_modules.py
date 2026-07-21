from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1 import auth as auth_api
from app.api.v1 import documents as documents_api
from app.api.v1 import health as health_api
from app.api.v1 import queries as queries_api
from app.core import ids as ids_module
from app.auth.dependencies import AuthContext, build_auth_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.auth.rbac import require_permissions
from app.auth.tenancy import (
    get_tenant_context,
    require_login_tenant_id,
    require_request_tenant_id,
)
from app.db import session as session_module
from app.auth.models.user import User
from app.documents.models.data_deletion import DataDeletion
from app.auth.repositories.roles import RolesRepository
from app.auth.repositories.users import UsersRepository
from app.documents.repositories.chunks import ChunksRepository
from app.documents.repositories.data_deletions import DataDeletionsRepository
from app.query.repositories.queries import QueriesRepository
from app.system.repositories.audit_logs import AuditLogsRepository
from app.documents.services.deletion_service import DeletionService
from app.ingestion.services.chunking_service import ChunkingService
from app.ingestion.services.parser_service import ParserService
from app.services.security.malware_scan_service import MalwareScanService
from app.system.services.audit_service import AuditService

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _mk_request(
    path: str = "/x",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_ids_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ids_module, "generate_uuid7", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    value = ids_module.generate_uuid7_with_fallback()
    assert value is not None


def test_tenancy_header_validations() -> None:
    with pytest.raises(ApiError):
        require_login_tenant_id(None)
    with pytest.raises(ApiError):
        require_login_tenant_id("bad")
    with pytest.raises(ApiError):
        require_request_tenant_id(None)
    with pytest.raises(ApiError):
        require_request_tenant_id("bad")


def test_get_tenant_context_applies_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, str] = {}

    def _apply(db, tenant_id):  # type: ignore[no-untyped-def]
        _ = db
        called["tenant"] = str(tenant_id)

    monkeypatch.setattr("app.auth.tenancy.apply_tenant_context", _apply)
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"admin"}),
        token_id=str(uuid4()),
    )
    result = get_tenant_context(auth=auth, db=cast(Session, object()))
    assert result.tenant_id == auth.tenant_id
    assert called["tenant"] == str(auth.tenant_id)


@pytest.mark.asyncio
async def test_rbac_dependency_paths() -> None:
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"reader"}),
        token_id=str(uuid4()),
    )
    dep_no_req = require_permissions()
    assert await dep_no_req(auth=auth) == auth

    dep_need_admin = require_permissions("admin:audit_logs:read")
    with pytest.raises(ApiError) as exc:
        await dep_need_admin(auth=auth)
    assert exc.value.code == "FORBIDDEN"


class _FakeSessionForDB:
    def __init__(
        self, *, rollback_fail=False, reset_fail=False, rollback2_fail=False
    ) -> None:
        self.rollback_calls = 0
        self.rollback_fail = rollback_fail
        self.reset_fail = reset_fail
        self.rollback2_fail = rollback2_fail
        self.closed = False

    def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
        _ = params
        if "RESET ROLE" in str(stmt) and self.reset_fail:
            raise RuntimeError("reset fail")
        return None

    def rollback(self):
        self.rollback_calls += 1
        if self.rollback_calls == 1 and self.rollback_fail:
            raise RuntimeError("rb1")
        if self.rollback_calls > 1 and self.rollback2_fail:
            raise RuntimeError("rb2")

    def commit(self):
        return None

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_get_db_cleanup_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_module,
        "DB_CONNECTION_CHECKOUT_DURATION_SECONDS",
        SimpleNamespace(observe=lambda *_: None),
    )
    monkeypatch.setattr(
        session_module,
        "get_session_factory",
        lambda: (
            lambda: _FakeSessionForDB(
                rollback_fail=True, reset_fail=True, rollback2_fail=True
            )
        ),
    )

    gen = session_module.get_db()
    db = next(gen)
    assert db is not None
    with pytest.raises(StopIteration):
        next(gen)


def test_reset_db_state_calls_cache_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    flags = {"engine": False, "session": False}
    monkeypatch.setattr(
        session_module.get_engine,
        "cache_clear",
        lambda: flags.__setitem__("engine", True),
    )
    monkeypatch.setattr(
        session_module.get_session_factory,
        "cache_clear",
        lambda: flags.__setitem__("session", True),
    )
    session_module.reset_db_state()
    assert flags["engine"] and flags["session"]


def test_register_exception_handlers_branches() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    class Payload(BaseModel):
        value: int

    @app.get("/http")
    def http_err():
        raise HTTPException(status_code=418, detail={"x": 1})

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    @app.post("/validation")
    def validation(payload: Payload):
        return payload

    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/validation", json={"value": "bad"}).status_code == 422
    assert client.get("/http").status_code == 418
    assert client.get("/boom").status_code == 500


@pytest.mark.asyncio
async def test_middleware_rate_limit_block_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Limiter:
        def enforce_global_ip_limit(self, *, request):  # type: ignore[no-untyped-def]
            request.state.rate_limit = SimpleNamespace(
                limit=10, remaining=0, reset_unix=123
            )
            raise ApiError(
                code="RATE_LIMIT_EXCEEDED", message="x", status_code=429, details={}
            )

    monkeypatch.setattr("app.core.middleware.get_settings", get_settings)
    monkeypatch.setattr(
        "app.core.middleware.RateLimitService", lambda _settings: _Limiter()
    )
    monkeypatch.setattr(
        "app.core.middleware.API_REQUESTS_TOTAL",
        SimpleNamespace(labels=lambda **_: SimpleNamespace(inc=lambda: None)),
    )
    monkeypatch.setattr(
        "app.core.middleware.API_REQUEST_LATENCY_SECONDS",
        SimpleNamespace(labels=lambda **_: SimpleNamespace(observe=lambda _: None)),
    )

    async def _app(scope: Any, receive: Any, send: Any) -> None:
        pass

    mw = RequestContextMiddleware(app=_app)
    req = _mk_request(path="/api/v1/queries")

    async def _next(_request):
        return Response(status_code=200)

    resp = await mw.dispatch(req, _next)
    assert resp.status_code == 429

    class _Limiter2:
        def enforce_global_ip_limit(self, *, request):  # type: ignore[no-untyped-def]
            request.state.rate_limit = SimpleNamespace(
                limit=10, remaining=9, reset_unix=123
            )

    monkeypatch.setattr(
        "app.core.middleware.RateLimitService", lambda _settings: _Limiter2()
    )
    req2 = _mk_request(path="/health/live")
    resp2 = await mw.dispatch(req2, _next)
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_auth_api_refresh_and_documents_and_queries_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()

    # auth refresh missing cookie
    with pytest.raises(ApiError) as refresh_missing:
        auth_api.refresh(
            request=_mk_request(path="/api/v1/auth/refresh"),
            response=Response(),
            db=cast(Session, SimpleNamespace()),
            settings=settings,
        )
    assert refresh_missing.value.code == "REFRESH_TOKEN_REQUIRED"

    # auth refresh invalid tenant-part path (except ValueError)
    req = _mk_request(
        path="/api/v1/auth/refresh",
        headers=[
            (
                b"cookie",
                f"{settings.refresh_cookie_name}=not-a-uuid.{'a' * 40}".encode(),
            )
        ],
    )

    class _AuthSvc:
        def __init__(self, db, settings):  # type: ignore[no-untyped-def]
            _ = (db, settings)

        def refresh(self, *, raw_refresh_token):  # type: ignore[no-untyped-def]
            _ = raw_refresh_token
            return SimpleNamespace(
                access_token="t", refresh_token=f"{uuid4()}.{'b' * 40}", expires_in=60
            )

    monkeypatch.setattr(auth_api, "AuthService", _AuthSvc)
    monkeypatch.setattr(
        auth_api,
        "RateLimitService",
        lambda _s: SimpleNamespace(enforce_auth_refresh_limit=lambda **_: None),
    )
    monkeypatch.setattr(
        auth_api,
        "AuditService",
        lambda _db: SimpleNamespace(write_event=lambda **_: None),
    )
    db = SimpleNamespace(commit=lambda: None)
    out = auth_api.refresh(
        request=req, response=Response(), db=cast(Session, db), settings=settings
    )
    assert out.access_token == "t"

    # documents errors
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"admin"}),
        token_id=str(uuid4()),
    )
    with pytest.raises(ApiError):
        await documents_api.upload_document(
            request=_mk_request(path="/api/v1/documents/upload", method="POST"),
            file=cast(
                UploadFile,
                SimpleNamespace(
                    read=lambda: b"", filename="x.pdf", content_type="application/pdf"
                ),
            ),
            idempotency_key=None,
            request_tenant_id=auth.tenant_id,
            auth=auth,
            db=cast(Session, SimpleNamespace()),
            settings=settings,
        )
    with pytest.raises(ApiError):
        await documents_api.upload_document(
            request=_mk_request(path="/api/v1/documents/upload", method="POST"),
            file=cast(
                UploadFile,
                SimpleNamespace(
                    read=lambda: b"", filename="x.pdf", content_type="application/pdf"
                ),
            ),
            idempotency_key="x" * 129,
            request_tenant_id=auth.tenant_id,
            auth=auth,
            db=cast(Session, SimpleNamespace()),
            settings=settings,
        )
    with pytest.raises(ApiError):
        await documents_api.upload_document(
            request=_mk_request(path="/api/v1/documents/upload", method="POST"),
            file=cast(
                UploadFile,
                SimpleNamespace(
                    read=lambda: b"", filename="x.pdf", content_type="application/pdf"
                ),
            ),
            idempotency_key="ok",
            request_tenant_id=uuid4(),
            auth=auth,
            db=cast(Session, SimpleNamespace()),
            settings=settings,
        )

    with pytest.raises(ApiError):
        documents_api.get_document(
            document_id=uuid4(),
            request_tenant_id=uuid4(),
            auth=auth,
            db=cast(Session, SimpleNamespace()),
            settings=settings,
        )
    with pytest.raises(ApiError):
        documents_api.get_document_status(
            document_id=uuid4(),
            request_tenant_id=uuid4(),
            auth=auth,
            db=cast(Session, SimpleNamespace()),
            settings=settings,
        )

    # queries errors
    monkeypatch.setattr(
        queries_api,
        "RateLimitService",
        lambda _s: SimpleNamespace(enforce_query_user_limit=lambda **_: None),
    )

    class _Req:
        def __init__(self, payload: Any) -> None:
            self._payload = payload
            self.state = SimpleNamespace()
            self.client = SimpleNamespace(host="127.0.0.1")

        async def json(self):
            return self._payload

    with pytest.raises(ApiError):
        await queries_api.run_query(
            request=_Req({}),  # type: ignore[arg-type]
            request_tenant_id=uuid4(),
            auth=auth,
            db=SimpleNamespace(),  # type: ignore[arg-type]
            settings=settings,
        )

    with pytest.raises(ApiError):
        await queries_api.run_query(
            request=_Req([]),  # type: ignore[arg-type]
            request_tenant_id=auth.tenant_id,
            auth=auth,
            db=SimpleNamespace(),  # type: ignore[arg-type]
            settings=settings,
        )

    with pytest.raises(ApiError):
        await queries_api.run_query(
            request=_Req({"query": "x", "filters": []}),  # type: ignore[arg-type]
            request_tenant_id=auth.tenant_id,
            auth=auth,
            db=SimpleNamespace(),  # type: ignore[arg-type]
            settings=settings,
        )

    with pytest.raises(ApiError):
        await queries_api.run_query(
            request=_Req({"query": "x", "filters": {"unknown": 1}}),  # type: ignore[arg-type]
            request_tenant_id=auth.tenant_id,
            auth=auth,
            db=SimpleNamespace(),  # type: ignore[arg-type]
            settings=settings,
        )

    with pytest.raises(ApiError):
        await queries_api.run_query(
            request=_Req({"query": "", "top_k": 0, "filters": {}}),  # type: ignore[arg-type]
            request_tenant_id=auth.tenant_id,
            auth=auth,
            db=SimpleNamespace(),  # type: ignore[arg-type]
            settings=settings,
        )


def test_health_ready_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

        def execute(self, stmt):  # type: ignore[no-untyped-def]
            _ = stmt
            raise SQLAlchemyError("db bad")

    monkeypatch.setattr(
        health_api, "get_engine", lambda: SimpleNamespace(connect=lambda: _Conn())
    )
    with pytest.raises(ApiError) as db_exc:
        health_api.ready()
    assert db_exc.value.code == "DATABASE_NOT_READY"

    class _ConnOk(_Conn):
        def execute(self, stmt):  # type: ignore[no-untyped-def]
            _ = stmt
            return None

    monkeypatch.setattr(
        health_api, "get_engine", lambda: SimpleNamespace(connect=lambda: _ConnOk())
    )
    monkeypatch.setattr(
        health_api,
        "get_redis_client",
        lambda: SimpleNamespace(
            ping=lambda: (_ for _ in ()).throw(RuntimeError("redis"))
        ),
    )
    with pytest.raises(ApiError) as redis_exc:
        health_api.ready()
    assert redis_exc.value.code == "REDIS_NOT_READY"


class _FakeExecResult:
    def __init__(self, rows):  # type: ignore[no-untyped-def]
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    def flush(self) -> None:
        self.flushed += 1

    def execute(self, stmt: Any) -> _FakeExecResult:
        _ = stmt
        return _FakeExecResult([])


def test_repository_branches() -> None:
    db = _FakeDB()
    tenant_id = uuid4()

    # Audit repo action + cursor branches
    repo_audit = AuditLogsRepository(db)  # type: ignore[arg-type]
    repo_audit.apply_tenant_scope = lambda _tenant: None  # type: ignore[assignment]
    db.execute = lambda stmt: _FakeExecResult(
        [SimpleNamespace(created_at=datetime.now(tz=UTC), id=uuid4())]
    )  # type: ignore[assignment]
    rows = repo_audit.list_page(
        tenant_id=tenant_id,
        limit=2,
        cursor_created_at=datetime.now(tz=UTC),
        cursor_id=uuid4(),
        action="x",
    )
    assert len(rows) == 1

    # Data deletion mark branches
    repo_del = DataDeletionsRepository(db)  # type: ignore[arg-type]
    repo_del.apply_tenant_scope = lambda _tenant: None  # type: ignore[assignment]
    row = SimpleNamespace(
        status="queued",
        started_at=None,
        failed_at=None,
        error_code="e",
        error_message="m",
        completed_at=None,
        result_counts={},
    )
    db.execute = lambda stmt: _FakeExecResult([])  # type: ignore[assignment]
    assert repo_del.get_next_queued(tenant_id=tenant_id) is None
    repo_del.mark_processing(tenant_id=tenant_id, row=cast(DataDeletion, row))
    repo_del.mark_completed(
        tenant_id=tenant_id, row=cast(DataDeletion, row), result_counts={"x": 1}
    )
    repo_del.mark_failed(
        tenant_id=tenant_id,
        row=cast(DataDeletion, row),
        error_code="e2",
        error_message="m2",
    )

    repo_chunks = ChunksRepository(db)  # type: ignore[arg-type]
    repo_chunks.apply_tenant_scope = lambda _tenant: None  # type: ignore[assignment]
    db.execute = lambda stmt: _FakeExecResult([])  # type: ignore[assignment]
    assert (
        repo_chunks.search_top_k(
            tenant_id=tenant_id,
            query_embedding=[0.1, 0.2],
            top_k=3,
            document_ids=[uuid4()],
            created_at_from=datetime.now(tz=UTC) - timedelta(days=1),
            created_at_to=datetime.now(tz=UTC),
            source_types=["prose"],
            min_extraction_coverage=0.1,
            max_extraction_coverage=0.9,
        )
        == []
    )

    repo_queries = QueriesRepository(db)  # type: ignore[arg-type]
    repo_queries.apply_tenant_scope = lambda _tenant: None  # type: ignore[assignment]
    db.execute = lambda stmt: _FakeExecResult([])  # type: ignore[assignment]
    assert repo_queries.get_query(tenant_id=tenant_id, query_id=uuid4()) is None

    # Roles/users branches
    repo_roles = RolesRepository(db)  # type: ignore[arg-type]
    db.execute = lambda stmt: _FakeExecResult([])  # type: ignore[assignment]
    assert repo_roles.get_by_name("none") is None

    repo_users = UsersRepository(db)  # type: ignore[arg-type]
    repo_users.apply_tenant_scope = lambda _tenant: None  # type: ignore[assignment]
    user = SimpleNamespace(
        failed_login_attempts=0, locked_until=None, last_login_at=None
    )
    repo_users.register_failed_login(
        tenant_id=tenant_id,
        user=cast(User, user),
        max_failed_attempts=1,
        lockout_minutes=10,
    )
    assert user.locked_until is not None


def test_audit_service_cursor_and_purge(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = AuditService(db=SimpleNamespace())  # type: ignore[arg-type]

    class _Repo:
        def list_page(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            now = datetime.now(tz=UTC)
            return [
                SimpleNamespace(created_at=now, id=uuid4()),
                SimpleNamespace(created_at=now, id=uuid4()),
            ]

        def delete_older_than(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            return 7

    svc.repo = _Repo()  # type: ignore[assignment]
    page = svc.list_events(
        tenant_id=uuid4(),
        limit=1,
        cursor=f"{datetime.now(tz=UTC).isoformat()}|{uuid4()}",
        action="x",
    )
    assert page.has_more is True
    assert page.next_cursor is not None
    assert svc.purge_old_events(tenant_id=uuid4(), retention_days=1) == 7


def test_deletion_service_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    svc = DeletionService(db=SimpleNamespace(commit=lambda: None), settings=settings)  # type: ignore[arg-type]

    # status early return branch
    row = SimpleNamespace(status="completed", id=uuid4(), requested_by_user_id=uuid4())
    svc.get_status = lambda **kwargs: row  # type: ignore[assignment]
    svc.process_deletion(tenant_id=uuid4(), deletion_id=uuid4())

    # storage delete exception warning branch in purge
    class _ExecRes:
        def __init__(self, rows=None, rowcount=1):
            self._rows = rows or []
            self.rowcount = rowcount

        def all(self):
            return self._rows

        def scalar_one(self):
            return self.rowcount

    class _DB:
        def execute(self, stmt):  # type: ignore[no-untyped-def]
            s = str(stmt)
            if "SELECT documents.storage_bucket" in s:
                return _ExecRes(rows=[("b", "k")])
            return _ExecRes(rowcount=1)

    svc.repo.apply_tenant_scope = lambda _tenant: None  # type: ignore[assignment]
    svc.db = _DB()  # type: ignore[assignment]
    svc.storage = SimpleNamespace(  # type: ignore[assignment]
        delete_object=lambda **_: (_ for _ in ()).throw(RuntimeError("x"))
    )
    counts = svc._purge_tenant_data(tenant_id=uuid4())
    assert counts["documents"] == 1

    # process_deletion exception branch (mark_failed + audit + re-raise)
    db_commits: list[str] = []
    svc.db = SimpleNamespace(commit=lambda: db_commits.append("commit"))  # type: ignore[assignment]
    failed_row = SimpleNamespace(
        status="queued", id=uuid4(), requested_by_user_id=uuid4()
    )
    svc.get_status = lambda **kwargs: failed_row  # type: ignore[assignment]
    mark_failed_calls: list[str] = []
    svc.repo = SimpleNamespace(  # type: ignore[assignment]
        mark_processing=lambda **kwargs: None,
        mark_completed=lambda **kwargs: None,
        mark_failed=lambda **kwargs: mark_failed_calls.append("failed"),
    )
    svc.audit = SimpleNamespace(write_event=lambda **kwargs: None)  # type: ignore[assignment]
    svc._purge_tenant_data = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("purge boom"))  # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        svc.process_deletion(tenant_id=uuid4(), deletion_id=uuid4())
    assert mark_failed_calls == ["failed"]


def test_parser_chunking_malware_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = ParserService(max_pdf_pages=1, max_text_chars=5)

    with pytest.raises(ApiError):
        parser.parse_bytes(
            filename="x.bin", content_type="application/octet-stream", payload=b"x"
        )

    monkeypatch.setattr(
        "app.ingestion.services.parser_service.PdfReader",
        lambda _bio: (_ for _ in ()).throw(RuntimeError("pdf")),
    )
    with pytest.raises(ApiError):
        parser.parse_bytes(
            filename="x.pdf", content_type="application/pdf", payload=b"x"
        )

    class _Page:
        def extract_text(self):
            return "abcdef"

    monkeypatch.setattr(
        "app.ingestion.services.parser_service.PdfReader",
        lambda _bio: SimpleNamespace(pages=[_Page(), _Page()]),
    )
    with pytest.raises(ApiError):
        parser.parse_bytes(
            filename="x.pdf", content_type="application/pdf", payload=b"x"
        )

    monkeypatch.setattr(
        "app.ingestion.services.parser_service.PdfReader",
        lambda _bio: SimpleNamespace(pages=[_Page()]),
    )
    with pytest.raises(ApiError):
        parser.parse_bytes(
            filename="x.pdf", content_type="application/pdf", payload=b"x"
        )

    with pytest.raises(ApiError):
        parser._parse_text(b"abcdef")
    parsed = ParserService(max_text_chars=100)._parse_text(b"\\xff")
    assert parsed.text

    chunker = ChunkingService()
    assert chunker.chunk("", chunk_size=10, overlap=1, min_length=1) == []
    with pytest.raises(ValueError):
        chunker.chunk("abc", chunk_size=0)
    with pytest.raises(ValueError):
        chunker.chunk("abc", chunk_size=3, overlap=-1)
    with pytest.raises(ValueError):
        chunker.chunk("abc", chunk_size=3, overlap=3)

    malware = MalwareScanService()
    assert (
        malware.scan_bytes(
            filename="empty.txt", content_type="text/plain", payload=b""
        ).is_clean
        is False
    )


def test_core_auth_and_config_remaining_branches() -> None:
    # core.auth branches
    with pytest.raises(ApiError):
        build_auth_context({"sub": "bad"}, None)
    with pytest.raises(ApiError):
        build_auth_context(
            {
                "sub": str(uuid4()),
                "tenant_id": str(uuid4()),
                "jti": str(uuid4()),
                "roles": "admin",
            },
            None,
        )
    with pytest.raises(ApiError):
        build_auth_context(
            {
                "sub": str(uuid4()),
                "tenant_id": str(uuid4()),
                "jti": str(uuid4()),
                "roles": [],
            },
            "bad-tenant",
        )

    # config validator branches
    with pytest.raises(ValidationError):
        Settings(env="invalid")
    with pytest.raises(ValidationError):
        Settings(jwt_secret="short")
    with pytest.raises(ValidationError):
        Settings(jwt_access_ttl_minutes=0)
    with pytest.raises(ValidationError):
        Settings(jwt_refresh_ttl_days=0)
    with pytest.raises(ValidationError):
        Settings(auth_max_failed_attempts=0)
    with pytest.raises(ValidationError):
        Settings(upload_max_bytes=0)
    with pytest.raises(ValidationError):
        Settings(llm_monthly_budget_usd=0)
    with pytest.raises(ValidationError):
        Settings(llm_temperature=3.0)
    with pytest.raises(ValidationError):
        Settings(query_top_k_min=10, query_top_k_max=1)
