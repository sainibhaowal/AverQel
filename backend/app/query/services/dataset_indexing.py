"""Bounded, exact table indexing and querying for Grounded Query attachments."""

from __future__ import annotations

import csv
import io
import logging
import math
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.documents.models.document import Document
from app.query.models.dataset_index import QueryDatasetIndex
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.storage_service import StorageService

MAX_GROUNDED_DATASET_BYTES = 25 * 1024 * 1024
MAX_GROUNDED_DATASET_ROWS = 1_000_000
MAX_GROUNDED_DATASET_COLUMNS = 256
MAX_GROUNDED_DATASET_QUERY_ROWS = 100
MAX_GROUNDED_DATASET_FILTERS = 10
MAX_GROUNDED_DATASET_GROUP_COLUMNS = 3
MAX_GROUNDED_DATASET_REFERENCE_ROWS = 20
MAX_GROUNDED_DATASET_PREVIEW_CELL_CHARS = 4_000
DATASET_INDEX_FILENAME = "_grounded_query_dataset.parquet"
SOURCE_ROW_COLUMN = "__gq_source_row_number"
logger = logging.getLogger(__name__)

_CSV_TYPES = {"text/csv", "text/x-csv"}
_TSV_TYPES = {"text/tab-separated-values", "text/tsv"}
_PROCESSING_STALE_SECONDS = 10 * 60


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    row_count: int
    columns: list[dict[str, str]]
    parquet_payload: bytes


def is_tabular_document(document: Document) -> bool:
    suffix = Path(str(getattr(document, "filename", ""))).suffix.lower()
    content_type = (getattr(document, "content_type", None) or "").lower().split(";", 1)[0]
    return suffix in {".csv", ".tsv"} or content_type in _CSV_TYPES | _TSV_TYPES


def _delimiter_for_document(document: Document) -> str:
    suffix = Path(str(getattr(document, "filename", ""))).suffix.lower()
    content_type = (getattr(document, "content_type", None) or "").lower().split(";", 1)[0]
    return "\t" if suffix == ".tsv" or content_type in _TSV_TYPES else ","


def _validate_csv_source(payload: bytes, delimiter: str) -> tuple[list[str], int]:
    """Validate the whole CSV source and count rows before DuckDB indexes it."""
    try:
        with io.TextIOWrapper(
            io.BytesIO(payload), encoding="utf-8-sig", errors="strict", newline=""
        ) as text_file:
            reader = csv.reader(text_file, delimiter=delimiter, strict=True)
            header = next(reader, None)
            if not header or len(header) > MAX_GROUNDED_DATASET_COLUMNS:
                raise ApiError(
                    code="DATASET_INVALID_HEADER",
                    message=f"A table must have between 1 and {MAX_GROUNDED_DATASET_COLUMNS} columns.",
                    status_code=422,
                )
            names = [name.strip() for name in header]
            normalized = [name.casefold() for name in names]
            if any(not name for name in names) or len(set(normalized)) != len(normalized):
                raise ApiError(
                    code="DATASET_INVALID_HEADER",
                    message="Column names must be non-empty and unique, ignoring letter case.",
                    status_code=422,
                )
            if any(name.casefold() == SOURCE_ROW_COLUMN.casefold() for name in names):
                raise ApiError(
                    code="DATASET_RESERVED_COLUMN",
                    message=f"The column name {SOURCE_ROW_COLUMN} is reserved for source row tracking.",
                    status_code=422,
                )

            row_count = 0
            for row_number, row in enumerate(reader, start=2):
                if len(row) != len(names):
                    raise ApiError(
                        code="DATASET_PARSE_FAILED",
                        message=(
                            f"The table has a row with {len(row)} fields; expected {len(names)}. "
                            "No rows were indexed."
                        ),
                        status_code=422,
                        details={"source_row_number": row_number},
                    )
                row_count += 1
                if row_count > MAX_GROUNDED_DATASET_ROWS:
                    raise ApiError(
                        code="DATASET_ROW_LIMIT_EXCEEDED",
                        message=(
                            "Grounded Query table indexing supports up to 1,000,000 data rows. "
                            "The file was rejected without dropping rows."
                        ),
                        status_code=422,
                        details={"max_rows": MAX_GROUNDED_DATASET_ROWS},
                    )

    except (UnicodeDecodeError, csv.Error) as exc:
        raise ApiError(
            code="DATASET_PARSE_FAILED",
            message="This CSV or TSV is malformed or is not valid UTF-8. No rows were indexed.",
            status_code=422,
        ) from exc
    return names, row_count


