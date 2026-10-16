// 실제 렌더링 (Chrome + FFmpeg). 번들과 브라우저가 든 이미지 안에서만 돈다: RENDER_INTEGRATION=1
// 5초짜리 고정 timeline 과 1초 무음 WAV 로 MP4 를 만들고 길이·해상도·오디오를 확인한다.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";

import { createFileServer } from "../server/app.ts";
import { renderTimeline } from "../server/render.ts";
import { assetBaseFor } from "../server/request.ts";

const enabled = process.env.RENDER_INTEGRATION === "1";
const appDir = path.resolve(import.meta.dirname, "..");

function silentWav(seconds: number, rate = 44100): Buffer {
  const data = Buffer.alloc(rate * seconds * 2);
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + data.length, 4); h.write("WAVE", 8);
  h.write("fmt ", 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write("data", 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

test("고정 timeline 을 MP4 로 렌더한다", { skip: !enabled && "RENDER_INTEGRATION=1 일 때만", timeout: 300_000 }, async () => {
  const dataDir = mkdtempSync(path.join(tmpdir(), "render-int-"));
  const jobDir = path.join(dataDir, "jobs", "j1");
  mkdirSync(path.join(jobDir, "tts"), { recursive: true });
  mkdirSync(path.join(jobDir, "render"), { recursive: true });
  copyFileSync(path.join(appDir, "test", "fixtures", "sample-timeline.json"), path.join(jobDir, "timeline.json"));
  writeFileSync(path.join(jobDir, "tts", "s01.wav"), silentWav(1));

  const files = createFileServer(dataDir).listen(0, "127.0.0.1");
  await new Promise((r) => files.once("listening", r));
  const filePort = (files.address() as AddressInfo).port;
  try {
    const out = path.join(jobDir, "render", "final.mp4");
    const result = await renderTimeline({
      serveUrl: path.join(appDir, "build"),
      timelinePath: path.join(jobDir, "timeline.json"),
      out,
      assetBase: assetBaseFor(path.join(jobDir, "timeline.json"), dataDir, filePort),
      concurrency: 2,
    });
    assert.equal(result.frames, 150);
    assert.ok(existsSync(out));
    assert.deepEqual(readdirSync(path.join(jobDir, "render")), ["final.mp4"]); // 임시 파일이 남지 않는다
    const probe = JSON.parse(execFileSync("npx", ["remotion", "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", out], { cwd: appDir }).toString());
    const video = probe.streams.find((s: any) => s.codec_type === "video");
    const audio = probe.streams.filter((s: any) => s.codec_type === "audio");
    assert.equal(video.width, 1080);
    assert.equal(video.height, 1920);
    assert.equal(audio.length, 1);
    assert.ok(Math.abs(Number(probe.format.duration) - 5) < 0.2, `길이 ${probe.format.duration}`);
    console.log(`렌더 ${result.renderSec}초, 프레임 ${result.frames}, 길이 ${probe.format.duration}초, 코덱 ${video.codec_name}/${audio[0].codec_name}`);
  } finally {
    files.close();
  }
});
