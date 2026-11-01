// 실험 과제 스크립트: 가짜 claude(기록된 stream-json 을 내보내고 파일을 만든다)로 기록·판정·토큰 지우기·미리보기를 시험한다.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const lib = await import(path.join(here, "..", "run-task.mjs"));
const TOKEN = "sk-ant-oat01-TESTONLYnotarealtoken000";

function fakeClaude(dir, { sleep = 0, exitCode = 0 } = {}) {
  const p = path.join(dir, "claude");
  const events = [
    { type: "system", subtype: "init", model: "x" },
    { type: "assistant", message: { content: [{ type: "text", text: "만들게요" }, { type: "tool_use", id: "t1", name: "Write", input: { file_path: "/work/workspace/hello.html", content: "<h1>안녕</h1>" } }] } },
    { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "t1", content: "File created" }] } },
    { type: "assistant", message: { content: [{ type: "tool_use", id: "t2", name: "Bash", input: { command: "ls -la\n && echo done" } }] } },
    { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "t2", content: [{ type: "text", text: `hello.html\nleak ${TOKEN}` }] }] } },
    { type: "result", subtype: "success", is_error: false, result: "hello.html 을 만들었어요", total_cost_usd: 0.01, num_turns: 3, duration_ms: 4200 },
  ];
  fs.writeFileSync(p, `#!/usr/bin/env node
const fs = require("fs");
const args = process.argv.slice(2);
fs.writeFileSync("args.json", JSON.stringify(args));
fs.writeFileSync("hello.html", "<h1>안녕</h1>");
fs.writeFileSync("notes.txt", "token is ${TOKEN}\\n");
setTimeout(() => {
  for (const e of ${JSON.stringify(events)}) process.stdout.write(JSON.stringify(e) + "\\n");
  process.exit(${exitCode});
}, ${sleep * 1000});
`);
  fs.chmodSync(p, 0o755);
  return p;
}

function setup(task, opts) {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "lab-"));
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), "bin-"));
  fs.writeFileSync(path.join(work, "task.json"), JSON.stringify(task));
  process.env.LAB_CLAUDE_BIN = fakeClaude(bin, opts);
  process.env.CLAUDE_CODE_OAUTH_TOKEN = TOKEN;
  return work;
}

test("parseEvents: 도구 호출과 결과를 단계로, 마지막 결과", () => {
  const lines = [
    JSON.stringify({ type: "assistant", message: { content: [{ type: "tool_use", id: "a", name: "Bash", input: { command: "npm test" } }] } }),
    JSON.stringify({ type: "user", message: { content: [{ type: "tool_result", tool_use_id: "a", content: "ok 1\nok 2" }] } }),
    JSON.stringify({ type: "assistant", parent_tool_use_id: "x", message: { content: [{ type: "tool_use", id: "b", name: "Bash", input: { command: "sub" } }] } }),
    "not json",
    JSON.stringify({ type: "result", is_error: false, result: "끝", total_cost_usd: 0.1, num_turns: 2 }),
  ];
  const { steps, result } = lib.parseEvents(lines);
  assert.deepEqual(steps, [{ kind: "command", input: "npm test", output: ["ok 1", "ok 2"], error: false }]);
  assert.equal(result.text, "끝");
});

test("redact: 토큰 값과 토큰 모양을 지운다", () => {
  assert.equal(lib.redact(`a ${TOKEN} b`, TOKEN), "a *** b");
  assert.equal(lib.redact("x sk-ant-api03-abcdefghijk y", ""), "x *** y");
});

test("과제 하나: 기록·판정·토큰 지우기·명령 옵션", async () => {
  const work = setup({ prompt: "hello.html 을 만들어 줘", timeoutSec: 30, maxTurns: 5, check: { fileExists: "hello.html" } });
  const r = await lib.main(work);
  assert.equal(r.status, "done");
  assert.equal(r.ok, true);
  assert.equal(r.check.detail, "hello.html 있음");
  assert.deepEqual(r.steps.map((s) => s.input), ["Write hello.html", "ls -la && echo done"]);
  const all = fs.readdirSync(work, { recursive: true }).map((f) => path.join(work, f)).filter((p) => fs.statSync(p).isFile());
  for (const p of all) assert.ok(!fs.readFileSync(p, "utf8").includes("TESTONLY"), `토큰이 남음: ${p}`);
  const args = JSON.parse(fs.readFileSync(path.join(work, "workspace", "args.json"), "utf8"));
  assert.equal(args[args.indexOf("--disallowedTools") + 1], "WebSearch,WebFetch");
  assert.ok(args.includes("--dangerously-skip-permissions"));
  assert.ok(r.files.some((f) => f.path === "hello.html"));
  assert.ok(r.excerpts.some((e) => e.path === "notes.txt" && e.lines[0] === "token is ***"));
});

test("시간 상한을 넘으면 timeout, ok 아님", async () => {
  const work = setup({ prompt: "느린 일", timeoutSec: 10, check: { fileExists: "hello.html" } }, { sleep: 20 });
  const r = await lib.main(work);
  assert.equal(r.status, "timeout");
  assert.equal(r.ok, false);
});

test("미리보기: html 은 브라우저 캡처 (브라우저가 있는 이미지 안에서만)", { skip: !fs.existsSync("/ms-playwright") }, async () => {
  const work = setup({ prompt: "hello", timeoutSec: 30, check: { fileExists: "hello.html" } });
  const r = await lib.main(work);
  assert.equal(r.previews.length, 1);
  assert.ok(fs.statSync(path.join(work, r.previews[0].preview)).size > 1000);
});