def _sql_string(value: str) -> str:
    """Quote an internal temporary path or delimiter for DuckDB SQL."""
    return "'" + value.replace("'", "''") + "'"


def _csv_relation(source_path: Path, delimiter: str) -> str:
    return (
        "read_csv("
        f"{_sql_string(str(source_path))}, delim = {_sql_string(delimiter)}, "
        f"header = true, auto_detect = true, sample_size = -1, max_line_size = {MAX_GROUNDED_DATASET_BYTES}, "
        "strict_mode = true, "
        "ignore_errors = false, null_padding = false)"
    )


def build_parquet_derivative(*, document: Document, payload: bytes) -> DatasetBuildResult:
    """Parse a complete CSV/TSV into a private Parquet derivative, never truncating rows."""
    if len(payload) > MAX_GROUNDED_DATASET_BYTES:
        raise ApiError(
            code="DATASET_FILE_TOO_LARGE",
            message="Grounded Query table indexing supports files up to 25 MiB.",
            status_code=413,
            details={"max_bytes": MAX_GROUNDED_DATASET_BYTES},
        )
    delimiter = _delimiter_for_document(document)
    header_names, validated_row_count = _validate_csv_source(payload, delimiter)
    try:
        with tempfile.TemporaryDirectory(prefix="averqel-grounded-dataset-") as temp_dir:
            source_path = Path(temp_dir) / "source.csv"
            parquet_path = Path(temp_dir) / "dataset.parquet"
            source_path.write_bytes(payload)
            connection = duckdb.connect(database=":memory:")
            try:
                connection.execute("SET threads = 1")
                connection.execute("SET memory_limit = '512MB'")
                connection.execute("SET temp_directory = ?", [temp_dir])
                csv_reader = _csv_relation(source_path, delimiter)
                count_result = connection.execute(
                    f"SELECT count(*) FROM (SELECT 1 FROM {csv_reader} LIMIT ?)",  # nosec B608
                    [MAX_GROUNDED_DATASET_ROWS + 1],
                ).fetchone()
                if count_result is None:
                    raise ApiError(
                        code="DATASET_PARSE_FAILED",
                        message="The table row count could not be verified. No rows were indexed.",
                        status_code=422,
                    )
                row_count = int(count_result[0])
                if row_count != validated_row_count:
                    raise ApiError(
                        code="DATASET_PARSE_FAILED",
                        message="The table parser did not read every source row consistently. No rows were indexed.",
                        status_code=422,
                    )
                described = connection.execute(
                    f"DESCRIBE SELECT * FROM {csv_reader}"  # nosec B608
                ).fetchall()
                inferred_names = [str(item[0]) for item in described]
                if len(inferred_names) != len(header_names):
                    raise ApiError(
                        code="DATASET_INVALID_HEADER",
                        message="The table header could not be read consistently. No rows were indexed.",
                        status_code=422,
                    )
                column_profiles = [
                    {"name": name, "type": str(described[index][1])}
                    for index, name in enumerate(header_names)
                ]
                normalized_columns = ", ".join(
                    f"{_quote_identifier(source_name)} AS {_quote_identifier(target_name)}"
                    for source_name, target_name in zip(inferred_names, header_names, strict=True)
                )
                connection.execute(
                    f"""COPY (
                        SELECT row_number() OVER () + 1 AS {SOURCE_ROW_COLUMN}, {normalized_columns}
                        FROM {csv_reader}
                    ) TO {_sql_string(str(parquet_path))} """  # nosec B608
                    "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
                )
            finally:
                connection.close()
            return DatasetBuildResult(
                row_count=row_count,
                columns=column_profiles,
                parquet_payload=parquet_path.read_bytes(),
            )
    except ApiError:
        raise
    except Exception as exc:  # parser details can contain untrusted source content
        raise ApiError(
            code="DATASET_PARSE_FAILED",
            message="This CSV or TSV could not be parsed completely. No partial table was indexed.",
            status_code=422,
        ) from exc


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _clean_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list | tuple):
        return [_clean_value(item) for item in value]
    return str(value)


