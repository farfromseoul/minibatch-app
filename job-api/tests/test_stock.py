"""스톡 영상 (2026-10-17: 레터박스 스타일 가운데 판에 실사 영상, Pixabay).

Pixabay API 규칙: 같은 검색은 24시간 캐시, 받아서 우리 쪽에 저장(영구 링크 금지), 대량 다운로드 금지, 출처 표시.
기본 User-Agent 는 Cloudflare 가 막는다(오류 1010, 2026-10-17 실제) → 우리 User-Agent 를 보낸다.
"""
import json
import pathlib
import shutil
import tempfile
import unittest

import httpx

from app.pipeline.steps.media import RenderStep, VisualsStep
from app.stock.pixabay import Pixabay, StockError
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import AppTestCase

REAL_CATEGORY = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories" / "ai-it.yaml"


def hit(i, duration, low=False, width=1280):
    return {"id": i, "duration": duration, "tags": "t", "user": f"user{i}", "pageURL": f"https://pixabay.com/videos/{i}/",
            "isLowQuality": low, "type": "film", "downloads": 100 - i,
            "videos": {"medium": {"url": f"https://cdn.pixabay.com/video/{i}_medium.mp4", "width": width, "height": 720, "size": 3_000_000},
                       "large": {"url": f"https://cdn.pixabay.com/video/{i}_large.mp4", "width": 1920, "height": 1080, "size": 30_000_000}}}


def img(i, width=1920, height=1280):
    return {"id": i, "tags": "data, center", "user": f"photo{i}", "pageURL": f"https://pixabay.com/photos/{i}/",
            "imageWidth": width, "imageHeight": height, "largeImageURL": f"https://cdn.pixabay.com/photo/{i}_1280.jpg",
            "webformatURL": f"https://cdn.pixabay.com/photo/{i}_640.jpg"}


class FakePixabayServer:
    def __init__(self, hits):
        self.hits, self.requests, self.status = hits, [], 200

    def __call__(self, request):
        self.requests.append(request)
        if request.url.host == "cdn.pixabay.com":
            return httpx.Response(200, content=b"mp4-bytes-" + request.url.path.encode())
        if self.status != 200:
            return httpx.Response(self.status, text="error")
        return httpx.Response(200, json={"total": len(self.hits), "hits": self.hits})


class PixabayClientTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.now = [1000.0]
        self.server = FakePixabayServer([hit(1, 4), hit(2, 20, low=True), hit(3, 12), hit(4, 30, width=640)])
        self.px = Pixabay("KEY-NOT-SECRET", self.root / "cache", http=httpx.Client(transport=httpx.MockTransport(self.server)),
                          now=lambda: self.now[0])

    def tearDown(self):
        self._tmp.cleanup()

    def test_search_sends_user_agent_and_filters(self):
        clips = self.px.search("server room", min_seconds=8)

        req = self.server.requests[0]
        self.assertTrue(req.headers["User-Agent"].startswith("minibatch-job-api"))
        self.assertEqual((req.url.params["video_type"], req.url.params["safesearch"]), ("film", "true"))
        # 저품질(2)·폭 1280 미만(4)은 빼고, 장면 길이 이상인 것(3)을 앞에
        self.assertEqual([c.id for c in clips], [3, 1])
        self.assertEqual((clips[0].user, clips[0].url), ("user3", "https://cdn.pixabay.com/video/3_medium.mp4"))

    def test_image_search_asks_horizontal_photos_and_uses_large_image(self):
        self.server.hits = [img(51), img(52, width=800), img(53, width=1200, height=1600)]

        pics = self.px.search_images("data center")

        req = self.server.requests[0]
        self.assertEqual(req.url.path, "/api/")
        self.assertEqual({k: req.url.params[k] for k in ("image_type", "orientation", "safesearch", "min_width")},
                         {"image_type": "photo", "orientation": "horizontal", "safesearch": "true", "min_width": "1280"})
        # 폭 1280 미만(52), 세로가 더 긴 것(53)은 뺀다
        self.assertEqual([p.id for p in pics], [51])
        self.assertEqual((pics[0].url, pics[0].kind, pics[0].user), ("https://cdn.pixabay.com/photo/51_1280.jpg", "image", "photo51"))

    def test_image_and_video_searches_are_cached_separately(self):
        self.px.search("data center", 8)
        self.server.hits = [img(51)]
        self.px.search_images("data center")

        self.assertEqual(len(self.server.requests), 2)

    def test_relevance_order_is_kept_within_long_enough_clips(self):
        self.server.hits = [hit(11, 20), hit(12, 30), hit(13, 25)]  # API 가 관련도 순으로 준다 (downloads 는 13 이 가장 적음)

        self.assertEqual([c.id for c in self.px.search("robot arm", 8)], [11, 12, 13])

    def test_clips_whose_tags_match_query_words_come_first(self):
        h1, h2 = hit(21, 20), hit(22, 20)
        h1["tags"], h2["tags"] = "woodwork, hands, craft", "robot, arm, factory, industry"
        self.server.hits = [h1, h2]  # 관련도는 21 이 앞이지만 태그가 검색어와 맞는 것은 22 (2026-10-17 실제: 목공 영상)

        self.assertEqual([c.id for c in self.px.search("robot arm factory", 8)], [22, 21])

    def test_same_query_is_cached_for_24_hours(self):
        self.px.search("server room", 8)
        self.px.search("server room", 8)
        self.now[0] += 24 * 3600 + 1
        self.px.search("server room", 8)

        self.assertEqual(len(self.server.requests), 2)
        self.assertNotIn("KEY-NOT-SECRET", "".join(p.read_text() for p in (self.root / "cache").glob("*.json")))  # 키는 캐시에 안 남긴다

    def test_rate_limit_is_transient(self):
        self.server.status = 429

        with self.assertRaises(StockError) as cm:
            self.px.search("server room", 8)
        self.assertEqual(cm.exception.kind, "transient")

    def test_download_saves_file(self):
        clip = self.px.search("server room", 8)[0]
        dest = self.root / "clips" / "s01.mp4"

        self.px.download(clip, dest)

        self.assertEqual(dest.read_bytes(), b"mp4-bytes-/video/3_medium.mp4")


SCENES = {"scenes": [{"id": "s01", "lines": ["벡터 DB 는 무엇일까요?"], "visual": {"component": "TitleReveal"}},
                     {"id": "s02", "lines": ["데이터를 숫자로 바꿉니다."], "visual": {"component": "FlowDiagram"}}]}


def timeline(theme):
    return {"schemaVersion": 1, "fps": 30, "width": 1080, "height": 1920, "durationInFrames": 600, "theme": theme,
            "scenes": [{"id": "s01", "fromFrame": 0, "durationInFrames": 300, "animationPreset": "fade",
                        "visual": {"type": "template", "component": "TitleReveal", "props": {"title": "벡터 DB"}}},
                       {"id": "s02", "fromFrame": 300, "durationInFrames": 300, "animationPreset": "fade",
                        "visual": {"type": "template", "component": "FlowDiagram", "props": {}}}],
            "audio": [], "captions": [], "bgm": None}


class FakeStock:
    def __init__(self, fail=None):
        from app.stock.pixabay import Clip
        self.fail, self.queries, self.image_queries = fail, [], []
        self.videos = [Clip(id=7, url="https://cdn/x.mp4", width=1280, height=720, duration=15.0, user="kim", page="https://pixabay.com/videos/7/",
                            tags="server, room, data, center, rack, lights")]
        self.images = [Clip(id=70, url="https://cdn/p.jpg", width=1920, height=1280, duration=0.0, user="lee",
                            page="https://pixabay.com/photos/70/", kind="image", tags="data, center, aisle, server, rack, lights")]

    def search(self, q, min_seconds):
        self.queries.append((q, min_seconds))
        if self.fail:
            raise self.fail
        return list(self.videos)

    def search_images(self, q):
        self.image_queries.append(q)
        if self.fail:
            raise self.fail
        return list(self.images)

    def download(self, clip, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"clip")


class Write:
    def __init__(self, name, inputs, files):
        self.name, self.inputs, self.outputs, self.files = name, inputs, list(files), files

    def run(self, ctx):
        for rel, content in self.files.items():
            ctx.write_json(rel, content)


