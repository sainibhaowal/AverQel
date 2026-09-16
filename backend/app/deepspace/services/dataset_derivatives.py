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
                frame = pl.read_excel(io.BytesIO(payload))
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
        frame.write_parquet(output, compression="zstd", statistics=True)
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
                f"SELECT {quoted} FROM read_parquet(?) {order} LIMIT ? OFFSET ?",
                [path, limit + 1, offset],
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


def safe_dataset_profile(derivative: DatasetDerivative) -> dict[str, Any]:
    return {
        "status": "ready",
        "format": derivative.format,
        "storage_format": "parquet",
        "row_count": derivative.row_count,
        "column_count": derivative.column_count,
        "columns": derivative.columns,
        "derivative_bucket": derivative.bucket,
        "derivative_key": derivative.object_key,
    }
