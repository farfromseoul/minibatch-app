"""scenes 단계: 문장을 장면으로 묶고 템플릿·속성을 고른다 (앱 설계 "Scene JSON").

LLM 은 장면마다 문장 **번호**만 고르고, 문장은 코드가 번호로 채운다. 2026-10-16 실측: 17문장을 그대로 베끼게 하니
27B 가 글자를 바꾸거나 빠뜨려 3번 모두 실패(208초). 번호로 바꾸면 베끼다 틀릴 일이 없고 응답도 짧다.

검사: 번호가 1부터 빠짐없이 차례대로인가, 장면당 1~4문장, 첫 장면 hook·끝 장면 summary|outro,
카테고리가 허용한 템플릿인가, 템플릿 속성이 규격에 맞나. 2번 다시 요청해도 안 되면 deterministic(retry_from=scenes).
"""
from __future__ import annotations

import json
from typing import Any

from app.core.category import load_category
from app.llm.prompting import render
from app.schemas.templates import LISTICLE_TEMPLATES, TEMPLATES, check_props
from app.text.cta import outro_for
from app.text.sentences import script_sentences

from .base import StepContext, StepFailure
from .llm_common import ask, meta_of

ROLES = ["hook", "explain", "example", "compare", "summary", "outro"]
PRESETS = ["pop", "fade", "sequential", "draw"]
PAD_AFTER_SEC = 0.3
FIX_CHARS = 28  # 자동 교정 때 문장에서 따올 제목·요점 길이


def fix_repeats(scenes: list[dict], sentences: list[str], templates: list[str]) -> tuple[list[dict], list[str]]:
    """같은 템플릿이 세 번 이어지면 가운데 장면을 TitleReveal(또는 SummaryScene)로 바꾼다. 내용(문장·순서)은 그대로.
    2026-10-19 실제: Gemma 12B 가 '3연속 금지' 를 세 번 어겨 작업이 실패했다. 다시 묻는 대신 코드가 고친다"""
    fixed = []
    for i in range(1, len(scenes) - 1):
        comp = scenes[i].get("component")
        if not (scenes[i - 1].get("component") == comp == scenes[i + 1].get("component")):
            continue
        lines = [sentences[n - 1] for n in scenes[i].get("sentences", []) if isinstance(n, int) and 1 <= n <= len(sentences)]
        if not lines:
            continue
        if comp != "TitleReveal" and "TitleReveal" in templates:
            new = {"component": "TitleReveal", "props": {"title": lines[0][:FIX_CHARS]}}
        elif comp != "SummaryScene" and "SummaryScene" in templates:
            new = {"component": "SummaryScene", "props": {"points": [ln[:FIX_CHARS] for ln in lines[:3]]}}
        else:
            continue
        scenes[i] = {**scenes[i], **new}
        fixed.append(f"{i + 1}번 장면 {comp} → {new['component']} (같은 템플릿 3연속)")
    return scenes, fixed


def _schema(templates: list[str]) -> dict:
    scene = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": ROLES},
            "sentences": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 4},
            "component": {"type": "string", "enum": templates},
            "props": {"type": "object"},  # 템플릿마다 모양이 달라 받은 뒤 검사한다(구조화 출력의 oneOf 지원은 미확인)
            "animationPreset": {"type": "string", "enum": PRESETS},
        },
        "required": ["role", "sentences", "component", "props", "animationPreset"],
        "additionalProperties": False,
    }
    return {"type": "object", "properties": {"scenes": {"type": "array", "items": scene, "minItems": 2, "maxItems": 10}},
            "required": ["scenes"], "additionalProperties": False}


