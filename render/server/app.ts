// render-worker HTTP 서버 (아키텍처 "내부 작업자": POST /render).
// - 0.0.0.0:<port>: job-api 가 부르는 API (internal 망에서만 닿는다)
// - 127.0.0.1:<filePort>: 데이터 폴더를 읽기 전용으로 내주는 파일 서버. 컨테이너 안의 헤드리스 Chrome 만 쓴다
import { createReadStream } from "node:fs";
import { mkdir, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";

import { assetBaseFor, insideDir, parseRenderRequest } from "./request.ts";
import { InvalidTimeline, renderTimeline, type RenderResult } from "./render.ts";

export type ServerOptions = {
  dataDir: string;
  serveUrl: string; // 번들 위치
  port: number;
  filePort: number;
  concurrency: number;
  render?: typeof renderTimeline; // 테스트에서 바꿔 끼운다
};

const MIME: Record<string, string> = { ".wav": "audio/wav", ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg" };

function send(res: http.ServerResponse, status: number, body: unknown) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
}

async function readJson(req: http.IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const c of req) {
    size += (c as Buffer).length;
    if (size > 64 * 1024) throw new Error("본문이 너무 크다");
    chunks.push(c as Buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "null");
}

export function createFileServer(dataDir: string): http.Server {
  return http.createServer(async (req, res) => {
    const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
    const target = path.join(dataDir, rel);
    if (req.method !== "GET" || !insideDir(dataDir, target)) return send(res, 403, { error: "forbidden" });
    try {
      const st = await stat(target);
      if (!st.isFile()) return send(res, 404, { error: "not_found" });
      res.writeHead(200, { "Content-Type": MIME[path.extname(target)] ?? "application/octet-stream", "Content-Length": st.size });
      createReadStream(target).pipe(res);
    } catch {
      send(res, 404, { error: "not_found" });
    }
  });
}

export function createApiServer(opts: ServerOptions): http.Server {
  const render = opts.render ?? renderTimeline;
  let busy: string | null = null; // 한 번에 하나만 렌더한다 (메모리 예산)
  return http.createServer(async (req, res) => {
    const url = (req.url ?? "/").split("?")[0];
    if (req.method === "GET" && url === "/healthz") return send(res, 200, { status: "ok", busy: busy !== null });
    if (req.method !== "POST" || url !== "/render") return send(res, 404, { error: { code: "not_found", message: url } });
    let body: unknown;
    try {
      body = await readJson(req);
    } catch {
      return send(res, 400, { error: { code: "invalid_request", message: "JSON 본문이 아니다" } });
    }
    const parsed = parseRenderRequest(body, opts.dataDir);
    if (!parsed.ok) return send(res, 400, { error: { code: "invalid_request", message: parsed.error } });
    if (busy) return send(res, 409, { error: { code: "busy", message: `렌더링 중: ${busy}` } });
    busy = parsed.timeline;
    try {
      await mkdir(path.dirname(parsed.out), { recursive: true });
      const result: RenderResult = await render({
        serveUrl: opts.serveUrl,
        timelinePath: parsed.timeline,
        out: parsed.out,
        assetBase: assetBaseFor(parsed.timeline, opts.dataDir, opts.filePort),
        concurrency: opts.concurrency,
      });
      send(res, 200, result);
    } catch (e) {
      if (e instanceof InvalidTimeline) send(res, 422, { error: { code: "invalid_timeline", message: e.errors.join("; ") } });
      else send(res, 500, { error: { code: "render_failed", message: e instanceof Error ? `${e.name}: ${e.message}`.slice(0, 1000) : String(e) } });
    } finally {
      busy = null;
    }
  });
}
