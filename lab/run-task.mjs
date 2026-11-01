// 실습 리뷰 실험 과제 하나 (실습리뷰쇼츠 아키텍처 "실행기와 파일"). 실험 컨테이너 안에서 돈다.
// /work/task.json 을 읽어 Claude Code 를 무인으로 돌리고, 기록(events.jsonl)·만든 파일·미리보기·판정을 /work/result.json 에 남긴다.
// 끝나기 전에 로그인 토큰 문자열을 모든 출력에서 지운다(영상·텔레그램으로 나가는 것은 이 결과뿐이다).
// 시간 상한은 바깥 실행기도 걸지만(docker kill), 여기서도 걸어 결과를 남긴다.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const WORK = process.env.LAB_WORK_DIR || "/work";
const TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN";
const TOKEN_SHAPE = /sk-ant-[A-Za-z0-9_-]{8,}/g; // 토큰 모양(추정). 실제 값과 같은 문자열은 따로 지운다
const SKIP_DIRS = new Set([".claude", "node_modules", ".git", ".cache", "__pycache__"]);
const TEXT_EXT = new Set([".txt", ".md", ".py", ".js", ".mjs", ".ts", ".json", ".csv", ".html", ".css", ".svg", ".yaml", ".yml", ".sh", ".sql", ".xml"]);
const MAX_LINE = 120;
const MAX_FILES = 40;

/** stream-json 줄들 → 화면에 쓸 단계(에이전트가 실제로 한 일)와 마지막 결과 */
export function parseEvents(lines) {
  const steps = [];
  const byId = new Map();
  let result = null;
  for (const line of lines) {
    let ev;
    try {
      ev = JSON.parse(line);
    } catch {
      continue;
    }
    if (ev.type === "result") {
      result = { isError: !!ev.is_error, text: String(ev.result ?? ""), costUsd: ev.total_cost_usd ?? null, turns: ev.num_turns ?? null,
        durationMs: ev.duration_ms ?? null, subtype: ev.subtype ?? null };
      continue;
    }
    if (ev.parent_tool_use_id) continue; // 서브에이전트 안의 일은 빼고 본 대화만
    const content = ev.message?.content;
    if (!Array.isArray(content)) continue;
    for (const c of content) {
      if (ev.type === "assistant" && c.type === "tool_use") {
        const step = toolStep(c.name, c.input || {});
        if (step) {
          steps.push(step);
          byId.set(c.id, step);
        }
      } else if (ev.type === "user" && c.type === "tool_result") {
        const step = byId.get(c.tool_use_id);
        if (step) {
          step.output = outputLines(c.content);
          step.error = !!c.is_error;
        }
      }
    }
  }
  return { steps, result };
}

function toolStep(name, input) {
  if (name === "Bash") return { kind: "command", input: oneLine(input.command), output: [] };
  if (name === "Write") return { kind: "file", input: `Write ${rel(input.file_path)}`, output: [] };
  if (name === "Edit" || name === "MultiEdit") return { kind: "file", input: `Edit ${rel(input.file_path)}`, output: [] };
  if (name === "Read") return { kind: "read", input: `Read ${rel(input.file_path)}`, output: [] };
  if (name === "Skill") return { kind: "skill", input: `Skill ${input.skill ?? input.name ?? ""}`.trim(), output: [] };
  if (name === "TodoWrite") return null;
  return { kind: "tool", input: name, output: [] };
}

const rel = (p) => String(p ?? "").replace(/^\/work\/workspace\/?/, "") || ".";
const oneLine = (s) => String(s ?? "").replace(/\s+/g, " ").trim().slice(0, 200);

export function outputLines(content) {
  const text = Array.isArray(content) ? content.map((x) => (typeof x === "string" ? x : x?.text ?? "")).join("\n") : String(content ?? "");
  return text.split("\n").map((l) => l.replace(/\s+$/, "")).filter((l) => l.trim()).slice(0, 6).map((l) => l.slice(0, MAX_LINE));
}

/** 토큰 값과 토큰 모양 문자열을 지운다 */
export function redact(text, token) {
  let out = String(text);
  if (token && token.length >= 8) out = out.split(token).join("***");
  return out.replace(TOKEN_SHAPE, "***");
}

export function listFiles(root) {
  const out = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (out.length >= MAX_FILES) return;
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (!SKIP_DIRS.has(e.name)) walk(p);
      } else if (e.isFile()) {
        out.push({ path: path.relative(root, p), size: fs.statSync(p).size });
      }
    }
  };
  if (fs.existsSync(root)) walk(root);
  return out.sort((a, b) => a.path.localeCompare(b.path));
}