def _validate_filters(filters: Any, available: set[str]) -> tuple[str, list[Any]]:
    if not isinstance(filters, list) or len(filters) > MAX_GROUNDED_DATASET_FILTERS:
        raise ApiError(
            code="INVALID_DATASET_FILTERS",
            message=f"Use no more than {MAX_GROUNDED_DATASET_FILTERS} table filters.",
            status_code=422,
        )
    clauses: list[str] = []
    parameters: list[Any] = []

    def validate_value(value: Any) -> Any:
        if value is None or isinstance(value, str | int | float | bool):
            if isinstance(value, str) and len(value) > 200:
                raise ApiError(
                    code="INVALID_DATASET_FILTERS",
                    message="Filter values are limited to 200 characters.",
                    status_code=422,
                )
            if isinstance(value, float) and not math.isfinite(value):
                raise ApiError(
                    code="INVALID_DATASET_FILTERS",
                    message="A filter value is invalid.",
                    status_code=422,
                )
            return value
        raise ApiError(
            code="INVALID_DATASET_FILTERS",
            message="A filter value must be a short scalar value.",
            status_code=422,
        )

    operators = {
        "eq": "=",
        "ne": "<>",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
    }
    for item in filters:
        if not isinstance(item, dict):
            raise ApiError(
                code="INVALID_DATASET_FILTERS",
                message="A table filter is invalid.",
                status_code=422,
            )
        column = item.get("column")
        operation = item.get("op")
        if not isinstance(column, str) or column not in available or not isinstance(operation, str):
            raise ApiError(
                code="INVALID_DATASET_COLUMN",
                message="A filter uses an unknown column.",
                status_code=422,
            )
        quoted = _quote_identifier(column)
        if operation in operators:
            if "value" not in item:
                raise ApiError(
                    code="INVALID_DATASET_FILTERS",
                    message="A filter value is missing.",
                    status_code=422,
                )
            clauses.append(f"{quoted} {operators[str(operation)]} ?")
            parameters.append(validate_value(item["value"]))
        elif operation == "contains":
            value = item.get("value")
            if not isinstance(value, str) or len(value) > 200:
                raise ApiError(
                    code="INVALID_DATASET_FILTERS",
                    message="Text filters are limited to 200 characters.",
                    status_code=422,
                )
            clauses.append(f"instr(lower(CAST({quoted} AS VARCHAR)), lower(?)) > 0")
            parameters.append(value)
        elif operation == "in":
            values = item.get("value")
            if not isinstance(values, list) or not values or len(values) > 100:
                raise ApiError(
                    code="INVALID_DATASET_FILTERS",
                    message="A list filter must contain 1 to 100 values.",
                    status_code=422,
                )
            clauses.append(f"{quoted} IN ({', '.join('?' for _ in values)})")
            parameters.extend(validate_value(value) for value in values)
        elif operation in {"is_null", "not_null"}:
            clauses.append(f"{quoted} IS {'NULL' if operation == 'is_null' else 'NOT NULL'}")
        else:
            raise ApiError(
                code="INVALID_DATASET_FILTERS",
                message="A table filter uses an unsupported operator.",
                status_code=422,
            )
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), parameters


def _table_sql(derivative_path: str) -> str:
    # The path is generated by tempfile and is never accepted from a request.
    escaped = derivative_path.replace("'", "''")
    return f"read_parquet('{escaped}')"


