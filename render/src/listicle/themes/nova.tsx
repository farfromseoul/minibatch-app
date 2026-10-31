// 테마 nova (2026-10-31): 짙은 남색 + 민트 → 하늘 → 보라 그라데이션 빛, 유리 카드, 부드러운 움직임. 세련된 테크.
// 어울리는 주제: AI 도구·서비스 추천. 장면은 공통 장면 그대로(nova 기준으로 만들었다).
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../../lib/layout";
import { pad2, trackerSlots } from "../../lib/listicle";
import { Icon } from "../icons";
import { abs, L } from "../style";
import { itemSpan, useCaptionNow } from "./shared";
import type { FrameProps, HeaderProps, ProgressProps, ThemeSpec, Tokens } from "./types";

const G = "linear-gradient(120deg, #5CF2C4 0%, #6CC7FF 50%, #8E7BFF 100%)";

const tokens: Tokens = {
  bg: "#0A0C14",
  surface: "rgba(18, 22, 36, 0.72)",
  surfaceStrong: "rgba(14, 17, 28, 0.94)",
  line: "rgba(255, 255, 255, 0.10)",
  text: "#F3F5FB",
  sub: "#A7AEC2",
  muted: "#646B80",
  accent: "#5CF2C4",
  accent2: "#8E7BFF",
  warn: "#FF7A70",
  onAccent: "#0A0C14",
  gradient: G,
  gradientSoft: "linear-gradient(120deg, rgba(92,242,196,0.16), rgba(108,199,255,0.12), rgba(142,123,255,0.16))",
  font: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif",
  titleFont: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif",
  mono: "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace",
  titleWeight: 900,
  radius: 28,
  border: 2,
  cardShadow: "0 24px 60px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
  activeBorder: "rgba(92, 242, 196, 0.85)",
  glow: (s = 1) => `0 0 ${Math.round(28 * s)}px rgba(92, 242, 196, 0.35), 0 0 ${Math.round(80 * s)}px rgba(142, 123, 255, ${0.14 * s})`,
  accentText: { backgroundImage: G, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" },
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const a = Math.sin(frame / 160);
  const b = Math.cos(frame / 200);
  return (
    <>
      <AbsoluteFill style={{ background: tokens.bg }} />
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 60% 34% at ${22 + a * 8}% ${16 + b * 4}%, rgba(92,242,196,0.16), transparent 70%)` }} />
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 65% 38% at ${82 - b * 8}% ${62 + a * 5}%, rgba(142,123,255,0.18), transparent 70%)` }} />
      <AbsoluteFill
        style={{
          backgroundImage: "radial-gradient(rgba(255,255,255,0.10) 1.6px, transparent 2px)",
          backgroundSize: "40px 40px",
          WebkitMaskImage: "linear-gradient(180deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.35) 60%, rgba(0,0,0,0) 85%)",
          maskImage: "linear-gradient(180deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.35) 60%, rgba(0,0,0,0) 85%)",
        }}
      />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 40%, transparent 55%, rgba(0,0,0,0.55) 100%)" }} />
    </>
  );
};

