// Remotion 렌더링. 번들(브라우저용으로 묶은 화면 코드)은 이미지 빌드 때 한 번 만들어 두고 재사용한다
// (공식 문서: 번들은 한 번 만들어 여러 렌더에 쓴다).
import { rename, readFile, rm } from "node:fs/promises";
import path from "node:path";

import { renderMedia, selectComposition } from "@remotion/renderer";

import { validateTimeline } from "../src/lib/timeline.ts";

export type RenderResult = { path: string; frames: number; renderSec: number };

export class InvalidTimeline extends Error {
  // Node 의 TypeScript 실행은 타입만 지운다: 생성자 매개변수 속성(public errors) 같은 문법은 쓰지 않는다
  errors: string[];
  constructor(errors: string[]) {
    super(`timeline 검증 실패: ${errors.join("; ")}`);
    this.errors = errors;
  }
}

export async function renderTimeline(opts: {
  serveUrl: string;
  timelinePath: string;
  out: string;
  assetBase: string;
  concurrency: number;
  onProgress?: (progress: number) => void;
}): Promise<RenderResult> {
  const timeline = JSON.parse(await readFile(opts.timelinePath, "utf8"));
  const errors = validateTimeline(timeline);
  if (errors.length) throw new InvalidTimeline(errors);
  const inputProps = { timeline, assetBase: opts.assetBase };
  const started = performance.now();
  const composition = await selectComposition({ serveUrl: opts.serveUrl, id: "Short", inputProps });
  // 임시 이름으로 렌더하고 끝나면 이름을 바꾼다. 중간에 죽어도 반쯤 쓴 final.mp4 가 남지 않는다
  const tmp = path.join(path.dirname(opts.out), `.${path.basename(opts.out)}.rendering.mp4`);
  try {
    await renderMedia({
      composition,
      serveUrl: opts.serveUrl,
      codec: "h264",
      outputLocation: tmp,
      inputProps,
      concurrency: opts.concurrency, // 메모리 예산 (아키텍처 D13: 동시성 2)
      onProgress: ({ progress }) => opts.onProgress?.(progress),
    });
    await rename(tmp, opts.out);
  } catch (e) {
    await rm(tmp, { force: true });
    throw e;
  }
  return { path: opts.out, frames: composition.durationInFrames, renderSec: Math.round((performance.now() - started) / 100) / 10 };
}
