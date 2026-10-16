"""인증, 단계 순서 목록, 상태 확인, 오류 응답 형식."""
import unittest

from tests.helpers import AUTH, AppTestCase


class AuthTest(AppTestCase):
    def test_requires_bearer_token(self):
        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic x"}):
            with self.subTest(headers=headers):
                res = self.client.get("/pipeline", headers=headers)

                self.assertEqual(res.status_code, 401)
                self.assertEqual(res.json()["error"]["code"], "unauthorized")

    def test_healthz_needs_no_token(self):
        res = self.client.get("/healthz")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["checks"]["db"])
        self.assertIn("disk_free_gb", body["checks"])


class PipelineTest(AppTestCase):
    def test_returns_step_order(self):
        res = self.client.get("/pipeline", headers=AUTH)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"steps": ["topic", "script", "review"]})


class DefaultPipelineTest(unittest.TestCase):
    def test_design_order(self):
        from app.pipeline.pipeline import PIPELINE

        self.assertEqual(PIPELINE, ["topic", "script", "review", "scenes", "tts", "timeline",
                                    "visuals", "render", "qc", "upload"])


class ErrorFormatTest(AppTestCase):
    def test_unknown_job_uses_error_envelope(self):
        res = self.get("/jobs/short-20990101-001")

        self.assertEqual(res.status_code, 404)
        self.assertEqual(set(res.json()), {"error"})
        self.assertEqual(res.json()["error"]["code"], "job_not_found")

    def test_validation_error_uses_error_envelope(self):
        res = self.post("/jobs", {"topic": ""})

        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "invalid_request")


class StartupTest(unittest.TestCase):
    def test_refuses_to_start_without_token_file(self):
        import pathlib
        import tempfile

        from fastapi.testclient import TestClient

        from app.core.config import Settings
        from app.main import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            s = Settings(data_dir=root / "data", db_path=root / "db.sqlite",
                         token_file=root / "missing", content_dir=root)
            with self.assertRaises(RuntimeError):
                with TestClient(create_app(s)):
                    pass


if __name__ == "__main__":
    unittest.main()