def execute_dataset_plan(
    *, derivative_payload: bytes, profile: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    """Execute a validated, read-only operation plan against the complete derivative."""
    columns = profile.get("columns")
    if not isinstance(columns, list):
        raise ApiError(
            code="DATASET_NOT_READY", message="The table index is not ready.", status_code=409
        )
    column_types = {
        str(item.get("name")): str(item.get("type", ""))
        for item in columns
        if isinstance(item, dict) and item.get("name")
    }
    available = set(column_types)
    action = plan.get("action")
    allowed_plan_fields = {
        "action",
        "filters",
        "columns",
        "limit",
        "sort",
        "aggregations",
        "group_by",
    }
    if set(plan) - allowed_plan_fields:
        raise ApiError(
            code="INVALID_DATASET_PLAN",
            message="The requested table operation contains unsupported fields.",
            status_code=422,
        )
    if not isinstance(action, str):
        raise ApiError(
            code="INVALID_DATASET_PLAN",
            message="The requested table operation is unsupported.",
            status_code=422,
        )
    allowed_fields = (
        {"action", "filters", "columns", "limit", "sort"}
        if action == "rows"
        else {"action", "filters", "aggregations", "group_by"}
    )
    if set(plan) - allowed_fields:
        raise ApiError(
            code="INVALID_DATASET_PLAN",
            message="The requested table operation has fields that do not apply to this action.",
            status_code=422,
        )
    if action not in {"rows", "aggregate"}:
        raise ApiError(
            code="INVALID_DATASET_PLAN",
            message="The requested table operation is unsupported.",
            status_code=422,
        )
    where_sql, filter_parameters = _validate_filters(plan.get("filters", []), available)
    source_rows: list[int] = []
    matched_row_count = 0
    output_rows: list[dict[str, Any]] = []
    groups_truncated = False
    with tempfile.TemporaryDirectory(prefix="averqel-grounded-query-") as temp_dir:
        parquet_path = Path(temp_dir) / "dataset.parquet"
        parquet_path.write_bytes(derivative_payload)
        connection = duckdb.connect(database=":memory:")
        try:
            connection.execute("SET threads = 1")
            connection.execute("SET memory_limit = '512MB'")
            connection.execute("SET temp_directory = ?", [temp_dir])
            table = _table_sql(str(parquet_path))
            count_row = connection.execute(
                f"SELECT count(*) FROM {table}{where_sql}",  # nosec B608
                filter_parameters,
            ).fetchone()
            matched_row_count = int(count_row[0] if count_row else 0)
            row_numbers = connection.execute(
                f"SELECT {SOURCE_ROW_COLUMN} FROM {table}{where_sql} "
                f"ORDER BY {SOURCE_ROW_COLUMN} LIMIT ?",  # nosec B608
                [*filter_parameters, MAX_GROUNDED_DATASET_REFERENCE_ROWS],
            ).fetchall()
            source_rows = [int(row[0]) for row in row_numbers]
            if action == "rows":
                selected = plan.get("columns")
                if not isinstance(selected, list) or not selected:
                    selected = list(column_types)[:50]
                if (
                    len(selected) > 50
                    or any(not isinstance(name, str) or name not in available for name in selected)
                    or len(set(selected)) != len(selected)
                ):
                    raise ApiError(
                        code="INVALID_DATASET_COLUMN",
                        message="The table operation selects an invalid column.",
                        status_code=422,
                    )
                limit = plan.get("limit", 20)
                if (
                    isinstance(limit, bool)
                    or not isinstance(limit, int)
                    or not 1 <= limit <= MAX_GROUNDED_DATASET_QUERY_ROWS
                ):
                    raise ApiError(
                        code="INVALID_DATASET_LIMIT",
                        message=f"Table results are limited to {MAX_GROUNDED_DATASET_QUERY_ROWS} rows per request.",
                        status_code=422,
                    )
                sort = plan.get("sort")
                order_sql = ""
                if sort is not None:
                    if (
                        not isinstance(sort, dict)
                        or not isinstance(sort.get("column"), str)
                        or sort.get("column") not in available
                    ):
                        raise ApiError(
                            code="INVALID_DATASET_SORT",
                            message="The table sort column is invalid.",
                            status_code=422,
                        )
                    raw_direction = sort.get("direction", "asc")
                    if raw_direction not in {"asc", "desc"}:
                        raise ApiError(
                            code="INVALID_DATASET_SORT",
                            message="Sort direction must be asc or desc.",
                            status_code=422,
                        )
                    direction = "DESC" if raw_direction == "desc" else "ASC"
                    order_sql = f" ORDER BY {_quote_identifier(str(sort['column']))} {direction}, {SOURCE_ROW_COLUMN} ASC"
                else:
                    order_sql = f" ORDER BY {SOURCE_ROW_COLUMN} ASC"
                selected_sql = ", ".join(_quote_identifier(name) for name in selected)
                rows = connection.execute(
                    f"SELECT {SOURCE_ROW_COLUMN}, {selected_sql} FROM {table}{where_sql}{order_sql} LIMIT ?",  # nosec B608
                    [*filter_parameters, limit],
                ).fetchall()
                output_rows = [
                    {
                        "source_row_number": int(row[0]),
                        **{
                            name: _clean_value(value)
                            for name, value in zip(selected, row[1:], strict=True)
                        },
                    }
                    for row in rows
                ]
                source_rows = [item["source_row_number"] for item in output_rows]
                result_columns = [SOURCE_ROW_COLUMN, *selected]
            else:
                aggregations = plan.get("aggregations")
                group_by = plan.get("group_by", [])
                if not isinstance(aggregations, list) or not 1 <= len(aggregations) <= 10:
                    raise ApiError(
                        code="INVALID_DATASET_AGGREGATION",
                        message="Choose between 1 and 10 table calculations.",
                        status_code=422,
                    )
                if (
                    not isinstance(group_by, list)
                    or len(group_by) > MAX_GROUNDED_DATASET_GROUP_COLUMNS
                    or any(not isinstance(name, str) or name not in available for name in group_by)
                    or len(set(group_by)) != len(group_by)
                ):
                    raise ApiError(
                        code="INVALID_DATASET_GROUP",
                        message="The table grouping is invalid.",
                        status_code=422,
                    )
                select_items = [_quote_identifier(name) for name in group_by]
                aggregate_names: list[str] = []
                allowed_functions = {"count", "sum", "avg", "min", "max"}
                for index, item in enumerate(aggregations):
                    if not isinstance(item, dict):
                        raise ApiError(
                            code="INVALID_DATASET_AGGREGATION",
                            message="A table calculation is invalid.",
                            status_code=422,
                        )
                    function = item.get("function")
                    column = item.get("column", "*")
                    if (
                        not isinstance(function, str)
                        or function not in allowed_functions
                        or not isinstance(column, str)
                        or (column != "*" and column not in available)
                    ):
                        raise ApiError(
                            code="INVALID_DATASET_AGGREGATION",
                            message="A table calculation uses an unsupported function or column.",
                            status_code=422,
                        )
                    if function in {"sum", "avg"} and column == "*":
                        raise ApiError(
                            code="INVALID_DATASET_AGGREGATION",
                            message="Sum and average require a numeric column.",
                            status_code=422,
                        )
                    if function in {"sum", "avg"} and not any(
                        token in column_types[str(column)].upper()
                        for token in (
                            "INT",
                            "UINT",
                            "DECIMAL",
                            "NUMERIC",
                            "DOUBLE",
                            "FLOAT",
                            "REAL",
                        )
                    ):
                        raise ApiError(
                            code="INVALID_DATASET_AGGREGATION",
                            message="Sum and average require a numeric column.",
                            status_code=422,
                        )
                    alias = f"calculation_{index + 1}"
                    operand = "*" if column == "*" else _quote_identifier(str(column))
                    select_items.append(
                        f"{str(function).upper()}({operand}) AS {_quote_identifier(alias)}"
                    )
                    aggregate_names.append(alias)
                group_sql = (
                    " GROUP BY " + ", ".join(_quote_identifier(name) for name in group_by)
                    if group_by
                    else ""
                )
                rows = connection.execute(
                    f"SELECT {', '.join(select_items)} FROM {table}{where_sql}{group_sql} LIMIT 101",  # nosec B608
                    filter_parameters,
                ).fetchall()
                groups_truncated = len(rows) > 100
                rows = rows[:100]
                output_rows = [
                    {
                        **{
                            name: _clean_value(value)
                            for name, value in zip(group_by, row[: len(group_by)], strict=True)
                        },
                        **{
                            name: _clean_value(value)
                            for name, value in zip(
                                aggregate_names, row[len(group_by) :], strict=True
                            )
                        },
                    }
                    for row in rows
                ]
                result_columns = [*group_by, *aggregate_names]
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="DATASET_OPERATION_FAILED",
                message="That table operation could not be applied to the selected columns or values. Check the column types and try again.",
                status_code=422,
            ) from exc
        finally:
            connection.close()
        result = {
            "action": action,
            "rows": output_rows,
            "columns": result_columns,
            "matched_row_count": matched_row_count,
            "source_row_numbers": source_rows,
            "result_truncated": bool(
                (action == "rows" and matched_row_count > len(output_rows))
                or (action == "aggregate" and groups_truncated)
            ),
            "source_file": str(profile.get("filename") or "Document"),
        }
    return result


