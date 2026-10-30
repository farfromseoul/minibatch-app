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


def _obj(required: list[str], **props: Any) -> dict[str, Any]:
    return {"type": "object", "required": required, "properties": props, "additionalProperties": False}


def _strs(lo: int, hi: int) -> dict[str, Any]:
    return {"type": "array", "minItems": lo, "maxItems": hi, "items": _STR}


ICONS = ["search", "memory", "shield", "bolt", "clock", "code", "chat", "check", "warning", "lock", "globe", "terminal",
         "chart", "sparkles", "book", "gear"]  # render/src/listicle/icons.tsx 와 같다

# 목록형 쇼츠 (D42). render/src/lib/timeline.ts 의 목록형 검사와 같은 규칙. 틀(첫마디·소개·정리·끝)은 코드가 만들고,
# 항목 설명 그림(DETAIL_VISUALS)만 LLM 이 고른다
LISTICLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "LHookClaim": {"use": "첫마디: 수많은 카드 위에 큰 숫자 말풍선",
                   "props": _obj(["kicker", "claim"], kicker=_STR, claim=_STR, claimNote=_STR, aside=_STR)},
    "LHookReveal": {"use": "첫마디: 제목 + 번호 카드 N장",
                    "props": _obj(["kicker", "headline", "count"], kicker=_STR, headline=_STR, highlight=_STR,
                                  count={"type": "integer", "minimum": 2, "maximum": 7})},
    "LItemCard": {"use": "항목 소개 카드",
                  "props": _obj(["number", "name"], number={"type": "integer", "minimum": 1}, name=_STR, meta=_STR,
                                tagline=_STR, badge=_STR)},
    "LChat": {"use": "말로 시키면 알아서 해 주는 도구. 입력창에 요청을 치면 결과 1~4개가 뜨고 첫 결과가 골라진다",
              "props": _obj(["prompt", "results"], prompt=_STR, results=_strs(1, 4), status=_STR)},
    "LSteps": {"use": "순서·절차가 있는 것. 단계 칩 2~4개가 차례로 켜지고 확인 목록이 체크된다",
               "props": _obj(["steps"], steps=_strs(2, 4), checks=_strs(0, 4))},
    "LBeforeAfter": {"use": "쓰기 전과 후가 달라지는 것(정리·디자인·품질). 요란한 화면 → 정돈된 화면",
                     "props": _obj(["before", "after"], **{k: _obj(["label"], label=_STR, note=_STR) for k in ("before", "after")})},
    "LTerminal": {"use": "명령어·설치·설정 파일이 핵심인 것. 터미널에 명령을 치고 출력 1~4줄",
                  "props": _obj(["command", "output"], command=_STR, output=_strs(1, 4))},
    "LStat": {"use": "숫자 하나가 핵심일 때(참고 자료에 있는 숫자만). 큰 숫자 + 설명",
              "props": _obj(["value", "label"], value=_STR, unit=_STR, label=_STR)},
    "LIcon": {"use": "개념 하나를 상징으로 보여 줄 때(기억, 보안, 속도 등). 큰 아이콘 + 제목 + 짧은 꼬리표 0~3개",
              "props": _obj(["icon", "title"], icon={"type": "string", "enum": ICONS}, title=_STR, lines=_strs(0, 3))},
    "LCompare": {"use": "둘을 비교해 하나가 낫다고 할 때. 카드 두 장, 요점 1~3개씩",
                 "props": _obj(["left", "right"], **{k: _obj(["title", "points"], title=_STR, points=_strs(1, 3)) for k in ("left", "right")},
                               winner={"type": "string", "enum": ["left", "right"]})},
    "LRecap": {"use": "정리: 노란 바탕 목록",
               "props": _obj(["title", "items"], title=_STR, subtitle=_STR,
                             items={"type": "array", "minItems": 1, "maxItems": 7,
                                    "items": _obj(["name"], name=_STR, note=_STR, tag=_STR)})},
    "LOutro": {"use": "끝 카드", "props": _obj(["title"], title=_STR, subtitle=_STR)},
}
DETAIL_VISUALS = ["LChat", "LSteps", "LBeforeAfter", "LTerminal", "LStat", "LIcon", "LCompare"]
TEMPLATES.update(LISTICLE_TEMPLATES)


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