/** 성공 조건: fileExists(파일 있음) · contains({file, text}) · 없으면 claude 가 오류 없이 끝났는지 */
export function judge(check, workspace, result, files) {
  if (check?.fileExists) {
    const ok = files.some((f) => f.path === check.fileExists || f.path.endsWith(`/${check.fileExists}`));
    return { ok, detail: ok ? `${check.fileExists} 있음` : `${check.fileExists} 없음` };
  }
  if (check?.contains?.file) {
    const p = path.join(workspace, check.contains.file);
    const ok = fs.existsSync(p) && fs.readFileSync(p, "utf8").includes(check.contains.text ?? "");
    return { ok, detail: ok ? `${check.contains.file} 에 '${check.contains.text}' 있음` : `${check.contains.file} 에 '${check.contains.text}' 없음` };
  }
  const ok = !!result && !result.isError;
  return { ok, detail: ok ? "오류 없이 끝남" : "오류로 끝남" };
}

function redactTree(root, token) {
  for (const f of listFiles(root)) {
    const p = path.join(root, f.path);
    if (!TEXT_EXT.has(path.extname(p).toLowerCase()) || f.size > 2_000_000) continue;
    const s = fs.readFileSync(p, "utf8");
    const r = redact(s, token);
    if (r !== s) fs.writeFileSync(p, r);
  }
}

function excerpts(workspace, files) {
  return files.filter((f) => TEXT_EXT.has(path.extname(f.path).toLowerCase()) && f.size < 200_000).slice(0, 4).map((f) => ({
    path: f.path,
    lines: fs.readFileSync(path.join(workspace, f.path), "utf8").split("\n").slice(0, 12).map((l) => l.slice(0, MAX_LINE)),
  }));
}

function runClaude(task, workspace, eventsPath) {
  return new Promise((resolve) => {
    const args = ["-p", String(task.prompt), "--output-format", "stream-json", "--verbose", "--dangerously-skip-permissions",
      "--disallowedTools", "WebSearch,WebFetch", "--max-turns", String(task.maxTurns || 12)];
    if (task.model) args.push("--model", String(task.model));
    const out = fs.createWriteStream(eventsPath);
    const child = spawn(process.env.LAB_CLAUDE_BIN || "claude", args, { cwd: workspace, stdio: ["ignore", "pipe", "pipe"] });
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 5000).unref();
    }, Math.max(10, task.timeoutSec || 600) * 1000);
    child.stdout.pipe(out);
    child.stderr.on("data", (d) => {
      stderr = (stderr + d.toString()).slice(-4000);
    });
    child.on("error", (e) => {
      clearTimeout(timer);
      out.end();
      resolve({ code: -1, timedOut, stderr: String(e.message) });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      out.end(() => resolve({ code, timedOut, stderr }));
    });
  });
}

export async function main(work = WORK) {
  const token = process.env[TOKEN_ENV] || "";
  const task = JSON.parse(fs.readFileSync(path.join(work, "task.json"), "utf8"));
  const workspace = path.join(work, "workspace");
  const previewsDir = path.join(work, "previews");
  fs.mkdirSync(workspace, { recursive: true });
  fs.mkdirSync(previewsDir, { recursive: true });
  for (const s of task.seedFiles || []) { // 과제에 필요한 입력 파일(계획에 적힌 것만)
    const p = path.join(workspace, path.basename(s.path));
    fs.writeFileSync(p, String(s.content ?? ""));
  }
  const eventsPath = path.join(work, "events.jsonl");
  const started = Date.now();
  const run = await runClaude(task, workspace, eventsPath);
  const seconds = Math.round((Date.now() - started) / 100) / 10;
  const raw = fs.existsSync(eventsPath) ? fs.readFileSync(eventsPath, "utf8") : "";
  fs.writeFileSync(eventsPath, redact(raw, token));
  redactTree(workspace, token);
  const { steps, result } = parseEvents(redact(raw, token).split("\n"));
  const files = listFiles(workspace);
  let previews = [];
  try {
    const { capture } = await import("./capture.mjs");
    previews = await capture(files, workspace, previewsDir);
  } catch (e) {
    previews = [];
    process.stderr.write(`미리보기 실패: ${e?.message ?? e}\n`);
  }
  const check = judge(task.check, workspace, result, files);
  const status = run.timedOut ? "timeout" : run.code === 0 && result && !result.isError ? "done" : "error";
  const out = {
    ok: status === "done" && check.ok,
    status,
    seconds,
    exitCode: run.code,
    check,
    final: redact(result?.text ?? "", token).slice(0, 1500),
    costUsd: result?.costUsd ?? null,
    turns: result?.turns ?? null,
    steps: steps.map((s) => ({ ...s, input: redact(s.input, token), output: s.output.map((l) => redact(l, token)) })),
    files,
    previews,
    excerpts: excerpts(workspace, files).map((x) => ({ ...x, lines: x.lines.map((l) => redact(l, token)) })),
    stderr: redact(run.stderr, token).slice(-800),
  };
  fs.writeFileSync(path.join(work, "result.json"), JSON.stringify(out, null, 1));
  return out;
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  main().then((r) => {
    process.stdout.write(`${r.status} ok=${r.ok} ${r.seconds}s\n`);
    process.exit(0);
  }, (e) => {
    process.stderr.write(`실험 실패: ${e?.stack ?? e}\n`);
    process.exit(2);
  });
}
