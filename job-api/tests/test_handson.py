"""실습 리뷰 쇼츠 (메인 D46, 실습리뷰쇼츠 기획서·아키텍처, 2026-11-01).

/try → 주제 단계(웹 검색 요청으로 기능 확인 + 과제 계획) → lab 단계는 [실험 시작] 전까지 기다림(텔레그램 계획 버튼)
→ 승인 뒤 실험 실행기 호출(가짜: 컨테이너처럼 result.json·미리보기를 쓴다) → evidence.json → 기록만 근거로 대본 → 장면
(실습 재생·결과물·평가) → 업로드는 [업로드 승인] 전까지 기다림(영상 미리보기).
"""
import json
import shutil
import unittest

import httpx

from app.pipeline.steps import handson as ho
from app.pipeline.steps.lab import LabStep
from app.schemas.templates import check_props
from tests.fakes import GOOD_SCORES
from tests.test_listicle import CATS, ListicleCase
from tests.test_media_steps import FakeWorker

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
PLAN = {"feature": {"name": "Claude Code", "released": "2026-10", "what": "말로 시키면 파일을 만들어 준다", "howToUse": "터미널에서 claude"},
        "facts": ["Claude Code 는 터미널에서 쓰는 코딩 도구다", "파일을 읽고 쓴다", "셸 명령을 실행한다"],
        "sources": [{"title": "docs", "url": "https://code.claude.com/docs/en/overview"}],
        "tasks": [{"id": "t1", "goal": "막대 차트 페이지", "prompt": "막대 차트를 chart.html 에 그려 줘. 값은 3, 5, 2", "why": "결과가 눈에 보인다",
                   "check": {"kind": "fileExists", "file": "chart.html", "text": ""}, "timeoutSec": 300},
                  {"id": "t2", "goal": "세 줄 요약", "prompt": "세 줄로 summary.md 에 요약해 줘", "why": "문서 정리",
                   "check": {"kind": "fileExists", "file": "summary.md", "text": ""}, "timeoutSec": 120}]}


def l(text, emph):
    return text.replace(emph, f"[{emph}]", 1)


SCRIPT = {
    "hook": [l("막대 차트를 말 한마디로 만들어 봤어요", "막대 차트를"), l("요약은 시간 안에 끝나지 않았죠", "시간 안에"),
             l("직접 돌려 본 결과를 볼게요", "직접")],
    "hookCard": {"kicker": "클로드 코드", "claim": "말로 차트", "headline": "직접 돌려 본 결과", "highlight": "직접"},
    "intro": {"tagline": "말로 시키는 코딩", "lines": [l("터미널에서 말로 시키면 파일을 만들어 줘요", "파일을")]},
    "tasks": [{"lines": [l("먼저 막대 차트를 그려 달라고 했어요", "막대 차트를"), l("에이전트가 페이지 파일을 바로 썼어요", "바로"),
                         l("결과 페이지가 깔끔하게 열렸어요", "깔끔하게")]},
              {"lines": [l("다음은 세 줄로 요약을 부탁했어요", "세 줄로"), l("이건 시간 안에 못 끝냈어요", "못 끝냈어요")]}],
    "verdict": {"pros": ["말로 바로 결과물", "파일을 직접 씀"], "cons": ["긴 일은 시간 초과"], "forWhom": "빠른 시안이 필요한 분",
                "lines": [l("간단한 화면 시안에는 바로 써 볼 만해요", "시안에는"), l("긴 문서 작업은 나눠서 시키세요", "나눠서")]},
    "titleCandidates": ["a", "b", "c"], "hashtags": ["#AI"], "readings": []}