/** "ITEM 02 / 05" + 분할 막대. 지금 칸은 항목이 진행되는 만큼 차오른다 */
const Progress: React.FC<ProgressProps> = ({ t, index }) => {
  const frame = useCurrentFrame();
  const items = t.tracker?.items ?? [];
  const slots = trackerSlots(items.length, index);
  const [s0, s1] = itemSpan(t, index);
  const fill = interpolate(frame, [s0, s1], [0.04, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const gap = 10;
  const w = (L.width - gap * (items.length - 1)) / items.length;
  return (
    <>
      <div style={{ ...abs(L.side, L.counterY), display: "flex", alignItems: "baseline", gap: 12, fontFamily: tokens.mono }}>
        <span style={{ fontSize: 26, letterSpacing: 6, color: tokens.accent, fontWeight: 700 }}>ITEM</span>
        <span style={{ fontSize: 30, color: tokens.text, fontWeight: 700 }}>{pad2(index)}</span>
        <span style={{ fontSize: 26, color: tokens.muted }}>/ {pad2(items.length)}</span>
      </div>
      {items.map((it, i) => (
        <div key={it.name + i} style={{ ...abs(L.side + i * (w + gap), L.barY, w, 10), borderRadius: 5, background: "rgba(255,255,255,0.12)", overflow: "hidden" }}>
          <div style={{ width: slots[i] === "done" ? "100%" : slots[i] === "current" ? `${fill * 100}%` : "0%", height: "100%", borderRadius: 5, background: slots[i] === "done" ? "rgba(92,242,196,0.55)" : G }} />
        </div>
      ))}
    </>
  );
};

const ItemHeader: React.FC<HeaderProps> = ({ t, index, since }) => {
  const it = t.tracker?.items[index - 1];
  if (!it) return null;
  const p = interpolate(since, [0, 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const size = fitFontSize(it.name, L.width - 130, 76, 44, 1) ?? 44;
  return (
    <div style={{ ...abs(L.side, L.headerY, L.width), opacity: p, transform: `translateY(${(1 - p) * 16}px)` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ padding: "4px 16px", borderRadius: 14, background: G, color: tokens.onAccent, fontSize: 38, fontWeight: 900 }}>{pad2(index)}</div>
        <div style={{ fontSize: size, fontWeight: 900, color: tokens.text, letterSpacing: -2, whiteSpace: "nowrap" }}>{it.name}</div>
      </div>
      {it.meta ? (
        <div style={{ marginTop: 14, display: "inline-flex", alignItems: "center", gap: 10, padding: "6px 16px", borderRadius: 12, background: "rgba(255,255,255,0.08)", border: `1px solid ${tokens.line}`, fontFamily: tokens.mono, fontSize: 24, color: tokens.sub }}>
          <Icon name="code" size={24} color="#6CC7FF" />
          {it.meta}
        </div>
      ) : null}
    </div>
  );
};

/** 지금 단어는 흰 글자 + 그라데이션 밑줄, 읽은 단어 흰색(강조 민트), 남은 단어 옅게 */
const Caption: React.FC<FrameProps> = ({ t }) => {
  const { fps } = useVideoConfig();
  const now = useCaptionNow(t);
  if (!now) return null;
  const { words, size, since, frame } = now;
  const enter = spring({ frame: since, fps, config: { damping: 22, stiffness: 140 } });
  return (
    <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "flex-end", columnGap: Math.round(size * 0.26), rowGap: 14, opacity: Math.min(1, enter * 1.3), transform: `translateY(${(1 - enter) * 14}px)` }}>
      {words.map((w, i) => {
        const color = w.state === "next" ? "rgba(243,245,251,0.30)" : w.emphasis ? tokens.accent : tokens.text;
        const bar = w.state === "current" ? spring({ frame: frame - w.fromFrame, fps, config: { damping: 20, stiffness: 160 } }) : 0;
        return (
          <span key={i} style={{ position: "relative", fontSize: size, fontWeight: 800, color, lineHeight: 1.3, letterSpacing: -0.5, textShadow: "0 4px 24px rgba(0,0,0,0.6)", transform: w.state === "current" ? `translateY(${-4 * bar}px)` : undefined, display: "inline-block" }}>
            {w.text}
            {w.state === "current" ? <span style={{ position: "absolute", left: 0, bottom: -8, height: 7, width: `${bar * 100}%`, borderRadius: 4, background: G }} /> : null}
          </span>
        );
      })}
    </div>
  );
};

export const nova: ThemeSpec = {
  name: "nova",
  tokens,
  motion: { spring: { damping: 20, stiffness: 110, mass: 1 }, stagger: 7, float: 5 },
  Background,
  Progress,
  ItemHeader,
  Caption,
};
