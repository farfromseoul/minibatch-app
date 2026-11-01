"""실습 리뷰 쇼츠 (실습리뷰쇼츠 기획서·아키텍처, 메인 D46, 2026-11-01).

- 계획(topic 단계): 웹 검색을 켠 요청(research)으로 기능을 확인하고 과제 1~3개를 만든다. 사람이 [실험 시작]을 눌러야 lab 단계가 돈다.
- 대본(script 단계): 실험 기록(evidence.json)만 근거로 쓴다. 화면의 실습(LWalkthrough)·결과물(LArtifact)은 기록에서 코드가 만든다.
  대본 모양은 목록형과 같게 맞춰(과제 = 항목) 음성·자막·쉼 맞추기·검토를 목록형 그대로 쓴다.
- 장면(scenes 단계): 첫마디 → 기능 소개 → 과제마다 실습 재생 + 결과물 → 평가(LVerdict) → 끝.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.llm.prompting import render_messages
from app.schemas.templates import check_props
from app.text import readings as rd
from app.text.pronunciation import load_dictionary
from app.text.sentences import count_chars, repeated_sentences

from .base import StepContext, StepFailure
from .listicle import (ENDING, LENGTH_TAG, MIN_CHARS, PAD_SEC, _scene, foreign_problems, outro_for, split_emphasis,
                       step_key)
from .llm_common import ask, meta_of

TOOLS = {"claude": "Claude Code"}  # v1 은 Claude Code 만 (기획서 Q1). codex·gemini 는 같은 틀로 더한다
TASK_IDS = ["t1", "t2", "t3"]
MAX_TASKS = 3
OFFLINE_WORDS = ("http://", "https://", "설치", "install", "pip ", "npm i", "brew ", "curl ", "wget ", "검색", "웹에서")
FAIL_WORDS = ("실패", "못 ", "못했", "못 했", "안 됐", "안됐", "안 돼", "시간 안에", "시간을 넘")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
TOLERANCE = 0.2

_S = {"type": "string"}
PLAN_SCHEMA = {"type": "object", "properties": {
    "feature": {"type": "object", "properties": {"name": _S, "released": _S, "what": _S, "howToUse": _S},
                "required": ["name", "released", "what", "howToUse"], "additionalProperties": False},
    "facts": {"type": "array", "items": _S, "minItems": 3, "maxItems": 15},
    "sources": {"type": "array", "minItems": 1, "maxItems": 8, "items": {
        "type": "object", "properties": {"title": _S, "url": _S}, "required": ["title", "url"], "additionalProperties": False}},
    "tasks": {"type": "array", "minItems": 1, "maxItems": MAX_TASKS, "items": {
        "type": "object", "properties": {
            "id": {"type": "string", "enum": TASK_IDS}, "goal": _S, "prompt": _S, "why": _S,
            "check": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["fileExists", "contains", "none"]},
                                                       "file": _S, "text": _S},
                      "required": ["kind", "file", "text"], "additionalProperties": False},
            "timeoutSec": {"type": "integer", "minimum": 60, "maximum": 600}},
        "required": ["id", "goal", "prompt", "why", "check", "timeoutSec"], "additionalProperties": False}}},
    "required": ["feature", "facts", "sources", "tasks"], "additionalProperties": False}


def check_plan(d: Any) -> list[str]:
    if not isinstance(d, dict):
        return ["JSON 객체가 필요하다"]
    out = []
    tasks = d.get("tasks") or []
    if [t.get("id") for t in tasks] != TASK_IDS[:len(tasks)]:
        out.append("tasks 의 id 는 t1, t2, t3 차례로")
    for t in tasks:
        p = str(t.get("prompt", ""))
        if not 10 <= len(p) <= 400:
            out.append(f"{t.get('id')} prompt 는 10~400자")
        low = p.lower()
        if any(w in low for w in OFFLINE_WORDS):
            out.append(f"{t.get('id')} prompt 는 인터넷·설치 없이 작업 폴더 안에서 끝나는 일만: {p[:60]}")
        if count_chars(str(t.get("goal", ""))) > 20:
            out.append(f"{t.get('id')} goal 은 20자 이내")
        c = t.get("check") or {}
        if c.get("kind") in ("fileExists", "contains") and not str(c.get("file", "")).strip():
            out.append(f"{t.get('id')} check.file 이 필요하다")
    if not any(str(x.get("url", "")).startswith(("http://", "https://")) for x in d.get("sources") or [] if isinstance(x, dict)):
        out.append("sources 에 실제로 본 http 주소를 1개 이상")
    out += foreign_problems(d)
    return out


def make_plan(ctx: StepContext, topic: str, req: dict[str, Any], cat: dict[str, Any]) -> dict[str, Any]:
    tool = str(req.get("tool") or "claude")
    rv = cat.get("review_video") or {}
    messages, version = render_messages("handson_plan", topic=topic, tool=TOOLS.get(tool, tool), max_tasks=int(rv.get("max_tasks", MAX_TASKS)),
                                        task_timeout=int(rv.get("task_timeout_sec", 600)))
    out = ask(ctx, messages, PLAN_SCHEMA, "research", check_plan)  # 이름이 research 라 중계기가 웹 검색을 켠다 (D45)
    if out.problems:
        raise StepFailure("deterministic", "실험 계획 규칙을 지키지 못했다: " + "; ".join(out.problems)[:600], retry_from="topic")
    model = (out.result.model if out.result else "") or ""
    if model.startswith("fallback:"):
        ctx.note_degraded(f"실험 계획을 검색 없는 대체 모델({model})이 만들었다. 계획을 꼭 확인")
    d = out.data
    tasks = []
    for t in d["tasks"][:int(rv.get("max_tasks", MAX_TASKS))]:
        c = t["check"]
        check = ({"fileExists": c["file"]} if c["kind"] == "fileExists" else
                 {"contains": {"file": c["file"], "text": c["text"]}} if c["kind"] == "contains" else {})
        tasks.append({"id": t["id"], "goal": t["goal"].strip(), "prompt": t["prompt"].strip(), "why": t["why"].strip(), "check": check,
                      "timeoutSec": min(int(t["timeoutSec"]), int(rv.get("task_timeout_sec", 600)))})
    return {"feature": {k: str(v).strip() for k, v in d["feature"].items()}, "tool": tool, "toolLabel": TOOLS.get(tool, tool),
            "facts": [str(f) for f in d["facts"]], "sources": [{"title": str(x["title"]), "url": str(x["url"])} for x in d["sources"]
                                                              if str(x["url"]).startswith(("http://", "https://"))],
            "tasks": tasks, "planMeta": meta_of(out, version)}


def plan_text(job_id: str, topic: str, rv: dict[str, Any]) -> str:
    """텔레그램 계획 메시지 (승인 전에 무엇이 실행되는지 그대로 보인다)"""
    f = rv.get("feature") or {}
    lines = [f"🧪 실험 계획: {topic} ({job_id})", f"도구: {rv.get('toolLabel')}  ·  기능: {f.get('name', '')} ({f.get('released', '')})",
             f"무엇: {f.get('what', '')}", ""]
    for t in rv.get("tasks") or []:
        c = t.get("check") or {}
        cond = (f"{c['fileExists']} 파일이 생기면 성공" if c.get("fileExists") else
                f"{c['contains']['file']} 에 '{c['contains']['text']}' 가 있으면 성공" if c.get("contains") else "오류 없이 끝나면 성공")
        lines += [f"[{t['id']}] {t['goal']} (최대 {t['timeoutSec']}초)", f"  시킬 말: {t['prompt']}", f"  판정: {cond}"]
    lines += ["", "실험 컨테이너: 인터넷·DNS 차단(Anthropic API 만), 작업 폴더 하나만, 웹 검색·웹 읽기 도구 끔",
              "출처: " + ", ".join(x["url"] for x in (rv.get("sources") or [])[:3])]
    return "\n".join(lines)


# ---------- 대본

def _num_text(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, ensure_ascii=False)


def demo_for(task: dict[str, Any], tool_label: str) -> dict[str, Any]:
    """기록으로 만든 실습 재생: 시킨 말(채팅 입력) → 에이전트가 실제로 한 일(앞 3개)"""
    acts = [s["input"][:40] for s in task.get("steps") or [] if s.get("kind") in ("file", "command", "skill")][:3]
    if not acts:
        acts = [("✓ 완료" if task.get("ok") else "✗ 실패")]
    return {"kind": "chat", "title": tool_label, "steps": [{"input": task["prompt"][:60], "output": acts}]}


def _schema(n: int) -> dict[str, Any]:
    s = {"type": "string"}
    lines = lambda lo, hi: {"type": "array", "items": s, "minItems": lo, "maxItems": hi}  # noqa: E731
    return {"type": "object", "properties": {
        "hook": lines(2, 3),
        "hookCard": {"type": "object", "properties": {k: s for k in ("kicker", "claim", "headline", "highlight")},
                     "required": ["kicker", "claim", "headline", "highlight"], "additionalProperties": False},
        "intro": {"type": "object", "properties": {"tagline": s, "lines": lines(1, 1)}, "required": ["tagline", "lines"],
                  "additionalProperties": False},
        "tasks": {"type": "array", "minItems": n, "maxItems": n, "items": {
            "type": "object", "properties": {"lines": lines(2, 3)}, "required": ["lines"], "additionalProperties": False}},
        "verdict": {"type": "object", "properties": {"pros": lines(2, 2), "cons": lines(1, 1), "forWhom": s, "lines": lines(2, 2)},
                    "required": ["pros", "cons", "forWhom", "lines"], "additionalProperties": False},
        "titleCandidates": lines(3, 3), "hashtags": lines(1, 5), "readings": rd.SCHEMA},
        "required": ["hook", "hookCard", "intro", "tasks", "verdict", "titleCandidates", "hashtags", "readings"],
        "additionalProperties": False}


def spoken_lines(d: dict[str, Any]) -> list[str]:
    obj = lambda x: x if isinstance(x, dict) else {}  # noqa: E731 (모양이 틀린 답도 검사가 문제로 돌려준다)
    out = list(d.get("hook") or []) + list(obj(d.get("intro")).get("lines") or [])
    for t in d.get("tasks") or []:
        out += list(obj(t).get("lines") or [])
    return out + list(obj(d.get("verdict")).get("lines") or [])


def check_script(d: Any, *, evidence: dict[str, Any], max_sentence: int, target: int) -> list[str]:
    if not isinstance(d, dict):
        return ["JSON 객체가 필요하다"]
    tasks = evidence["tasks"]
    got = d.get("tasks") or []
    problems = []
    if not isinstance(d.get("verdict"), dict) or not isinstance(d.get("intro"), dict):
        return ["intro·verdict 객체가 필요하다"]
    if len(got) != len(tasks):
        problems.append(f"tasks 는 과제 순서대로 {len(tasks)}개")
    allowed = _num_text(evidence)
    for i, (t, ev) in enumerate(zip(got, tasks), start=1):
        lines = [split_emphasis(str(x))[0] for x in t.get("lines") or []]
        if lines and step_key(ev["prompt"]) and step_key(ev["prompt"]) not in re.sub(r"[\s\W_]+", "", lines[0]).lower():
            problems.append(f"{i}번 과제 첫 문장에 시킨 말의 앞부분 '{' '.join(ev['prompt'].split()[:2])}' 을 그대로 넣는다(화면과 일치)")
        joined = " ".join(lines)
        if not ev["ok"] and not any(w in joined for w in FAIL_WORDS):
            problems.append(f"{i}번 과제는 실패했다({ev['status']}). 실패를 그대로 말한다(예: '이건 시간 안에 못 끝냈어요')")
        if ev["ok"] and "실패" in joined:
            problems.append(f"{i}번 과제는 성공했다. 실패라고 말하지 않는다")
    texts = []
    for line in spoken_lines(d):
        text, _, p = split_emphasis(str(line))
        problems += p
        texts.append(text)
        c = count_chars(text)
        if c > max_sentence:
            problems.append(f"{c}자다. {max_sentence}자 이내로: {text}")
        elif c < MIN_CHARS:
            problems.append(f"{c}자로 너무 짧다: {text}")
        if text and not ENDING.search(text):
            problems.append(f"끝맺지 않은 조각 문장이다: {text}")
        for n in NUMBER.findall(text):
            if n not in allowed:
                problems.append(f"숫자 {n} 은 실험 기록에 없다. 기록의 숫자만 쓴다: {text}")
    for a, b in repeated_sentences(texts):
        problems.append(f"{b + 1}번째 문장이 {a + 1}번째를 되풀이한다: {texts[b]}")
    problems += foreign_problems({k: v for k, v in d.items() if k != "readings"})
    total = sum(count_chars(t) for t in texts)
    if texts and abs(total - target) > target * TOLERANCE:
        problems.append(f"{LENGTH_TAG}가 {total}자로 목표 {target}자에서 벗어났다")
    return problems


def run_script(ctx: StepContext, job: dict[str, Any], cat: dict[str, Any], review_feedback: str) -> None:
    rv = job["review"]
    evidence = ctx.read_json("evidence.json")
    n = len(evidence["tasks"])
    rules = cat.get("script", {})
    max_sentence = int(rules.get("max_sentence_chars", 30))
    cps = float((cat.get("tts") or {}).get("speech_chars_per_sec") or ctx.providers.chars_per_sec)
    outro = outro_for(cat, job["jobId"])
    overhead = (4 + 2 * n) * (0.15 + PAD_SEC) + (4 + 3 * n) * 0.42
    target = max(80, round((job["targetDurationSec"] - overhead - (count_chars(outro["line"]) / cps if outro else 0)) * cps))
    ev_text = "\n".join(
        f"[{t['id']}] {t['goal']} — {'성공' if t['ok'] else '실패(' + t['status'] + ')'}, {t['seconds']}초, 판정: {t['check']}\n"
        f"  시킨 말: {t['prompt']}\n  에이전트가 한 일: " + " / ".join(s["input"] for s in t["steps"][:6]) +
        (f"\n  만든 파일: {', '.join(f['path'] for f in t['files'][:6])}" if t["files"] else "") +
        (f"\n  마지막 답: {t['final'][:200]}" if t["final"] else "")
        for t in evidence["tasks"])
    f = rv["feature"]
    messages, version = render_messages(
        "handson_script", topic=job["topic"], tool=rv["toolLabel"], feature=f"{f['name']} ({f['released']}): {f['what']}",
        facts="\n".join(f"- {x}" for x in rv.get("facts") or []), evidence=ev_text, count=n, target_chars=target,
        max_sentence=max_sentence, min_chars=MIN_CHARS, audience=cat.get("audience", ""),
        forbidden=", ".join(rules.get("forbidden", [])), review_feedback=review_feedback)

    def check(d: Any) -> list[str]:
        return check_script(d, evidence=evidence, max_sentence=max_sentence, target=target)

    out = ask(ctx, messages, _schema(n), "handson_script", check)
    hard = [p for p in out.problems if not p.startswith(LENGTH_TAG)]
    if hard:
        raise StepFailure("deterministic", "실습 리뷰 대본 규칙을 지키지 못했다: " + "; ".join(hard)[:800], retry_from="script")
    if out.problems:
        ctx.note_degraded("; ".join(out.problems))
    data = pack(out.data, evidence, rv)
    words = load_dictionary(ctx.settings.content_dir / "pronunciation.yaml", cat.get("pronunciation"))
    spoken = [data["hook"], *data["body"], data["summary"]]
    data["readings"] = rd.fill(ctx, spoken, data["readings"], words)
    data["meta"] = meta_of(out, version, targetChars=target, charCount=sum(count_chars(t) for t in spoken), format="review")
    ctx.write_json("script.json", data)


def pack(d: dict[str, Any], evidence: dict[str, Any], rv: dict[str, Any]) -> dict[str, Any]:
    """목록형과 같은 모양(listicle 키)으로 펼친다: 과제 = 항목. 실습 재생(demo)은 기록에서"""
    def lines(xs):
        out = []
        for x in xs:
            text, emph, _ = split_emphasis(str(x))
            out.append({"text": text, "emphasis": emph})
        return out
    hook = lines(d["hook"])
    intro = lines(d["intro"]["lines"])
    items = []
    for t, ev in zip(d["tasks"], evidence["tasks"]):
        items.append({"name": ev["goal"], "meta": rv["toolLabel"], "tagline": ev["check"].get("detail", ""), "badge": "성공" if ev["ok"] else "실패",
                      "lines": lines(t["lines"]), "demo": demo_for(ev, rv["toolLabel"])})
    verdict = {"pros": [str(x).strip() for x in d["verdict"]["pros"]], "cons": [str(x).strip() for x in d["verdict"]["cons"]],
               "forWhom": str(d["verdict"]["forWhom"]).strip()}
    recap = {"title": "직접 써 보니", "subtitle": verdict["forWhom"], "lines": lines(d["verdict"]["lines"])}
    spoken = ([x["text"] for x in hook] + [x["text"] for x in intro] + [x["text"] for it in items for x in it["lines"]]
              + [x["text"] for x in recap["lines"]])
    card = {k: str(v).strip() for k, v in d["hookCard"].items()}
    return {"listicle": {"hook": hook, "hookStyle": "result", "hookCard": {**card, "claimNote": "", "aside": ""}, "items": items,
                         "recap": recap},
            "handson": {"intro": intro, "tagline": str(d["intro"]["tagline"]).strip(), "verdict": verdict,
                        "feature": rv["feature"], "tool": rv["toolLabel"]},
            "readings": rd.to_map(d.get("readings"), spoken)[0],
            "hook": spoken[0], "body": spoken[1:-1], "summary": spoken[-1],
            "titleCandidates": d["titleCandidates"], "hashtags": d["hashtags"]}


# ---------- 장면

def build_scenes(script: dict[str, Any], evidence: dict[str, Any], outro: dict[str, str] | None) -> list[dict[str, Any]]:
    lst, hs = script["listicle"], script["handson"]
    card, hook = lst["hookCard"], lst["hook"]
    n = len(lst["items"])
    out = [_scene("hook", "LHookClaim", {"kicker": card["kicker"], "claim": card["claim"]}, hook[:1])]
    out.append(_scene("hook", "LHookReveal", {"kicker": hs["tool"], "headline": card["headline"], "count": n,
                                              **({"highlight": card["highlight"]} if card.get("highlight") and card["highlight"] in card["headline"] else {})},
                      hook[1:] + hs["intro"]))
    for i, (it, ev) in enumerate(zip(lst["items"], evidence["tasks"]), start=1):
        lines = it["lines"]
        preview = (ev.get("previews") or [None])[0]
        walk_lines = lines[:-1] if preview and len(lines) > 1 else lines
        out.append(_scene("item", "LWalkthrough", {"kind": "chat", "title": it["demo"]["title"], "steps": it["demo"]["steps"]}, walk_lines, i))
        if preview and len(lines) > 1:
            meta = f"{ev['seconds']}초 · {ev['check'].get('detail', '')}".strip(" ·")
            out.append(_scene("item", "LArtifact", {"image": preview["preview"], "title": preview["path"], "ok": bool(ev["ok"]),
                                                    **({"meta": meta} if meta else {})}, lines[-1:], i))
    v = hs["verdict"]
    total = round(sum(t["seconds"] for t in evidence["tasks"]))
    out.append(_scene("recap", "LVerdict", {"title": lst["recap"]["title"], "pros": v["pros"], "cons": v["cons"], "forWhom": v["forWhom"],
                                            "meta": f"{hs['tool']} · 실험 {n}개 · {total}초"}, lst["recap"]["lines"], pad=0.5))
    if outro:
        out.append(_scene("outro", "LOutro", {"title": outro["title"], **({"subtitle": outro["subtitle"]} if outro["subtitle"] else {})},
                          [{"text": outro["line"], "emphasis": ""}], pad=0.8))
    return [sc for sc in out if sc["lines"]]


def run_scenes(ctx: StepContext, script: dict[str, Any], job: dict[str, Any], cat: dict[str, Any]) -> None:
    evidence = ctx.read_json("evidence.json")
    scenes = build_scenes(script, evidence, outro_for(cat, job["jobId"]))
    for sc in scenes:
        bad = check_props(sc["visual"]["component"], sc["visual"]["props"])
        if bad:
            raise StepFailure("deterministic", f"장면 속성 오류: {'; '.join(bad)[:300]}", retry_from="script")
    ctx.write_json("scenes.json", {
        "schemaVersion": 1, "jobId": job["jobId"], "title": script["titleCandidates"][0],
        "tracker": {"items": [{"name": it["name"]} for it in script["listicle"]["items"]]},
        "readings": script.get("readings") or {},
        "scenes": [{"id": f"s{i:02d}", **sc} for i, sc in enumerate(scenes, start=1)],
        "meta": {"format": "review"},
    })

