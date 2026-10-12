from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ApiError
from app.documents.models.document import Document
from app.query.services.dataset_indexing import (
    MAX_GROUNDED_DATASET_BYTES,
    MAX_GROUNDED_DATASET_ROWS,
    build_parquet_derivative,
    execute_dataset_plan,
    read_dataset_rows,
)


def _document(filename: str = "sales.csv") -> Document:
    return Document(
        id=uuid4(),
        tenant_id=uuid4(),
        uploaded_by_user_id=uuid4(),
        filename=filename,
        content_type="text/csv",
    )


def _table_payload(rows: int) -> bytes:
    output = io.StringIO()
    output.write("id,value,region\n")
    for row_id in range(1, rows + 1):
        output.write(f"{row_id},{row_id % 97},r{row_id % 10}\n")
    return output.getvalue().encode("utf-8")


def _profile(document: Document, built) -> dict[str, object]:
    return {
        "filename": document.filename,
        "columns": built.columns,
        "row_count": built.row_count,
    }


@pytest.mark.parametrize("row_count", [100_000, 1_000_000])
def test_large_table_indexes_every_row_and_calculates_known_answers(row_count: int) -> None:
    document = _document()
    built = build_parquet_derivative(document=document, payload=_table_payload(row_count))
    profile = _profile(document, built)

    result = execute_dataset_plan(
        derivative_payload=built.parquet_payload,
        profile=profile,
        plan={
            "action": "aggregate",
            "filters": [],
            "aggregations": [
                {"function": "count", "column": "*"},
                {"function": "sum", "column": "id"},
            ],
        },
    )

    assert built.row_count == row_count
    assert result["matched_row_count"] == row_count
    assert result["rows"] == [
        {
            "calculation_1": row_count,
            "calculation_2": row_count * (row_count + 1) // 2,
        }
    ]
    assert result["source_row_numbers"] == list(range(2, 22))

    region = row_count % 10
    filtered = execute_dataset_plan(
        derivative_payload=built.parquet_payload,
        profile=profile,
        plan={
            "action": "aggregate",
            "filters": [{"column": "region", "op": "eq", "value": f"r{region}"}],
            "aggregations": [{"function": "sum", "column": "id"}],
        },
    )
    expected_ids = range(region if region else 10, row_count + 1, 10)
    assert filtered["rows"][0]["calculation_1"] == sum(expected_ids)


def test_row_jump_reads_source_range_without_scanning_pages() -> None:
    document = _document()
    built = build_parquet_derivative(document=document, payload=_table_payload(1_000))
    page = read_dataset_rows(
        derivative_payload=built.parquet_payload,
        profile=_profile(document, built),
        start_row=802,
        limit=5,
    )
    assert [row["source_row_number"] for row in page["rows"]] == [802, 803, 804, 805, 806]
    assert page["has_more"] is True


def test_sort_and_average_are_exact_and_keep_source_row_provenance() -> None:
    document = _document()
    built = build_parquet_derivative(document=document, payload=_table_payload(100))
    profile = _profile(document, built)

    sorted_rows = execute_dataset_plan(
        derivative_payload=built.parquet_payload,
        profile=profile,
        plan={
            "action": "rows",
            "filters": [{"column": "region", "op": "eq", "value": "r1"}],
            "columns": ["id", "region"],
            "sort": {"column": "id", "direction": "desc"},
            "limit": 2,
        },
    )
    assert sorted_rows["rows"] == [
        {"source_row_number": 92, "id": 91, "region": "r1"},
        {"source_row_number": 82, "id": 81, "region": "r1"},
    ]
    assert sorted_rows["matched_row_count"] == 10
    assert sorted_rows["result_truncated"] is True

    average = execute_dataset_plan(
        derivative_payload=built.parquet_payload,
        profile=profile,
        plan={
            "action": "aggregate",
            "filters": [],
            "aggregations": [{"function": "avg", "column": "id"}],
        },
    )
    assert average["rows"] == [{"calculation_1": 50.5}]


def test_json_string_numeric_filter_values_are_handled_safely() -> None:
    document = _document()
    built = build_parquet_derivative(document=document, payload=b"id,amount\n1,2\n2,10\n")
    result = execute_dataset_plan(
        derivative_payload=built.parquet_payload,
        profile=_profile(document, built),
        plan={
            "action": "aggregate",
            "filters": [{"column": "amount", "op": "gte", "value": "10"}],
            "aggregations": [{"function": "sum", "column": "amount"}],
        },
    )
    assert result["matched_row_count"] == 1
    assert result["rows"] == [{"calculation_1": 10}]


def test_simultaneous_queries_are_isolated_and_deterministic() -> None:
    document = _document()
    built = build_parquet_derivative(document=document, payload=_table_payload(100_000))
    profile = _profile(document, built)
    plan = {
        "action": "aggregate",
        "filters": [{"column": "id", "op": "gte", "value": 90_000}],
        "aggregations": [{"function": "count", "column": "*"}],
    }
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: execute_dataset_plan(
                    derivative_payload=built.parquet_payload,
                    profile=profile,
                    plan=plan,
                ),
                range(4),
            )
        )
    assert [result["rows"] for result in results] == [[{"calculation_1": 10_001}]] * 4


