from __future__ import annotations

import io
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.core.errors import ApiError
from app.deepspace.services.dataset_derivatives import DatasetDerivativeService


def _service_with_derivative() -> tuple[DatasetDerivativeService, dict[str, object]]:
    output = io.BytesIO()
    pl.DataFrame(
        {
            "region": ["north", "south", "north", "west"],
            "revenue": [10, 20, 30, 5],
        }
    ).write_parquet(output, compression="zstd", statistics=True, row_group_size=2)
    service = DatasetDerivativeService.__new__(DatasetDerivativeService)
    service.read_derivative = lambda **_: output.getvalue()  # type: ignore[method-assign]
    profile: dict[str, object] = {
        "status": "ready",
        "columns": ["region", "revenue"],
        "derivative_bucket": "private",
        "derivative_key": "tenant/file.parquet",
    }
    return service, profile


def test_query_is_bounded_filtered_and_sorted_server_side() -> None:
    service, profile = _service_with_derivative()

    result = service.query(
        profile=profile,
        columns=["region", "revenue"],
        limit=2,
        offset=0,
        order_by="revenue",
        descending=True,
        filters=[{"column": "revenue", "operator": "gte", "value": 10}],
    )

    assert result["rows"] == [
        {"region": "north", "revenue": 30},
        {"region": "south", "revenue": 20},
    ]
    assert result["has_more"] is True


def test_aggregate_is_allowlisted_and_uses_private_derivative() -> None:
    service, profile = _service_with_derivative()

    result = service.aggregate(
        profile=profile,
        metric="sum",
        column="revenue",
        group_by="region",
        filters=[],
    )

    assert result["columns"] == ["group", "value"]
    assert result["rows"][0] == {"group": "north", "value": 40.0}


def test_join_is_bounded_and_returns_namespaced_columns() -> None:
    output = io.BytesIO()
    pl.DataFrame({"id": [1, 2], "name": ["one", "two"]}).write_parquet(output)
    right = output.getvalue()
    output = io.BytesIO()
    pl.DataFrame({"id": [2, 3], "amount": [20, 30]}).write_parquet(output)
    left = output.getvalue()
    service = DatasetDerivativeService.__new__(DatasetDerivativeService)
    payloads = iter((right, left))
    service.read_derivative = lambda **_: next(payloads)  # type: ignore[method-assign]
    profile_left = {"columns": ["id", "name"], "derivative_bucket": "p", "derivative_key": "l"}
    profile_right = {"columns": ["id", "amount"], "derivative_bucket": "p", "derivative_key": "r"}

    result = service.join(
        left_profile=profile_left,
        right_profile=profile_right,
        left_on="id",
        right_on="id",
        left_columns=["id", "name"],
        right_columns=["amount"],
        join_type="inner",
        limit=10,
    )

    assert result["columns"] == ["left_id", "left_name", "right_amount"]
    assert result["rows"] == [{"left_id": 2, "left_name": "two", "right_amount": 20}]


def test_query_rejects_unknown_column_before_sql() -> None:
    service, profile = _service_with_derivative()

    with pytest.raises(ApiError, match="Requested columns are invalid"):
        service.query(
            profile=profile,
            columns=["region; DROP TABLE files"],
            limit=10,
            offset=0,
            order_by=None,
            descending=False,
        )


def test_build_creates_private_parquet_with_durable_row_groups() -> None:
    stored: dict[str, object] = {}
    service = DatasetDerivativeService.__new__(DatasetDerivativeService)
    service.storage = SimpleNamespace(
        put_bytes=lambda **kwargs: stored.update(kwargs)
        or SimpleNamespace(bucket="private", object_key="tenant/derived.parquet")
    )

    derivative = service.build(
        tenant_id=uuid4(),
        file_id=uuid4(),
        filename="sales.csv",
        content_type="text/csv",
        payload=b"region,revenue\nnorth,10\nsouth,20\n",
    )

    assert derivative.row_count == 2
    assert derivative.columns == ["region", "revenue"]
    assert derivative.row_group_size == 100_000
    assert stored["content_type"] == "application/vnd.apache.parquet"
