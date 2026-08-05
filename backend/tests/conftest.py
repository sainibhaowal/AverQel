from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import UUID

# Local test workers do not run the Docker-only OTEL collector. Disable export
# before application modules construct Settings so traces remain test-local.
os.environ.setdefault("AKS_OTEL_ENABLED", "false")

import pytest
import urllib3
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.auth.roles import canonicalize_role_name

ALEMBIC_COMMAND = [sys.executable, "-m", "alembic"]


def _is_tcp_reachable(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_container_ip(container_name: str) -> str | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                container_name,
                "--format",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    ip_address = result.stdout.strip()
    return ip_address or None


def _docker_container_env(container_name: str) -> dict[str, str]:
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                container_name,
                "--format",
                "{{range .Config.Env}}{{println .}}{{end}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _docker_container_cmd(container_name: str) -> list[str]:
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                container_name,
                "--format",
                "{{json .Config.Cmd}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return []

    try:
        parsed = json.loads(result.stdout.strip() or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _resolve_sqlalchemy_url(url: str, *, container_name: str, container_port: int) -> str:
    parsed = make_url(url)
    container_env = _docker_container_env(container_name)
    username = container_env.get("POSTGRES_USER") or parsed.username
    password = container_env.get("POSTGRES_PASSWORD") or parsed.password
    database = parsed.database
    if database and database.endswith("_test"):
        database_name = database
    else:
        database_name = container_env.get("POSTGRES_DB") or database
    host = parsed.host or "localhost"
    port = int(parsed.port or 0)
    if port and _is_tcp_reachable(host, port):
        return parsed.set(
            username=username,
            password=password,
            database=database_name,
        ).render_as_string(hide_password=False)

    container_ip = _docker_container_ip(container_name)
    if not container_ip or not _is_tcp_reachable(container_ip, container_port):
        return parsed.set(
            username=username,
            password=password,
            database=database_name,
        ).render_as_string(hide_password=False)

    return parsed.set(
        username=username,
        password=password,
        database=database_name,
        host=container_ip,
        port=container_port,
    ).render_as_string(hide_password=False)


def _replace_netloc(split_result: SplitResult, *, host: str, port: int) -> SplitResult:
    credentials = ""
    if split_result.username is not None:
        credentials = split_result.username
        if split_result.password is not None:
            credentials = f"{credentials}:{split_result.password}"
        credentials = f"{credentials}@"
    return split_result._replace(netloc=f"{credentials}{host}:{port}")


def _resolve_url(url: str, *, container_name: str, container_port: int) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 0
    if port and _is_tcp_reachable(host, port):
        return url

    container_ip = _docker_container_ip(container_name)
    if not container_ip or not _is_tcp_reachable(container_ip, container_port):
        return url

    return urlunsplit(_replace_netloc(parsed, host=container_ip, port=container_port))


def _resolve_redis_url(url: str) -> str:
    command = _docker_container_cmd("averqel-redis")
    container_ip = _docker_container_ip("averqel-redis")
    password: str | None = None
    for index, part in enumerate(command):
        if part == "--requirepass" and index + 1 < len(command):
            password = command[index + 1]
            break

    if container_ip and _is_tcp_reachable(container_ip, 6379):
        parsed = urlsplit(url)
        username = parsed.username or ""
        if password:
            credentials = f":{password}@" if not username else f"{username}:{password}@"
        elif parsed.password:
            credentials = (
                f":{parsed.password}@" if not username else f"{username}:{parsed.password}@"
            )
        else:
            credentials = f"{username}@" if username else ""
        netloc = f"{credentials}{container_ip}:6379"
        return urlunsplit(parsed._replace(netloc=netloc))

    resolved_url = _resolve_url(url, container_name="averqel-redis", container_port=6379)
    parsed = urlsplit(resolved_url)
    if parsed.password or not password:
        return resolved_url

    username = parsed.username or ""
    credentials = f":{password}@" if not username else f"{username}:{password}@"
    netloc = f"{credentials}{parsed.hostname}:{parsed.port}"
    return urlunsplit(parsed._replace(netloc=netloc))


def _redis_url_with_db(url: str, db_index: int) -> str:
    parsed = urlsplit(url)
    path = f"/{db_index}"
    return urlunsplit(parsed._replace(path=path))


os.environ.setdefault("AKS_ENV", "test")
os.environ.setdefault(
    "AKS_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:1005/knowledge_test",
)
os.environ.setdefault("AKS_REDIS_URL", "redis://:averqel-redis-secret@localhost:1010/0")
os.environ.setdefault("AKS_JWT_SECRET", "test-jwt-secret-with-minimum-32-chars-123456")
os.environ.setdefault(
    "AKS_REFRESH_TOKEN_HASH_SECRET",
    "test-refresh-hash-secret-with-minimum-32-chars-123456",
)
os.environ.setdefault("AKS_REFRESH_COOKIE_SECURE", "false")
os.environ.setdefault("AKS_CELERY_TASK_ALWAYS_EAGER", "true")
os.environ["AKS_MINIO_ENDPOINT"] = "localhost:1015"
os.environ["AKS_MINIO_SECURE"] = "false"
os.environ["AKS_MINIO_VERIFY_SSL"] = "false"
os.environ.setdefault("AKS_AI_INTEGRATION_SCOPE", "embeddings_only")
os.environ.setdefault("AKS_EMBEDDING_PROVIDER", "local-deterministic")
os.environ.setdefault("AKS_EMBEDDING_MODEL", "hash-v1")
os.environ.setdefault("AKS_EMBEDDING_DIMENSION", "384")
os.environ.setdefault("AKS_LLM_PROVIDER", "disabled")
os.environ["AKS_LLM_MAX_REQUESTS_PER_MINUTE"] = "10000"
os.environ["AKS_LLM_MONTHLY_BUDGET_USD"] = "10000.0"
_minio_env = _docker_container_env("averqel-minio")
os.environ["AKS_DATABASE_URL"] = _resolve_sqlalchemy_url(
    os.environ["AKS_DATABASE_URL"],
    container_name="averqel-postgres",
    container_port=5432,
)
os.environ["AKS_REDIS_URL"] = _resolve_redis_url(os.environ["AKS_REDIS_URL"])
os.environ["AKS_MINIO_ENDPOINT"] = _resolve_url(
    f"http://{os.environ['AKS_MINIO_ENDPOINT']}",
    container_name="averqel-minio",
    container_port=9000,
).removeprefix("http://")
if _minio_env.get("MINIO_ROOT_USER"):
    os.environ.setdefault("AKS_MINIO_ACCESS_KEY", _minio_env["MINIO_ROOT_USER"])
if _minio_env.get("MINIO_ROOT_PASSWORD"):
    os.environ.setdefault("AKS_MINIO_SECRET_KEY", _minio_env["MINIO_ROOT_PASSWORD"])
logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_TEST_PROVIDER_SECRET_KEY = base64.urlsafe_b64encode(b"0" * 32).decode("utf-8")
os.environ.setdefault("AKS_PROVIDER_SECRET_ACTIVE_KID", "test-kid")
os.environ.setdefault(
    "AKS_PROVIDER_SECRET_KEYRING_JSON",
    json.dumps({"test-kid": _TEST_PROVIDER_SECRET_KEY}),
)
os.environ.setdefault("AKS_TOTP_SECRET_ACTIVE_KID", "test-kid")
os.environ.setdefault(
    "AKS_TOTP_SECRET_KEYRING_JSON",
    json.dumps({"test-kid": _TEST_PROVIDER_SECRET_KEY}),
)

# ---------------------------------------------------------------------------
# pytest-xdist: per-worker database & Redis isolation
# Each xdist worker (gw0, gw1, …) gets its own database and Redis DB so that
# parallel workers never interfere with each other.
# When running without xdist this block is skipped entirely.
# ---------------------------------------------------------------------------
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
if _xdist_worker is not None:
    _base_url = make_url(os.environ["AKS_DATABASE_URL"])
    _worker_db = f"{_base_url.database}_{_xdist_worker}"
    os.environ["AKS_DATABASE_URL"] = _base_url.set(
        database=_worker_db,
    ).render_as_string(hide_password=False)
    # Each worker uses a separate Redis DB (gw0→1, gw1→2, …)
    _worker_num = int(_xdist_worker.replace("gw", ""))
    os.environ["AKS_REDIS_URL"] = _redis_url_with_db(
        os.environ["AKS_REDIS_URL"],
        _worker_num + 1,
    )

import filelock  # noqa: E402

from app.auth.models.role import Role  # noqa: E402
from app.auth.models.tenant import Tenant  # noqa: E402
from app.auth.models.user import User  # noqa: E402
from app.auth.models.user_role import UserRole  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.ids import generate_uuid7_with_fallback  # noqa: E402
from app.ingestion.services.embedding_service import EmbeddingService  # noqa: E402
from app.main import create_app  # noqa: E402
from app.platform.database.session import (  # noqa: E402
    get_engine,
    get_session_factory,
    reset_db_state,
    set_db_tenant_context,
)
from app.query.services.answer_service import AnswerService  # noqa: E402
from app.system.services.rate_limit_service import (  # noqa: E402
    RateLimitService,
    _get_redis_client,
)

TEST_DATABASE_NAME = make_url(os.environ["AKS_DATABASE_URL"]).database or "knowledge_test"
SOURCE_DATABASE_NAME = (
    TEST_DATABASE_NAME[: -len("_test")] if TEST_DATABASE_NAME.endswith("_test") else "knowledge"
)
TEST_TEMPLATE_DATABASE_NAME = f"{SOURCE_DATABASE_NAME}_test_template"
RUNTIME_CACHE_DIR = Path(os.environ.get("AVERQEL_RUNTIME_CACHE_DIR", "/tmp/averqel/backend/cache"))
_DATABASE_TEST_FIXTURE_NAMES = {"client", "db_session", "seed_user"}
_DATABASE_SOURCE_TOKENS = (
    "get_session_factory(",
    "SessionLocal(",
    "get_db(",
    "create_engine(",
    "sessionmaker(",
    "app.platform.database",
)


def _generate_test_collection_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass(slots=True)
class SeededUser:
    tenant_id: UUID
    user_id: UUID
    collection_code: str
    email: str
    password: str


class TestDatabaseBootstrapUnavailableError(RuntimeError):
    """Raised when the test database cannot be prepared in this environment."""


def _ensure_default_roles(session) -> None:
    bind = session.get_bind()
    if bind is not None and not sa_inspect(bind).has_table(Role.__tablename__):
        Role.__table__.create(bind=bind, checkfirst=True)
    existing_names = {
        str(name)
        for name in session.execute(select(Role.name)).scalars().all()
        if isinstance(name, str) and name.strip()
    }
    default_roles = {
        "admin": "Platform admin with full administrative permissions.",
        "editor": "Can upload documents, manage collections, and configure providers.",
        "user": "Standard user who can read documents and run queries.",
    }
    missing = [
        Role(name=name, description=description)
        for name, description in default_roles.items()
        if name not in existing_names
    ]
    if missing:
        session.add_all(missing)
        session.flush()


def _all_selected_tests_use_no_db_bootstrap(session: pytest.Session) -> bool:
    items = list(getattr(session, "items", []))
    return bool(items) and all(item.get_closest_marker("unit_no_db") is not None for item in items)


def _is_strict_test_bootstrap() -> bool:
    if os.environ.get("AKS_TEST_ALLOW_BOOTSTRAP_SKIP", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return False
    # Database-backed runs must never silently become false-green runs. The
    # explicit escape hatch above is reserved for local diagnosis.
    return True


def _database_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise TestDatabaseBootstrapUnavailableError(
            f"unsafe PostgreSQL test database name: {name!r}"
        )
    return f'"{name}"'


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "xdist_group(name): assign a test to a named xdist loadgroup for serialized scheduling",
    )


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    del config
    configured = os.environ.get("AKS_TEST_XDIST_MAX_WORKERS", "").strip()
    if configured:
        try:
            return max(1, int(configured))
        except ValueError:
            logger.warning(
                "Invalid AKS_TEST_XDIST_MAX_WORKERS value %r; falling back to a safe default",
                configured,
            )
    cpu_count = os.cpu_count() or 1
    return max(1, min(4, cpu_count))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    for item in items:
        path = str(getattr(item, "path", getattr(item, "fspath", ""))).replace("\\", "/")
        if (
            "/tests/unit/" in path
            and item.get_closest_marker("unit_no_db") is None
            and item.get_closest_marker("db") is None
        ):
            try:
                source = Path(path).read_text(encoding="utf-8")
            except OSError:
                source = ""
            fixture_names = set(getattr(item, "fixturenames", ()))
            has_database_dependency = bool(fixture_names & _DATABASE_TEST_FIXTURE_NAMES) or any(
                token in source for token in _DATABASE_SOURCE_TOKENS
            )
            if not has_database_dependency:
                # Conservative source-level classification for unit modules
                # that use fakes/mocks only. A module can opt out with
                # pytestmark = pytest.mark.db when it gains a database path.
                item.add_marker(pytest.mark.unit_no_db)

        if item.get_closest_marker("unit_no_db") is None:
            item.add_marker(pytest.mark.db)
        if "/tests/e2e/" in path:
            item.add_marker(pytest.mark.e2e)
            # E2E tests exercise shared object-storage/application workflows;
            # keep those workflows serialized until they have explicit
            # per-test storage namespaces.
            item.add_marker(pytest.mark.xdist_group("e2e_serial"))


@pytest.fixture(scope="session", autouse=True)
def migrate_database(request: pytest.FixtureRequest) -> Iterator[None]:
    if _all_selected_tests_use_no_db_bootstrap(request.session):
        yield
        return

    get_settings.cache_clear()
    reset_db_state()
    try:
        _reset_test_database_from_template()
    except TestDatabaseBootstrapUnavailableError as exc:
        if _is_strict_test_bootstrap():
            raise
        pytest.skip(str(exc))
    yield


@pytest.fixture(autouse=True)
def clean_database(
    migrate_database: None,
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    if _all_selected_tests_use_no_db_bootstrap(request.session):
        yield
        return

    get_settings.cache_clear()
    use_transaction = (
        request.node.get_closest_marker("db_commit") is None
        and request.node.get_closest_marker("e2e") is None
    )
    if not use_transaction:
        try:
            yield
        finally:
            _truncate_test_tables()
            get_settings.cache_clear()
        return

    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = get_session_factory()
    # Every application/test session opened during this test joins the same
    # worker-local outer transaction. SQLAlchemy uses SAVEPOINTs for commit()
    # so existing tests retain real commit semantics while the outer rollback
    # removes all state at test teardown.
    session_factory.configure(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield
    finally:
        with suppress(Exception):
            transaction.rollback()
        with suppress(Exception):
            session_factory.configure(bind=engine)
        with suppress(Exception):
            connection.close()
        with suppress(Exception):
            engine.dispose()
        reset_db_state()
        _reset_in_memory_and_redis_state()
        get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def client() -> Iterator[TestClient]:
    get_settings.cache_clear()
    reset_db_state()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Iterator[object]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seed_user() -> Callable[[str, str, str, tuple[str, ...]], SeededUser]:
    def _seed(tenant_name: str, email: str, password: str, roles: tuple[str, ...]) -> SeededUser:
        normalized_email = email.strip().lower()
        canonical_roles = tuple(canonicalize_role_name(role) for role in roles)
        session = get_session_factory()()
        try:
            _ensure_default_roles(session)
            tenant = Tenant(id=generate_uuid7_with_fallback(), name=tenant_name)
            session.add(tenant)
            session.flush()

            set_db_tenant_context(session, tenant.id)
            user = User(
                id=generate_uuid7_with_fallback(),
                tenant_id=tenant.id,
                email=normalized_email,
                collection_code=_generate_test_collection_code(),
                password_hash=hash_password(password),
                is_active=True,
            )
            session.add(user)
            session.flush()

            role_rows = (
                session.execute(select(Role).where(Role.name.in_(canonical_roles))).scalars().all()
            )
            if len(role_rows) != len(set(canonical_roles)):
                raise AssertionError("requested role is missing from seeded role catalog")
            for role in role_rows:
                session.add(
                    UserRole(
                        id=generate_uuid7_with_fallback(),
                        tenant_id=tenant.id,
                        user_id=user.id,
                        role_id=role.id,
                    )
                )
            tenant_id = tenant.id
            user_id = user.id
            session.commit()
            return SeededUser(
                tenant_id=tenant_id,
                user_id=user_id,
                collection_code=user.collection_code,
                email=normalized_email,
                password=password,
            )
        finally:
            session.rollback()
            session.close()

    return _seed


def _truncate_test_tables() -> None:
    _reset_in_memory_and_redis_state()
    reset_db_state()
    engine = get_engine()
    engine.dispose()

    tables_to_truncate = [
        "provider_usage_records",
        "provider_health_checks",
        "provider_assignments",
        "provider_model_cache",
        "provider_secrets",
        "provider_configs",
        "query_citations",
        "queries",
        "idempotency_keys",
        "chunk_embeddings",
        "document_chunks",
        "ingestion_jobs",
        "documents",
        "data_deletions",
        "audit_logs",
        "refresh_tokens",
        "user_roles",
        "users",
        "tenants",
    ]
    last_exc: OperationalError | ProgrammingError | None = None
    for _ in range(3):
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text("RESET ROLE"))
                existing_tables = [
                    table_name
                    for table_name in tables_to_truncate
                    if connection.execute(
                        text("SELECT to_regclass(:name)"),
                        {"name": table_name},
                    ).scalar()
                    is not None
                ]
                if existing_tables:
                    truncate_sql = text(
                        "SET statement_timeout = '5s';"
                        "TRUNCATE TABLE " + ", ".join(existing_tables) + " RESTART IDENTITY CASCADE"
                    )
                    connection.execute(truncate_sql)
            last_exc = None
            break
        except (OperationalError, ProgrammingError) as exc:
            last_exc = exc
            engine.dispose()
            time.sleep(0.25)
    if last_exc is not None:
        # If it timed out, just log and continue rather than hanging the worker
        logger.warning(f"Database truncation timed out or failed: {last_exc}")

    engine.dispose()


def _grant_test_database_access(connection) -> None:
    """Re-apply runtime grants after a schema restore or local bootstrap."""
    connection.execute(text("GRANT USAGE ON SCHEMA public TO aks_app"))
    connection.execute(
        text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aks_app")
    )
    connection.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aks_app"))
    connection.execute(text("""
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aks_app
            """))
    connection.execute(text("""
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO aks_app
            """))


def _grant_database_access(test_url, database_name: str) -> None:
    database_engine = create_engine(
        test_url.set(database=database_name).render_as_string(hide_password=False),
        pool_pre_ping=True,
    )
    try:
        with database_engine.begin() as connection:
            _grant_test_database_access(connection)
    finally:
        database_engine.dispose()


def _reset_test_database_from_template() -> None:
    """Create the worker database from one migrated template.

    The template is rebuilt when the source migration head changes.
    Worker databases are then created with PostgreSQL's native TEMPLATE
    operation, avoiding a pg_dump/restore and Alembic run for every xdist
    worker.
    """
    RUNTIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = RUNTIME_CACHE_DIR / "pytest-postgres-clone.lock"
    with filelock.FileLock(str(lock_path)):
        try:
            test_url = make_url(os.environ["AKS_DATABASE_URL"])
            admin_url = test_url.set(database="postgres")
            admin_engine = create_engine(
                admin_url.render_as_string(hide_password=False),
                pool_pre_ping=True,
            )
            try:
                _ensure_test_database_template(admin_engine, test_url)
                for _ in range(3):
                    try:
                        with admin_engine.connect().execution_options(
                            isolation_level="AUTOCOMMIT"
                        ) as connection:
                            connection.execute(
                                text(
                                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                                ),
                                {"name": TEST_DATABASE_NAME},
                            )
                            connection.execute(
                                text(
                                    f"DROP DATABASE IF EXISTS "
                                    f"{_database_identifier(TEST_DATABASE_NAME)}"
                                )
                            )
                            connection.execute(
                                text(
                                    f"CREATE DATABASE {_database_identifier(TEST_DATABASE_NAME)} "
                                    f"TEMPLATE {_database_identifier(TEST_TEMPLATE_DATABASE_NAME)}"
                                )
                            )
                        break
                    except OperationalError:
                        admin_engine.dispose()
                else:
                    raise TestDatabaseBootstrapUnavailableError(
                        f"failed to reset test database {TEST_DATABASE_NAME}"
                    )
            finally:
                admin_engine.dispose()

            _wait_for_database(TEST_DATABASE_NAME)
            _grant_database_access(test_url, TEST_DATABASE_NAME)
        except Exception as exc:
            raise TestDatabaseBootstrapUnavailableError(
                "isolated PostgreSQL test bootstrap failed; refusing to run "
                "against a shared or partially initialized database"
            ) from exc


def _database_revisions(engine, database_name: str) -> tuple[str, ...]:
    database_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    try:
        with database_engine.connect() as connection:
            return tuple(
                str(value)
                for value in connection.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                ).scalars()
            )
    except (OperationalError, ProgrammingError):
        return ()


def _expected_alembic_heads() -> tuple[str, ...]:
    """Read migration heads from source, not from a potentially stale dev database."""
    try:
        result = subprocess.run(
            [*ALEMBIC_COMMAND, "heads"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ()
    return tuple(
        line.split(maxsplit=1)[0]
        for line in result.stdout.splitlines()
        if line.strip() and "(head)" in line
    )


def _ensure_test_database_template(admin_engine, test_url) -> None:
    template_exists = False
    expected_heads = _expected_alembic_heads()
    try:
        with admin_engine.connect() as connection:
            template_exists = bool(
                connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": TEST_TEMPLATE_DATABASE_NAME},
                ).scalar()
            )
    except Exception:
        expected_heads = ()

    if template_exists and expected_heads:
        template_engine = create_engine(
            test_url.set(database=TEST_TEMPLATE_DATABASE_NAME).render_as_string(
                hide_password=False
            ),
            pool_pre_ping=True,
        )
        template_revisions = _database_revisions(template_engine, TEST_TEMPLATE_DATABASE_NAME)
        template_engine.dispose()
        if template_revisions == expected_heads:
            return

    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": TEST_TEMPLATE_DATABASE_NAME},
        )
        if template_exists:
            # PostgreSQL refuses to drop a database while it is marked as a clone
            # template. Clear the marker before rebuilding for a newer migration head.
            connection.execute(
                text(
                    f"ALTER DATABASE {_database_identifier(TEST_TEMPLATE_DATABASE_NAME)} "
                    "IS_TEMPLATE FALSE"
                )
            )
        connection.execute(
            text(f"DROP DATABASE IF EXISTS " f"{_database_identifier(TEST_TEMPLATE_DATABASE_NAME)}")
        )
        connection.execute(
            text(f"CREATE DATABASE {_database_identifier(TEST_TEMPLATE_DATABASE_NAME)}")
        )

    schema_dump = subprocess.run(
        [
            "docker",
            "exec",
            "averqel-postgres",
            "pg_dump",
            "-U",
            "postgres",
            "--schema-only",
            "--no-owner",
            SOURCE_DATABASE_NAME,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout
    _restore_dump_into_database(TEST_TEMPLATE_DATABASE_NAME, schema_dump)
    seed_dump = subprocess.run(
        [
            "docker",
            "exec",
            "averqel-postgres",
            "pg_dump",
            "-U",
            "postgres",
            "--data-only",
            "--column-inserts",
            "--table=roles",
            "--table=alembic_version",
            SOURCE_DATABASE_NAME,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout
    _restore_dump_into_database(TEST_TEMPLATE_DATABASE_NAME, seed_dump)
    template_env = os.environ.copy()
    template_env["AKS_DATABASE_URL"] = test_url.set(
        database=TEST_TEMPLATE_DATABASE_NAME
    ).render_as_string(hide_password=False)
    subprocess.run(
        [*ALEMBIC_COMMAND, "upgrade", "heads"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        check=True,
        env=template_env,
        timeout=120,
    )
    _grant_database_access(test_url, TEST_TEMPLATE_DATABASE_NAME)
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                f"ALTER DATABASE {_database_identifier(TEST_TEMPLATE_DATABASE_NAME)} "
                "IS_TEMPLATE TRUE"
            )
        )


def _wait_for_database(
    database_name: str, *, attempts: int = 10, delay_seconds: float = 0.5
) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for _ in range(attempts):
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "averqel-postgres",
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                    "-tAc",
                    f"SELECT 1 FROM pg_database WHERE datname = '{database_name}'",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.stdout.strip() == "1":
                return
        except subprocess.CalledProcessError as exc:
            last_error = exc
        time.sleep(delay_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"database {database_name} did not become ready")


def _restore_dump_into_database(
    database_name: str,
    dump_bytes: bytes,
    *,
    attempts: int = 5,
    delay_seconds: float = 0.75,
) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for _ in range(attempts):
        _wait_for_database(database_name)
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    "averqel-postgres",
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    database_name,
                ],
                input=dump_bytes,
                check=True,
                timeout=120,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            time.sleep(delay_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"failed to restore database dump into {database_name}")


def _reset_in_memory_and_redis_state() -> None:
    RateLimitService._memory_store._values.clear()
    AnswerService._limit_state.requests.clear()
    AnswerService._limit_state.cost_micros.clear()
    AnswerService._llm_circuit.failures = 0
    AnswerService._llm_circuit.opened_until = None
    EmbeddingService._state.failures = 0
    EmbeddingService._state.opened_until = None

    try:
        _get_redis_client().flushdb()
    except Exception:
        pass
