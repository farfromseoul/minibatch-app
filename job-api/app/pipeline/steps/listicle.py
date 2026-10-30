"""목록형 쇼츠 (아키텍처 D42, 목록형쇼츠 아키텍처). script·scenes·timeline 단계가 format=listicle 일 때 부른다.

- 대본: LLM 이 첫마디·항목·정리를 쓰고, 문장마다 강조할 말을 [ ] 로 감싼다. 코드가 괄호를 떼어 text·emphasis 로 나누고,
  검토·설명란이 읽는 호환 필드(hook·body·summary)를 말하는 순서대로 펼쳐 둔다.
- 장면: 틀(첫마디 두 장면, 항목 소개 카드, 정리, 끝)은 코드가 만들고, 항목 설명 그림만 LLM 이 고른다.
  그림을 끝내 못 고르면 아이콘 장면으로 대신하고 영상은 계속 만든다(degraded).
- 자막: 문장 WAV 의 쉼에 맞춰 구절·단어 시각을 정한다(app/media/align.py).
"""
from __future__ import annotations

import json
import re
import zlib
from typing import Any

from app.llm.prompting import render_messages
from app.media.align import align, analyze, read_pcm16
from app.schemas.templates import DETAIL_VISUALS, TEMPLATES, check_props
from app.text.sentences import count_chars, repeated_sentences

from .base import StepContext, StepFailure
from .llm_common import ask, meta_of

LENGTH_TAG = "글자 수"
TOLERANCE = 0.15       # 목록형은 문장을 빼서 맞추지 않는다(항목 구조). 넉넉히 두고 timeline 이 실제 길이로 다시 판정
MIN_CHARS = 6
FIRST_MIN = 12         # 항목 첫 문장(이름 + 한 줄 소개). '첫째는 pdf예요'(8자)는 카드가 1.6초만 보였다
# 목록형 쉼 (2026-10-31: 장면이 2~4초마다 바뀌고 문장 사이 무음이 1.3초라 빠르고 끊긴다는 피드백).
# 문장 앞뒤 무음은 잘라 내고(timeline_calc spans) 이 쉼만 둔다
PACING = {"lead": 0.15, "gap": 0.3, "tail": 0.12, "hold": 0.6}
PAD_SEC = 0.4          # 장면 뒤 쉼
ITEM_LINES = 3         # 항목 문장: 이름과 한 줄 소개 + 설명 둘
BRACKET = re.compile(r"\[([^\[\]]+)\]")
ENDING = re.compile(r"(요|죠|다|까|네|세요)[.?!~]*$")  # 끝맺는 말끝 (2026-10-31: 조각 문장을 따로 합성하면 끊겨 들린다)
ORDINALS = ["첫", "두", "세", "네", "다섯", "여섯", "일곱"]


# ---------- 길이

def target_chars(target_sec: float, cps: float, n: int, outro_chars: int = 0) -> int:
    """대본(첫마디·항목·정리) 글자 수 목표. cps 는 무음을 뺀 말 구간의 초당 글자(카테고리 tts.speech_chars_per_sec).
    장면(첫마디 2 + 항목마다 2 + 정리 + 끝)과 문장 사이 쉼만큼 시간을 뺀다"""
    extra = 1 if outro_chars else 0
    scenes = 2 + 2 * n + 1 + extra
    sentences = 3 + ITEM_LINES * n + 2 + extra
    overhead = (scenes * (PACING["lead"] + PAD_SEC) + max(0, sentences - scenes) * PACING["gap"]
                + sentences * PACING["tail"])
    outro_sec = outro_chars / cps if outro_chars else 0.0
    return max(60, round((target_sec - overhead - outro_sec) * cps))


# ---------- 문장 [강조]

def split_emphasis(line: str) -> tuple[str, str, list[str]]:
    """'[일을] 말하면' → ('일을 말하면', '일을', 문제). 괄호는 하나만"""
    found = BRACKET.findall(line)
    text = " ".join(BRACKET.sub(lambda m: m.group(1), line).split())
    problems = []
    if len(found) != 1:
        problems.append(f"강조할 말을 [ ] 로 하나만 감싼다 (지금 {len(found)}개): {line}")
    if "[" in text or "]" in text:
        problems.append(f"괄호 짝이 맞지 않다: {line}")
    return text, (found[0].strip() if found else ""), problems


