from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_MERMAID_PREFIXES = (
    "flowchart",
    "graph",
    "sequencediagram",
    "mindmap",
    "statediagram",
    "classdiagram",
    "erdiagram",
    "journey",
    "gantt",
    "timeline",
    "gitgraph",
    "pie",
    "quadrantchart",
    "requirementdiagram",
    "block-beta",
    "xychart-beta",
    "c4context",
    "c4container",
    "c4component",
    "c4dynamic",
    "c4deployment",
    "architecture-beta",
    "sankey",
    "packet",
    "kanban",
    "zenuml",
)

_MERMAID_COMPLEX_LABEL_RE = r"([A-Za-z][\w-]*)\[((?:[^\[\]]|\[[^\]]*\])*)\]"
_MERMAID_ER_RELATION_RE = re.compile(
    r"^(\s*[A-Za-z_][\w]*)\s+([|o{}.\- ]+)\s+([A-Za-z_][\w]*)\s*:\s*(.+)$"
)


def _normalize_er_cardinality(token: str, *, side: str) -> str:
    normalized = token.strip().strip('"').strip("'").lower()
    if normalized in {"1", "one", "exactly one", "||", "|"}:
        return "||"
    if normalized in {"0..1", "0,1", "zero or one", "optional one", "o|", "|o", "o"}:
        return "o|" if side == "left" else "|o"
    if normalized in {"many", "1..*", "one or more", "mandatory many", "|{", "}|", "{"}:
        return "}|" if side == "left" else "|{"
    if normalized in {"0..*", "0,*", "zero or more", "optional many", "o{", "}o", "*"}:
        return "}o" if side == "left" else "o{"
    return token.strip()


def _normalize_er_connector(token: str) -> str:
    stripped = token.strip().strip('"').strip("'")
    if ".." in stripped:
        return ".."
    if "--" in stripped or "-" in stripped:
        return "--"
    return "--"


def _sanitize_er_relation(candidate: str) -> str | None:
    stripped = candidate.strip().strip("|").strip()
    if not stripped or ":" not in stripped:
        return None

    for pattern, mapping in (
        (
            r'^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.o|{}]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)(\s*:\s*.*)?$',
            ("entity", "left_card", "connector", "right_card", "target", "label"),
        ),
        (
            r'^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.o|{}]+)\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$',
            ("entity", "left_card", "connector", "target", "right_card", "label"),
        ),
        (
            r'^([A-Za-z_][\w]*)\s+([-.o|{}]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$',
            ("entity", "connector", "left_card", "target", "right_card", "label"),
        ),
    ):
        match = re.match(pattern, stripped)
        if not match:
            continue
        parts = dict(zip(mapping, match.groups(), strict=False))
        left_entity = str(parts["entity"]).strip()
        left_card = _normalize_er_cardinality(str(parts["left_card"]), side="left")
        connector = _normalize_er_connector(str(parts["connector"]))
        right_card = _normalize_er_cardinality(str(parts["right_card"]), side="right")
        right_entity = str(parts["target"]).strip()
        label = str(parts.get("label") or "")
        return f"{left_entity} {left_card}{connector}{right_card} {right_entity}{label}"

    relation_match = _MERMAID_ER_RELATION_RE.match(stripped)
    if not relation_match:
        return None

    left_entity = relation_match.group(1).strip()
    relation_blob = re.sub(r"\s+", "", relation_match.group(2))
    right_entity = relation_match.group(3).strip()
    label = relation_match.group(4).strip()
    connector = ".." if ".." in relation_blob else "--"
    left_raw, right_raw = relation_blob.split(connector, 1)
    left_card = _normalize_er_cardinality(left_raw or "|", side="left")
    right_card = _normalize_er_cardinality(right_raw or "|", side="right")
    return f"{left_entity} {left_card}{connector}{right_card} {right_entity} : {label}"


