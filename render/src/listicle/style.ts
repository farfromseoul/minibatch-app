// 목록형 쇼츠(D42) 색·배치. 2026-10-31 nova: 참고 영상(검정·노랑)을 그대로 닮지 않게, 짙은 남색 바탕에
// 민트 → 하늘 → 보라 그라데이션 빛, 유리 카드, 점 무늬·오로라 배경 (사용자 피드백 "너무 똑같이 베꼈다").
import type React from "react";

export const C = {
  bg: "#0A0C14",
  glass: "rgba(255, 255, 255, 0.045)",
  glass2: "rgba(255, 255, 255, 0.08)",
  line: "rgba(255, 255, 255, 0.10)",
  mint: "#5CF2C4",
  sky: "#6CC7FF",
  violet: "#8E7BFF",
  coral: "#FF7A70",
  text: "#F3F5FB",
  sub: "#A7AEC2",
  muted: "#646B80",
  dim: "rgba(255, 255, 255, 0.12)",
  ink: "#0A0C14",
  green: "#5CF2C4",
};

/** 대표 그라데이션 (민트 → 하늘 → 보라) */
export const G = "linear-gradient(120deg, #5CF2C4 0%, #6CC7FF 50%, #8E7BFF 100%)";
export const G_SOFT = "linear-gradient(120deg, rgba(92,242,196,0.22) 0%, rgba(108,199,255,0.16) 50%, rgba(142,123,255,0.22) 100%)";

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

export const MONO = "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace";

export const glow = (color = "rgba(92, 242, 196, 0.35)", s = 1): string => `0 0 ${Math.round(28 * s)}px ${color}, 0 0 ${Math.round(80 * s)}px rgba(142, 123, 255, ${0.14 * s})`;

/** 그라데이션 글자 */
export const gradText: React.CSSProperties = {
  backgroundImage: G,
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  color: "transparent",
};

export const abs = (x: number, y: number, w?: number, h?: number): React.CSSProperties => ({
  position: "absolute",
  left: x,
  top: y,
  ...(w !== undefined ? { width: w } : {}),
  ...(h !== undefined ? { height: h } : {}),
});

/** 유리 카드 기본 모양 */
export const glassStyle = (opts: { active?: boolean; radius?: number; strong?: boolean } = {}): React.CSSProperties => ({
  background: opts.strong ? "rgba(18, 22, 36, 0.92)" : "rgba(18, 22, 36, 0.72)",
  border: `2px solid ${opts.active ? "rgba(92, 242, 196, 0.85)" : C.line}`,
  borderRadius: opts.radius ?? 28,
  boxShadow: opts.active ? glow() : "0 24px 60px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
});