def _flat_lines(data: dict[str, Any]) -> list[str]:
    """말하는 순서의 원문(괄호 포함): 첫마디 → 항목 → 정리"""
    out = list(data.get("hook") or [])
    for it in data.get("items") or []:
        out.extend(it.get("lines") or [])
    out.extend((data.get("recap") or {}).get("lines") or [])
    return [str(x) for x in out]


def _schema(n: int) -> dict[str, Any]:
    s = {"type": "string"}
    item = {"type": "object", "properties": {"name": s, "meta": s, "tagline": s, "badge": s,
                                             "lines": {"type": "array", "items": s, "minItems": ITEM_LINES, "maxItems": ITEM_LINES}},
            "required": ["name", "meta", "tagline", "badge", "lines"], "additionalProperties": False}
    card = {"type": "object", "properties": {k: s for k in ("kicker", "claim", "claimNote", "aside", "headline", "highlight")},
            "required": ["kicker", "claim", "claimNote", "aside", "headline", "highlight"], "additionalProperties": False}
    recap = {"type": "object", "properties": {"title": s, "subtitle": s, "lines": {"type": "array", "items": s, "minItems": 1, "maxItems": 2}},
             "required": ["title", "subtitle", "lines"], "additionalProperties": False}
    return {"type": "object", "properties": {
        "hook": {"type": "array", "items": s, "minItems": 2, "maxItems": 3}, "hookCard": card,
        "items": {"type": "array", "items": item, "minItems": n, "maxItems": n}, "recap": recap,
        "titleCandidates": {"type": "array", "items": s, "minItems": 3, "maxItems": 3},
        "hashtags": {"type": "array", "items": s, "minItems": 1, "maxItems": 5}},
        "required": ["hook", "hookCard", "items", "recap", "titleCandidates", "hashtags"], "additionalProperties": False}


def _core(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text).lower()


def check_script(data: Any, *, n: int, given: list[str], max_sentence: int, target: int, has_facts: bool,
                 source: str = "") -> list[str]:
    if not isinstance(data, dict):
        return ["JSON 객체가 필요하다"]
    items = data.get("items") or []
    problems: list[str] = []
    if len(items) != n:
        problems.append(f"items 는 정확히 {n}개 (지금 {len(items)}개)")
    for i, (it, want) in enumerate(zip(items, given), start=1):
        if _core(want) not in _core(str(it.get("name", ""))):
            problems.append(f"{i}번 항목 이름은 운영자가 준 '{want}' 여야 한다 (지금 '{it.get('name')}')")
    for i, it in enumerate(items, start=1):
        lines = it.get("lines") or []
        name = str(it.get("name", ""))
        if lines and _core(name)[:6] not in _core(lines[0]):
            problems.append(f"{i}번 항목 첫 문장에 이름 '{name}' 을 부른다: {lines[0]}")
        if lines and count_chars(split_emphasis(lines[0])[0]) < FIRST_MIN:
            problems.append(f"{i}번 항목 첫 문장은 이름과 한 줄 소개를 함께 {FIRST_MIN}자 이상으로 (예: '첫 번째, 문서 작업을 도와주는 docx예요'): {lines[0]}")
        if count_chars(name) > 20:
            problems.append(f"{i}번 항목 name 은 20자 이내: {name}")
    card = data.get("hookCard") or {}
    if count_chars(str(card.get("claim", ""))) > 8:
        problems.append(f"hookCard.claim 은 8자 이내: {card.get('claim')}")
    if card.get("highlight") and card["highlight"] not in str(card.get("headline", "")):
        problems.append("hookCard.highlight 는 headline 안의 글자여야 한다")
    if not has_facts and re.search(r"\d", str(card.get("claim", ""))):
        problems.append("참고 자료가 없으면 claim 에 구체적인 숫자를 쓰지 않는다 ('수백 가지', '끝없이' 같은 말로)")
    texts = []
    for line in _flat_lines(data):
        text, _, p = split_emphasis(line)
        problems += p
        texts.append(text)
        c = count_chars(text)
        if c > max_sentence:
            problems.append(f"{c}자다. {max_sentence}자 이내로 줄이거나 나눈다: {text}")
        elif c < MIN_CHARS:
            problems.append(f"{c}자로 너무 짧다({MIN_CHARS}자 이상): {text}")
        if text and not ENDING.search(text):
            problems.append(f"끝맺지 않은 조각 문장이다. 문장마다 따로 읽으므로 ~요·~죠·~다·~까? 로 끝맺는다: {text}")
        if source and _copied(text, source):
            problems.append(f"참고 자료 표현을 그대로 옮겼다. 우리 말로 바꿔 쓴다: {text}")
    for a, b in repeated_sentences(texts):
        problems.append(f"{b + 1}번째 문장이 {a + 1}번째를 되풀이한다: {texts[b]}")
    total = sum(count_chars(t) for t in texts)
    if texts and abs(total - target) > target * TOLERANCE:
        how = "설명 문장을 조금 더 구체적으로 늘려" if total < target else "설명 문장을 줄여"
        problems.append(f"{LENGTH_TAG}가 {total}자로 목표 {target}자에서 벗어났다. {how} 쓴다")
    return problems


