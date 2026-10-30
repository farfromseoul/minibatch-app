"""목록형 쇼츠 (아키텍처 D42, 목록형쇼츠 기획서 2026-10-30).

/top 주제 → listicle 단독 작업 → 주제(참고 자료 사실) → 목록형 대본([강조]) → 검토 → 장면(틀은 코드, 그림은 LLM)
→ 음성 → timeline(문장 음성의 쉼에 맞춘 구절·단어 자막, 진행 표시). LLM·tts-worker 는 가짜.
"""
import array
import json
import math
import pathlib
import shutil
import unittest
import wave

from app.media import align as al
from app.pipeline.steps import listicle as ls
from app.pipeline.steps.publishing import _description
from app.pipeline.timeline_calc import compute_timeline
from app.schemas.templates import check_props
from tests.fakes import GOOD_SCORES, FakeLlm, FakeRegistry
from tests.test_media_steps import FakeWorker, MediaCase
from tests.test_telegram import TelegramCase

CATS = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories"
NAMES = ["find-skills", "superpowers", "claude-mem"]


def fill(prefix: str, n: int) -> str:
    """앞부분이 prefix 이고 공백 빼고 n 글자쯤인 문장 (괄호 강조 하나)"""
    body = prefix + " " + "나" * max(0, n - len(prefix.replace(" ", "")) - 3) + " [핵심]"
    return body


def reply(names=NAMES, per=15, claim="수백 가지"):
    items = []
    for i, name in enumerate(names):
        items.append({"name": name, "meta": f"repo/{name}", "tagline": "할 일 → 바로", "badge": "무료" if i == 0 else "",
                      "lines": [f"{ls.ORDINALS[i]} 번째는 [{name}]예요",
                                fill(f"{i}가 하는 일 설명", per), fill(f"{i}를 쓰는 순간", per)]})
    return {"hook": [fill("첫마디 하나", per), fill("둘째 첫마디", per), fill("셋째 이어서", per)],
            "hookCard": {"kicker": "클로드 스킬", "claim": claim, "claimNote": "소문", "aside": "", "headline": "진짜 쓸 건 3개",
                         "highlight": "3개"},
            "items": items, "recap": {"title": "정리하면", "subtitle": "", "lines": [fill("정리 첫 문장", per), fill("마무리 권하기", per)]},
            "titleCandidates": ["a", "b", "c"], "hashtags": ["#AI"]}


VISUALS = {"items": [
    {"visuals": [{"component": "LChat", "props": {"prompt": "PDF 표를 엑셀로", "results": ["pdf-to-xlsx", "table-extract"]}},
                 {"component": "LTerminal", "props": {"command": "npx skills add x", "output": ["설치 완료"]}}]},
    {"visuals": [{"component": "LSteps", "props": {"steps": ["계획", "코드", "검증"]}},
                 {"component": "LCompare", "props": {"left": {"title": "그냥", "points": ["바로 코드"]},
                                                      "right": {"title": "계획 먼저", "points": ["덜 헤맨다"]}, "winner": "right"}}]},
    {"visuals": [{"component": "LIcon", "props": {"icon": "memory", "title": "세션 넘어 기억"}},
                 {"component": "LRocket", "props": {}}]},  # 없는 그림 → 이 항목만 대체
]}