def test_files_over_size_or_row_limit_are_rejected_without_truncation() -> None:
    document = _document()
    oversized = b"x" * (MAX_GROUNDED_DATASET_BYTES + 1)
    with pytest.raises(ApiError) as size_error:
        build_parquet_derivative(document=document, payload=oversized)
    assert size_error.value.code == "DATASET_FILE_TOO_LARGE"
    assert size_error.value.status_code == 413

    payload = _table_payload(MAX_GROUNDED_DATASET_ROWS + 1)
    assert len(payload) < MAX_GROUNDED_DATASET_BYTES
    with pytest.raises(ApiError) as row_error:
        build_parquet_derivative(document=document, payload=payload)
    assert row_error.value.code == "DATASET_ROW_LIMIT_EXCEEDED"
    assert row_error.value.status_code == 422
    assert "without dropping rows" in row_error.value.message


def test_file_exactly_at_size_limit_is_fully_indexed() -> None:
    row_count = 32
    column_count = 8
    headers = [f"column_{index}" for index in range(column_count)]
    header = (",".join(headers) + "\n").encode("utf-8")
    fixed_bytes = len(header) + row_count * column_count
    cell_count = row_count * column_count
    cell_size, extra_bytes = divmod(MAX_GROUNDED_DATASET_BYTES - fixed_bytes, cell_count)
    remaining_extra = extra_bytes
    rows: list[bytes] = []
    for _ in range(row_count):
        values = []
        for _ in range(column_count):
            extra = 1 if remaining_extra else 0
            remaining_extra -= extra
            values.append(b"x" * (cell_size + extra))
        rows.append(b",".join(values) + b"\n")
    payload = header + b"".join(rows)

    assert len(payload) == MAX_GROUNDED_DATASET_BYTES
    built = build_parquet_derivative(document=_document(), payload=payload)
    assert built.row_count == row_count
    assert len(built.columns) == column_count


@pytest.mark.parametrize(
    "payload",
    [
        b'a,b\n1,2\n"unterminated,3\n',
        b"name,amount\nitem\n",
        b"name\n\xff\n",
        b"name,Name\nfirst,second\n",
        b",amount\nitem,1\n",
    ],
)
def test_malformed_or_ambiguous_table_headers_fail_explicitly(payload: bytes) -> None:
    with pytest.raises(ApiError):
        build_parquet_derivative(document=_document(), payload=payload)


def test_plan_rejects_sql_injection_and_unbounded_or_unknown_operations() -> None:
    document = _document()
    built = build_parquet_derivative(document=document, payload=b"name,value\na,1\nb,2\n")
    profile = _profile(document, built)

    with pytest.raises(ApiError) as unknown_column:
        execute_dataset_plan(
            derivative_payload=built.parquet_payload,
            profile=profile,
            plan={
                "action": "rows",
                "filters": [],
                "columns": ["name; DROP TABLE documents"],
                "limit": 1,
            },
        )
    assert unknown_column.value.code == "INVALID_DATASET_COLUMN"

    with pytest.raises(ApiError) as oversized_limit:
        execute_dataset_plan(
            derivative_payload=built.parquet_payload,
            profile=profile,
            plan={"action": "rows", "filters": [], "columns": ["name"], "limit": 101},
        )
    assert oversized_limit.value.code == "INVALID_DATASET_LIMIT"


def test_quoted_untrusted_csv_header_is_safe_to_query() -> None:
    document = _document()
    column = 'name"; DROP TABLE documents; --'
    built = build_parquet_derivative(
        document=document,
        payload=b'"name""; DROP TABLE documents; --"\nsafe value\n',
    )
    result = execute_dataset_plan(
        derivative_payload=built.parquet_payload,
        profile=_profile(document, built),
        plan={"action": "rows", "filters": [], "columns": [column], "limit": 1},
    )

    assert result["rows"] == [{"source_row_number": 2, column: "safe value"}]


@pytest.mark.parametrize(
    "request_text",
    ["What is the sum of amount?", "Which region had the highest sales?"],
)
def test_dataset_planner_receives_only_schema_not_cell_contents(
    monkeypatch, request_text: str
) -> None:
    from app.query.services import query_service as query_module

    document = SimpleNamespace(
        id=uuid4(), filename="private.csv", content_type="text/csv", status="indexed"
    )
    captured: dict[str, str] = {}
    service = object.__new__(query_module.QueryService)
    service.db = object()
    service.settings = object()
    service.documents = SimpleNamespace(list_by_ids=lambda **_: [document])
    service.answer = SimpleNamespace(
        _call_llm_provider=lambda **kwargs: (
            captured.update(context=kwargs["context"], prompt=kwargs["query_text"])
            or '{"action":"aggregate","filters":[],"aggregations":[{"function":"sum","column":"amount"}],"group_by":[]}',
            {},
        )
    )

    class _IndexService:
        def __init__(self, **_kwargs) -> None:
            pass

        def derivative_profile(self, **_kwargs):
            table = build_parquet_derivative(
                document=_document("private.csv"),
                payload=b"amount\n13\n29\n",
            )
            return (
                {"filename": "private.csv", "row_count": 2, "columns": table.columns},
                table.parquet_payload,
            )

    monkeypatch.setattr(query_module, "QueryDatasetIndexService", _IndexService)
    chunks = service._build_dataset_operation_chunks(
        auth=SimpleNamespace(tenant_id=uuid4(), user_id=uuid4()),
        query_text=request_text,
        attached_document_ids=[document.id],
        provider_candidates=[SimpleNamespace()],
    )

    assert len(chunks) == 1
    assert '"calculation_1":42' in chunks[0].content.replace(" ", "")
    assert chunks[0].source_row_numbers == [2, 3]
    assert chunks[0].matched_row_count == 2
    assert "13" not in captured["context"] and "29" not in captured["context"]