COPY_RUN = 15


def _copied(sentence: str, bare_source: str) -> bool:
    b = _core(sentence)
    return len(b) >= COPY_RUN and any(b[i:i + COPY_RUN] in bare_source for i in range(len(b) - COPY_RUN + 1))


def _pack(data: dict[str, Any]) -> dict[str, Any]:
    """괄호를 떼어 {text, emphasis} 로, 호환 필드(hook·body·summary)를 말하는 순서대로"""
    def lines(xs):
        out = []
        for x in xs:
            text, emph, _ = split_emphasis(str(x))
            out.append({"text": text, "emphasis": emph})
        return out
    hook = lines(data["hook"])
    items = [{"name": str(it["name"]).strip(), "meta": str(it.get("meta") or "").strip(), "tagline": str(it.get("tagline") or "").strip(),
              "badge": str(it.get("badge") or "").strip(), "lines": lines(it["lines"])} for it in data["items"]]
    recap = {"title": str(data["recap"]["title"]).strip(), "subtitle": str(data["recap"].get("subtitle") or "").strip(),
             "lines": lines(data["recap"]["lines"])}
    spoken = [x["text"] for x in hook] + [x["text"] for it in items for x in it["lines"]] + [x["text"] for x in recap["lines"]]
    card = {k: str(v).strip() for k, v in data["hookCard"].items()}
    return {"listicle": {"hook": hook, "hookCard": card, "items": items, "recap": recap},
            "hook": spoken[0], "body": spoken[1:-1], "summary": spoken[-1],
            "titleCandidates": data["titleCandidates"], "hashtags": data["hashtags"]}


def run_script(ctx: StepContext, job: dict[str, Any], cat: dict[str, Any], review_feedback: str) -> None:
    lst = job.get("listicle") or {}
    given = [str(x) for x in lst.get("items") or []]
    n = len(given) or int(lst.get("count") or (cat.get("listicle") or {}).get("count", {}).get("default", 5))
    rules = cat.get("script", {})
    max_sentence = int(rules.get("max_sentence_chars", 28))
    cps = float((cat.get("tts") or {}).get("speech_chars_per_sec") or ctx.providers.chars_per_sec)
    outro = outro_for(cat, job["jobId"])
    target = target_chars(job["targetDurationSec"], cps, n, count_chars(outro["line"]) if outro else 0)
    facts = lst.get("facts") or []
    facts_block = ("참고 자료에서 확인한 사실(항목 이름·숫자·저장소는 이 목록 안에서만 쓴다. 문장을 그대로 옮기지 않는다):\n"
                   + "\n".join(f"- {f}" for f in facts) + "\n") if facts else ""
    given_items = ("운영자가 정한 항목(이 순서·이 이름으로 쓴다):\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(given, start=1))
                   + "\n") if given else ""
    number_rule = ("참고 자료 사실 목록에 있는 숫자만 쓴다" if facts else
                   "참고 자료가 없으니 별 수·다운로드 수·가격·버전 같은 구체적인 숫자를 쓰지 않는다(항목 수 N 은 된다)")
    messages, version = render_messages(
        "listicle_script", topic=job["topic"], count=n, target_sec=job["targetDurationSec"], audience=cat.get("audience", ""),
        structure=rules.get("structure", ""), forbidden=", ".join(rules.get("forbidden", [])), max_sentence=max_sentence,
        min_chars=MIN_CHARS, target_chars=target, item_chars=round(target * 0.75 / n), given_items=given_items,
        facts_block=facts_block, number_rule=number_rule, review_feedback=review_feedback)
    source = _core(ctx.path("listicle_sources.txt").read_text(encoding="utf-8")) if ctx.path("listicle_sources.txt").exists() else ""

    def check(d: Any) -> list[str]:
        return check_script(d, n=n, given=given, max_sentence=max_sentence, target=target, has_facts=bool(facts), source=source)

    out = ask(ctx, messages, _schema(n), "listicle_script", check)
    hard = [p for p in out.problems if not p.startswith(LENGTH_TAG)]
    if hard:
        raise StepFailure("deterministic", "목록형 대본 규칙을 지키지 못했다: " + "; ".join(hard)[:800], retry_from="script")
    if out.problems:
        ctx.note_degraded("; ".join(out.problems))
    data = _pack(out.data)
    chars = sum(count_chars(t) for t in [data["hook"], *data["body"], data["summary"]])
    data["meta"] = meta_of(out, version, targetChars=target, charCount=chars, format="listicle")
    ctx.write_json("script.json", data)


