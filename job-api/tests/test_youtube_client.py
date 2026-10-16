"""YouTube 연결부 (앱 설계 "YouTube 게시"). 실제 Google 대신 httpx.MockTransport 로 요청·응답을 흉내 낸다.

2026-10-16 손 업로드(실행계획 15·15-b)에서 확인한 흐름을 그대로 따른다:
갱신 토큰 → access token, 재개 가능한 업로드(POST 세션 → PUT 파일), 재생목록 만들기·넣기.
"""
import json
import pathlib
import tempfile
import unittest
from datetime import datetime

import httpx

from app.youtube.client import YouTube, YouTubeError, with_disclosure

DISCLOSURE = "AI 도구로 대본과 음성을 만들었습니다"


class FakeGoogle:
    """요청을 기록하고, 경로마다 정해 둔 응답을 돌려준다."""

    def __init__(self):
        self.requests = []
        self.token_status = 200
        self.token_error = None
        self.api_status = {}  # (method, 경로) → (상태, 본문)
        self.playlist_items = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if request.url.host == "oauth2.googleapis.com":
            if self.token_error:
                return httpx.Response(400, json={"error": self.token_error, "error_description": "만료"})
            return httpx.Response(200, json={"access_token": f"at-{len(self.requests)}", "expires_in": 3599})
        if (method, path) in self.api_status:
            status, body = self.api_status.pop((method, path))
            return httpx.Response(status, json=body)
        if method == "POST" and path == "/upload/youtube/v3/videos":
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=S1"})
        if method == "PUT" and path == "/upload/youtube/v3/videos":
            return httpx.Response(201, json={"id": "VID123", "status": {"privacyStatus": "private", "uploadStatus": "uploaded"}})
        if method == "POST" and path == "/youtube/v3/playlists":
            return httpx.Response(200, json={"id": "PL1"})
        if method == "GET" and path == "/youtube/v3/playlistItems":
            return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": v}} for v in self.playlist_items]})
        if method == "POST" and path == "/youtube/v3/playlistItems":
            vid = json.loads(request.content)["snippet"]["resourceId"]["videoId"]
            self.playlist_items.append(vid)
            return httpx.Response(200, json={"snippet": {"position": len(self.playlist_items) - 1}})
        if method == "GET" and path == "/youtube/v3/videos":
            return httpx.Response(200, json={"items": [{"id": "VID123", "snippet": {
                "title": "제목", "description": f"설명\n\n{DISCLOSURE}", "categoryId": "28", "tags": ["AI"]},
                "status": {"uploadStatus": "processed", "privacyStatus": "private", "license": "youtube",
                           "embeddable": True, "publicStatsViewable": True, "madeForKids": False,
                           "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}}]})
        if method == "PUT" and path == "/youtube/v3/videos":
            return httpx.Response(200, json=json.loads(request.content))
        return httpx.Response(404, json={"error": {"message": f"모르는 경로 {method} {path}"}})

    def api_calls(self):
        return [r for r in self.requests if r.url.host != "oauth2.googleapis.com"]


def error_body(reason, message="오류"):
    return {"error": {"code": 403, "message": message, "errors": [{"reason": reason}]}}


class ClientCase(unittest.TestCase):
    def setUp(self):
        self.google = FakeGoogle()
        self.yt = YouTube("cid", "csecret", "rtoken", http=httpx.Client(transport=httpx.MockTransport(self.google)))
        self._tmp = tempfile.TemporaryDirectory()
        self.video = pathlib.Path(self._tmp.name) / "final.mp4"
        self.video.write_bytes(b"fake-mp4-bytes")

    def tearDown(self):
        self._tmp.cleanup()


class TokenTest(ClientCase):
    def test_refreshes_once_and_reuses_access_token(self):
        self.yt.create_playlist("시리즈", "설명")
        self.yt.create_playlist("시리즈2", "설명")

        token_calls = [r for r in self.google.requests if r.url.host == "oauth2.googleapis.com"]
        self.assertEqual(len(token_calls), 1)
        form = dict(httpx.QueryParams(token_calls[0].content.decode()))
        self.assertEqual(form["grant_type"], "refresh_token")
        self.assertEqual(form["refresh_token"], "rtoken")
        self.assertTrue(all(r.headers["Authorization"].startswith("Bearer at-") for r in self.google.api_calls()))

    def test_expired_refresh_token_is_deterministic_with_procedure_hint(self):
        self.google.token_error = "invalid_grant"

        with self.assertRaises(YouTubeError) as cm:
            self.yt.create_playlist("시리즈", "설명")

        self.assertEqual(cm.exception.kind, "deterministic")
        self.assertIn("15번", cm.exception.message)  # 실행계획 15번 ②~④로 다시 발급

    def test_401_refreshes_and_retries_once(self):
        self.google.api_status[("POST", "/youtube/v3/playlists")] = (401, {"error": {"message": "만료"}})

        self.assertEqual(self.yt.create_playlist("시리즈", "설명"), "PL1")

        token_calls = [r for r in self.google.requests if r.url.host == "oauth2.googleapis.com"]
        self.assertEqual(len(token_calls), 2)

    def test_from_files_reads_installed_client_and_token(self):
        root = pathlib.Path(self._tmp.name)
        (root / "client.json").write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b"}}))
        (root / "token.json").write_text(json.dumps({"refresh_token": "c", "scope": "https://www.googleapis.com/auth/youtube"}))

        yt = YouTube.from_files(root / "client.json", root / "token.json")

        self.assertEqual((yt.client_id, yt.refresh_token), ("a", "c"))

    def test_from_files_missing_token_is_deterministic(self):
        root = pathlib.Path(self._tmp.name)
        (root / "client.json").write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b"}}))

        with self.assertRaises(YouTubeError) as cm:
            YouTube.from_files(root / "client.json", root / "없음.json")

        self.assertEqual(cm.exception.kind, "deterministic")


class UploadTest(ClientCase):
    def test_resumable_upload_with_private_status_and_disclosure(self):
        res = self.yt.upload_video(self.video, title="RAG <쉽게>", description="설명입니다", disclosure=DISCLOSURE,
                                   category_id="28", tags=["AI"], synthetic=False)

        self.assertEqual(res["id"], "VID123")
        init, put = self.google.api_calls()
        self.assertEqual(init.url.params["uploadType"], "resumable")
        self.assertEqual(init.url.params["part"], "snippet,status")
        self.assertEqual(init.headers["X-Upload-Content-Type"], "video/mp4")
        self.assertEqual(init.headers["X-Upload-Content-Length"], str(len(b"fake-mp4-bytes")))
        meta = json.loads(init.content)
        self.assertEqual(meta["status"], {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                                          "containsSyntheticMedia": False})
        self.assertEqual(meta["snippet"]["categoryId"], "28")
        self.assertEqual(meta["snippet"]["title"], "RAG 쉽게")  # YouTube 는 < > 를 받지 않는다
        self.assertEqual(meta["snippet"]["description"], f"설명입니다\n\n{DISCLOSURE}")  # 줄을 바꿔 끝에
        self.assertEqual(put.url.params["upload_id"], "S1")
        self.assertEqual(put.content, b"fake-mp4-bytes")

    def test_disclosure_cannot_be_empty(self):
        with self.assertRaises(ValueError):
            self.yt.upload_video(self.video, title="t", description="d", disclosure="  ",
                                 category_id="28", tags=[], synthetic=False)

    def test_quota_reasons_are_quota_kind(self):
        for reason in ("quotaExceeded", "uploadLimitExceeded"):
            with self.subTest(reason=reason):
                self.google.api_status[("POST", "/upload/youtube/v3/videos")] = (403, error_body(reason))

                with self.assertRaises(YouTubeError) as cm:
                    self.yt.upload_video(self.video, title="t", description="d", disclosure=DISCLOSURE,
                                         category_id="28", tags=[], synthetic=False)

                self.assertEqual((cm.exception.kind, cm.exception.reason), ("quota", reason))

    def test_channel_upload_limit_comes_as_400_and_is_quota(self):
        # 2026-10-16 실제: 채널 하루 업로드 한도는 403 이 아니라 400 uploadLimitExceeded 로 왔다
        self.google.api_status[("POST", "/upload/youtube/v3/videos")] = (400, {"error": {
            "code": 400, "message": "The user has exceeded the number of videos they may upload.",
            "errors": [{"reason": "uploadLimitExceeded"}]}})

        with self.assertRaises(YouTubeError) as cm:
            self.yt.upload_video(self.video, title="t", description="d", disclosure=DISCLOSURE,
                                 category_id="28", tags=[], synthetic=False)

        self.assertEqual((cm.exception.kind, cm.exception.reason), ("quota", "uploadLimitExceeded"))

    def test_server_error_is_transient_and_bad_request_is_deterministic(self):
        for status, kind in ((503, "transient"), (400, "deterministic")):
            with self.subTest(status=status):
                self.google.api_status[("POST", "/upload/youtube/v3/videos")] = (status, error_body("x"))

                with self.assertRaises(YouTubeError) as cm:
                    self.yt.upload_video(self.video, title="t", description="d", disclosure=DISCLOSURE,
                                         category_id="28", tags=[], synthetic=False)

                self.assertEqual(cm.exception.kind, kind)

    def test_connection_error_is_transient(self):
        def boom(request):
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json={"access_token": "at", "expires_in": 3599})
            raise httpx.ConnectError("끊김")

        yt = YouTube("cid", "cs", "rt", http=httpx.Client(transport=httpx.MockTransport(boom)))

        with self.assertRaises(YouTubeError) as cm:
            yt.create_playlist("t", "d")
        self.assertEqual(cm.exception.kind, "transient")


class PlaylistAndUpdateTest(ClientCase):
    def test_add_to_playlist_skips_video_already_in_it(self):
        self.yt.add_to_playlist("PL1", "VID123")
        self.yt.add_to_playlist("PL1", "VID123")  # 재시도해도 두 번 넣지 않는다

        self.assertEqual(self.google.playlist_items, ["VID123"])

    def test_create_playlist_is_public_by_default(self):
        self.yt.create_playlist("민지의 AI 적응기", "신입 개발자 이야기")

        body = json.loads(self.google.api_calls()[0].content)
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertEqual(body["snippet"]["title"], "민지의 AI 적응기")

    def test_set_privacy_public_and_scheduled_keep_other_status_values(self):
        self.yt.set_privacy("VID123", "public")
        self.yt.set_privacy("VID123", "private", publish_at=datetime(2026, 10, 20, 9, 0, 0))

        puts = [r for r in self.google.api_calls() if r.method == "PUT"]
        public, scheduled = [json.loads(r.content)["status"] for r in puts]
        # status 를 바꿀 때 빠진 값은 지워진다(공식 문서). 지금 값을 읽어 함께 보낸다. 읽기 전용 값은 빼고
        keep = {"license": "youtube", "embeddable": True, "publicStatsViewable": True}
        self.assertEqual(public, {"privacyStatus": "public", **keep})
        self.assertEqual(scheduled, {"privacyStatus": "private", "publishAt": "2026-10-20T09:00:00Z", **keep})
        self.assertEqual(puts[0].url.params["part"], "status")
        self.assertEqual(json.loads(puts[0].content)["id"], "VID123")

    def test_append_before_disclosure_keeps_disclosure_last(self):
        changed = self.yt.append_to_description("VID123", "▶ 다음 화: https://youtube.com/shorts/NEXT", DISCLOSURE)

        self.assertTrue(changed)
        put = self.google.api_calls()[-1]
        body = json.loads(put.content)
        self.assertEqual(put.url.params["part"], "snippet")
        self.assertEqual(body["snippet"]["description"],
                         f"설명\n\n▶ 다음 화: https://youtube.com/shorts/NEXT\n\n{DISCLOSURE}")
        self.assertEqual(body["snippet"]["categoryId"], "28")  # snippet 을 바꿀 때 제목·카테고리를 함께 보내야 한다

    def test_append_is_skipped_when_text_already_there(self):
        self.google.api_status[("GET", "/youtube/v3/videos")] = (200, {"items": [{"id": "VID123", "snippet": {
            "title": "t", "categoryId": "28", "description": f"설명\n\n▶ 다음 화: X\n\n{DISCLOSURE}"}}]})

        self.assertFalse(self.yt.append_to_description("VID123", "▶ 다음 화: X", DISCLOSURE))
        self.assertEqual([r.method for r in self.google.api_calls()], ["GET"])


class DisclosureTest(unittest.TestCase):
    def test_adds_once_and_strips_angle_brackets(self):
        self.assertEqual(with_disclosure("a <b>", "고지"), "a b\n\n고지")
        self.assertEqual(with_disclosure("a\n\n고지", "고지"), "a\n\n고지")

    def test_long_description_is_cut_but_keeps_disclosure(self):
        text = with_disclosure("가" * 6000, "고지")
        self.assertLessEqual(len(text.encode("utf-8")), 5000)  # 설명란 한도는 5000바이트 (한글 한 글자 3바이트)
        self.assertTrue(text.endswith("\n\n고지"))


if __name__ == "__main__":
    unittest.main()
