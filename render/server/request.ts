// 렌더 요청 검사. tts-worker 와 같은 원칙: 경로는 데이터 폴더 안의 절대 경로만 받는다.
import path from "node:path";

export function insideDir(base: string, target: string): boolean {
  if (!path.isAbsolute(target)) return false;
  const b = path.resolve(base);
  const t = path.resolve(target); // ../ 를 풀어 실제 위치로 비교
  return t === b || t.startsWith(b + path.sep);
}

export type RenderRequest = { ok: true; timeline: string; out: string } | { ok: false; error: string };

export function parseRenderRequest(body: unknown, dataDir: string): RenderRequest {
  if (typeof body !== "object" || body === null) return { ok: false, error: "본문은 {timeline, out}" };
  const { timeline, out } = body as Record<string, unknown>;
  if (typeof timeline !== "string" || typeof out !== "string") return { ok: false, error: "timeline, out 은 문자열 경로" };
  if (!insideDir(dataDir, timeline) || !insideDir(dataDir, out)) return { ok: false, error: `경로는 데이터 폴더(${dataDir}) 안이어야 한다` };
  if (!out.endsWith(".mp4")) return { ok: false, error: "out 은 .mp4" };
  return { ok: true, timeline: path.resolve(timeline), out: path.resolve(out) };
}

/** 오디오 파일 주소: 렌더러(헤드리스 Chrome)가 내부 파일 서버에서 작업 폴더 파일을 받는다 */
export function assetBaseFor(timelinePath: string, dataDir: string, filePort: number): string {
  const rel = path.relative(path.resolve(dataDir), path.dirname(path.resolve(timelinePath)));
  const encoded = rel.split(path.sep).map(encodeURIComponent).join("/");
  return `http://127.0.0.1:${filePort}/${encoded}/`;
}
