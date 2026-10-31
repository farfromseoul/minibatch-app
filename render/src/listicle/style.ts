// 목록형 쇼츠(D42) 배치. 색·글꼴·모양은 테마 템플릿(themes/*.tsx)의 tokens 가 정한다.
import type React from "react";

/** 1080×1920 화면 배치. 아래 약 470px 는 쇼츠 화면의 제목·채널 글자가 덮는다 */
export const L = {
  side: 72,
  width: 1080 - 144,
  counterY: 150,
  barY: 198,
  headerY: 262,
  stageTop: 470,
  stageBottom: 1240,
  captionY: 1400,
};

export const abs = (x: number, y: number, w?: number, h?: number): React.CSSProperties => ({
  position: "absolute",
  left: x,
  top: y,
  ...(w !== undefined ? { width: w } : {}),
  ...(h !== undefined ? { height: h } : {}),
});

export const rise = (p: number, px = 36): React.CSSProperties => ({ opacity: Math.min(1, p), transform: `translateY(${(1 - p) * px}px)` });