def read_dataset_rows(
    *, derivative_payload: bytes, profile: dict[str, Any], start_row: int, limit: int
) -> dict[str, Any]:
    """Read a bounded source-row window, using the exact row ordinal created at indexing."""
    if (
        isinstance(start_row, bool)
        or not isinstance(start_row, int)
        or not 1 <= start_row <= MAX_GROUNDED_DATASET_ROWS + 1
    ):
        raise ApiError(
            code="INVALID_DATASET_ROW",
            message="Start row must be between source rows 1 and 1,000,001.",
            status_code=422,
        )
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ApiError(
            code="INVALID_DATASET_LIMIT",
            message="Table previews are limited to 200 rows per request.",
            status_code=422,
        )
    columns = profile.get("columns")
    if not isinstance(columns, list):
        raise ApiError(
            code="DATASET_NOT_READY", message="The table index is not ready.", status_code=409
        )
    names = [str(item["name"]) for item in columns if isinstance(item, dict) and item.get("name")]
    if not names:
        raise ApiError(
            code="DATASET_NOT_READY",
            message="The table index has no readable columns.",
            status_code=409,
        )
    displayed = names[:50]
    with tempfile.TemporaryDirectory(prefix="averqel-grounded-preview-") as temp_dir:
        parquet_path = Path(temp_dir) / "dataset.parquet"
        parquet_path.write_bytes(derivative_payload)
        connection = duckdb.connect(database=":memory:")
        try:
            connection.execute("SET threads = 1")
            connection.execute("SET memory_limit = '256MB'")
            connection.execute("SET temp_directory = ?", [temp_dir])
            table = _table_sql(str(parquet_path))
            rows = connection.execute(
                f"SELECT {SOURCE_ROW_COLUMN}, {', '.join(_quote_identifier(name) for name in displayed)} "
                f"FROM {table} WHERE {SOURCE_ROW_COLUMN} >= ? "
                f"ORDER BY {SOURCE_ROW_COLUMN} LIMIT ?",  # nosec B608
                [start_row, limit + 1],
            ).fetchall()
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="DATASET_READ_FAILED",
                message="The indexed table could not be read. Retry the preview.",
                status_code=503,
            ) from exc
        finally:
            connection.close()
    has_more = len(rows) > limit
    rows = rows[:limit]
    truncated_cells = 0
    preview_rows: list[dict[str, Any]] = []
    for row in rows:
        values: dict[str, Any] = {}
        for name, value in zip(displayed, row[1:], strict=True):
            cleaned = _clean_value(value)
            if isinstance(cleaned, str) and len(cleaned) > MAX_GROUNDED_DATASET_PREVIEW_CELL_CHARS:
                cleaned = cleaned[:MAX_GROUNDED_DATASET_PREVIEW_CELL_CHARS]
                truncated_cells += 1
            values[name] = cleaned
        preview_rows.append({"source_row_number": int(row[0]), **values})
    return {
        "filename": str(profile.get("filename") or "Document"),
        "columns": displayed,
        "omitted_column_count": max(0, len(names) - len(displayed)),
        "rows": preview_rows,
        "truncated_cells": truncated_cells,
        "start_row": start_row,
        "limit": limit,
        "has_more": has_more,
        "row_count": int(profile.get("row_count") or 0),
    }


