"""되돌리기(reset)와 재시작 복구."""
from fastapi.testclient import TestClient

from tests.helpers import AppTestCase, FakeStep, StepFailure


class ResetTest(AppTestCase):
    def test_moves_outputs_from_step_onward_and_keeps_earlier(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")

        res = self.post(f"/jobs/{job_id}/reset?from=script")

        self.assertEqual(res.status_code, 200, res.text)
        d = self.job_dir(job_id)
        self.assertTrue((d / "job.json").is_file())
        self.assertFalse((d / "script.json").exists())
        self.assertTrue((d / "attempt-1" / "script.json").is_file())
        self.assertTrue((d / "attempt-1" / "review.json").is_file())
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/script").json()["status"], "not_started")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/topic").json()["status"], "succeeded")
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "RUNNING")

    def test_second_reset_uses_next_attempt_folder(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")
        self.post(f"/jobs/{job_id}/reset?from=script")
        self.run_step(job_id, "script")

        self.post(f"/jobs/{job_id}/reset?from=script")

        self.assertTrue((self.job_dir(job_id) / "attempt-2" / "script.json").is_file())

    def test_failed_job_runs_again_after_reset(self):
        self.steps["script"].fail = StepFailure("deterministic", "짧다", retry_from="script")
        job_id = self.new_job()
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")
        self.steps["script"].fail = None

        self.post(f"/jobs/{job_id}/reset?from=script")
        res = self.run_step(job_id, "script")

        self.assertEqual(res.status_code, 202)
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/script").json()["status"], "succeeded")

    def test_unknown_from_step_is_400(self):
        job_id = self.new_job()

        self.assertEqual(self.post(f"/jobs/{job_id}/reset?from=nope").status_code, 400)

    def test_cannot_reset_approved_job(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})

        res = self.post(f"/jobs/{job_id}/reset?from=script")

        self.assertEqual(res.status_code, 409)


class RecoveryTest(AppTestCase):
    def test_running_attempt_left_by_crash_becomes_transient_failure(self):
        from app.db.models import StepRun
        from app.main import create_app

        job_id = self.new_job()
        self.run_step(job_id, "topic")
        with self.app.state.db() as s:
            s.add(StepRun(job_id=job_id, step="script", attempt=1, status="running",
                          started_at=self.clock()))
            s.commit()
        self.client.__exit__(None, None, None)

        app = create_app(self.settings, steps=self.make_steps(), pipeline=self.pipeline,
                         notify=lambda u, p: None, clock=self.clock)
        with TestClient(app) as client:
            from tests.helpers import AUTH
            status = client.get(f"/jobs/{job_id}/steps/script", headers=AUTH).json()
        self.client.__enter__()

        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["kind"], "transient")
        self.assertIn("재시작", status["error"])


class DegradedTest(AppTestCase):
    def make_steps(self):
        steps = super().make_steps()

        class Degraded(FakeStep):
            def run(self, ctx):
                super().run(ctx)
                ctx.note_degraded("클립 1개를 대체 템플릿으로 바꿈")

        steps["script"] = Degraded("script", ["job.json"], ["script.json"])
        return steps

    def test_degraded_counts_as_success_with_note(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")

        status = self.get(f"/jobs/{job_id}/steps/script").json()

        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["kind"], "degraded")
        self.assertIn("대체 템플릿", status["error"])
