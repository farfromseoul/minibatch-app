// 지금 그리는 테마. Listicle 이 timeline.theme 으로 정해 넣고, 장면·부품은 useTheme() 로 읽는다.
import React, { createContext, useContext } from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";

import type { ThemeSpec, Tokens } from "./types";

export const ThemeContext = createContext<ThemeSpec | null>(null);

export const useTheme = (): ThemeSpec => {
  const t = useContext(ThemeContext);
  if (!t) throw new Error("ThemeContext 가 없다 (Listicle 안에서만 그린다)");
  return t;
};

export const useTokens = (): Tokens => useTheme().tokens;

/** 테마 움직임으로 0→1 등장 (delay 프레임 뒤) */
export const useIn = (delay = 0): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { motion } = useTheme();
  return spring({ frame: Math.max(0, frame - delay), fps, config: motion.spring });
};

/** 카드 기본 모양 (테마 tokens) */
export const cardStyle = (k: Tokens, opts: { active?: boolean; strong?: boolean; radius?: number } = {}): React.CSSProperties => ({
  background: opts.strong ? k.surfaceStrong : k.surface,
  border: `${k.border}px solid ${opts.active ? k.activeBorder : k.line}`,
  borderRadius: opts.radius ?? k.radius,
  boxShadow: opts.active ? `${k.cardShadow}${k.glow() !== "none" ? `, ${k.glow(0.8)}` : ""}` : k.cardShadow,
});

export const Accent: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => {
  const k = useTokens();
  return <span style={{ ...k.accentText, ...style }}>{children}</span>;
};