class ScenesStep:
    name = "scenes"
    inputs = ["script.json"]
    outputs = ["scenes.json"]

    def run(self, ctx: StepContext) -> None:
        script = ctx.read_json("script.json")
        job = ctx.read_json("job.json")
        cat = load_category(ctx.settings, job["category"])
        if job.get("format") == "listicle":  # 목록형 쇼츠 (D42): 틀은 코드, 항목 그림만 LLM
            from .listicle import run_scenes
            run_scenes(ctx, script, job, cat)
            return
        templates = [t for t in (cat.get("templates") or [t for t in TEMPLATES if t not in LISTICLE_TEMPLATES]) if t in TEMPLATES]
        if not templates:
            raise StepFailure("deterministic", "카테고리에 쓸 수 있는 템플릿이 없다")
        sentences = script_sentences(script)
        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, start=1))
        spec = "\n".join(f"- {t}: {TEMPLATES[t]['use']}. props 형식: {json.dumps(TEMPLATES[t]['props']['properties'], ensure_ascii=False)}"
                         for t in templates)
        prompt, version = render("scenes", numbered=numbered, templates=spec)

        auto_fixed: list[str] = []

        def adjust(data: Any) -> Any:
            if isinstance(data, dict) and isinstance(data.get("scenes"), list):
                data = dict(data, scenes=[dict(sc) for sc in data["scenes"] if isinstance(sc, dict)])
                data["scenes"], fixed = fix_repeats(data["scenes"], sentences, templates)
                auto_fixed[:] = fixed  # 시도마다 새로
            return data

        def check(data: Any) -> list[str]:
            scenes = data.get("scenes") if isinstance(data, dict) else None
            if not isinstance(scenes, list) or len(scenes) < 2:
                return ["scenes 배열(2개 이상)이 필요하다"]
            problems = []
            flat = [n for sc in scenes for n in sc.get("sentences", [])]
            if flat != list(range(1, len(sentences) + 1)):
                problems.append(f"sentences 번호는 1부터 {len(sentences)}까지 빠짐없이 차례대로 장면에 나눠 담는다 (지금: {flat})")
            for i, sc in enumerate(scenes, start=1):
                if not 1 <= len(sc.get("sentences", [])) <= 4:
                    problems.append(f"{i}번 장면: sentences 는 1~4개")
                if sc.get("component") not in templates:
                    problems.append(f"{i}번 장면: 쓸 수 없는 템플릿 {sc.get('component')} (가능: {', '.join(templates)})")
                else:
                    problems += [f"{i}번 장면 {p}" for p in check_props(sc["component"], sc.get("props"))]
            comps = [sc.get("component") for sc in scenes]
            for i in range(len(comps) - 2):  # 같은 화면이 계속되면 지루하다 (2026-10-16 실측: FlowDiagram 3연속)
                if comps[i] == comps[i + 1] == comps[i + 2]:
                    problems.append(f"{i + 1}~{i + 3}번 장면이 모두 {comps[i]}다. 같은 템플릿을 세 번 연달아 쓰지 않는다")
                    break
            if scenes[0].get("role") != "hook":
                problems.append("첫 장면 role 은 hook")
            if scenes[-1].get("role") not in ("summary", "outro"):
                problems.append("마지막 장면 role 은 summary 또는 outro")
            return problems

        out = ask(ctx, [{"role": "user", "content": prompt}], _schema(templates), "scenes", check, adjust=adjust)
        if out.problems:
            raise StepFailure("deterministic", "장면 구성 규칙을 지키지 못했다: " + "; ".join(out.problems)[:800], retry_from="scenes")
        scenes = [{"role": sc["role"], "lines": [sentences[n - 1] for n in sc["sentences"]],
                   "visual": {"type": "template", "component": sc["component"], "props": sc["props"]},
                   "animationPreset": sc["animationPreset"], "padAfterSec": PAD_AFTER_SEC}
                  for sc in out.data["scenes"]]
        outro = outro_for(cat, job.get("series"))
        if outro:  # 시리즈 끝 장면은 코드가 붙인다. 문구는 카테고리 파일 (D26)
            scenes.append({"role": "outro", "lines": [outro["line"]],
                           "visual": {"type": "template", "component": "TitleReveal",
                                      "props": {"title": outro["title"], "subtitle": outro["subtitle"]}},
                           "animationPreset": "pop", "padAfterSec": 0.5})
        ctx.write_json("scenes.json", {
            "schemaVersion": 1,
            "jobId": job["jobId"],
            "title": script["titleCandidates"][0],
            "readings": script.get("readings") or {},  # 영어 단어의 한글 읽기 → tts (2026-10-31)
            "scenes": [{"id": f"s{i:02d}", **sc} for i, sc in enumerate(scenes, start=1)],
            "meta": meta_of(out, version, **({"autoFixed": auto_fixed} if auto_fixed else {})),
        })
