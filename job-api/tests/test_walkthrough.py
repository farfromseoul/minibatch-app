"""목록형 실습 데모 (목록형쇼츠 v1.4 L20~L22, 2026-11-01 사용자: 커맨드·코드가 대본과 일치하고, 설명만 말고 직접 쳐 보여 달라).

대본 LLM 이 항목마다 데모(입력할 명령과 출력)를 대본과 함께 쓴다. 대본 문장은 그 입력을 말하고, 장면 단계는 데모를
그대로 LWalkthrough 로 그린다(그림 LLM 을 거치지 않는다). timeline 은 문장 시작 프레임을 beats 로 넣어 문장마다 한 단계씩 넘긴다.
화면 글자·대본에 일본어 가나·한자가 섞이면 다시 쓰게 한다(2026-11-01 실제: '変更差分を点検').
"""
import copy
import unittest

from app.pipeline.steps import listicle as ls
from app.pipeline.timeline_calc import compute_timeline
from app.schemas.templates import check_props
from tests.fakes import GOOD_SCORES
from tests.test_listicle import NAMES, VISUALS, ListicleCase, fill, reply

DEMO = {"kind": "terminal", "title": "터미널",
        "steps": [{"input": "npx skills find pdf", "output": ["pdf-to-xlsx  표 추출", "pdf-reader  요약"]},
                  {"input": "npx skills add pdf-to-xlsx", "output": ["✓ 설치 완료"]}]}
NONE = {"kind": "none", "title": "", "steps": []}


def demo_reply(per=15, demo=DEMO, **kw):
    d = reply(per=per, **kw)
    for it in d["items"]:
        it["demo"] = copy.deepcopy(NONE)
    it = d["items"][0]
    it["demo"] = copy.deepcopy(demo)
    it["lines"] = [it["lines"][0], "먼저 [npx skills find] 뒤에 할 일을 쳐요",
                   "고른 이름을 [npx skills add] 로 설치해요", fill("이럴 때 쓰면 좋아요", per)]
    d["readings"] += [{"term": t, "reading": r} for t, r in (("npx", "엔피엑스"), ("skills", "스킬스"), ("find", "파인드"), ("add", "애드"))]
    return d


class DemoRulesTest(unittest.TestCase):
    def check(self, data, **kw):
        texts = [ls.split_emphasis(x)[0] for x in ls._flat_lines(data)]
        args = dict(n=3, given=[], max_sentence=28, target=sum(len("".join(t.split())) for t in texts), has_facts=False)
        args.update(kw)
        return ls.check_script(data, **args)

    def test_demo_reply_passes(self):
        self.assertEqual(self.check(demo_reply()), [])

    def test_schema_has_demo_and_allows_one_more_line(self):
        item = ls._schema(3)["properties"]["items"]["items"]
        self.assertIn("demo", item["required"])
        self.assertEqual(item["properties"]["lines"]["maxItems"], ls.ITEM_LINES + 1)
        self.assertEqual(item["properties"]["demo"]["properties"]["kind"]["enum"], ["terminal", "code", "chat", "settings", "none"])

    def test_step_input_must_be_said_in_its_sentence(self):
        d = demo_reply()
        d["items"][0]["lines"][1] = "먼저 [찾기 명령]으로 할 일을 쳐요"
        self.assertTrue(any("npx skills" in p and "말" in p for p in self.check(d)))

    def test_steps_fit_in_sentences(self):
        d = demo_reply()
        d["items"][0]["demo"]["steps"] *= 2  # 단계 4개 > 문장 3개(소개 뒤)
        self.assertTrue(any("단계" in p for p in self.check(d)))

    def test_demo_needs_steps_and_none_has_none(self):
        d = demo_reply()
        d["items"][0]["demo"]["steps"] = []
        self.assertTrue(any("단계" in p for p in self.check(d)))
        d = demo_reply()
        d["items"][1]["demo"] = {"kind": "none", "title": "", "steps": DEMO["steps"][:1]}
        self.assertTrue(any("none" in p for p in self.check(d)))

    def test_extra_line_only_with_demo(self):
        d = demo_reply()
        d["items"][1]["lines"].append(fill("하나 더 말해요", 15))
        self.assertTrue(any("2번 항목" in p and "문장" in p for p in self.check(d)))

    def test_filler_commands_are_rejected(self):
        """2026-11-02 사용자: 구독자가 따라 쳐서 쓸모 있는 실제 명령만. ls·cat·wc·top 같은 시늉 명령은 안 된다"""
        for cmd in ("ls ~/skills | wc -l", "cat SKILL.md", "top -n 3", "echo done", "pwd"):
            d = demo_reply()
            d["items"][0]["demo"]["steps"][0]["input"] = cmd
            d["items"][0]["lines"][1] = f"먼저 [{' '.join(cmd.split()[:2])}] 를 쳐 봐요"
            self.assertTrue(any("쓸모 있는" in p for p in self.check(d)), cmd)
        self.assertEqual(self.check(demo_reply()), [])  # npx skills find·add 는 실제로 쓰는 명령

    def test_terminal_is_not_a_picker_choice(self):
        from app.schemas.templates import DETAIL_VISUALS
        self.assertNotIn("LTerminal", DETAIL_VISUALS)  # 터미널 화면은 검사된 데모(LWalkthrough)로만

    def test_missing_demo_is_treated_as_none(self):
        self.assertEqual(self.check(reply()), [])

    def test_japanese_or_hanja_is_rejected_anywhere(self):
        d = demo_reply()
        d["items"][0]["demo"]["steps"][0]["output"][0] = "変更差分を点検"
        self.assertTrue(any("일본어" in p for p in self.check(d)))
        d = demo_reply()
        d["items"][2]["tagline"] = "設定 정리"
        self.assertTrue(any("일본어" in p for p in self.check(d)))

    def test_visual_check_rejects_japanese(self):
        items = ls._pack(reply())["listicle"]["items"]
        v = {"items": [{"visuals": [{"component": "LSteps", "props": {"steps": ["変更差分を点検", "적용"]}}]}] * 1
                      + VISUALS["items"][1:2] * 2}
        self.assertTrue(any("일본어" in p for p in ls.check_visuals(v, items)))

    def test_pack_keeps_demo(self):
        items = ls._pack(demo_reply())["listicle"]["items"]
        self.assertEqual(items[0]["demo"]["steps"][1]["input"], "npx skills add pdf-to-xlsx")
        self.assertEqual(items[1]["demo"]["kind"], "none")
        self.assertEqual(ls._pack(reply())["listicle"]["items"][0]["demo"]["kind"], "none")