class QueryDatasetIndexService:
    def __init__(self, *, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.storage = StorageService(settings)

    def _delete_or_queue_derivative(
        self,
        *,
        tenant_id: uuid.UUID,
        document: Document,
        bucket: str,
        object_key: str,
    ) -> None:
        try:
            self.storage.delete_tenant_object(
                tenant_id=tenant_id,
                bucket=bucket,
                object_key=object_key,
                raise_on_error=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Grounded Query derivative cleanup deferred.",
                extra={"tenant_id": str(tenant_id), "document_id": str(document.id)},
                exc_info=True,
            )
            try:
                self.db.add(
                    StorageCleanupJob(
                        tenant_id=tenant_id,
                        owner_user_id=document.uploaded_by_user_id,
                        bucket=bucket,
                        object_key=object_key,
                    )
                )
                self.db.commit()
            except Exception:  # noqa: BLE001
                self.db.rollback()
                logger.exception(
                    "Could not queue cleanup for a Grounded Query derivative.",
                    extra={"tenant_id": str(tenant_id), "document_id": str(document.id)},
                )

    def get_index(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> QueryDatasetIndex | None:
        return self.db.scalar(
            select(QueryDatasetIndex).where(
                QueryDatasetIndex.tenant_id == tenant_id,
                QueryDatasetIndex.document_id == document_id,
            )
        )

    def fail_stale_processing(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> QueryDatasetIndex | None:
        """Turn an abandoned worker lease into a visible, retryable failure."""
        row = self.db.scalar(
            select(QueryDatasetIndex)
            .where(
                QueryDatasetIndex.tenant_id == tenant_id,
                QueryDatasetIndex.document_id == document_id,
            )
            .with_for_update()
        )
        if (
            row is not None
            and row.status == "processing"
            and row.updated_at is not None
            and (datetime.now(tz=UTC) - row.updated_at).total_seconds() >= _PROCESSING_STALE_SECONDS
        ):
            row.status = "failed"
            row.stage = "failed"
            row.progress = 0
            row.error_code = "DATASET_INDEX_FAILED"
            row.error_message = "Table indexing stopped before it finished. Retry to rebuild it from the saved file."
            self.db.commit()
        return row

    def request_index(
        self, *, tenant_id: uuid.UUID, document: Document, retry: bool
    ) -> QueryDatasetIndex:
        # Lock the source row so concurrent first-time requests serialize before
        # either tries to create the unique (tenant, document) index record.
        locked_document = self.db.scalar(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.id == document.id,
                Document.is_deleted.is_(False),
            )
            .with_for_update()
        )
        if locked_document is None:
            raise ApiError(
                code="DOCUMENT_NOT_FOUND", message="Document not found.", status_code=404
            )
        document = locked_document
        row = self.get_index(tenant_id=tenant_id, document_id=document.id)
        if row is None:
            row = QueryDatasetIndex(
                tenant_id=tenant_id,
                document_id=document.id,
                source_sha256=document.sha256_hash,
                status="queued",
                stage="queued",
                progress=0,
            )
            self.db.add(row)
            self.db.commit()
            return row
        if row.source_sha256 != document.sha256_hash:
            if row.derivative_bucket and row.derivative_object_key:
                self._delete_or_queue_derivative(
                    tenant_id=tenant_id,
                    document=document,
                    bucket=row.derivative_bucket,
                    object_key=row.derivative_object_key,
                )
            row.source_sha256 = document.sha256_hash
            row.status = "queued"
            row.stage = "queued"
            row.progress = 0
            row.row_count = None
            row.column_count = None
            row.columns = []
            row.error_code = None
            row.error_message = None
            row.derivative_bucket = None
            row.derivative_object_key = None
            self.db.commit()
            return row
        if row.status == "processing" and row.updated_at is not None:
            if (datetime.now(tz=UTC) - row.updated_at).total_seconds() >= _PROCESSING_STALE_SECONDS:
                row.status = "queued"
                row.stage = "queued"
                row.progress = 0
                row.error_code = None
                row.error_message = None
                self.db.commit()
        if row.status == "failed" and retry:
            row.status = "queued"
            row.stage = "queued"
            row.progress = 0
            row.error_code = None
            row.error_message = None
            self.db.commit()
        return row

    def index_document(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
        row = self.db.scalar(
            select(QueryDatasetIndex)
            .where(
                QueryDatasetIndex.tenant_id == tenant_id,
                QueryDatasetIndex.document_id == document_id,
            )
            .with_for_update()
        )
        document = self.db.scalar(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.id == document_id,
                Document.is_deleted.is_(False),
            )
        )
        if row is None or document is None or row.status == "ready":
            return
        if (
            row.status == "processing"
            and row.updated_at is not None
            and (datetime.now(tz=UTC) - row.updated_at).total_seconds() < _PROCESSING_STALE_SECONDS
        ):
            return
        if document.quarantined or document.security_scan_result != "passed":
            row.status = "failed"
            row.stage = "failed"
            row.progress = 0
            row.error_code = "DOCUMENT_NOT_SAFE"
            row.error_message = "Documents Hub did not approve this file for table indexing."
            self.db.commit()
            return
        if row.source_sha256 != document.sha256_hash:
            row.status = "failed"
            row.stage = "failed"
            row.progress = 0
            row.error_code = "DATASET_SOURCE_CHANGED"
            row.error_message = (
                "The source file changed. Request indexing again to refresh its table index."
            )
            self.db.commit()
            return
        row.status = "processing"
        row.stage = "loading_source"
        row.progress = max(row.progress, 5)
        row.error_code = None
        row.error_message = None
        self.db.commit()
        stored: tuple[str, str] | None = None
        try:
            if document.size_bytes > MAX_GROUNDED_DATASET_BYTES:
                raise ApiError(
                    code="DATASET_FILE_TOO_LARGE",
                    message="Grounded Query table indexing supports files up to 25 MiB.",
                    status_code=413,
                )
            if not document.storage_bucket or not document.storage_object_key:
                raise ApiError(
                    code="STORAGE_MISSING",
                    message="The original file is unavailable.",
                    status_code=404,
                )
            payload = self.storage.get_tenant_bytes(
                tenant_id=tenant_id,
                bucket=document.storage_bucket,
                object_key=document.storage_object_key,
            )
            row.progress = 20
            row.stage = "building_index"
            self.db.commit()
            built = build_parquet_derivative(document=document, payload=payload)
            row.progress = 80
            row.stage = "saving_index"
            self.db.commit()
            stored_object = self.storage.put_bytes(
                tenant_id=tenant_id,
                document_id=document.id,
                filename=DATASET_INDEX_FILENAME,
                content_type="application/vnd.apache.parquet",
                payload=built.parquet_payload,
            )
            stored = (stored_object.bucket, stored_object.object_key)
            row.row_count = built.row_count
            row.column_count = len(built.columns)
            row.columns = built.columns
            row.derivative_bucket = stored_object.bucket
            row.derivative_object_key = stored_object.object_key
            row.progress = 100
            row.status = "ready"
            row.stage = "ready"
            row.error_code = None
            row.error_message = None
            self.db.commit()
        except ApiError as exc:
            self.db.rollback()
            row = self.get_index(tenant_id=tenant_id, document_id=document_id)
            if row is not None:
                row.status = "failed"
                row.stage = "failed"
                row.progress = 0
                row.error_code = exc.code
                row.error_message = exc.message[:512]
                row.derivative_bucket = None
                row.derivative_object_key = None
                row.row_count = None
                row.column_count = None
                row.columns = []
                self.db.commit()
            if stored is not None:
                self._delete_or_queue_derivative(
                    tenant_id=tenant_id,
                    document=document,
                    bucket=stored[0],
                    object_key=stored[1],
                )
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            row = self.get_index(tenant_id=tenant_id, document_id=document_id)
            if row is not None:
                row.status = "failed"
                row.stage = "failed"
                row.progress = 0
                row.error_code = "DATASET_INDEX_FAILED"
                row.error_message = "Table indexing failed. Retry it from Grounded Query."
                row.derivative_bucket = None
                row.derivative_object_key = None
                row.row_count = None
                row.column_count = None
                row.columns = []
                self.db.commit()
            if stored is not None:
                self._delete_or_queue_derivative(
                    tenant_id=tenant_id,
                    document=document,
                    bucket=stored[0],
                    object_key=stored[1],
                )
            raise RuntimeError("Grounded Query dataset indexing failed safely") from exc

    def derivative_profile(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[dict[str, Any], bytes]:
        row = self.get_index(tenant_id=tenant_id, document_id=document_id)
        if (
            row is None
            or row.status != "ready"
            or not row.derivative_bucket
            or not row.derivative_object_key
        ):
            raise ApiError(
                code="DATASET_NOT_READY",
                message="The table index is not ready yet.",
                status_code=409,
            )
        payload = self.storage.get_tenant_bytes(
            tenant_id=tenant_id,
            bucket=row.derivative_bucket,
            object_key=row.derivative_object_key,
        )
        document = self.db.scalar(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.id == document_id,
                Document.is_deleted.is_(False),
                Document.quarantined.is_(False),
            )
        )
        if document is None or row.source_sha256 != document.sha256_hash:
            raise ApiError(
                code="DATASET_SOURCE_CHANGED",
                message="The table index no longer matches its source file.",
                status_code=409,
            )
        return {
            "filename": document.filename,
            "columns": row.columns,
            "row_count": row.row_count,
        }, payload

    def delete_indexes_for_documents(
        self, *, tenant_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> list[tuple[str, str]]:
        if not document_ids:
            return []
        rows = list(
            self.db.scalars(
                select(QueryDatasetIndex).where(
                    QueryDatasetIndex.tenant_id == tenant_id,
                    QueryDatasetIndex.document_id.in_(document_ids),
                )
            )
        )
        objects = [
            (row.derivative_bucket, row.derivative_object_key)
            for row in rows
            if row.derivative_bucket and row.derivative_object_key
        ]
        for row in rows:
            self.db.delete(row)
        self.db.flush()
        return [(str(bucket), str(key)) for bucket, key in objects]


def serialize_dataset_index(row: QueryDatasetIndex | None, *, document: Document) -> dict[str, Any]:
    is_supported = is_tabular_document(document)
    if not is_supported:
        status = "not_required"
    elif row is None:
        status = "not_started"
    else:
        status = row.status
    return {
        "document_id": str(document.id),
        "filename": document.filename,
        "supported": is_supported,
        "status": status,
        "stage": row.stage if row else status,
        "progress": row.progress if row else 0,
        "row_count": row.row_count if row else None,
        "column_count": row.column_count if row else None,
        "columns": row.columns if row else [],
        "error_code": row.error_code if row else None,
        "error_message": row.error_message if row else None,
        "max_file_size_bytes": MAX_GROUNDED_DATASET_BYTES,
        "max_data_rows": MAX_GROUNDED_DATASET_ROWS,
    }