def tone_wav(path: pathlib.Path, parts, rate=8000):
    """[(초, 소리 여부)] 로 WAV (소리는 440Hz)"""
    data = array.array("h")
    for sec, loud in parts:
        for i in range(int(sec * rate)):
            data.append(int(8000 * math.sin(2 * math.pi * 440 * i / rate)) if loud else 0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


class PhraseTest(unittest.TestCase):
    def test_split_by_length_and_comma(self):
        self.assertEqual(al.split_phrases("하고 싶은 일을 말하면 맞는 스킬을 찾아서 깔아 줘요"),
                         [["하고", "싶은", "일을", "말하면"], ["맞는", "스킬을", "찾아서", "깔아", "줘요"]])
        self.assertEqual(al.split_phrases("정말요, 이게 다예요"), [["정말요,", "이게", "다예요"]])  # 짧은 문장은 그대로
        self.assertEqual(al.split_phrases("직접 써 보니까, 생각보다 훨씬 빨라요")[0], ["직접", "써", "보니까,"])
        self.assertEqual(al.split_phrases("이거 하나면"), [["이거", "하나면"]])

    def test_breaks_after_particle_not_inside_number(self):
        self.assertEqual(al.split_phrases("클로드 스킬이 10만 개가 넘는다는데"), [["클로드", "스킬이"], ["10만", "개가", "넘는다는데"]])

    def test_phrases_stay_short(self):
        for text in ("코드를 손대기 전에 계획부터 세우고 됐는지 검증하게 만들어요", "superpowers-plugin-for-claude 를 설치해요"):
            for p in al.split_phrases(text):
                self.assertTrue(len(p) == 1 or al.chars(" ".join(p)) <= al.PHRASE_CHARS, p)

    def test_boundary_snaps_to_pause_in_audio(self):
        tmp = pathlib.Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        wav = tmp / "s.wav"
        # 소리 1.0초 → 쉼 0.2초 → 소리 1.0초. 글자 비율 추정은 쉼과 조금 어긋나게 둔다
        tone_wav(wav, [(0.1, False), (1.0, True), (0.2, False), (1.0, True), (0.1, False)])
        out = al.align("하고 싶은 일을 말하면 맞는 스킬을 깔아 줘요", 2.4, wav, emphasis="스킬을")

        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[1]["start"], 1.2, delta=0.05)  # 쉼 가운데 (1.1~1.3)
        self.assertEqual(out[0]["start"], 0.0)                     # 첫 구절은 문장 처음부터 보인다
        self.assertAlmostEqual(out[0]["words"][0]["start"], 0.1, delta=0.02)  # 첫 단어는 소리 시작에
        self.assertEqual([w["text"] for w in out[1]["words"] if w.get("emphasis")], ["스킬을"])
        starts = [w["start"] for c in out for w in c["words"]]
        self.assertEqual(starts, sorted(starts))

    def test_without_audio_uses_character_ratio(self):
        out = al.align("하나 둘 셋 넷 다섯 여섯 일곱 여덟 아홉", 3.0, None)
        self.assertEqual(out[-1]["end"], 3.0)
        self.assertGreater(len(out), 1)


class ScriptRulesTest(unittest.TestCase):
    def check(self, data, **kw):
        args = dict(n=3, given=[], max_sentence=28, target=sum(len("".join(t.split())) for t in self.texts(data)), has_facts=False)
        args.update(kw)
        return ls.check_script(data, **args)

    @staticmethod
    def texts(data):
        return [ls.split_emphasis(x)[0] for x in ls._flat_lines(data)]

    def test_good_reply_passes(self):
        self.assertEqual(self.check(reply()), [])

    def test_emphasis_bracket_is_required_once(self):
        d = reply()
        d["hook"][0] = "강조 없는 첫마디 문장이에요"
        self.assertTrue(any("[ ]" in p for p in self.check(d)))

    def test_number_claim_needs_references(self):
        d = reply(claim="10만 개+")
        self.assertTrue(any("숫자" in p for p in self.check(d)))
        self.assertEqual(self.check(d, has_facts=True), [])

    def test_given_names_must_be_used_in_order(self):
        problems = self.check(reply(), given=["superpowers", "find-skills", "claude-mem"])
        self.assertTrue(any("운영자가 준 'superpowers'" in p for p in problems))

    def test_first_line_calls_the_name(self):
        d = reply()
        d["items"][1]["lines"][0] = "두 번째 [도구]를 볼게요"
        self.assertTrue(any("이름" in p for p in self.check(d)))

    def test_pack_splits_emphasis_and_keeps_compat_fields(self):
        data = ls._pack(reply())
        first = data["listicle"]["items"][0]["lines"][0]
        self.assertEqual(first, {"text": "첫 번째는 find-skills예요", "emphasis": "find-skills"})
        self.assertEqual(data["hook"], data["listicle"]["hook"][0]["text"])
        self.assertEqual(data["summary"], data["listicle"]["recap"]["lines"][-1]["text"])
        self.assertEqual(len(data["body"]), 2 + 9 + 1)
        texts = [data["hook"], *data["body"], data["summary"]]
        self.assertFalse([t for t in texts if "[" in t or "]" in t])

    def test_target_chars_leaves_room_for_scene_gaps(self):
        self.assertLess(ls.target_chars(45, 5.3, 5), 45 * 5.3)
        self.assertGreater(ls.target_chars(45, 5.3, 3), ls.target_chars(45, 5.3, 5))


