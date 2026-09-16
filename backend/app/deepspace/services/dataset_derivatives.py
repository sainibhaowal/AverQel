"""Private, worker-owned structured-data derivatives for the DeepSpace Library."""

from __future__ import annotations

import io
import os
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any

import duckdb
import polars as pl
from openpyxl import load_workbook

from app.core.config import Settings
from app.core.errors import ApiError
from app.system.services.storage_service import StorageService, StorageServiceError

_TABULAR_TYPES = {
    "text/csv",
    "text/x-csv",
    "text/tab-separated-values",
    "application/json",
    "application/x-ipynb+json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True, slots=True)
class DatasetDerivative:
    bucket: str
    object_key: str
    row_count: int
    column_count: int
    columns: list[str]
    format: str
    row_group_size: int


class DatasetDerivativeService:
    """Build tenant-private Parquet derivatives outside interactive services."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = StorageService(settings)

    @staticmethod
    def supports(content_type: str) -> bool:
        return content_type in _TABULAR_TYPES

    def build(
        self,
        *,
        tenant_id: uuid.UUID,
        file_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> DatasetDerivative:
        if not self.supports(content_type):
            raise ApiError(
                code="UNSUPPORTED_DATASET_TYPE",
                message="This file type cannot be converted into a queryable dataset.",
                status_code=422,
            )
        try:
            if content_type in {"text/csv", "text/x-csv", "text/tab-separated-values"}:
                frame = pl.read_csv(
                    io.BytesIO(payload),
                    separator="\t" if content_type == "text/tab-separated-values" else ",",
                    infer_schema_length=1_000,
                    truncate_ragged_lines=True,
                    ignore_errors=False,
                )
                source_format = "tsv" if content_type == "text/tab-separated-values" else "csv"
            elif (
                content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ):
                # Read-only mode prevents openpyxl from materialising workbook styles,
                # formula graphs, and empty cells in the API process. This task only
                # runs on the dedicated dataset worker.
                workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
                worksheet = workbook.active
                if worksheet is None:
                    raise ValueError("Workbook has no worksheet")
                values = worksheet.iter_rows(values_only=True)
                header = next(values, None)
                if not header:
                    raise ValueError("Workbook is empty")
                names = [str(value or f"column_{index + 1}") for index, value in enumerate(header)]
                records = [dict(zip(names, row, strict=True)) for row in values]
                workbook.close()
                frame = pl.from_dicts(records, schema=names)
                source_format = "xlsx"
            else:
                frame = pl.read_json(io.BytesIO(payload))
                source_format = "json"
        except Exception as exc:  # parser messages are not user-controlled output
            raise ApiError(
                code="DATASET_PARSE_FAILED",
                message="AverQel could not safely parse this structured file.",
                status_code=422,
            ) from exc

        output = io.BytesIO()
        # Row groups are durable columnar indexes. DuckDB uses their statistics
        # for predicate pushdown instead of rescanning a CSV on every request.
        row_group_size = 100_000
        frame.write_parquet(
            output,
            compression="zstd",
            statistics=True,
            row_group_size=row_group_size,
        )
        stored = self.storage.put_bytes(
            tenant_id=tenant_id,
            document_id=uuid.uuid4(),
            filename=f"{filename}.parquet",
            content_type="application/vnd.apache.parquet",
            payload=output.getvalue(),
        )
        return DatasetDerivative(
            bucket=stored.bucket,
            object_key=stored.object_key,
            row_count=frame.height,
            column_count=frame.width,
            columns=list(frame.columns)[:200],
            format=source_format,
            row_group_size=row_group_size,
        )

    def read_derivative(self, *, bucket: str, object_key: str) -> bytes:
        try:
            return self.storage.get_bytes(bucket=bucket, object_key=object_key)
        except StorageServiceError as exc:
            raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc

    def query(
        self,
        *,
        profile: dict[str, Any],
        columns: list[str] | None,
        limit: int,
        offset: int,
        order_by: str | None,
        descending: bool,
        filters: list[dict[str, object]] | None = None,
    ) -> dict[str, Any]:
        """Run a bounded read-only DuckDB query against a private derivative."""
        available = [str(column) for column in profile.get("columns", [])]
        selected = columns or available
        if not selected or any(column not in available for column in selected):
            raise ApiError(
                code="INVALID_DATASET_COLUMNS",
                message="Requested columns are invalid.",
                status_code=422,
            )
        if order_by is not None and order_by not in available:
            raise ApiError(
                code="INVALID_DATASET_SORT", message="Sort column is invalid.", status_code=422
            )
        bucket = str(profile.get("derivative_bucket") or "")
        object_key = str(profile.get("derivative_key") or "")
        if not bucket or not object_key:
            raise ApiError(
                code="DATASET_NOT_READY",
                message="Dataset derivative is not ready.",
                status_code=409,
            )
        where_sql, where_values = self._filters_sql(filters or [], available)
        payload = self.read_derivative(bucket=bucket, object_key=object_key)
        path = ""
        connection: duckdb.DuckDBPyConnection | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as handle:
                handle.write(payload)
                path = handle.name
            connection = duckdb.connect(":memory:", read_only=False)
            quoted = ", ".join(f'"{column.replace("\"", "\"\"")}"' for column in selected)
            order = (
                f' ORDER BY "{order_by.replace("\"", "\"\"")}" {"DESC" if descending else "ASC"}'
                if order_by
                else ""
            )
            result = connection.execute(
                f"SELECT {quoted} FROM read_parquet(?) {where_sql}{order} LIMIT ? OFFSET ?",
                [path, *where_values, limit + 1, offset],
            )
            values = result.fetchall()
            has_more = len(values) > limit
            rows = [dict(zip(selected, row, strict=True)) for row in values[:limit]]
            return {"columns": selected, "rows": rows, "offset": offset, "has_more": has_more}
        finally:
            if connection is not None:
                connection.close()
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    def aggregate(
        self,
        *,
        profile: dict[str, Any],
        metric: str,
        column: str,
        group_by: str | None,
        filters: list[dict[str, object]] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Run a bounded, allowlisted aggregation for tables and charts."""
        available = [str(item) for item in profile.get("columns", [])]
        if column not in available or (group_by is not None and group_by not in available):
            raise ApiError(
                code="INVALID_DATASET_COLUMNS",
                message="Requested columns are invalid.",
                status_code=422,
            )
        aggregates = {
            "count": "COUNT(*)",
            "sum": f'SUM(TRY_CAST("{self._quote(column)}" AS DOUBLE))',
            "avg": f'AVG(TRY_CAST("{self._quote(column)}" AS DOUBLE))',
            "min": f'MIN("{self._quote(column)}")',
            "max": f'MAX("{self._quote(column)}")',
        }
        expression = aggregates.get(metric)
        if expression is None:
            raise ApiError(
                code="INVALID_DATASET_AGGREGATION",
                message="Aggregation is invalid.",
                status_code=422,
            )
        bucket, object_key = self._storage_location(profile)
        where_sql, where_values = self._filters_sql(filters or [], available)
        payload = self.read_derivative(bucket=bucket, object_key=object_key)
        path = ""
        connection: duckdb.DuckDBPyConnection | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as handle:
                handle.write(payload)
                path = handle.name
            connection = duckdb.connect(":memory:", read_only=False)
            if group_by:
                group = f'"{self._quote(group_by)}"'
                statement = (
                    f"SELECT {group} AS group, {expression} AS value FROM read_parquet(?)"
                    f" {where_sql} GROUP BY {group} ORDER BY value DESC NULLS LAST LIMIT ?"
                )
                result_columns = ["group", "value"]
            else:
                statement = f"SELECT {expression} AS value FROM read_parquet(?) {where_sql}"
                result_columns = ["value"]
            rows = connection.execute(
                statement, [path, *where_values, *([limit] if group_by else [])]
            ).fetchall()
            return {
                "columns": result_columns,
                "rows": [dict(zip(result_columns, row, strict=True)) for row in rows],
            }
        finally:
            if connection is not None:
                connection.close()
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    def join(
        self,
        *,
        left_profile: dict[str, Any],
        right_profile: dict[str, Any],
        left_on: str,
        right_on: str,
        left_columns: list[str] | None,
        right_columns: list[str] | None,
        join_type: str,
        limit: int,
    ) -> dict[str, Any]:
        """Join two private Parquet derivatives with an allowlisted contract."""
        left_available = [str(item) for item in left_profile.get("columns", [])]
        right_available = [str(item) for item in right_profile.get("columns", [])]
        if left_on not in left_available or right_on not in right_available:
            raise ApiError(
                code="INVALID_DATASET_JOIN", message="Join columns are invalid.", status_code=422
            )
        if join_type not in {"inner", "left"}:
            raise ApiError(
                code="INVALID_DATASET_JOIN", message="Join type is invalid.", status_code=422
            )
        left_selected = left_columns or left_available
        right_selected = right_columns or right_available
        if any(item not in left_available for item in left_selected) or any(
            item not in right_available for item in right_selected
        ):
            raise ApiError(
                code="INVALID_DATASET_JOIN",
                message="Selected join columns are invalid.",
                status_code=422,
            )
        left_bucket, left_key = self._storage_location(left_profile)
        right_bucket, right_key = self._storage_location(right_profile)
        left_payload = self.read_derivative(bucket=left_bucket, object_key=left_key)
        right_payload = self.read_derivative(bucket=right_bucket, object_key=right_key)
        paths: list[str] = []
        connection: duckdb.DuckDBPyConnection | None = None
        try:
            for payload in (left_payload, right_payload):
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as handle:
                    handle.write(payload)
                    paths.append(handle.name)
            connection = duckdb.connect(":memory:", read_only=False)
            left_expr = ", ".join(
                f'l."{self._quote(item)}" AS "left_{self._quote(item)}"' for item in left_selected
            )
            right_expr = ", ".join(
                f'r."{self._quote(item)}" AS "right_{self._quote(item)}"' for item in right_selected
            )
            rows = connection.execute(
                f'SELECT {left_expr}, {right_expr} FROM read_parquet(?) l {join_type.upper()} JOIN read_parquet(?) r ON l."{self._quote(left_on)}" = r."{self._quote(right_on)}" LIMIT ?',
                [paths[0], paths[1], limit],
            ).fetchall()
            columns = [f"left_{item}" for item in left_selected] + [
                f"right_{item}" for item in right_selected
            ]
            return {
                "columns": columns,
                "rows": [dict(zip(columns, row, strict=True)) for row in rows],
            }
        finally:
            if connection is not None:
                connection.close()
            for path in paths:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _quote(value: str) -> str:
        return value.replace('"', '""')

    def _storage_location(self, profile: dict[str, Any]) -> tuple[str, str]:
        bucket = str(profile.get("derivative_bucket") or "")
        object_key = str(profile.get("derivative_key") or "")
        if not bucket or not object_key:
            raise ApiError(
                code="DATASET_NOT_READY",
                message="Dataset derivative is not ready.",
                status_code=409,
            )
        return bucket, object_key

    def _filters_sql(
        self, filters: list[dict[str, object]], available: list[str]
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        values: list[object] = []
        operators = {
            "eq": "=",
            "ne": "!=",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "contains": "ILIKE",
        }
        if len(filters) > 10:
            raise ApiError(
                code="TOO_MANY_DATASET_FILTERS",
                message="At most 10 filters are allowed.",
                status_code=422,
            )
        for item in filters:
            column = str(item.get("column") or "")
            operator = str(item.get("operator") or "")
            if column not in available or operator not in operators:
                raise ApiError(
                    code="INVALID_DATASET_FILTER",
                    message="Dataset filter is invalid.",
                    status_code=422,
                )
            value = item.get("value")
            if operator == "contains":
                clauses.append(f'CAST("{self._quote(column)}" AS VARCHAR) ILIKE ?')
                values.append(f"%{value}%")
            elif isinstance(value, int | float) and not isinstance(value, bool):
                clauses.append(
                    f'TRY_CAST("{self._quote(column)}" AS DOUBLE) {operators[operator]} ?'
                )
                values.append(value)
            else:
                clauses.append(f'CAST("{self._quote(column)}" AS VARCHAR) {operators[operator]} ?')
                values.append(str(value))
        return (f" WHERE {' AND '.join(clauses)}" if clauses else "", values)


def safe_dataset_profile(derivative: DatasetDerivative) -> dict[str, Any]:
    return {
        "status": "ready",
        "format": derivative.format,
        "storage_format": "parquet",
        "row_count": derivative.row_count,
        "column_count": derivative.column_count,
        "columns": derivative.columns,
        "row_group_size": derivative.row_group_size,
        "derivative_bucket": derivative.bucket,
        "derivative_key": derivative.object_key,
    }
