// HTTP 서버: 요청 검사, 한 번에 하나, 오류 형식, 파일 서버. 렌더 함수는 가짜로 바꿔 빠르게 시험한다.
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import type http from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import { createApiServer, createFileServer } from "../server/app.ts";
import { InvalidTimeline } from "../server/render.ts";

const dataDir = mkdtempSync(path.join(tmpdir(), "render-data-"));
mkdirSync(path.join(dataDir, "jobs", "j1", "tts"), { recursive: true });
writeFileSync(path.join(dataDir, "jobs", "j1", "tts", "s01.wav"), "RIFF-fake");
writeFileSync(path.join(dataDir, "secret.txt"), "x");

let mode: "ok" | "invalid" | "crash" | "slow" = "ok";
let release: () => void = () => {};
const calls: any[] = [];
const fakeRender = async (o: any) => {
  calls.push(o);
  if (mode === "invalid") throw new InvalidTimeline(["장면 s02: fromFrame 은 60"]);
  if (mode === "crash") throw new Error("Chrome 이 죽었다");
  if (mode === "slow") await new Promise<void>((r) => (release = r));
  return { path: o.out, frames: 150, renderSec: 1.5 };
};

let api: http.Server;
let files: http.Server;
let base = "";
let fileBase = "";

before(async () => {
  files = createFileServer(dataDir).listen(0, "127.0.0.1");
  await new Promise((r) => files.once("listening", r));
  const filePort = (files.address() as AddressInfo).port;
  api = createApiServer({ dataDir, serveUrl: "/bundle", port: 0, filePort, concurrency: 2, render: fakeRender }).listen(0, "127.0.0.1");
  await new Promise((r) => api.once("listening", r));
  base = `http://127.0.0.1:${(api.address() as AddressInfo).port}`;
  fileBase = `http://127.0.0.1:${filePort}`;
});
after(() => {
  api.close();
  files.close();
});

const post = (body: unknown) => fetch(`${base}/render`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
const good = () => ({ timeline: path.join(dataDir, "jobs/j1/timeline.json"), out: path.join(dataDir, "jobs/j1/render/final.mp4") });

test("healthz", async () => {
  const res = await fetch(`${base}/healthz`);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { status: "ok", busy: false });
});

test("성공하면 결과와 오디오 주소를 넘긴다", async () => {
  mode = "ok";
  const res = await post(good());
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { path: good().out, frames: 150, renderSec: 1.5 });
  const last = calls.at(-1);
  assert.equal(last.concurrency, 2);
  assert.match(last.assetBase, /^http:\/\/127\.0\.0\.1:\d+\/jobs\/j1\/$/);
});

test("데이터 폴더 밖 경로·잘못된 본문은 400", async () => {
  for (const body of [{ timeline: "/etc/t.json", out: good().out }, { timeline: good().timeline }, "문자열"]) {
    const res = await post(body);
    assert.equal(res.status, 400, JSON.stringify(body));
    assert.equal((await res.json()).error.code, "invalid_request");
  }
});

test("타임라인 검증 실패는 422 와 이유", async () => {
  mode = "invalid";
  const res = await post(good());
  assert.equal(res.status, 422);
  assert.match((await res.json()).error.message, /s02/);
});

test("렌더 실패는 500", async () => {
  mode = "crash";
  const res = await post(good());
  assert.equal(res.status, 500);
  assert.match((await res.json()).error.message, /Chrome/);
});

test("렌더링 중에는 두 번째 요청이 409 busy", async () => {
  mode = "slow";
  const first = post(good());
  await new Promise((r) => setTimeout(r, 50));
  const second = await post(good());
  release();
  assert.equal(second.status, 409);
  assert.equal((await second.json()).error.code, "busy");
  assert.equal((await first).status, 200);
});

test("파일 서버는 데이터 폴더 안 파일만 읽기 전용으로 준다", async () => {
  const ok = await fetch(`${fileBase}/jobs/j1/tts/s01.wav`);
  assert.equal(ok.status, 200);
  assert.equal(ok.headers.get("content-type"), "audio/wav");
  const escape = await fetch(`${fileBase}/jobs/j1/..%2F..%2F..%2Fetc%2Fpasswd`);
  assert.ok([403, 404].includes(escape.status));
  const write = await fetch(`${fileBase}/jobs/j1/tts/s01.wav`, { method: "POST", body: "x" });
  assert.equal(write.status, 403);
});
