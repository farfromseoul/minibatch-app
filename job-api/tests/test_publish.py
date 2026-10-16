"""승인 → 공개 전환 (아키텍처 흐름 2, D9, 성공 기준 5) 과 앞 화 설명란 다음 화 링크 (D26 ④)."""
from datetime import datetime

from app.db.models import Publication
from app.youtube.client import YouTubeError
from tests.test_qc_upload import DISCLOSURE, PublishCase


class PublishTest(PublishCase):
    def uploaded_job(self, topic="RAG란?"):
        job_id = self.new_job(topic)
        self.run_until(job_id, "upload")
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "REVIEW")
        return job_id

    def test_approve_publishes_immediately(self):
        job_id = self.uploaded_job()

        res = self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})

        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "PUBLISHED")
        self.assertEqual(res.json()["publish"], {"ok": True, "status": "PUBLISHED", "warnings": []})
        self.assertEqual(self.yt.named("set_privacy"), [{"video": "VID1", "privacy": "public", "publish_at": None}])
        pub = self.get(f"/jobs/{job_id}").json()["publication"]
        self.assertEqual((pub["visibility"], pub["approvedBy"]), ("public", "운영자"))

    def test_approve_with_future_time_schedules(self):
        job_id = self.uploaded_job()  # 시계: 2026-10-16 01:00 UTC

        res = self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자", "publishAt": "2026-10-17T09:00:00+09:00"})

        self.assertEqual(res.json()["status"], "SCHEDULED")
        self.assertEqual(self.yt.named("set_privacy"),
                         [{"video": "VID1", "privacy": "private", "publish_at": datetime(2026, 10, 17, 0, 0, 0)}])
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["publication"]["visibility"], "scheduled")

    def test_youtube_failure_keeps_approval_and_publish_retries(self):
        job_id = self.uploaded_job()
        self.yt.fail["set_privacy"] = YouTubeError("transient", "연결 실패")

        res = self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})

        self.assertEqual(res.status_code, 200)  # 승인은 사람의 결정이라 기록이 남는다
        self.assertEqual(res.json()["status"], "APPROVED")
        self.assertEqual((res.json()["publish"]["ok"], res.json()["publish"]["kind"]), (False, "transient"))

        again = self.post(f"/jobs/{job_id}/publish")

        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["status"], "PUBLISHED")

    def test_publish_failure_answers_502_with_kind(self):
        job_id = self.uploaded_job()
        self.yt.fail["set_privacy"] = YouTubeError("transient", "x")
        self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})
        self.yt.fail["set_privacy"] = YouTubeError("quota", "할당량", 403, "quotaExceeded")

        res = self.post(f"/jobs/{job_id}/publish")

        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "youtube_quota")

    def test_publish_requires_approved_status(self):
        job_id = self.uploaded_job()

        res = self.post(f"/jobs/{job_id}/publish")

        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.yt.named("set_privacy"), [])

    def test_no_approval_record_blocks_youtube_call_even_if_status_says_approved(self):
        # 상태가 어떻게 바뀌었든, 승인 기록(approved_at)이 없으면 YouTube 를 부르지 않는다 (성공 기준 5)
        job_id = self.uploaded_job()
        self.yt.fail["set_privacy"] = YouTubeError("transient", "x")
        self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})
        with self.app.state.db() as s:
            s.get(Publication, job_id).approved_at = None
            s.commit()

        res = self.post(f"/jobs/{job_id}/publish")

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_approved")
        self.assertEqual(self.yt.named("set_privacy"), [])

    def test_approve_without_uploaded_video_only_records(self):
        job_id = self.new_job()
        self.run_until(job_id, "qc")
        with self.app.state.db() as s:  # 업로드 전 상태를 REVIEW 로 만든다 (업로드 없는 파이프라인 흉내)
            from app.db.models import Job
            s.get(Job, job_id).status = "REVIEW"
            s.commit()

        res = self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})

        self.assertEqual(res.json()["status"], "APPROVED")
        self.assertEqual(res.json()["publish"], {"ok": False, "skipped": "업로드된 영상이 없다"})


class SeriesLinkTest(PublishCase):
    def episode(self):
        res = self.post("/jobs", {"seriesId": "ai-office"})
        self.assertEqual(res.status_code, 201, res.text)
        job_id = res.json()["id"]
        self.run_until(job_id, "upload")
        return job_id

    def setUp(self):
        super().setUp()
        self.post("/series", {"key": "ai-office", "title": "민지의 AI 적응기", "bible": {"premise": "p"},
                              "episodes": [{"number": 1, "title": "배우기", "outline": "a"},
                                           {"number": 2, "title": "판단하기", "outline": "b"}]})

    def test_publishing_next_episode_links_it_from_previous_description(self):
        ep1 = self.episode()
        self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"})
        self.assertEqual(self.yt.named("append_to_description"), [])  # 1화는 앞 화가 없다
        ep2 = self.episode()

        res = self.post(f"/jobs/{ep2}/approve", {"approvedBy": "운영자"})

        self.assertEqual(res.json()["status"], "PUBLISHED")
        (link,) = self.yt.named("append_to_description")
        self.assertEqual(link["video"], "VID1")
        self.assertEqual(link["text"], "▶ 다음 화: 2화 판단하기\nhttps://www.youtube.com/shorts/VID2")
        self.assertEqual(link["disclosure"], DISCLOSURE)

    def test_link_failure_is_a_warning_not_a_publish_failure(self):
        ep1 = self.episode()
        self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"})
        ep2 = self.episode()
        self.yt.fail["append_to_description"] = YouTubeError("transient", "설명란 수정 실패")

        res = self.post(f"/jobs/{ep2}/approve", {"approvedBy": "운영자"})

        self.assertEqual(res.json()["status"], "PUBLISHED")
        self.assertIn("1화", res.json()["publish"]["warnings"][0])