class ScenesBuildTest(unittest.TestCase):
    def test_frame_is_built_by_code_and_props_are_valid(self):
        lst = ls._pack(reply())["listicle"]
        picks = [v["visuals"] for v in VISUALS["items"][:2]] + [[ls._fallback(lst["items"][2])] * 2]
        scenes = ls.build_scenes(lst, picks, {"line": "저장해 두고 하나씩 써 보세요.", "title": "저장", "subtitle": ""})

        comps = [s["visual"]["component"] for s in scenes]
        self.assertEqual(comps[:3], ["LHookClaim", "LHookReveal", "LItemCard"])
        self.assertEqual(comps[-2:], ["LRecap", "LOutro"])
        self.assertEqual(comps.count("LItemCard"), 3)
        for s in scenes:
            self.assertEqual(check_props(s["visual"]["component"], s["visual"]["props"]), [], s["visual"])
            self.assertEqual(len(s["emphasis"]), len(s["lines"]))
        items = [s for s in scenes if s["section"]["kind"] == "item"]
        self.assertEqual(sorted({s["section"]["index"] for s in items}), [1, 2, 3])
        # 항목 문장 3개: 소개 카드 1 + 그림 두 장이 1·1
        self.assertEqual([len(s["lines"]) for s in items[:3]], [1, 1, 1])
        hook = scenes[1]["visual"]["props"]
        self.assertEqual((hook["count"], hook["highlight"]), (3, "3개"))

    def test_visual_check_limits_repeats_and_bad_props(self):
        items = ls._pack(reply())["listicle"]["items"]
        problems = ls.check_visuals(VISUALS, items)
        self.assertTrue(any("LRocket" in p for p in problems))
        same = {"items": [{"visuals": [{"component": "LIcon", "props": {"icon": "bolt", "title": "x"}}] * 2}] * 3}
        self.assertTrue(any("두 번까지" in p for p in ls.check_visuals(same, items)))


class TimelinePhrasesTest(unittest.TestCase):
    def test_phrase_captions_are_ordered_and_inside(self):
        scenes = {"tracker": {"items": [{"name": "a"}]}, "scenes": [
            {"id": "s01", "section": {"kind": "item", "index": 1}, "lines": ["하고 싶은 일을 말하면 맞는 스킬을 깔아 줘요"],
             "visual": {"type": "template", "component": "LIcon", "props": {"icon": "bolt", "title": "x"}},
             "animationPreset": "pop", "padAfterSec": 0.15}]}
        tts = {"items": [{"id": "s01-01", "scene": "s01", "text": scenes["scenes"][0]["lines"][0], "path": "tts/x.wav", "seconds": 2.4}]}
        phrases = {"s01-01": al.align(tts["items"][0]["text"], 2.4, None, "스킬을")}

        t = compute_timeline(scenes, tts, fps=30, width=1080, height=1920, theme="gold", phrases=phrases)

        self.assertEqual(t["tracker"], scenes["tracker"])
        self.assertEqual(t["scenes"][0]["section"], {"kind": "item", "index": 1})
        last = 0
        for c in t["captions"]:
            self.assertGreaterEqual(c["fromFrame"], last)
            frames = [w["fromFrame"] for w in c["words"]]
            self.assertEqual(frames, sorted(frames))
            self.assertTrue(all(c["fromFrame"] <= f < c["toFrame"] for f in frames))
            last = c["toFrame"]
        self.assertTrue(any(w.get("emphasis") for c in t["captions"] for w in c["words"]))


class ListicleCase(TelegramCase, MediaCase):
    pipeline = ["topic", "script", "review", "scenes", "tts", "timeline"]

    def setUp(self):
        self.llm = FakeLlm()
        super().setUp()
        for f in ("listicle.yaml", "it-news.yaml"):
            shutil.copy(CATS / f, self.settings.content_dir / "categories" / f)
        FakeWorker.seconds = 2.4

    def make_providers(self):
        return FakeRegistry(self.llm, tts_url=self.url)

    def make_steps(self):
        return {}  # 진짜 단계들

    def top(self, text):
        self.tg.say(text)
        self.poll()
        return self.tg.sent("sendMessage")[-1]["text"]