# ---------- 장면

def outro_for(cat: dict[str, Any], job_id: str) -> dict[str, str] | None:
    """카테고리 listicle.outro 중 하나 (작업 ID 로 돌려 쓴다). 없으면 None"""
    opts = [o for o in (cat.get("listicle") or {}).get("outro") or [] if isinstance(o, dict) and o.get("line")]
    if not opts:
        return None
    o = opts[zlib.crc32(job_id.encode()) % len(opts)]
    return {"line": str(o["line"]), "title": str(o.get("title") or o["line"]), "subtitle": str(o.get("subtitle") or "")}


def _visual_count(item: dict[str, Any]) -> int:
    """항목마다 설명 그림 한 장(설명 문장 둘을 함께 맡아 5~7초 머문다, 2026-10-31)"""
    return 1


def _fallback(item: dict[str, Any]) -> dict[str, Any]:
    return {"component": "LIcon", "props": {"icon": "sparkles", "title": (item["tagline"] or item["name"])[:16]}}


def _visual_schema(n: int) -> dict[str, Any]:
    vis = {"type": "object", "properties": {"component": {"type": "string", "enum": DETAIL_VISUALS}, "props": {"type": "object"}},
           "required": ["component", "props"], "additionalProperties": False}
    item = {"type": "object", "properties": {"visuals": {"type": "array", "items": vis, "minItems": 1, "maxItems": 2}},
            "required": ["visuals"], "additionalProperties": False}
    return {"type": "object", "properties": {"items": {"type": "array", "items": item, "minItems": n, "maxItems": n}},
            "required": ["items"], "additionalProperties": False}


def check_visuals(data: Any, items: list[dict[str, Any]]) -> list[str]:
    got = data.get("items") if isinstance(data, dict) else None
    if not isinstance(got, list) or len(got) != len(items):
        return [f"items 는 항목 순서대로 {len(items)}개"]
    problems, used = [], {}
    for i, (g, it) in enumerate(zip(got, items), start=1):
        vs = g.get("visuals") if isinstance(g, dict) else None
        want = _visual_count(it)
        if not isinstance(vs, list) or len(vs) != want:
            problems.append(f"{i}번 항목 visuals 는 {want}장")
            continue
        for v in vs:
            comp = v.get("component") if isinstance(v, dict) else None
            if comp not in DETAIL_VISUALS:
                problems.append(f"{i}번 항목: 쓸 수 없는 그림 {comp}")
                continue
            used[comp] = used.get(comp, 0) + 1
            problems += [f"{i}번 항목 {p}" for p in check_props(comp, v.get("props"))]
    for comp, k in used.items():
        if k > 2:
            problems.append(f"{comp} 를 {k}번 썼다. 같은 그림은 두 번까지")
    return problems


