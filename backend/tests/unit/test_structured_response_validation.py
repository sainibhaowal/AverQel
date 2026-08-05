from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.query.schemas.structured_response import (
    StructuredDiagramResponse,
    is_valid_mermaid_syntax,
    sanitize_mermaid_syntax,
)


def test_is_valid_mermaid_syntax_requires_real_mermaid_starter() -> None:
    assert is_valid_mermaid_syntax("flowchart TD\nA --> B") is True
    assert is_valid_mermaid_syntax("sequenceDiagram\nA->>B: hello") is True
    assert is_valid_mermaid_syntax("erDiagram\nDocument ||--o{ Chunk : contains") is True
    assert is_valid_mermaid_syntax("classDiagram\nclass Document") is True
    assert is_valid_mermaid_syntax("xychart-beta\nbar [1, 2, 3]") is True
    assert is_valid_mermaid_syntax('C4Context\nPerson(user, "User")') is True
    assert is_valid_mermaid_syntax("kanban\nTodo") is True
    assert is_valid_mermaid_syntax("diagram TD\nA --> B") is False


def test_structured_diagram_rejects_invalid_mermaid_prefix() -> None:
    with pytest.raises(ValidationError):
        StructuredDiagramResponse(
            title="Invalid Diagram",
            diagram_type="mermaid_flowchart",
            source="mermaid",
            syntax="diagram TD\nA --> B",
            description="",
        )


def test_structured_diagram_canonicalizes_mermaid_syntax_before_validation() -> None:
    diagram = StructuredDiagramResponse(
        title="Journey",
        diagram_type="mermaid_journey",
        source="mermaid",
        syntax="journey\nsection Upload\nUser uploads a document: $start$\n-> Upload complete",
        description="",
    )

    assert "User uploads a document: 5: User" in diagram.syntax
    assert "Upload complete: 5: System" in diagram.syntax


def test_sanitize_mermaid_er_relationship_spacing() -> None:
    syntax = """erDiagram
Document | | -- o{ Chunk : contains
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "Document ||--o{ Chunk : contains" in sanitized


def test_sanitize_mermaid_er_same_line_and_quoted_cardinality() -> None:
    syntax = (
        'erDiagram| Document | | --o{ Chunk : contains\nCollection "1" -- "many" Document : groups'
    )

    sanitized = sanitize_mermaid_syntax(syntax)

    assert sanitized.startswith("erDiagram\n")
    assert "Document ||--o{ Chunk : contains" in sanitized
    assert "Collection ||--|{ Document : groups" in sanitized


def test_sanitize_mermaid_er_splits_collapsed_relations() -> None:
    syntax = "erDiagram\nDocument }o--|| Collection : belongsTo |Collection ||--|{ Chunk : contains"

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "Document }o--|| Collection : belongsTo" in sanitized
    assert "Collection ||--|{ Chunk : contains" in sanitized


def test_sanitize_mermaid_er_pipe_wrapped_relations() -> None:
    syntax = """erDiagram
