// 목록형 쇼츠(D42) 색·배치. 참고 영상(2026-10-30): 검정 바탕 + 노랑 하나, 카드·빛나는 테두리.
import type React from "react";

export const C = {
  bg: "#0B0B0D",
  card: "#131316",
  card2: "#1A1A1E",
  border: "#2A2A30",
  gold: "#FFC83D",
  goldDeep: "#F2A900",
  goldSoft: "rgba(255, 200, 61, 0.16)",
  text: "#FFFFFF",
  sub: "#B6B6BE",
  muted: "#6E6E76",
  dim: "#3A3A40",
  red: "#FF5A4E",
  green: "#3DDC84",
  ink: "#111113",
  paper: "#F3EFE6",
  recapBg: "#F7C531",
};

/** 1080×1920 화면 배치. 아래 약 470px 는 쇼츠 화면의 제목·채널 글자가 덮는다 */
export const L = {
  side: 70,
  width: 1080 - 140,
  trackerY: 150,
  trackerH: 96,
  headerY: 290,
  stageTop: 470,
  stageBottom: 1250,
  captionY: 1395,
};

export const MONO = "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace";

export const goldGlow = (s = 1): string => `0 0 ${Math.round(22 * s)}px rgba(255, 200, 61, 0.45), 0 0 ${Math.round(70 * s)}px rgba(255, 200, 61, 0.16)`;

export const abs = (x: number, y: number, w?: number, h?: number): React.CSSProperties => ({
  position: "absolute",
  left: x,
  top: y,
  ...(w !== undefined ? { width: w } : {}),
  ...(h !== undefined ? { height: h } : {}),
});

/** 둥근 카드 기본 모양 */
export const cardStyle = (opts: { border?: string; glow?: boolean; bg?: string; radius?: number } = {}): React.CSSProperties => ({
  background: opts.bg ?? C.card,
  border: `3px solid ${opts.border ?? C.border}`,
  borderRadius: opts.radius ?? 28,
  boxShadow: opts.glow ? goldGlow() : "0 18px 40px rgba(0, 0, 0, 0.45)",
});