def run_scenes(ctx: StepContext, script: dict[str, Any], job: dict[str, Any], cat: dict[str, Any]) -> None:
    lst = script["listicle"]
    items = lst["items"]
    catalog = "\n".join(f"- {c}: {TEMPLATES[c]['use']}. props: {json.dumps(TEMPLATES[c]['props']['properties'], ensure_ascii=False)}"
                        for c in DETAIL_VISUALS)
    listing = "\n".join(f"{i}. {it['name']} ({it['tagline']}) — 설명: {' / '.join(x['text'] for x in it['lines'][1:])}"
                        f" — 그림 {_visual_count(it)}장" for i, it in enumerate(items, start=1))
    facts = (job.get("listicle") or {}).get("facts") or []
    if facts:
        listing += "\n\n사실 목록(숫자는 여기 것만):\n" + "\n".join(f"- {f}" for f in facts)
    messages, version = render_messages("listicle_visuals", topic=job["topic"], catalog=catalog, items=listing, count=len(items),
                                        visual_rule="1")
    picks: list[list[dict[str, Any]]] = [[_fallback(it)] * _visual_count(it) for it in items]
    meta: dict[str, Any] = {"promptVersion": version}
    try:
        out = ask(ctx, messages, _visual_schema(len(items)), "listicle_visuals", lambda d: check_visuals(d, items))
        meta = meta_of(out, version)
        got = out.data.get("items") if isinstance(out.data, dict) else None
        if isinstance(got, list):
            for i, (g, it) in enumerate(zip(got, items)):
                vs = [v for v in (g.get("visuals") or []) if isinstance(v, dict) and v.get("component") in DETAIL_VISUALS
                      and not check_props(v["component"], v.get("props"))][:_visual_count(it)]
                if len(vs) == _visual_count(it):
                    picks[i] = [{"component": v["component"], "props": v["props"]} for v in vs]
                else:
                    ctx.note_degraded(f"{i + 1}번 항목 그림을 고르지 못해 아이콘 장면으로")
        if out.problems:
            meta["problems"] = out.problems[:10]
    except StepFailure as e:
        if e.kind != "transient":
            raise
        ctx.note_degraded(f"그림 고르기 실패({e.message[:120]}), 모두 아이콘 장면으로")
    scenes = build_scenes(lst, picks, outro_for(cat, job["jobId"]))
    ctx.write_json("scenes.json", {
        "schemaVersion": 1, "jobId": job["jobId"], "title": script["titleCandidates"][0],
        "tracker": {"items": [{"name": it["name"], **({"meta": it["meta"]} if it["meta"] else {})} for it in items]},
        "scenes": [{"id": f"s{i:02d}", **sc} for i, sc in enumerate(scenes, start=1)],
        "meta": meta,
    })


def _scene(kind: str, component: str, props: dict[str, Any], lines: list[dict[str, str]], index: int | None = None,
           pad: float = PAD_SEC) -> dict[str, Any]:
    return {"role": kind, "section": {"kind": kind, **({"index": index} if index else {})},
            "lines": [x["text"] for x in lines], "emphasis": [x["emphasis"] for x in lines],
            "visual": {"type": "template", "component": component, "props": props}, "animationPreset": "pop", "padAfterSec": pad}


def _split(lines: list[dict[str, str]], k: int) -> list[list[dict[str, str]]]:
    if k <= 1 or len(lines) < 2:
        return [lines]
    cut = (len(lines) + 1) // 2
    return [lines[:cut], lines[cut:]]


def build_scenes(lst: dict[str, Any], picks: list[list[dict[str, Any]]], outro: dict[str, str] | None) -> list[dict[str, Any]]:
    """틀은 코드가: 첫마디(말풍선 → 번호 카드) → 항목마다 소개 카드 + 그림 → 정리 → 끝"""
    items, card, hook = lst["items"], lst["hookCard"], lst["hook"]
    n = len(items)
    out = [_scene("hook", "LHookClaim", {"kicker": card["kicker"], "claim": card["claim"],
                                         **{k: card[k] for k in ("claimNote", "aside") if card.get(k)}}, hook[:1])]
    out.append(_scene("hook", "LHookReveal", {"kicker": card["kicker"], "headline": card["headline"], "count": n,
                                              **({"highlight": card["highlight"]} if card.get("highlight") and card["highlight"] in card["headline"] else {})},
                      hook[1:]))
    for i, (it, vs) in enumerate(zip(items, picks), start=1):
        out.append(_scene("item", "LItemCard", {"number": i, "name": it["name"],
                                                **{k: it[k] for k in ("meta", "tagline", "badge") if it.get(k)}}, it["lines"][:1], i))
        for v, chunk in zip(vs, _split(it["lines"][1:], len(vs))):
            out.append(_scene("item", v["component"], v["props"], chunk, i))
    out.append(_scene("recap", "LRecap", {"title": lst["recap"]["title"],
                                          **({"subtitle": lst["recap"]["subtitle"]} if lst["recap"].get("subtitle") else {}),
                                          "items": [{"name": it["name"], **({"note": it["tagline"]} if it["tagline"] else {}),
                                                     **({"tag": it["badge"]} if it["badge"] else {})} for it in items]},
                      lst["recap"]["lines"], pad=0.5))
    if outro:
        out.append(_scene("outro", "LOutro", {"title": outro["title"], **({"subtitle": outro["subtitle"]} if outro["subtitle"] else {})},
                          [{"text": outro["line"], "emphasis": ""}], pad=0.8))
    return [sc for sc in out if sc["lines"]]  # 문장이 없는 장면(첫마디 1문장 등)은 뺀다