class TopCommandTest(ListicleCase):
    def test_top_creates_listicle_job_with_references_and_items(self):
        msg = self.top("/top 클로드 스킬 중 진짜 쓸 것, 3\nhttps://github.com/anthropics/skills\n1. find-skills\n- superpowers\n- claude-mem")

        self.assertIn("✅ 목록형 쇼츠 등록", msg)
        (job,) = self.get("/jobs?status=PENDING").json()["items"]
        self.assertEqual(job["category"], "listicle")
        from app.db.models import Job
        with self.app.state.db() as s:
            stored = s.get(Job, job["id"]).input
        self.assertEqual(stored["listicle"],
                         {"count": 3, "references": ["https://github.com/anthropics/skills"], "items": NAMES})

    def test_bad_count_explains(self):
        msg = self.top("/top 쿠버네티스 명령어, 9")
        self.assertIn("항목 수는 3~5", msg)
        self.assertEqual(self.get("/jobs").json()["items"], [])

    def test_help_lists_top(self):
        self.assertIn("/top 주제, 개수", self.top("/help"))

    def test_next_job_takes_news_then_listicle_then_others(self):
        plain = self.new_job("RAG란?")
        listicle = self.post("/listicle", {"topic": "터미널 도구", "count": 3}).json()["id"]
        news = self.post("/jobs", {"topic": "뉴스", "category": "it-news"}).json()["id"]
        order = []
        for _ in range(3):
            nxt = self.get("/jobs/next").json()["jobId"]
            order.append(nxt)
            self.post(f"/jobs/{nxt}/cancel", {"cancelledBy": "테스트", "reason": "순서 확인"})
        self.assertEqual(order, [news, listicle, plain])

    def test_api_rejects_non_http_reference(self):
        res = self.post("/listicle", {"topic": "x", "references": ["file:///etc/passwd"]})
        self.assertEqual(res.status_code, 400)


class ListicleProductionTest(ListicleCase):
    def test_chain_to_timeline_has_tracker_sections_and_word_captions(self):
        job_id = self.post("/listicle", {"topic": "클로드 스킬", "count": 3}).json()["id"]
        target = ls.target_chars(45, 5.6, 3, len("저장해두고하나씩써보세요."))
        per = max(8, round(target / 14))
        self.llm.responses = [reply(per=per), {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, VISUALS, VISUALS, VISUALS]

        for step in self.pipeline:
            res = self.run_step(job_id, step)
            self.assertIn(res.status_code, (200, 202), f"{step}: {res.text}")
            st = self.get(f"/jobs/{job_id}/steps/{step}").json()
            self.assertEqual(st["status"], "succeeded", f"{step}: {st} {[r['schema_name'] for r in self.llm.requests]}")

        job = self.read(job_id, "job.json")
        self.assertEqual((job["format"], job["targetDurationSec"], job["durationToleranceSec"], job["theme"]),
                         ("listicle", 45, 8, "gold"))
        prompt = [r for r in self.llm.requests if r["schema_name"] == "listicle_script"][0]["messages"][-1]["content"]
        self.assertIn("항목 수 N: 3", prompt)
        t = self.read(job_id, "timeline.json")
        self.assertEqual([i["name"] for i in t["tracker"]["items"]], NAMES)
        comps = [s["visual"]["component"] for s in t["scenes"]]
        self.assertEqual(comps[0], "LHookClaim")
        self.assertIn("LIcon", comps)  # 3번 항목의 없는 그림은 아이콘 장면으로
        self.assertEqual(comps[-1], "LOutro")
        self.assertTrue(all("words" in c for c in t["captions"]))
        self.assertTrue(37 <= t["durationInFrames"] / 30 <= 53, t["durationInFrames"] / 30)
        run = self.get(f"/jobs/{job_id}/steps/scenes").json()
        self.assertIn("아이콘", json.dumps(run, ensure_ascii=False))


class ListicleDescriptionTest(unittest.TestCase):
    def test_reference_links_in_description(self):
        text = _description({"hook": "h", "summary": "s", "hashtags": []}, None, None, None,
                            {"sources": [{"url": "https://github.com/anthropics/skills"}]})
        self.assertIn("참고:\nhttps://github.com/anthropics/skills", text)


class ListicleQcTest(unittest.TestCase):
    """qc 길이 검사도 카테고리 허용 범위(목록형 45±8초)를 쓴다. 2026-10-30: ±5초 고정이면 timeline 을 통과한 51초 영상이 qc 에서 떨어진다"""

    def test_qc_length_uses_job_tolerance(self):
        from tests.test_qc_upload import PublishCase, good_analysis

        class Case(PublishCase):
            def runTest(self):
                pass

        case = Case()
        case.setUp()
        try:
            shutil.copy(CATS / "listicle.yaml", case.settings.content_dir / "categories" / "listicle.yaml")
            case.analysis = good_analysis(durationSec=51.0)
            job_id = case.post("/listicle", {"topic": "터미널 도구", "count": 3}).json()["id"]
            case.run_until(job_id, "qc")
            qc = case.read(job_id, "qc.json")
            length = next(c for c in qc["checks"] if c["name"] == "length")
            self.assertEqual((length["ok"], length["expected"]), (True, "37~53초"))
        finally:
            case.tearDown()
