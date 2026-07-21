"""Structured, adaptive request classification used before mission planning."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class TaskClassification:
    task_type: str
    complexity: str
    risk: str
    needs_tools: bool
    needs_subagents: bool
    needs_approval: bool
    needs_verification: bool
    confidence: float
    rationale: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveTaskClassifier:
    """A deterministic safety floor; an LLM planner may refine this later.

    Safety-critical properties (risk and approval) are intentionally conservative
    and never inferred from an optimistic model response.
    """

    _coding = re.compile(r"\b(code|coding|repo|repository|bug|fix|refactor|implement|test|pytest|compile|module|function|api)\b", re.I)
    _research = re.compile(r"\b(research|investigate|compare|benchmark|sources|latest|analy[sz]e|report)\b", re.I)
    _automation = re.compile(r"\b(automate|workflow|pipeline|sync|migrate|deploy|schedule|run every)\b", re.I)
    _dangerous = re.compile(r"\b(delete|remove|drop|destroy|shutdown|send|publish|deploy|push|payment|production|sudo|credential|password)\b", re.I)
    _external = re.compile(r"\b(email|gmail|github|slack|calendar|drive|notion|connector|external)\b", re.I)

    def classify(self, text: str, *, note_content: str | None = None) -> TaskClassification:
        value = " ".join(str(text or "").split())
        rationale: list[str] = []
        coding = bool(self._coding.search(value))
        research = bool(self._research.search(value))
        automation = bool(self._automation.search(value))
        external = bool(self._external.search(value))
        dangerous = bool(self._dangerous.search(value))
        if coding:
            task_type = "coding"
            rationale.append("code or repository intent detected")
        elif external:
            task_type = "external_action"
            rationale.append("external system intent detected")
        elif automation:
            task_type = "automation"
            rationale.append("workflow or automation intent detected")
        elif research:
            task_type = "research"
            rationale.append("research or comparison intent detected")
        else:
            task_type = "chat"
        complexity_score = len(value.split()) + (8 if note_content and len(note_content) > 4000 else 0)
        complexity = "large" if complexity_score >= 40 or value.count(" and ") >= 2 else "medium" if complexity_score >= 14 else "small"
        needs_verification = coding or automation or task_type == "research"
        needs_tools = task_type != "chat" or bool(note_content)
        needs_subagents = complexity == "large" or coding or research or automation
        needs_approval = dangerous or external
        risk = "high" if dangerous else "medium" if external or coding or automation else "low"
        return TaskClassification(task_type, complexity, risk, needs_tools, needs_subagents, needs_approval, needs_verification, 0.72 if task_type != "chat" else 0.9, rationale)