# ---------- 길이 맞추기

MIN_PAUSE_SCALE, MAX_PAUSE_SCALE = 0.7, 2.0
FIT_MARGIN_SEC = 2.0  # 범위 끝에서 이만큼 안쪽을 노린다


def fit_pacing(scenes: dict[str, Any], tts: dict[str, Any], *, target: float, tol: float, fps: int, theme: str,
               phrases, spans, width: int = 1080, height: int = 1920) -> tuple[dict[str, Any], float]:
    """말 길이는 그대로 두고 쉼(앞 여백·문장 사이·장면 뒤)만 0.7~2배로 늘리고 줄여 목표 ± 허용 안에 넣는다.
    2026-10-31 실제: 짧은 한국어 문장은 초당 8.0글자로 읽혀(추정 6.3) 47.7초 → 대본을 세 번 다시 써도 같은 실패.
    범위 안이면 쉼을 그대로(1배) 둔다. 두 배로 늘려도 모자라면 그대로 돌려줘 timeline 단계가 실패시킨다"""
    from app.pipeline.timeline_calc import compute_timeline

    def run(scale: float) -> dict[str, Any]:
        return compute_timeline(scenes, tts, fps=fps, width=width, height=height, theme=theme, phrases=phrases, spans=spans,
                                pacing={**PACING, "scale": scale})
    t = run(1.0)
    d = t["durationInFrames"] / fps
    if target - tol <= d <= target + tol:
        return t, 1.0
    per = run(2.0)["durationInFrames"] / fps - d  # 쉼 배율 1 늘릴 때 늘어나는 초
    goal = target - tol + FIT_MARGIN_SEC if d < target - tol else target + tol - FIT_MARGIN_SEC
    scale = 1.0 + (goal - d) / per if per > 0 else 1.0
    scale = round(min(MAX_PAUSE_SCALE, max(MIN_PAUSE_SCALE, scale)), 3)
    return run(scale), scale


# ---------- 자막

def phrases_for(ctx: StepContext, scenes_doc: dict[str, Any], tts: dict[str, Any]
                ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, tuple[float, float]]]:
    """tts 문장마다 (자막 구절, 말 구간). 실패한 문장은 빼고(그 문장은 통째 자막·무음 그대로) 계속한다"""
    emph = {}
    for sc in scenes_doc["scenes"]:
        for j, e in enumerate(sc.get("emphasis") or [], start=1):
            emph[f"{sc['id']}-{j:02d}"] = e
    from app.core.category import load_category
    from app.text.pronunciation import apply_pronunciation, load_dictionary
    job = ctx.read_json("job.json")
    words = load_dictionary(ctx.settings.content_dir / "pronunciation.yaml", load_category(ctx.settings, job["category"]).get("pronunciation"))

    def speak(w: str) -> str:  # TTS 가 실제로 읽은 말로 길이를 잰다 (tts 단계와 같은 사전)
        return apply_pronunciation(w, words)
    out, spans = {}, {}
    for item in tts["items"]:
        wav = ctx.path(item["path"])
        try:
            out[item["id"]] = align(item["text"], float(item["seconds"]), wav, emph.get(item["id"]), speak=speak)
            samples, rate = read_pcm16(wav)
            begin, end, _ = analyze(samples, rate)
            if end - begin > 0.2:
                spans[item["id"]] = (begin, end)
        except Exception as e:  # 자막 쪼개기 실패가 영상을 막지 않게
            ctx.note_degraded(f"{item['id']} 자막 구절 계산 실패({type(e).__name__}), 문장 단위로")
    return out, spans