| Document |  | --o{ Collection : belongsTo |
| Collection |  | -- | { User : managedBy |
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "Document ||--o{ Collection : belongsTo" in sanitized
    assert "Collection ||--|{ User : managedBy" in sanitized


def test_sanitize_mermaid_er_same_line_starter_without_space() -> None:
    syntax = "erDiagramDOCUMENT ||--o{ CHUNK : contains"

    sanitized = sanitize_mermaid_syntax(syntax)

    assert sanitized.startswith("erDiagram\n")
    assert "DOCUMENT ||--o{ CHUNK : contains" in sanitized


def test_sanitize_mermaid_flowchart_same_line_starter_with_leading_pipe() -> None:
    syntax = "graph TD| A[Exponential Distribution] --> B[Gamma Distribution]"

    sanitized = sanitize_mermaid_syntax(syntax)

    assert sanitized.startswith("graph TD\n")
    assert "| A[" not in sanitized
    assert 'A["Exponential Distribution"] --> B["Gamma Distribution"]' in sanitized


def test_sanitize_mermaid_flowchart_concatenated_edges_and_label_spacing() -> None:
    syntax = (
        "graph TD\n"
        "A[Exponential Distribution] --> | Overlap with Gamma Distribution | B[Gamma Distribution] "
        "|| A --> | Overlap with Poisson Distribution | C[Poisson Distribution]"
    )

    sanitized = sanitize_mermaid_syntax(syntax)

    assert (
        'A["Exponential Distribution"] -->|Overlap with Gamma Distribution| B["Gamma Distribution"]'
        in sanitized
    )
    assert '\nA -->|Overlap with Poisson Distribution| C["Poisson Distribution"]' in sanitized
    assert "] || A --> |" not in sanitized
    assert "--> | Overlap" not in sanitized


def test_sanitize_mermaid_class_relations_with_trailing_cardinality() -> None:
    syntax = """classDiagram
Document "1" -- "o" Collection "1"
Chunk "1" -- "o" Document "1"
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert 'Document "1" -- "0..1" Collection' in sanitized
    assert 'Chunk "1" -- "0..1" Document' in sanitized


def test_sanitize_mermaid_class_generic_attributes_and_default_direction() -> None:
    syntax = """classDiagram
class Collection {
    +list<Document>
}
Collection "1" -- "many" Document : contains
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert sanitized.startswith("classDiagram\n")
    assert "direction TB" in sanitized
    assert "+list<Document>" not in sanitized
    assert 'Collection "1" -- "*" Document : contains' in sanitized


def test_sanitize_mermaid_class_drops_association_like_generic_field_lines() -> None:
    syntax = """classDiagram
class Collection {
    +list<Document> documents
}
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "+list<Document> documents" not in sanitized


def test_sanitize_mermaid_class_preserves_scalar_generic_field_lines() -> None:
    syntax = """classDiagram
class Collection {
    +list<string> tags
}
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "+tags: list~string~" in sanitized


def test_sanitize_mermaid_class_canonicalizes_member_types() -> None:
    syntax = """classDiagram
class Query {
    +string id
    -UUID queryId
    #List<Document> documents
}
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "+id: string" in sanitized
    assert "-queryId: UUID" in sanitized
    assert "#documents: List~Document~" in sanitized


def test_sanitize_mermaid_wraps_detached_class_members_into_blocks() -> None:
    syntax = """classDiagram
Query
+string id
+string text
+string collectionId
Collection
+string id
+string name
Query "1" --> "*" Collection : relatesTo
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "class Query {" in sanitized
    assert "class Collection {" in sanitized
    assert "+collectionId: string" in sanitized
    assert "\nQuery\n+string id" not in sanitized


def test_sanitize_mermaid_mindmap_simplifies_punctuation_heavy_labels() -> None:
    syntax = """mindmap
  root(Unit 2: Random Variables)
    Definition: Rule/function assigning outcomes of sample space to real numbers
    Kim, A. (2019). Exponential Distribution - Intuition, Derivation, and Applications
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert sanitized.startswith("mindmap\n")
    assert "root(Unit 2 Random Variables)" in sanitized
    assert (
        "Definition Rule/function assigning outcomes of sample space to real numbers" in sanitized
    )
    assert (
        "Kim A 2019 Exponential Distribution - Intuition Derivation and Applications" in sanitized
    )


def test_sanitize_mermaid_mindmap_adds_root_when_missing() -> None:
    syntax = """mindmap
Introduction
Background
Key Ideas
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "root((Introduction))" in sanitized
    assert "    Background" in sanitized
    assert "    Key Ideas" in sanitized


def test_sanitize_mermaid_journey_simplifies_task_labels() -> None:
    syntax = """journey
title Document workflow: upload, query, export
section Review & export
  Review evidence, compare answer: 5: User, Analyst
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "title Document workflow upload query export" in sanitized
    assert "section Review and export" in sanitized
    assert "Review evidence compare answer: 5: User Analyst" in sanitized


def test_sanitize_mermaid_journey_repairs_non_taskdata_lines() -> None:
    syntax = """journey
title User Document Interaction Journey
section Upload
User uploads a document: $start$
-> Upload complete
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert "User uploads a document: 5: User" in sanitized
    assert "Upload complete: 5: System" in sanitized