class StockCase(AppTestCase):
    pipeline = ["topic", "scenes", "timeline", "visuals"]
    theme = "letterbox"

    def setUp(self):
        self.llm = FakeLlm()
        self.stock = FakeStock()
        super().setUp()
        cat = REAL_CATEGORY.read_text(encoding="utf-8")
        (self.settings.content_dir / "categories" / "ai-it.yaml").write_text(cat, encoding="utf-8")

    def make_providers(self):
        reg = FakeRegistry(self.llm)
        reg.stock = {"engine": "pixabay", "max_per_video": 6}
        return reg

    def make_steps(self):
        return {"scenes": Write("scenes", ["job.json"], {"scenes.json": SCENES}),
                "timeline": Write("timeline", ["scenes.json"], {"timeline.json": timeline(self.theme)}),
                "visuals": VisualsStep(stock_factory=lambda settings, cfg: self.stock)}

    def visuals(self, job_id):
        return json.loads((self.job_dir(job_id) / "visuals.json").read_text())


class VisualsStockTest(StockCase):
    def test_llm_picks_queries_and_clips_are_downloaded(self):
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "server room"}, {"scene": "s02", "query": ""}]}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        v = self.visuals(job_id)
        self.assertEqual([(s["id"], s["source"]) for s in v["scenes"]], [("s01", "stock"), ("s02", "template")])
        self.assertEqual(v["scenes"][0]["path"], "clips/s01.mp4")
        self.assertEqual(v["credits"], [{"site": "Pixabay", "user": "kim", "page": "https://pixabay.com/videos/7/"}])
        self.assertEqual(self.stock.queries, [("server room", 10.0)])  # 장면 300프레임 = 10초
        self.assertTrue((self.job_dir(job_id) / "clips" / "s01.mp4").is_file())
        self.assertEqual(self.llm.requests[0]["messages"][0]["role"], "system")

    def test_stock_failure_falls_back_to_template(self):
        from app.stock.pixabay import StockError
        self.stock.fail = StockError("transient", "429")
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "server room"}, {"scene": "s02", "query": ""}]}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        st = self.get(f"/jobs/{job_id}/steps/visuals").json()
        self.assertEqual((st["status"], st["kind"]), ("succeeded", "degraded"))  # 영상은 계속 만든다
        self.assertEqual([s["source"] for s in self.visuals(job_id)["scenes"]], ["template", "template"])


class VisualsVarietyTest(StockCase):
    """2026-10-19 사용자 피드백: 커버가 다 비슷하다(노트북 키보드·휴대폰). 최근 쓴 소재·검색어를 피하고, 이미지도 쓴다"""

    def history(self):
        return self.settings.data_dir / "cache" / "pixabay" / "used.json"

    def test_image_kind_downloads_a_photo(self):
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "data center aisle", "kind": "image"},
                                           {"scene": "s02", "query": "", "kind": "video"}]}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        s01 = self.visuals(job_id)["scenes"][0]
        self.assertEqual((s01["source"], s01["mediaType"], s01["path"]), ("stock", "image", "clips/s01.jpg"))
        self.assertEqual(self.stock.image_queries, ["data center aisle"])
        self.assertEqual(self.stock.queries, [])
        self.assertTrue((self.job_dir(job_id) / "clips" / "s01.jpg").is_file())

    def test_video_without_results_falls_back_to_image(self):
        self.stock.videos = []
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "server rack lights", "kind": "video"},
                                           {"scene": "s02", "query": "", "kind": "video"}]}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        self.assertEqual(self.visuals(job_id)["scenes"][0]["mediaType"], "image")

    def test_recently_used_material_is_skipped(self):
        from app.stock.pixabay import Clip
        self.stock.videos.append(Clip(id=8, url="https://cdn/y.mp4", width=1280, height=720, duration=15.0, user="park",
                                      page="https://pixabay.com/videos/8/", tags="server, room"))
        self.history().parent.mkdir(parents=True, exist_ok=True)
        self.history().write_text(json.dumps([{"id": 7, "kind": "video", "query": "laptop keyboard typing", "at": "2026-10-18"}]))
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "server room", "kind": "video"},
                                           {"scene": "s02", "query": "", "kind": "video"}]}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        self.assertIn("pixabay.com/videos/8/", self.visuals(job_id)["scenes"][0]["credit"]["page"])  # 7 은 최근에 썼다
        self.assertIn("laptop keyboard typing", self.llm.requests[0]["messages"][-1]["content"])  # 최근 검색어를 알려 겹치지 않게
        used = json.loads(self.history().read_text())
        self.assertEqual([(u["id"], u["query"]) for u in used][-1], (8, "server room"))

    def test_material_whose_tags_do_not_match_the_query_is_not_used(self):
        # 2026-10-19 사용자: 소재는 대본 설명과 맞아야 한다. 태그가 검색어와 하나도 안 맞으면 쓰지 않고 도식으로 둔다
        from app.stock.pixabay import Clip
        self.stock.videos = [Clip(id=9, url="https://cdn/z.mp4", width=1280, height=720, duration=15.0, user="choi",
                                  page="https://pixabay.com/videos/9/", tags="chimney, smoke, sky")]
        self.stock.images = []
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "robot arm factory", "kind": "video"},
                                           {"scene": "s02", "query": "", "kind": "video"}]}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        self.assertEqual([s["source"] for s in self.visuals(job_id)["scenes"]], ["template", "template"])

    def test_query_prompt_asks_for_varied_concrete_material(self):
        self.llm.responses = [{"queries": []}]
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        system = self.llm.requests[0]["messages"][0]["content"]
        self.assertIn("image", system)
        self.assertIn("노트북", system)  # 흔한 노트북·키보드 영상은 그 내용일 때만
        self.assertIn("관련", system)  # 장면 설명과 맞는 소재만, 없으면 빈 문자열(도식)
        # 2026-10-19 실제: '관련 없으면 비워라' 만 강조하자 Codex(low)가 7장면을 모두 비웠다. 목표 개수를 함께 둔다
        self.assertIn("절반 이상", system)
        self.assertIn("후킹(첫 장면)에는 반드시", system)