class WalkthroughScenesTest(unittest.TestCase):
    def test_demo_item_becomes_walkthrough_with_all_explaining_lines(self):
        lst = ls._pack(demo_reply())["listicle"]
        picks = ls.demo_picks(lst["items"])
        self.assertEqual(picks[0][0]["component"], "LWalkthrough")
        self.assertIsNone(picks[1])
        picks[1] = picks[2] = [ls._fallback(lst["items"][1])]
        scenes = ls.build_scenes(lst, picks, None)
        walk = [s for s in scenes if s["visual"]["component"] == "LWalkthrough"][0]
        self.assertEqual(len(walk["lines"]), 3)
        self.assertEqual(check_props("LWalkthrough", walk["visual"]["props"]), [])
        self.assertEqual(walk["visual"]["props"]["steps"][0]["input"], "npx skills find pdf")

    def test_walkthrough_props_schema(self):
        good = {"kind": "terminal", "title": "t", "steps": [{"input": "ls", "output": []}], "beats": [0, 40]}
        self.assertEqual(check_props("LWalkthrough", good), [])
        self.assertTrue(check_props("LWalkthrough", {**good, "kind": "none"}))
        self.assertTrue(check_props("LWalkthrough", {**good, "steps": []}))


class BeatsTest(unittest.TestCase):
    def test_timeline_puts_sentence_starts_into_walkthrough_beats(self):
        vis = {"type": "template", "component": "LWalkthrough",
               "props": {"kind": "terminal", "title": "t", "steps": [{"input": "ls", "output": ["a"]}, {"input": "pwd", "output": []}]}}
        scenes = {"scenes": [
            {"id": "s01", "lines": ["하나요", "둘이요", "셋이요"], "visual": vis, "animationPreset": "pop", "padAfterSec": 0.3}]}
        tts = {"items": [{"id": f"s01-0{i}", "scene": "s01", "text": "x", "path": "tts/x.wav", "seconds": 2.0} for i in (1, 2, 3)]}

        t = compute_timeline(scenes, tts, fps=30, width=1080, height=1920, theme="nova")

        beats = t["scenes"][0]["visual"]["props"]["beats"]
        self.assertEqual(beats, [6, 71, 135])  # 앞 여백 0.2초, 문장 2초, 사이 0.15초 (2.35초 → 70.5 → 71)
        self.assertNotIn("beats", vis["props"])  # scenes.json 의 장면은 그대로


class WalkthroughProductionTest(ListicleCase):
    def test_demo_skips_visual_llm_for_that_item_and_review_sees_commands(self):
        job_id = self.post("/listicle", {"topic": "클로드 스킬", "count": 3}).json()["id"]
        target = ls.target_chars(46, 7.5, 3, len("저장해두고하나씩써보세요."))
        per = max(8, round(target / 15))
        two = {"items": VISUALS["items"][:2]}
        self.llm.responses = [demo_reply(per=per), {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, two]

        for step in ("topic", "script", "review", "scenes"):
            res = self.run_step(job_id, step)
            self.assertIn(res.status_code, (200, 202), f"{step}: {res.text}")
            st = self.get(f"/jobs/{job_id}/steps/{step}").json()
            self.assertEqual(st["status"], "succeeded", f"{step}: {st}")

        names = [r["schema_name"] for r in self.llm.requests]
        self.assertEqual(names, ["listicle_script", "review", "listicle_visuals"])
        review = self.llm.requests[1]["messages"][-1]["content"]
        self.assertIn("npx skills add pdf-to-xlsx", review)
        visuals = self.llm.requests[2]["messages"][-1]["content"]
        self.assertNotIn(NAMES[0], visuals.split("사실 목록")[0])  # 데모 항목은 그림을 묻지 않는다
        comps = [s["visual"]["component"] for s in self.read(job_id, "scenes.json")["scenes"]]
        self.assertEqual(comps[3], "LWalkthrough")
        self.assertEqual(comps.count("LWalkthrough"), 1)


if __name__ == "__main__":
    unittest.main()
