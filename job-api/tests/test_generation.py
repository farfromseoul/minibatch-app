"""주제 후보·시리즈 계획 자동 생성 (아키텍처 D25: 자동 생성물은 PROPOSED, 사용자가 승인해야 쓴다)."""
import pathlib
import shutil
import threading

from fastapi.testclient import TestClient

from tests.fakes import FakeLlm, FakeRegistry, transient
from tests.helpers import AUTH, AppTestCase, FakeStep

REAL_CATEGORY = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories" / "ai-it.yaml"

PLAN = {
    "bible": {"premise": "신입 민지가 AI 팀에서 매화 개념 하나씩 배운다",
              "characters": [{"name": "민지", "role": "질문하는 신입"}, {"name": "박 선임", "role": "비유로 설명"}],
              "tone": "가볍고 친근하게"},
    "episodes": [{"title": "AI가 뭐길래", "outline": "AI의 뜻"}, {"title": "머신러닝", "outline": "데이터로 배운다"},
                 {"title": "딥러닝", "outline": "층을 쌓는다"}],
}


class GenCase(AppTestCase):
    def setUp(self):
        self.llm = FakeLlm()
        super().setUp()
        shutil.copy(REAL_CATEGORY, self.settings.content_dir / "categories" / "ai-it.yaml")

    def make_providers(self):
        return FakeRegistry(self.llm)


class TopicGenerationTest(GenCase):
    def test_creates_proposed_topics_without_duplicates(self):
        self.post("/topics", {"titles": ["RAG란?"]})  # 이미 있는 주제
        self.llm.responses = [{"topics": ["임베딩이란?", "RAG 란", "토큰이란?", "임베딩이란?"]}]

        res = self.post("/topics/generate", {"category": "ai-it", "count": 3})

        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["created"], 2)  # 기존 RAG·응답 안 중복 제외
        proposed = [t["title"] for t in self.get("/topics?status=PROPOSED").json()["items"]]
        self.assertEqual(proposed, ["임베딩이란?", "토큰이란?"])
        self.assertTrue(all(t["source"] == "llm" for t in self.get("/topics?status=PROPOSED").json()["items"]))

    def test_prompt_has_hint_and_recent_topics_to_avoid(self):
        self.post("/topics", {"titles": ["RAG란?"]})
        self.llm.responses = [{"topics": ["벡터 DB란?"]}]

        self.post("/topics/generate", {"category": "ai-it", "count": 5})

        prompt = self.llm.last_user_text()
        self.assertIn("입문자가 자주 헷갈리는", prompt)  # 카테고리 topic_generation.prompt_hint
        self.assertIn("RAG란?", prompt)
        self.assertIn("5", prompt)

    def test_proposed_topics_are_not_picked_until_approved(self):
        self.llm.responses = [{"topics": ["벡터 DB란?"]}]
        self.post("/topics/generate", {"category": "ai-it", "count": 1})

        self.assertEqual(self.post("/jobs", {}).status_code, 409)

    def test_llm_down_is_503(self):
        self.llm.responses = [transient()]

        res = self.post("/topics/generate", {"category": "ai-it", "count": 3})

        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["error"]["code"], "llm_unavailable")


class SeriesPlanTest(GenCase):
    def test_generates_proposed_plan_with_bible_and_numbered_episodes(self):
        self.llm.responses = [PLAN]

        res = self.post("/series", {"key": "ai-office", "title": "민지의 AI 적응기", "episodeCount": 3})

        self.assertEqual(res.status_code, 201, res.text)
        s = res.json()
        self.assertEqual((s["status"], s["planSource"]), ("PROPOSED", "llm"))
        self.assertEqual([e["number"] for e in s["episodes"]], [1, 2, 3])
        self.assertEqual(s["bible"]["premise"], PLAN["bible"]["premise"])
        self.assertIn("민지의 AI 적응기", self.llm.last_user_text())
        self.assertIn("3", self.llm.last_user_text())

    def test_wrong_episode_count_is_asked_again(self):
        self.llm.responses = [dict(PLAN, episodes=PLAN["episodes"][:2]), PLAN]

        res = self.post("/series", {"key": "ai-office", "title": "민지", "episodeCount": 3})

        self.assertEqual(res.status_code, 201)
        self.assertIn("3", self.llm.last_user_text())

    def test_proposed_series_cannot_make_jobs_until_approved(self):
        self.llm.responses = [PLAN]
        self.post("/series", {"key": "ai-office", "title": "민지", "episodeCount": 3})

        blocked = self.post("/jobs", {"seriesId": "ai-office"})
        approved = self.post("/series/ai-office/approve", {"approvedBy": "운영자"})
        allowed = self.post("/jobs", {"seriesId": "ai-office"})

        self.assertEqual(blocked.json()["error"]["code"], "series_not_approved")
        self.assertEqual(approved.json()["status"], "APPROVED")
        self.assertEqual(allowed.status_code, 201)

    def test_approve_with_edited_plan(self):
        self.llm.responses = [PLAN]
        self.post("/series", {"key": "ai-office", "title": "민지", "episodeCount": 3})

        res = self.post("/series/ai-office/approve", {"approvedBy": "운영자", "episodes": [
            {"number": 1, "title": "고친 1화", "outline": "새 계획"}, {"number": 2, "title": "고친 2화", "outline": "새 계획 2"}]})

        self.assertEqual([e["title"] for e in res.json()["episodes"]], ["고친 1화", "고친 2화"])

    def test_approve_only_proposed(self):
        self.post("/series", {"key": "mine", "title": "직접", "episodes": [{"number": 1, "title": "a", "outline": "b"}]})

        self.assertEqual(self.post("/series/mine/approve", {"approvedBy": "운영자"}).status_code, 409)


class GenerationLockTest(GenCase):
    """LLM 생성도 단계 실행과 같은 전역 잠금을 쓴다 (메모리 예산)"""

    def test_busy_while_a_step_runs(self):
        from app.main import create_app

        gate = threading.Event()
        steps = {"script": FakeStep("script", ["job.json"], ["script.json"], block=gate)}
        app = create_app(self.settings, steps=steps, pipeline=self.pipeline, notify=lambda u, p: None,
                         clock=self.clock, providers=FakeRegistry(FakeLlm({"topics": ["x"]})))
        with TestClient(app) as client:
            job = client.post("/jobs", json={"topic": "가"}, headers=AUTH).json()["id"]
            client.post(f"/jobs/{job}/steps/topic", json={}, headers=AUTH)
            app.state.runner.wait_idle(5)
            client.post(f"/jobs/{job}/steps/script", json={}, headers=AUTH)

            res = client.post("/topics/generate", json={"category": "ai-it", "count": 1}, headers=AUTH)

            gate.set()
            app.state.runner.wait_idle(5)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "busy")