class VisualsCardThemeTest(StockCase):
    theme = "default"

    def test_other_themes_do_not_use_stock(self):
        job_id = self.new_job()

        self.run_until(job_id, "visuals")

        self.assertEqual(self.llm.requests, [])
        self.assertEqual(self.stock.queries, [])


class RenderTimelineTest(StockCase):
    pipeline = ["topic", "scenes", "timeline", "visuals", "render"]

    def make_steps(self):
        steps = super().make_steps()
        self.posted = []
        test = self

        class Render(RenderStep):
            def _post_render(self, ctx, timeline_path, out):
                test.posted.append(json.loads(pathlib.Path(timeline_path).read_text()))
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"mp4")
                return {}

        steps["render"] = Render(normalize=lambda src, dst, **kw: shutil.copy(src, dst) or {})
        return steps

    def test_render_gets_media_and_header(self):
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "server room"}, {"scene": "s02", "query": ""}]}]
        job_id = self.new_job("벡터 데이터베이스란?")

        self.run_until(job_id, "render")

        t = self.posted[0]
        self.assertEqual(t["scenes"][0]["media"], {"type": "video", "src": "clips/s01.mp4", "durationInFrames": 450})
        self.assertNotIn("media", t["scenes"][1])
        self.assertEqual(t["header"]["title"], "벡터 데이터베이스란?")
        self.assertNotIn("brand", t["header"])  # 영상 위 브랜드 글자는 넣지 않는다 (2026-10-18 사용자 피드백)
        self.assertTrue((self.job_dir(job_id) / "render.timeline.json").is_file())

    def test_image_media_goes_to_render_without_duration(self):
        self.llm.responses = [{"queries": [{"scene": "s01", "query": "data center", "kind": "image"}, {"scene": "s02", "query": "", "kind": "video"}]}]
        job_id = self.new_job("벡터 데이터베이스란?")

        self.run_until(job_id, "render")

        self.assertEqual(self.posted[0]["scenes"][0]["media"], {"type": "image", "src": "clips/s01.jpg"})


class CategoryThemeTest(StockCase):
    def test_topic_step_takes_theme_from_category(self):
        job_id = self.new_job()

        self.run_step(job_id, "topic")

        self.assertEqual(json.loads((self.job_dir(job_id) / "job.json").read_text())["theme"], "letterbox")
