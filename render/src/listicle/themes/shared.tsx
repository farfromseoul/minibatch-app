// 테마 틀 부품이 같이 쓰는 계산: 항목 구간, 지금 자막과 단어 상태
import { useCurrentFrame } from "remotion";

import { fitFontSize } from "../../lib/layout";
import { wordStates, type WordState } from "../../lib/listicle";
import type { Timeline } from "../../lib/timeline";
import { L } from "../style";

/** 항목 하나가 차지하는 구간 (첫 장면 시작 ~ 마지막 장면 끝) */
export const itemSpan = (t: Timeline, index: number): [number, number] => {
  const ss = t.scenes.filter((s) => s.section?.kind === "item" && s.section.index === index);
  if (!ss.length) return [0, 1];
  const last = ss[ss.length - 1];
  return [ss[0].fromFrame, last.fromFrame + last.durationInFrames];
};

export type CaptionWord = { text: string; fromFrame: number; emphasis?: boolean; state: WordState };

/** 지금 보일 자막 구절과 단어 상태. 단어 시각이 없으면 구절 통째로 '읽음' */
export const useCaptionNow = (t: Timeline, maxSize = 64, minSize = 44) => {
  const frame = useCurrentFrame();
  const c = t.captions.find((x) => frame >= x.fromFrame && frame < x.toFrame);
  if (!c) return null;
  const raw = c.words && c.words.length ? c.words : [{ text: c.text, fromFrame: c.fromFrame }];
  const states = c.words && c.words.length ? wordStates(raw, frame) : raw.map(() => "done" as const);
  const words: CaptionWord[] = raw.map((w, i) => ({ ...w, state: states[i] }));
  const size = fitFontSize(c.text, L.width - 40, maxSize, minSize, 2) ?? minSize;
  return { c, words, size, since: frame - c.fromFrame, frame };
};
