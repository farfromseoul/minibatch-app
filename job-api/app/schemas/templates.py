"""Remotion 템플릿의 속성 규격 (앱 설계 "Remotion 템플릿 규격").

render/src/lib/timeline.ts 의 검사와 같은 규칙이다. 바꿀 때는 두 곳을 함께 바꾼다
(scenes 단계에서 먼저 걸러 렌더 단계까지 가서 실패하지 않게 한다).
"""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

_STR = {"type": "string", "minLength": 1}

TEMPLATES: dict[str, dict[str, Any]] = {
    "TitleReveal": {
        "use": "후킹, 주제 소개. 큰 제목과 작은 부제",
        "props": {"type": "object", "required": ["title"],
                  "properties": {"title": _STR, "subtitle": {"type": "string"}}},
    },
    "FlowDiagram": {
        "use": "단계가 이어지는 흐름 (RAG, OAuth 등). 위→아래 상자와 화살표, 노드 2~6개",
        "props": {"type": "object", "required": ["nodes", "edges"],
                  "properties": {
                      "nodes": {"type": "array", "minItems": 2, "maxItems": 6,
                                "items": {"type": "object", "required": ["id", "label"],
                                          "properties": {"id": _STR, "label": _STR}}},
                      "edges": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": _STR}},
                      "revealOrder": {"type": "array", "items": _STR}}},
    },
    "ComparisonCards": {
        "use": "둘을 비교 (LLM vs RAG). 위아래 카드 두 장, 카드마다 요점 1~4개",
        "props": {"type": "object", "required": ["left", "right"],
                  "properties": {side: {"type": "object", "required": ["title", "points"],
                                        "properties": {"title": _STR,
                                                       "points": {"type": "array", "minItems": 1, "maxItems": 4, "items": _STR}}}
                                 for side in ("left", "right")}},
    },
    "NeuralNetwork": {
        "use": "신경망 층 구조 (딥러닝, 가중치). 층 2~6개, 층마다 노드 1~8개",
        "props": {"type": "object", "required": ["layers"],
                  "properties": {"layers": {"type": "array", "minItems": 2, "maxItems": 6,
                                            "items": {"type": "integer", "minimum": 1, "maximum": 8}},
                                 "labels": {"type": "array", "items": {"type": "string"}}}},
    },
    "SummaryScene": {
        "use": "정리. 번호 붙은 요점 1~3개",
        "props": {"type": "object", "required": ["points"],
                  "properties": {"points": {"type": "array", "minItems": 1, "maxItems": 3, "items": _STR}}},
    },
}


def check_props(component: str, props: Any) -> list[str]:
    spec = TEMPLATES.get(component)
    if spec is None:
        return [f"없는 템플릿 {component}"]
    errors = [f"{component}.{'.'.join(str(p) for p in e.absolute_path) or 'props'}: {e.message}"
              for e in Draft202012Validator(spec["props"]).iter_errors(props)]
    if component == "FlowDiagram" and not errors:
        ids = {n["id"] for n in props["nodes"]}
        for edge in props["edges"]:
            for i in edge:
                if i not in ids:
                    errors.append(f"FlowDiagram.edges: 없는 노드 {i} 를 가리킨다")
        for i in props.get("revealOrder", []):
            if i not in ids:
                errors.append(f"FlowDiagram.revealOrder: 없는 노드 {i}")
    return errors