def _normalize_class_cardinality(token: str) -> str:
    normalized = token.strip().strip('"').strip("'").lower()
    if normalized in {"o", "0..1", "0,1", "zero or one", "optional one"}:
        return "0..1"
    if normalized in {"*", "many", "0..*", "0,*", "zero or more"}:
        return "*"
    if normalized in {"1..*", "one or more"}:
        return "1..*"
    if normalized in {"1", "one", "exactly one"}:
        return "1"
    return token.strip().strip('"').strip("'")


def _sanitize_class_relation(candidate: str) -> str | None:
    stripped = candidate.strip()
    if not stripped or '"' not in stripped:
        return None

    malformed_double_card_match = re.match(
        r'^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.<>*o]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$',
        stripped,
    )
    if malformed_double_card_match:
        (
            left_entity,
            left_card,
            relation,
            middle_card,
            right_entity,
            _trailing_card,
            label,
        ) = malformed_double_card_match.groups()
        return (
            f'{left_entity} "{_normalize_class_cardinality(left_card)}" '
            f'{relation} "{_normalize_class_cardinality(middle_card)}" {right_entity}{label or ""}'
        )

    valid_match = re.match(
        r'^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.<>*o]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)(\s*:\s*.*)?$',
        stripped,
    )
    if valid_match:
        left_entity, left_card, relation, right_card, right_entity, label = valid_match.groups()
        return (
            f'{left_entity} "{_normalize_class_cardinality(left_card)}" '
            f'{relation} "{_normalize_class_cardinality(right_card)}" {right_entity}{label or ""}'
        )

    malformed_match = re.match(
        r'^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.<>*o]+)\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$',
        stripped,
    )
    if malformed_match:
        left_entity, left_card, relation, right_entity, right_card, label = malformed_match.groups()
        return (
            f'{left_entity} "{_normalize_class_cardinality(left_card)}" '
            f'{relation} "{_normalize_class_cardinality(right_card)}" {right_entity}{label or ""}'
        )

    return None


def _canonicalize_class_member(candidate: str) -> str:
    stripped = candidate.strip()
    if not stripped:
        return candidate

    if re.match(r"^[+\-#~]?\s*[A-Za-z_]\w*\s*:\s*[\w.~<> ,\[\]]+$", stripped):
        return stripped

    match = re.match(
        r"^([+\-#~]?)\s*([A-Za-z_][\w.<>~, \[\]]*)\s+([A-Za-z_]\w*)$",
        stripped,
    )
    if match:
        visibility, raw_type, name = match.groups()
        normalized_type = raw_type.strip().replace("<", "~").replace(">", "~")
        normalized_type = re.sub(r"\s+", " ", normalized_type)
        return f"{visibility}{name}: {normalized_type}"

    return stripped


def _sanitize_class_attribute(candidate: str) -> str:
    stripped = candidate.strip()
    if not stripped or stripped.startswith(("class ", "<<", "note ", "direction ")):
        return candidate
    if '"' in stripped:
        return candidate
    if re.match(r"^[+\-#~]", stripped):
        canonical = _canonicalize_class_member(stripped)
        if (
            canonical == stripped
            and re.search(r"[<~]\s*[A-Z][\w.]*\s*[>~]", canonical)
            and ":" not in canonical
        ):
            return ""
        if re.search(r"[<~]\s*[A-Z][\w.]*\s*[>~]", canonical):
            canonical = canonical.replace("<", "~").replace(">", "~")
        return canonical
    if re.search(r"[<~]\s*[A-Z][\w.]*\s*[>~]", stripped):
        return ""

    # Mermaid class diagrams handle generics more reliably with ~Type~ than <Type>.
    return re.sub(r"<([A-Za-z_][\w., ]*)>", lambda m: f"~{m.group(1).strip()}~", candidate)


def _class_declaration_name(candidate: str) -> str | None:
    stripped = candidate.strip()
    explicit_match = re.match(r"^class\s+([A-Za-z_][\w]*)\s*$", stripped)
    if explicit_match:
        return explicit_match.group(1)

    implicit_match = re.match(r"^([A-Za-z_][\w]*)\s*$", stripped)
    if implicit_match:
        return implicit_match.group(1)

    return None


