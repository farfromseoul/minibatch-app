"""단계 API: 순서 확인, 전역 잠금, 멱등, 비동기 응답, 실패 종류, 재개 주소, 원자적 쓰기."""
import json
import threading

from fastapi.testclient import TestClient

from tests.helpers import AUTH, AppTestCase, FakeStep, StepFailure


class TopicStepTest(AppTestCase):
    def test_topic_step_writes_job_json(self):
        job_id = self.new_job("RAG란?")

        res = self.run_step(job_id, "topic")

        self.assertEqual(res.status_code, 202, res.text)
        job_json = json.loads((self.job_dir(job_id) / "job.json").read_text())
        self.assertEqual(job_json["jobId"], job_id)
        self.assertEqual(job_json["topic"], "RAG란?")
        self.assertEqual(job_json["topicKey"], "rag")
        self.assertEqual(job_json["category"], "ai-it")
        self.assertIsNone(job_json["series"])
        self.assertEqual(job_json["resolution"], {"width": 1080, "height": 1920})


class OrderTest(AppTestCase):
    def test_previous_step_must_be_done(self):
        job_id = self.new_job()

        res = self.run_step(job_id, "script")

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "previous_step_incomplete")
        self.assertEqual(self.steps["script"].runs, 0)

    def test_unknown_step_is_404(self):
        job_id = self.new_job()

        self.assertEqual(self.run_step(job_id, "dance").status_code, 404)


class SuccessFlowTest(AppTestCase):
    def test_step_runs_and_is_recorded(self):
        job_id = self.new_job()
        self.run_step(job_id, "topic")

        res = self.run_step(job_id, "script")
        status = self.get(f"/jobs/{job_id}/steps/script").json()
        job = self.get(f"/jobs/{job_id}").json()

        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.json(), {"status": "started", "step": "script", "attempt": 1})
        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["attempt"], 1)
        self.assertEqual(job["status"], "RUNNING")
        self.assertEqual(job["currentStep"], "script")
        self.assertTrue((self.job_dir(job_id) / "script.json").is_file())
        self.assertEqual([a["path"] for a in job["artifacts"] if a["step"] == "script"], ["script.json"])

    def test_last_step_moves_job_to_review(self):
        job_id = self.new_job()

        self.run_until(job_id, "review")

        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "REVIEW")


class IdempotencyTest(AppTestCase):
    def test_same_inputs_return_already_done(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")

        res = self.run_step(job_id, "script")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "already_done")
        self.assertEqual(self.steps["script"].runs, 1)

    def test_changed_input_reruns(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")
        (self.job_dir(job_id) / "job.json").write_text('{"changed": true}')

        res = self.run_step(job_id, "script")

        self.assertEqual(res.status_code, 202)
        self.assertEqual(self.steps["script"].runs, 2)

    def test_deleted_output_reruns(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")
        (self.job_dir(job_id) / "script.json").unlink()

        self.assertEqual(self.run_step(job_id, "script").status_code, 202)


class FailureKindsTest(AppTestCase):
    def make_steps(self):
        steps = super().make_steps()
        steps["script"] = FakeStep("script", ["job.json"], ["script.json"])
        return steps

    def fail_script_with(self, failure):
        self.steps["script"].fail = failure
        job_id = self.new_job()
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script", resume_url="http://n8n:5678/webhook-waiting/1")
        return job_id

    def test_deterministic_failure_fails_job_with_retry_from(self):
        job_id = self.fail_script_with(StepFailure("deterministic", "대본이 너무 짧다", retry_from="script"))

        status = self.get(f"/jobs/{job_id}/steps/script").json()

        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["kind"], "deterministic")
        self.assertEqual(status["retryFrom"], "script")
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "FAILED")

    def test_quota_failure_waits(self):
        job_id = self.fail_script_with(StepFailure("quota", "할당량", retry_at="2026-10-17T00:00:00"))

        job = self.get(f"/jobs/{job_id}").json()

        self.assertEqual(job["status"], "WAITING")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/script").json()["retryAt"], "2026-10-17T00:00:00")

    def test_unknown_exception_is_transient_and_third_one_fails_job(self):
        job_id = self.fail_script_with(RuntimeError("LLM 서버 응답 없음"))
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "RUNNING")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/script").json()["kind"], "transient")

        self.run_step(job_id, "script")
        self.run_step(job_id, "script")

        self.assertEqual(self.get(f"/jobs/{job_id}/steps/script").json()["attempt"], 3)
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "FAILED")

    def test_failed_job_needs_reset_before_running_again(self):
        job_id = self.fail_script_with(StepFailure("deterministic", "짧다", retry_from="script"))
        self.steps["script"].fail = None

        res = self.run_step(job_id, "script")

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "job_not_runnable")

    def test_error_message_does_not_leak_stack(self):
        job_id = self.fail_script_with(RuntimeError("비밀 아님"))

        status = self.get(f"/jobs/{job_id}/steps/script").json()

        self.assertNotIn("Traceback", status["error"])
        self.assertIn("RuntimeError", status["error"])


class ResumeUrlTest(AppTestCase):
    def test_calls_resume_url_with_result(self):
        job_id = self.new_job()
        self.run_step(job_id, "topic")

        self.run_step(job_id, "script", resume_url="http://n8n:5678/webhook-waiting/abc")

        self.assertEqual(len(self.resumed), 1)
        url, payload = self.resumed[0]
        self.assertEqual(url, "http://n8n:5678/webhook-waiting/abc")
        self.assertEqual(payload["jobId"], job_id)
        self.assertEqual(payload["step"], "script")
        self.assertEqual(payload["status"], "succeeded")

    def test_rejects_resume_url_outside_n8n(self):
        job_id = self.new_job()

        res = self.run_step(job_id, "topic", resume_url="http://evil.example/steal")

        self.assertEqual(res.status_code, 422)


class AtomicWriteTest(AppTestCase):
    def make_steps(self):
        steps = super().make_steps()
        steps["script"] = FakeStep("script", ["job.json"], ["script.json"], partial_then_fail=True)
        return steps

    def test_half_written_output_is_not_left_behind(self):
        job_id = self.new_job()
        self.run_step(job_id, "topic")

        self.run_step(job_id, "script")

        self.assertFalse((self.job_dir(job_id) / "script.json").exists())
        self.assertEqual(list(self.job_dir(job_id).glob("*.tmp*")), [])


class BusyTest(AppTestCase):
    """전역 잠금은 진짜 스레드로 시험한다."""

    def test_second_step_while_running_is_busy(self):
        from app.main import create_app

        gate = threading.Event()
        steps = self.make_steps()
        steps["script"] = FakeStep("script", ["job.json"], ["script.json"], block=gate)
        app = create_app(self.settings, steps=steps, pipeline=self.pipeline,
                         notify=lambda u, p: None, clock=self.clock)
        with TestClient(app) as client:
            a = client.post("/jobs", json={"topic": "가"}, headers=AUTH).json()["id"]
            b = client.post("/jobs", json={"topic": "나"}, headers=AUTH).json()["id"]
            client.post(f"/jobs/{a}/steps/topic", json={}, headers=AUTH)
            app.state.runner.wait_idle(5)
            client.post(f"/jobs/{b}/steps/topic", json={}, headers=AUTH)
            app.state.runner.wait_idle(5)
            first = client.post(f"/jobs/{a}/steps/script", json={}, headers=AUTH)

            second = client.post(f"/jobs/{b}/steps/script", json={}, headers=AUTH)

            gate.set()
            app.state.runner.wait_idle(5)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "busy")