class FakeLabRunner:
    """맥 위 실험 실행기 대신: 과제 폴더에 컨테이너가 쓰는 것처럼 result.json·미리보기를 쓴다"""

    def __init__(self, case, results):
        self.case, self.results, self.requests = case, results, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path, request.headers.get("authorization"),
                              json.loads(request.content) if request.content else None))
        if request.method == "POST":
            body = json.loads(request.content)
            for t in body["tasks"]:
                d = self.case.job_dir(body["jobId"]) / "lab" / t["id"]
                r = self.results[t["id"]]
                (d / "previews").mkdir(parents=True, exist_ok=True)
                for pv in r.get("previews", []):
                    (d / pv["preview"]).write_bytes(PNG)
                (d / "result.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            return httpx.Response(202, json={"status": "running"})
        return httpx.Response(200, json={"status": "done", "tasks": [{"id": "t1", "status": "done"}, {"id": "t2", "status": "killed"}]})


OK_RESULT = {"ok": True, "status": "done", "seconds": 41.2, "check": {"ok": True, "detail": "chart.html 있음"},
             "steps": [{"kind": "file", "input": "Write chart.html", "output": ["File created"]},
                       {"kind": "command", "input": "ls", "output": ["chart.html"]}],
             "files": [{"path": "chart.html", "size": 900}], "previews": [{"path": "chart.html", "preview": "previews/chart.html.png"}],
             "final": "chart.html 을 만들었어요", "excerpts": []}
FAIL_RESULT = {"ok": False, "status": "timeout", "seconds": 120.0, "check": {"ok": False, "detail": "summary.md 없음"},
               "steps": [{"kind": "read", "input": "Read notes.txt", "output": []}], "files": [], "previews": [], "final": ""}


class HandsOnCase(ListicleCase):
    pipeline = ["topic", "lab", "script", "review", "scenes", "tts", "timeline"]
    results = {"t1": OK_RESULT, "t2": FAIL_RESULT}

    def extra_settings(self):
        import pathlib
        tok = pathlib.Path(self._tmp.name) / "lab_runner_token"
        tok.write_text("runner-token-0123456789\n")
        return {"lab_runner_url": "http://lab-runner:1236", "lab_image": "ghcr.io/x/minibatch-lab:abc1234", "lab_runner_token_file": tok}

    def make_steps(self):
        self.lab_runner = FakeLabRunner(self, self.results)
        return {"lab": LabStep(http=httpx.Client(transport=httpx.MockTransport(self.lab_runner)), sleep=lambda s: None)}

    def setUp(self):
        super().setUp()
        shutil.copy(CATS / "hands-on.yaml", self.settings.content_dir / "categories" / "hands-on.yaml")

    def try_job(self, text="/try Claude Code 로 차트 만들기"):
        self.tg.say(text)
        self.poll()
        return self.get("/jobs?status=PENDING").json()["items"][0]["id"]

    def stored(self, job_id):
        from app.db.models import Job
        with self.app.state.db() as s:
            return s.get(Job, job_id).input


class PlanTest(unittest.TestCase):
    def test_plan_must_stay_offline_and_ordered(self):
        self.assertEqual(ho.check_plan(PLAN), [])
        bad = json.loads(json.dumps(PLAN))
        bad["tasks"][0]["prompt"] = "https://example.com 을 열어서 요약해 줘"
        bad["tasks"][1]["id"] = "t3"
        problems = ho.check_plan(bad)
        self.assertTrue(any("인터넷" in p for p in problems))
        self.assertTrue(any("차례로" in p for p in problems))


class HandsOnFlowTest(HandsOnCase):
    def test_try_plan_wait_approve_lab_script_scenes(self):
        job_id = self.try_job()
        inp = self.stored(job_id)
        self.assertEqual((inp["review"]["tool"], inp["review"]["planApproved"], inp["uploadApproval"]), ("claude", False, True))

        self.llm.responses = [PLAN]
        self.run_step(job_id, "topic")
        job = self.read(job_id, "job.json")
        self.assertEqual((job["format"], job["targetDurationSec"], job["theme"]), ("review", 70, "noir"))
        self.assertEqual([t["id"] for t in job["review"]["tasks"]], ["t1", "t2"])
        self.assertEqual(self.llm.requests[0]["schema_name"], "research")  # 중계기가 웹 검색을 켜는 이름

        # 승인 전: 기다림 + 계획 버튼, 다음 작업 고르기에서 건너뜀
        self.run_step(job_id, "lab")
        st = self.get(f"/jobs/{job_id}").json()
        self.assertEqual((st["status"], st["blockedBy"]), ("WAITING", "실험 계획 승인 대기 (텔레그램 [실험 시작])"))
        msg = [m for m in self.tg.sent("sendMessage") if "reply_markup" in m][-1]
        self.assertIn("막대 차트를 chart.html 에 그려 줘", msg["text"])
        self.assertIn("인터넷·DNS 차단", msg["text"])
        datas = [b["callback_data"] for row in msg["reply_markup"]["inline_keyboard"] for b in row]
        self.assertEqual(datas, [f"lp:{job_id}:go", f"lp:{job_id}:re", f"lp:{job_id}:drop"])
        self.assertIsNone(self.get("/jobs/next").json()["jobId"])
        self.assertEqual(self.lab_runner.requests, [])  # 아무것도 실행하지 않았다

        self.tg.press(f"lp:{job_id}:go")
        self.poll()
        self.assertTrue(self.stored(job_id)["review"]["planApproved"])
        self.assertEqual(self.get("/jobs/next").json()["jobId"], job_id)

        self.run_step(job_id, "lab")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/lab").json()["status"], "succeeded")
        method, path, auth, body = self.lab_runner.requests[0]
        self.assertEqual((method, path, auth), ("POST", "/runs", "Bearer runner-token-0123456789"))
        self.assertEqual(body["image"], "ghcr.io/x/minibatch-lab:abc1234")
        task = json.loads((self.job_dir(job_id) / "lab" / "t1" / "task.json").read_text())
        self.assertEqual(task["check"], {"fileExists": "chart.html"})
        ev = self.read(job_id, "evidence.json")
        self.assertEqual([(t["id"], t["ok"], t["status"]) for t in ev["tasks"]], [("t1", True, "done"), ("t2", False, "timeout")])
        self.assertEqual(ev["tasks"][0]["previews"][0]["preview"], "lab/t1/previews/chart.html.png")

        self.llm.responses = [SCRIPT] * 3 + [{"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}]  # 길이(부드러운 규칙)로 다시 묻는다
        for step in ("script", "review", "scenes"):
            self.run_step(job_id, step)
            st = self.get(f"/jobs/{job_id}/steps/{step}").json()
            self.assertEqual(st["status"], "succeeded", f"{step}: {st}")
        review_prompt = [r for r in self.llm.requests if r["schema_name"] == "review"][0]["messages"][-1]["content"]
        self.assertIn("실험 기록", review_prompt)
        self.assertIn("실패(timeout)", review_prompt)
        scenes = self.read(job_id, "scenes.json")["scenes"]
        comps = [s["visual"]["component"] for s in scenes]
        self.assertEqual(comps, ["LHookClaim", "LHookReveal", "LWalkthrough", "LArtifact", "LWalkthrough", "LVerdict", "LOutro"])
        walk = scenes[2]["visual"]["props"]
        self.assertEqual(walk["steps"][0]["input"], "막대 차트를 chart.html 에 그려 줘. 값은 3, 5, 2")
        self.assertEqual(walk["steps"][0]["output"], ["Write chart.html", "ls"])
        self.assertEqual(scenes[3]["visual"]["props"]["image"], "lab/t1/previews/chart.html.png")
        for s in scenes:
            self.assertEqual(check_props(s["visual"]["component"], s["visual"]["props"]), [], s["visual"])

    def test_token_in_result_stops_the_video(self):
        self.results = {"t1": {**OK_RESULT, "final": "토큰 sk-ant-oat01-abcdefghijklmn"}, "t2": FAIL_RESULT}
        self.lab_runner.results = self.results
        job_id = self.try_job()
        self.llm.responses = [PLAN]
        self.run_step(job_id, "topic")
        self.tg.press(f"lp:{job_id}:go")
        self.poll()
        self.run_step(job_id, "lab")
        st = self.get(f"/jobs/{job_id}/steps/lab").json()
        self.assertEqual((st["status"], st["kind"]), ("failed", "deterministic"))
        self.assertIn("토큰 모양", st["error"])

    def test_all_failed_makes_no_video(self):
        self.lab_runner.results = {"t1": FAIL_RESULT, "t2": FAIL_RESULT}
        job_id = self.try_job()
        self.llm.responses = [PLAN]
        self.run_step(job_id, "topic")
        self.tg.press(f"lp:{job_id}:go")
        self.poll()
        self.run_step(job_id, "lab")
        st = self.get(f"/jobs/{job_id}").json()
        self.assertEqual(st["status"], "FAILED")
        self.assertIn("모두 실패", self.get(f"/jobs/{job_id}/steps/lab").json()["error"])

    def test_drop_cancels_and_replan_resets(self):
        job_id = self.try_job()
        self.llm.responses = [PLAN]
        self.run_step(job_id, "topic")
        self.run_step(job_id, "lab")
        self.tg.press(f"lp:{job_id}:re")
        self.poll()
        self.assertFalse(self.stored(job_id)["review"]["planApproved"])
        self.assertFalse((self.job_dir(job_id) / "job.json").exists())  # 주제 단계부터 다시
        self.tg.press(f"lp:{job_id}:drop")
        self.poll()
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "CANCELLED")

    def test_script_must_say_failure_and_quote_the_prompt(self):
        ev = {"tasks": [{"id": "t1", "goal": "g", "prompt": "막대 차트를 그려 줘", "ok": False, "status": "timeout", "seconds": 1,
                         "check": {}, "steps": [], "files": [], "previews": [], "final": ""}]}
        d = json.loads(json.dumps(SCRIPT))
        d["tasks"] = [{"lines": [l("먼저 표를 그려 달라고 했어요", "표를"), l("결과 페이지가 잘 열렸어요", "잘")]}]
        problems = ho.check_script(d, evidence=ev, max_sentence=30, target=200)
        self.assertTrue(any("시킨 말의 앞부분" in p for p in problems))
        self.assertTrue(any("실패를 그대로" in p for p in problems))

    def test_other_formats_pass_through_lab(self):
        job_id = self.post("/listicle", {"topic": "깃 기본 명령어", "count": 3}).json()["id"]
        self.run_step(job_id, "topic")
        self.run_step(job_id, "lab")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/lab").json()["status"], "succeeded")
        self.assertEqual(self.lab_runner.requests, [])


class UploadApprovalTest(HandsOnCase):
    pipeline = ["upload"]

    def test_upload_waits_for_approval_with_video_preview(self):
        job_id = self.try_job()
        d = self.job_dir(job_id) / "render"
        d.mkdir(parents=True)
        (d / "final.mp4").write_bytes(b"\x00" * 1000)
        self.run_step(job_id, "upload")
        st = self.get(f"/jobs/{job_id}").json()
        self.assertEqual((st["status"], st["blockedBy"]), ("WAITING", "업로드 승인 대기 (텔레그램 [업로드 승인])"))
        self.assertEqual(len(self.tg.sent("sendVideo")), 1)
        self.assertIn(f"ru:{job_id}".encode(), self.tg.sent("sendVideo")[0]["_raw"])
        self.tg.press(f"ru:{job_id}")
        self.poll()
        self.assertTrue(self.stored(job_id)["uploadApproved"])
        self.assertIsNone(self.get(f"/jobs/{job_id}").json()["blockedBy"])


if __name__ == "__main__":
    unittest.main()