def _repair_detached_class_members(lines: list[str]) -> list[str]:
    repaired: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        class_name = _class_declaration_name(line)

        if not class_name or "{" in stripped or stripped.startswith(("direction ", "note ", "%%")):
            repaired.append(line)
            index += 1
            continue

        members: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            candidate_stripped = candidate.strip()

            if not candidate_stripped:
                cursor += 1
                continue

            if (
                _class_declaration_name(candidate) is not None
                or candidate_stripped.startswith(("direction ", "note ", "%%", "class "))
                or "{" in candidate_stripped
                or "}" in candidate_stripped
                or _sanitize_class_relation(candidate_stripped) is not None
            ):
                break

            if re.match(r"^[+\-#~]", candidate_stripped):
                sanitized_member = _sanitize_class_attribute(candidate_stripped).strip()
                if sanitized_member:
                    members.append(f"  {sanitized_member}")
                cursor += 1
                continue

            break

        if members:
            repaired.append(f"class {class_name} {{")
            repaired.extend(members)
            repaired.append("}")
            index = cursor
            continue

        repaired.append(line)
        index += 1

    return repaired


def _simplify_textual_mermaid_label(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return value
    normalized = (
        normalized.replace("&", " and ")
        .replace(":", " ")
        .replace(";", " ")
        .replace(",", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace('"', "")
        .replace("'", "")
    )
    normalized = re.sub(r"[^\w\s/\-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _sanitize_mindmap_line(line: str) -> str:
    leading_match = re.match(r"^\s*", line)
    leading = leading_match.group(0) if leading_match else ""
    content = line[len(leading) :].rstrip()
    if not content or content.startswith(("%%", "::")):
        return line

    wrapped = re.match(
        r"^([A-Za-z_][\w-]*)(\(\(|\(\[|\[\[|\(|\[)(.*?)(\)\)|\]\)|\]\]|\)|\])$", content
    )
    if wrapped:
        node_id, open_wrap, label, close_wrap = wrapped.groups()
        return f"{leading}{node_id}{open_wrap}{_simplify_textual_mermaid_label(label)}{close_wrap}"

    return f"{leading}{_simplify_textual_mermaid_label(content)}"


def _repair_mindmap_structure(lines: list[str]) -> list[str]:
    body = lines[1:]
    content_lines = [line for line in body if line.strip() and not line.strip().startswith("%%")]
    if not content_lines:
        return lines

    if any(line.strip().startswith("root") for line in content_lines):
        return lines

    first_content = content_lines[0].strip()
    normalized_root = _simplify_textual_mermaid_label(
        re.sub(r"^[-*]\s*", "", re.sub(r"^#+\s*", "", first_content))
    )

    repaired = [
        lines[0] if lines else "mindmap",
        f"  root(({normalized_root or 'Root'}))",
    ]
    root_assigned = False
    first_normalized = _simplify_textual_mermaid_label(first_content)

    for original_line in body:
        stripped = original_line.strip()
        if not stripped:
            continue
        if stripped.startswith("%%"):
            repaired.append(original_line)
            continue

        sanitized_line = _sanitize_mindmap_line(original_line).strip()
        if not root_assigned and sanitized_line == first_normalized:
            root_assigned = True
            continue
        repaired.append(f"    {sanitized_line}")

    return repaired


def _sanitize_journey_line(line: str) -> str:
    def infer_actor(label: str) -> str:
        first_word = re.split(r"\s+", label.strip(), maxsplit=1)[0] if label.strip() else ""
        first_word = re.sub(r"[^\w-]", "", first_word)
        if re.match(
            r"^(user|admin|system|analyst|reviewer|customer|client)$",
            first_word,
            flags=re.I,
        ):
            return first_word
        return "User"

    stripped = line.strip()
    if not stripped or stripped.startswith("%%"):
        return line
    indent_match = re.match(r"^\s*", line)
    indent = indent_match.group(0) if indent_match else ""
    if stripped.lower().startswith("title "):
        return f"{indent}title {_simplify_textual_mermaid_label(stripped[6:])}"
    if stripped.lower().startswith("section "):
        return f"{indent}section {_simplify_textual_mermaid_label(stripped[8:])}"

    arrow_match = re.match(r"^(?:->|-->|[-*])\s*(.+)$", stripped)
    if arrow_match:
        label = _simplify_textual_mermaid_label(arrow_match.group(1) or "")
        return f"{indent}{label}: 5: System"

    parts = [part.strip() for part in stripped.split(":") if part.strip()]
    if len(parts) >= 2:
        label = _simplify_textual_mermaid_label(parts[0])
        score = parts[1]
        normalized_score = score if re.match(r"^\d+$", score) else "5"
        actor_source = (
            " ".join(parts[2:])
            if re.match(r"^\d+$", score) and len(parts) > 2
            else re.sub(r"\$[^$]+\$", "", score)
        )
        actor_source = re.sub(r"^[->-]+\s*", "", actor_source)
        actor = _simplify_textual_mermaid_label(actor_source) or infer_actor(label)
        return f"{indent}{label}: {normalized_score}: {actor}"
    label = _simplify_textual_mermaid_label(stripped)
    return f"{indent}{label}: 5: {infer_actor(label)}"


def _sanitize_timeline_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith("%%"):
        return line
    indent_match = re.match(r"^\s*", line)
    indent = indent_match.group(0) if indent_match else ""
    if stripped.lower().startswith("title "):
        return f"{indent}title {_simplify_textual_mermaid_label(stripped[6:])}"
    if stripped.lower().startswith("section "):
        return f"{indent}section {_simplify_textual_mermaid_label(stripped[8:])}"
    if ":" in stripped:
        left, right = stripped.split(":", 1)
        return f"{indent}{_simplify_textual_mermaid_label(left)} : {_simplify_textual_mermaid_label(right)}"
    return f"{indent}{_simplify_textual_mermaid_label(stripped)}"


def _sanitize_gantt_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith("%%"):
        return line
    indent_match = re.match(r"^\s*", line)
    indent = indent_match.group(0) if indent_match else ""
    lower = stripped.lower()
    for prefix in (
        "title ",
        "dateformat ",
        "axisformat ",
        "tickinterval ",
        "excludes ",
        "todaymarker ",
    ):
        if lower.startswith(prefix):
            if prefix == "title ":
                return f"{indent}title {_simplify_textual_mermaid_label(stripped[len(prefix) :])}"
            return line
    if lower.startswith("section "):
        return f"{indent}section {_simplify_textual_mermaid_label(stripped[8:])}"
    if ":" in stripped:
        left, right = stripped.split(":", 1)
        return f"{indent}{_simplify_textual_mermaid_label(left)} :{right}"
    return f"{indent}{_simplify_textual_mermaid_label(stripped)}"


def is_valid_mermaid_syntax(syntax: str) -> bool:
    normalized = syntax.strip().lower()
    if not normalized:
        return False
    first_line = normalized.splitlines()[0].strip()
    return any(first_line.startswith(prefix) for prefix in _VALID_MERMAID_PREFIXES)


def sanitize_mermaid_syntax(syntax: str) -> str:
    normalized = syntax.strip()
    if not normalized:
        return syntax

    def split_starter(text: str, pattern: str, starter: str) -> str:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            return text
        rest = (match.group(1) or "").lstrip()
        return starter if not rest else f"{starter}\n{rest}"

    def split_directional_starter(text: str, pattern: str) -> str:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            return text
        starter = (match.group(1) or "").strip()
        rest = (match.group(2) or "").lstrip()
        rest = re.sub(r"^\|+\s*", "", rest)
        return starter if not rest else f"{starter}\n{rest}"

    normalized = split_directional_starter(
        normalized,
        r"^((?:graph|flowchart)\s+(?:TB|TD|BT|RL|LR))\s*([\s\S]*)$",
    )
    normalized = split_starter(normalized, r"^erdiagram\s*([\s\S]*)$", "erDiagram")
    normalized = split_starter(normalized, r"^classdiagram\s*([\s\S]*)$", "classDiagram")
    normalized = split_starter(normalized, r"^journey\s*([\s\S]*)$", "journey")
    normalized = split_starter(normalized, r"^timeline\s*([\s\S]*)$", "timeline")
    normalized = split_starter(normalized, r"^gantt\s*([\s\S]*)$", "gantt")
    state_match = re.match(r"^(stateDiagram(?:-v2)?)\s*([\s\S]*)$", normalized, flags=re.IGNORECASE)
    if state_match:
        state_starter = state_match.group(1)
        rest = (state_match.group(2) or "").lstrip()
        normalized = state_starter if not rest else f"{state_starter}\n{rest}"
    normalized = split_starter(normalized, r"^sequencediagram\s*([\s\S]*)$", "sequenceDiagram")
    normalized = split_starter(normalized, r"^mindmap\s*([\s\S]*)$", "mindmap")

    first_line = normalized.splitlines()[0].strip().lower()
    if first_line.startswith("erdiagram"):
        sanitized_lines: list[str] = []
        for index, line in enumerate(normalized.splitlines()):
            stripped = line.strip()
            if (
                index == 0
                or not stripped
                or stripped.startswith(("%%", "title", "accTitle", "accDescr"))
            ):
                sanitized_lines.append(line)
                continue
            line = re.sub(r"^\|\s*([A-Za-z_][\w]*)\s*\|\s*", r"\1 ", line)
            line = re.sub(r"\s*\|\s*$", "", line)
            line = re.sub(r"\s+\|\s*\|\s*--", " ||--", line)
            line = re.sub(r"^(\s*[A-Za-z_][\w]*)\s+\|\s*--", r"\1 |--", line)
            line = re.sub(r"--\s*\|\s*\|", "--|| ", line)
            line = re.sub(
                r'(:\s*[^:\n]+?)\s+(?=\|?[A-Za-z_][\w]*\s+(?:[|o{}.\-"]|--))',
                r"\1\n",
                line,
            )

            for segment in line.splitlines():
                candidate = segment.strip()
                if not candidate:
                    continue
                repaired = _sanitize_er_relation(candidate)
                sanitized_lines.append(repaired or candidate)
        return "\n".join(sanitized_lines)

    if first_line.startswith("classdiagram"):
        class_lines: list[str] = []
        has_direction = False
        repaired_lines = _repair_detached_class_members(normalized.splitlines())
        for index, line in enumerate(repaired_lines):
            stripped = line.strip()
            if index == 0 or not stripped:
                class_lines.append(line)
                continue
            if stripped.lower().startswith("direction "):
                has_direction = True
                class_lines.append(line)
                continue
            repaired = _sanitize_class_relation(stripped)
            sanitized = repaired or _sanitize_class_attribute(line)
            if sanitized.strip():
                class_lines.append(sanitized)
        if not has_direction:
            class_lines.insert(1, "direction TB")
        return "\n".join(class_lines)

    if first_line.startswith("mindmap"):
        lines = _repair_mindmap_structure(normalized.splitlines())
        return "\n".join([lines[0], *[_sanitize_mindmap_line(line) for line in lines[1:]]])

    if first_line.startswith("journey"):
        lines = normalized.splitlines()
        return "\n".join([lines[0], *[_sanitize_journey_line(line) for line in lines[1:]]])

    if first_line.startswith("timeline"):
        lines = normalized.splitlines()
        return "\n".join([lines[0], *[_sanitize_timeline_line(line) for line in lines[1:]]])

    if first_line.startswith("gantt"):
        lines = normalized.splitlines()
        return "\n".join([lines[0], *[_sanitize_gantt_line(line) for line in lines[1:]]])

    if not (first_line.startswith("flowchart") or first_line.startswith("graph")):
        return normalized

    def replace_complex_label(match: re.Match[str]) -> str:
        node_id = match.group(1)
        label = match.group(2).strip()
        if not label or (label.startswith('"') and label.endswith('"')):
            return match.group(0)
        # Quote ANY label that contains spaces or special characters.
        # This prevents Mermaid from misinterpreting parentheses, colons,
        # commas, etc. as syntax tokens (e.g. "got 'PS'" errors).
        if re.search(r"[\s(),.:;'\"/\\&]", label):
            escaped = label.replace("\\", "\\\\").replace('"', '\\"')
            return f'{node_id}["{escaped}"]'
        return match.group(0)

    flow_lines: list[str] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("style ", "classDef ", "class ", "linkStyle ")):
            flow_lines.append(line)
            continue
        normalized_line = re.sub(r"(-->|==>|-.->)\s+\|", r"\1|", line)
        normalized_line = re.sub(
            r"(-->|==>|-.->)\|\s*([^|]+?)\s*\|",
            lambda match: f"{match.group(1)}|{match.group(2).strip()}|",
            normalized_line,
        )
        normalized_line = re.sub(r"\s+\|\|\s+", "\n", normalized_line)
        normalized_line = re.sub(r"\|\|\s+", "\n", normalized_line)
        normalized_line = re.sub(r"\s+\|\|", "\n", normalized_line)
        normalized_line = re.sub(
            r"\s+\|\|\s+(?=[A-Za-z][\w-]*\s+(?:\-{1,2}|\.?-{2,}\.?|={2,})[->])",
            "\n",
            normalized_line,
        )
        normalized_line = re.sub(
            r"\|\|\s*(?=[A-Za-z][\w-]*\s+(?:\-{1,2}|\.?-{2,}\.?|={2,})[->])",
            "\n",
            normalized_line,
        )
        for segment in normalized_line.splitlines():
            flow_lines.append(re.sub(_MERMAID_COMPLEX_LABEL_RE, replace_complex_label, segment))
    return "\n".join(flow_lines)


class StructuredTableResponse(BaseModel):
    title: str = Field(default="Comparison")
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StructuredChartPointResponse(BaseModel):
    label: str
    value: float

    model_config = ConfigDict(extra="forbid")


class StructuredChartResponse(BaseModel):
    title: str = Field(default="Chart Data")
    chart_type: str = Field(default="bar", description="bar|line")
    series: list[StructuredChartPointResponse] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StructuredDiagramResponse(BaseModel):
    class GraphNode(BaseModel):
        id: str
        label: str
        category: str | None = None

        model_config = ConfigDict(extra="forbid")

    class GraphEdge(BaseModel):
        source: str
        target: str
        label: str | None = None

        model_config = ConfigDict(extra="forbid")

    class GraphPayload(BaseModel):
        nodes: list[StructuredDiagramResponse.GraphNode] = Field(default_factory=list)
        edges: list[StructuredDiagramResponse.GraphEdge] = Field(default_factory=list)
        layout: str = Field(default="horizontal", description="horizontal|vertical|radial")

        model_config = ConfigDict(extra="forbid")

    title: str = Field(default="Process Diagram")
    diagram_type: str = Field(
        default="mermaid_flowchart",
        description=(
            "mermaid_flowchart|mermaid_sequence|mermaid_state|mermaid_class|mermaid_er|"
            "mermaid_journey|mermaid_timeline|mermaid_gantt|mermaid_mindmap|mermaid_pie|"
            "mermaid_gitgraph|mermaid_quadrant|mermaid_requirement|mermaid_block|"
            "mermaid_xychart|mermaid_c4|mermaid_architecture|mermaid_sankey|"
            "mermaid_packet|mermaid_kanban|graph_canvas"
        ),
    )
    source: str = Field(default="mermaid", description="mermaid|graph_json")
    syntax: str = Field(default="", description="Diagram definition string")
    description: str = Field(default="", description="Short supporting explanation")
    graph: GraphPayload | None = Field(
        default=None,
        description="Optional typed graph payload for non-Mermaid rendering",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_diagram_payload(self) -> StructuredDiagramResponse:
        if self.source == "mermaid":
            self.syntax = sanitize_mermaid_syntax(self.syntax)
            if not is_valid_mermaid_syntax(self.syntax):
                raise ValueError(
                    "Mermaid syntax must start with a valid Mermaid diagram keyword such as "
                    "flowchart, graph, sequenceDiagram, or mindmap."
                )
            if self.graph is not None:
                raise ValueError("Mermaid diagrams must not include a graph payload.")
        if self.source == "graph_json" and self.graph is None:
            raise ValueError("graph_json diagrams must include a graph payload.")
        return self


class StructuredAnswerResponse(BaseModel):
    key_findings: list[str] = Field(
        default_factory=list,
        description="Top-level executive summary bullet points. Must be a list of non-empty strings.",
    )
    detailed_analysis: str = Field(
        default="",
        description=(
            "Deep-dive professional analysis using structured Markdown "
            "(headings, lists, bolding). Must be comprehensive and well-spaced "
            "with logical paragraph breaks.\n\n"
            'FORMATTING RULE: Your "detailed_analysis" MUST be professionally '
            "structured using Markdown. Use H3 headings (###), bold sub-headers, "
            "and lists where appropriate. Ensure logical paragraph breaks and a "
            "professional, analytical tone. DO NOT output a single block of text. "
            'Use "justified" reasoning style.\n\n'
            "CRITICAL: You must ONLY respond with a single valid JSON object.\n"
            'DO NOT include "Thinking Process", "Reasoning", or any '
            "conversational filler before or after the JSON.\n"
            "Your entire response must be a valid JSON block starting with {{ "
            "and ending with }}."
        ),
    )
    limitations: str = Field(default="", description="Any missing context or ambiguity")
    conclusion: str = Field(default="", description="Final synthesized insight or takeaway")
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Calibrated confidence 0.0-1.0"
    )
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions. Must be a list of non-empty strings.",
    )
    comparison_table: StructuredTableResponse | None = Field(
        default=None,
        description="Optional comparison table for side-by-side answers.",
    )
    chart: StructuredChartResponse | None = Field(
        default=None,
        description="Optional chart payload for numeric or trend answers.",
    )
    diagram: StructuredDiagramResponse | None = Field(
        default=None,
        description="Optional diagram payload for workflow or architecture answers.",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("key_findings", "follow_up_suggestions")
    @classmethod
    def remove_blank_items(cls, values: list[str]) -> list[str]:
        return [item.strip() for item in values if item and item.strip()]

    @classmethod
    def fallback(cls, text: str) -> StructuredAnswerResponse:
        return cls(
            key_findings=[],
            detailed_analysis=text,
            limitations="",
            conclusion="",
        )


class ReasoningTraceModel(BaseModel):
    """Retrieval diagnostics — how the system reached the answer."""

    chunks_searched: int = Field(default=0, description="Total chunks in search space")
    chunks_evaluated: int = Field(default=0, description="Chunks scored by retrieval")
    chunks_selected: int = Field(default=0, description="Chunks passed to LLM")
    chunks_rejected: int = Field(default=0, description="Chunks below threshold")
    rejection_reasons: list[str] = Field(default_factory=list)
    search_strategy: str = Field(default="hybrid", description="hybrid|vector|keyword")
    timing_ms: dict[str, float] = Field(default_factory=dict, description="Per-stage timing in ms")
    metadata: dict[str, object] = Field(
        default_factory=dict, description="Additional trace diagnostics"
    )
    search_strategy_summary: str = Field(default="", description="Human-readable search summary")
    trace_id: str = Field(default="", description="Unique trace ID for audit/debugging")

    model_config = ConfigDict(extra="forbid")


class SynthesisMatrixCell(BaseModel):
    finding: str
    document: str
    status: str = Field(description="supported|partial|not_found")
    evidence: str = Field(default="", description="Supporting evidence snippet")

    model_config = ConfigDict(extra="forbid")


class SynthesisMatrix(BaseModel):
    findings: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    cells: list[SynthesisMatrixCell] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
