// 렌더 요청 검사: 경로는 데이터 폴더 안만, 출력은 .mp4 (tts-worker 와 같은 원칙).
import assert from "node:assert/strict";
import { test } from "node:test";

import { assetBaseFor, insideDir, parseRenderRequest } from "../server/request.ts";

test("데이터 폴더 안의 절대 경로만 통과", () => {
  assert.equal(insideDir("/data", "/data/jobs/j1/timeline.json"), true);
  assert.equal(insideDir("/data", "/data"), true);
  assert.equal(insideDir("/data", "/data/../etc/passwd"), false);
  assert.equal(insideDir("/data", "/datax/a"), false);
  assert.equal(insideDir("/data", "jobs/j1/timeline.json"), false);
});

test("올바른 요청", () => {
  const r = parseRenderRequest({ timeline: "/data/jobs/j1/timeline.json", out: "/data/jobs/j1/render/final.mp4" }, "/data");
  assert.deepEqual(r, { ok: true, timeline: "/data/jobs/j1/timeline.json", out: "/data/jobs/j1/render/final.mp4" });
});

test("잘못된 요청은 이유와 함께 거절", () => {
  const cases = [
    null,
    {},
    { timeline: "/etc/x.json", out: "/data/a.mp4" },
    { timeline: "/data/t.json", out: "/tmp/a.mp4" },
    { timeline: "/data/t.json", out: "/data/a.mov" },
    { timeline: 3, out: "/data/a.mp4" },
  ];
  for (const c of cases) {
    const r = parseRenderRequest(c, "/data");
    assert.equal(r.ok, false, JSON.stringify(c));
    assert.ok(!r.ok && r.error.length > 0);
  }
});

test("오디오 주소는 내부 파일 서버의 작업 폴더 주소", () => {
  assert.equal(assetBaseFor("/data/jobs/j1/timeline.json", "/data", 8092), "http://127.0.0.1:8092/jobs/j1/");
});
