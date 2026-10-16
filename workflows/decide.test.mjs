// n8n 생산 워크플로의 "다음 행동" 판단 (Code 노드에 그대로 들어간다). node --test 로 확인
import test from "node:test";
import assert from "node:assert/strict";
import { decide } from "./decide.mjs";

const P = ["topic", "script", "review", "upload"];
const NOW = new Date("2026-10-16T10:00:00Z");
const job = (status, steps = [], events = []) => ({ id: "short-1", topic: "주제", status, steps, events });
const run = (step, status, extra = {}) => ({ step, attempt: 1, status, kind: null, retryFrom: null, retryAt: null, error: null, ...extra });
const opt = { now: NOW, runIndex: 0, maxRuns: 360, maxResets: 2 };

test("처음이면 첫 단계를 바로 요청", () => {
  assert.deepEqual(decide(job("PENDING"), P, opt), { action: "run", step: "topic", waitSec: 5 });
});

test("성공한 단계는 건너뛰고 다음 단계", () => {
  const j = job("RUNNING", [run("topic", "succeeded"), run("script", "succeeded")]);
  assert.equal(decide(j, P, opt).step, "review");
});

test("도는 중이면 10초 뒤 다시 본다", () => {
  const j = job("RUNNING", [run("topic", "succeeded"), run("script", "running")]);
  assert.deepEqual(decide(j, P, opt), { action: "poll", step: "script", waitSec: 10 });
});

test("REVIEW 면 끝", () => {
  assert.equal(decide(job("REVIEW"), P, opt).action, "done");
});

test("일시적 실패는 60초 뒤 같은 단계 (job-api 가 3번째면 FAILED 로 바꾼다)", () => {
  const j = job("RUNNING", [run("topic", "succeeded"), run("script", "failed", { kind: "transient", error: "LM Studio 응답 없음" })]);
  assert.deepEqual(decide(j, P, opt), { action: "run", step: "script", waitSec: 60 });
});

test("결정적 실패는 retryFrom 으로 되돌리기, 두 번까지", () => {
  const f = run("review", "failed", { kind: "deterministic", retryFrom: "script", error: "길이 72초" });
  const j = job("FAILED", [run("topic", "succeeded"), run("script", "succeeded"), f]);
  assert.deepEqual(decide(j, P, opt), { action: "reset", from: "script", waitSec: 2, message: "review 결정적 실패 → script 부터 다시 (1번째): 길이 72초" });
  const twice = job("FAILED", j.steps, [{ reason: "reset from=script" }, { reason: "reset from=script" }]);
  const d = decide(twice, P, opt);
  assert.equal(d.action, "fail");
  assert.match(d.message, /되돌리기 2번 뒤에도/);
});

test("되돌릴 곳이 없는 실패·일시적 실패 한도 초과는 알림", () => {
  const j = job("FAILED", [run("topic", "succeeded"), run("script", "failed", { kind: "transient", error: "3번째" })]);
  const d = decide(j, P, opt);
  assert.equal(d.action, "fail");
  assert.match(d.message, /script/);
});

test("갱신 토큰 만료로 upload 실패하면 15번 안내가 메시지에 남는다", () => {
  const steps = P.slice(0, 3).map((s) => run(s, "succeeded"));
  steps.push(run("upload", "failed", { kind: "deterministic", error: "갱신 토큰을 쓸 수 없다(invalid_grant) 실행계획 15번" }));
  const d = decide(job("FAILED", steps), P, opt);
  assert.equal(d.action, "fail");
  assert.match(d.message, /15번/);
});

test("할당량 대기는 다시 할 시각 전이면 멈추고, 지나면 다시 요청", () => {
  const steps = P.slice(0, 3).map((s) => run(s, "succeeded"));
  steps.push(run("upload", "failed", { kind: "quota", retryAt: "2026-10-17T07:05:00Z" }));
  const before = decide(job("WAITING", steps), P, opt);
  assert.equal(before.action, "stop");
  assert.match(before.message, /2026-10-17T07:05:00Z/);
  const after = decide(job("WAITING", steps), P, { ...opt, now: new Date("2026-10-17T08:00:00Z") });
  assert.deepEqual(after, { action: "run", step: "upload", waitSec: 5 });
});

test("반려·이미 승인된 작업은 손대지 않는다", () => {
  assert.equal(decide(job("REJECTED"), P, opt).action, "stop");
  assert.equal(decide(job("PUBLISHED"), P, opt).action, "stop");
});

test("너무 오래 돌면 알림 (n8n 실행이 끝없이 이어지지 않게)", () => {
  const j = job("RUNNING", [run("topic", "running")]);
  const d = decide(j, P, { ...opt, runIndex: 360 });
  assert.equal(d.action, "fail");
  assert.match(d.message, /오래/);
});
