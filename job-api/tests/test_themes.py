"""목록형 화면 테마 템플릿 (D42 v1.3, 2026-10-31 사용자: 영상이 단조롭다. 테마를 여러 개 두고 추천·텔레그램 버튼·직접 지정).

테마는 카테고리 설정(listicle.yaml themes)과 render 테마 파일에 등록하는 템플릿이다. /top 이 작업을 만들 때 추천 테마를 두고,
텔레그램 등록 답에 미리보기 사진과 [테마] 버튼을 보낸다. 버튼은 만들기 시작 전(주제 단계 전)에만 바꾼다.
"""
import shutil
import unittest

from app.domain import themes as th
from tests.test_listicle import CATS, ListicleCase

CONF = {"theme": "nova", "themes": [
    {"name": "terminal", "label": "터미널", "aliases": ["터미널"], "keywords": ["터미널", "CLI", "명령어", "깃"]},
    {"name": "pop", "label": "팝", "aliases": ["팝"], "keywords": ["실수", "꿀팁"]},
    {"name": "paper", "label": "페이퍼", "aliases": ["페이퍼"], "keywords": ["개념", "방법", "팁"]},
    {"name": "nova", "label": "노바", "aliases": ["노바"], "keywords": ["AI", "클로드", "스킬"]},
]}


class RecommendTest(unittest.TestCase):
    def test_keywords_pick_theme(self):
        self.assertEqual(th.recommend(CONF, "개발자가 매일 쓰는 터미널 명령어", [], None)[0], "terminal")
        self.assertEqual(th.recommend(CONF, "신입이 자주 하는 실수", [], None)[0], "pop")
        self.assertEqual(th.recommend(CONF, "클로드 스킬 추천", [], None)[0], "nova")

    def test_no_keyword_uses_default(self):
        self.assertEqual(th.recommend(CONF, "아무 주제", [], None)[0], "nova")

    def test_avoids_previous_theme(self):
        name, why = th.recommend(CONF, "클로드 스킬 추천", [], "nova")
        self.assertNotEqual(name, "nova")
        self.assertIn("앞", why)

    def test_resolve_names_and_aliases(self):
        self.assertEqual(th.resolve(CONF, "Paper"), "paper")
        self.assertEqual(th.resolve(CONF, "터미널"), "terminal")
        self.assertIsNone(th.resolve(CONF, "rainbow"))


class ThemeFlowTest(ListicleCase):
    def setUp(self):
        super().setUp()
        shutil.copytree(CATS.parent / "themes", self.settings.content_dir / "themes", dirs_exist_ok=True)

    def stored(self, job_id):
        from app.db.models import Job
        with self.app.state.db() as s:
            return s.get(Job, job_id).input["listicle"]

    def job_id(self):
        return self.get("/jobs?status=PENDING").json()["items"][0]["id"]

    def test_top_recommends_theme_with_preview_and_buttons(self):
        self.tg.say("/top 개발자가 매일 쓰는 터미널 명령어, 3")
        self.poll()

        job_id = self.job_id()
        self.assertEqual((self.stored(job_id)["theme"], self.stored(job_id)["themeChosen"]), ("terminal", False))
        self.assertEqual(len(self.tg.sent("sendPhoto")), 1)
        msg = [m for m in self.tg.sent("sendMessage") if "reply_markup" in m][-1]
        datas = [b["callback_data"] for row in msg["reply_markup"]["inline_keyboard"] for b in row]
        self.assertEqual(datas, [f"th:{job_id}:{n}" for n in ("nova", "paper", "terminal", "pop")])
        self.assertIn("✓", [b["text"] for row in msg["reply_markup"]["inline_keyboard"] for b in row if b["callback_data"].endswith("terminal")][0])

    def test_direct_theme(self):
        self.tg.say("/top 클로드 스킬 추천, 3, paper")
        self.poll()

        self.assertEqual((self.stored(self.job_id())["theme"], self.stored(self.job_id())["themeChosen"]), ("paper", True))

    def test_unknown_theme_word_stays_in_topic(self):
        self.tg.say("/top 레인보우 효과, 3")
        self.poll()
        jobs = self.get("/jobs?status=PENDING").json()["items"]
        self.assertEqual(jobs[0]["topic"], "레인보우 효과")

    def test_button_changes_theme_before_production_only(self):
        self.tg.say("/top 클로드 스킬 추천, 3")
        self.poll()
        job_id = self.job_id()

        self.tg.press(f"th:{job_id}:pop")
        self.poll()
        self.assertEqual((self.stored(job_id)["theme"], self.stored(job_id)["themeChosen"]), ("pop", True))

        self.run_step(job_id, "topic")
        self.assertEqual(self.read(job_id, "job.json")["theme"], "pop")
        self.tg.press(f"th:{job_id}:paper")
        self.poll()
        self.assertEqual(self.stored(job_id)["theme"], "pop")  # 만들기 시작한 뒤에는 바꾸지 않는다

    def test_api_theme(self):
        res = self.post("/listicle", {"topic": "깃 명령어", "count": 3, "theme": "terminal"})
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(self.stored(res.json()["id"])["theme"], "terminal")
        self.assertEqual(self.post("/listicle", {"topic": "x", "theme": "rainbow"}).status_code, 400)

    def test_job_json_uses_category_default_without_theme(self):
        job_id = self.post("/listicle", {"topic": "아무 주제", "count": 3}).json()["id"]
        self.run_step(job_id, "topic")
        self.assertIn(self.read(job_id, "job.json")["theme"], ("nova", "paper", "terminal", "pop"))
