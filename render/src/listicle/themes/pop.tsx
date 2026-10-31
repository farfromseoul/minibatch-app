// 테마 pop (2026-10-31): 크림 바탕 + 원색 블록(코랄·파랑·노랑·민트), 두꺼운 검정 테두리 스티커, 통통 튀는 움직임. 가볍고 캐주얼.
// 어울리는 주제: 실수 모음·꿀팁. 첫마디·소개 카드·정리·끝은 스티커 레이아웃으로 덮어쓴다.
import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../../lib/layout";
import { pad2, phase, seeded } from "../../lib/listicle";
import { Icon } from "../icons";
import { fit, Highlighted, type LSceneProps } from "../scenes";
import { abs, L } from "../style";
import { useIn } from "./context";
import { useCaptionNow } from "./shared";
import type { FrameProps, HeaderProps, ProgressProps, ThemeSpec, Tokens } from "./types";

const INK = "#1B1B1F";
const COLORS = ["#FF5A5F", "#2F5BFF", "#FFC93C", "#2ED3A4", "#A06BFF"];
const BORDER = `5px solid ${INK}`;
const HARD = `8px 8px 0 ${INK}`;

const tokens: Tokens = {
  bg: "#FFF1DC",
  surface: "#FFFFFF",
  surfaceStrong: "#FFFFFF",
  line: INK,
  text: INK,
  sub: "#45454F",
  muted: "#8C8C99",
  accent: "#FF5A5F",
  accent2: "#2F5BFF",
  warn: "#FF5A5F",
  onAccent: "#FFFFFF",
  gradient: "linear-gradient(90deg, #FF5A5F, #FF8A3D)",
  gradientSoft: "#FFE3B8",
  font: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif",
  titleFont: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif",
  mono: "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace",
  titleWeight: 900,
  radius: 30,
  border: 5,
  cardShadow: HARD,
  activeBorder: INK,
  glow: () => "none",
  accentText: { color: "#FF5A5F" },
};

const useBounce = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: Math.max(0, frame - delay), fps, config: { damping: 9, stiffness: 170, mass: 0.8 } });
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const bob = (i: number) => Math.sin((frame + i * 40) / 30) * 10;
  return (
    <>
      <AbsoluteFill style={{ background: tokens.bg }} />
      <div style={{ ...abs(760, -120 + bob(0), 460, 460), borderRadius: 230, background: COLORS[0], border: BORDER }} />
      <div style={{ ...abs(-140, 1500 + bob(1), 380, 380), borderRadius: 70, background: COLORS[1], border: BORDER, transform: `rotate(${18 + frame * 0.2}deg)` }} />
      <div style={{ ...abs(-90, 380 + bob(2), 180, 180), borderRadius: 90, background: COLORS[2], border: BORDER }} />
      <div style={{ ...abs(930, 1180 + bob(3), 200, 200), borderRadius: 40, background: COLORS[3], border: BORDER, transform: "rotate(-14deg)" }} />
      {Array.from({ length: 26 }, (_, i) => (
        <div key={i} style={{ ...abs(seeded(i) * 1040, 300 + seeded(i + 50) * 1300, 14, 14), borderRadius: 7, background: COLORS[i % COLORS.length], opacity: 0.8 }} />
      ))}
    </>
  );
};

/** 번호 스티커 줄: 지난 것 노랑 체크, 지금 것 코랄로 커지며 튐, 남은 것 흰색 */
const Progress: React.FC<ProgressProps> = ({ t, index }) => {
  const n = t.tracker?.items.length ?? 0;
  const pop = useBounce(0);
  const d = 74;
  const gap = 20;
  const x0 = (1080 - (n * d + (n - 1) * gap)) / 2;
  return (
    <>
      {Array.from({ length: n }, (_, i) => {
        const st = i + 1 < index ? "done" : i + 1 === index ? "current" : "next";
        return (
          <div key={i} style={{ ...abs(x0 + i * (d + gap), 140, d, d), borderRadius: d / 2, border: BORDER, background: st === "done" ? COLORS[2] : st === "current" ? COLORS[0] : "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, fontWeight: 900, color: st === "current" ? "#FFFFFF" : INK, transform: st === "current" ? `scale(${1 + 0.18 * pop})` : undefined, boxShadow: `4px 4px 0 ${INK}` }}>
            {st === "done" ? <Icon name="check" size={36} color={INK} stroke={3} /> : i + 1}
          </div>
        );
      })}
    </>
  );
};

const ItemHeader: React.FC<HeaderProps> = ({ t, index, since }) => {
  const it = t.tracker?.items[index - 1];
  const { fps } = useVideoConfig();
  if (!it) return null;
  const p = spring({ frame: since, fps, config: { damping: 9, stiffness: 170, mass: 0.8 } });
  const size = fitFontSize(it.name, L.width - 160, 74, 42, 1) ?? 42;
  return (
    <div style={{ ...abs(L.side, 262, L.width), display: "flex", alignItems: "center", gap: 22, transform: `scale(${0.8 + 0.2 * Math.min(1.1, p)})`, transformOrigin: "left center" }}>
      <div style={{ padding: "6px 18px", background: COLORS[1], color: "#FFFFFF", border: BORDER, borderRadius: 18, fontSize: 40, fontWeight: 900, transform: "rotate(-6deg)", boxShadow: `4px 4px 0 ${INK}` }}>#{pad2(index)}</div>
      <div style={{ position: "relative", isolation: "isolate", fontSize: size, fontWeight: 900, color: INK, whiteSpace: "nowrap" }}>
        <div style={{ ...abs(-6, size * 0.55, undefined, size * 0.42), right: -6, background: COLORS[2], zIndex: -1 }} />
        {it.name}
      </div>
    </div>
  );
};

/** 지금 단어는 색 알약(단어마다 색이 바뀜)으로 튀어 오른다 */
const Caption: React.FC<FrameProps> = ({ t }) => {
  const { fps } = useVideoConfig();
  const now = useCaptionNow(t, 62, 42);
  if (!now) return null;
  const { words, size, frame } = now;
  return (
    <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "center", columnGap: Math.round(size * 0.22), rowGap: 14 }}>
      {words.map((w, i) => {
        if (w.state === "current") {
          const b = spring({ frame: frame - w.fromFrame, fps, config: { damping: 8, stiffness: 220, mass: 0.7 } });
          return (
            <span key={i} style={{ fontSize: size, fontWeight: 900, color: "#FFFFFF", background: COLORS[i % 4 === 2 ? 1 : i % 4], border: `4px solid ${INK}`, borderRadius: 20, padding: "0 16px", boxShadow: `4px 4px 0 ${INK}`, transform: `scale(${0.85 + 0.15 * b}) rotate(${(i % 2 ? 2 : -2) * b}deg)`, display: "inline-block", lineHeight: 1.25 }}>
              {w.text}
            </span>
          );
        }
        return (
          <span key={i} style={{ fontSize: size, fontWeight: 900, color: w.state === "next" ? "#C9BBA5" : w.emphasis ? COLORS[0] : INK, lineHeight: 1.25 }}>
            {w.text}
          </span>
        );
      })}
    </div>
  );
};

// ---------- 스티커 레이아웃 장면

const starPoints = (cx: number, cy: number, r1: number, r2: number, n = 14) =>
  Array.from({ length: n * 2 }, (_, i) => {
    const r = i % 2 ? r2 : r1;
    const a = (Math.PI * i) / n - Math.PI / 2;
    return `${cx + Math.cos(a) * r},${cy + Math.sin(a) * r}`;
  }).join(" ");

const HookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const kick = useBounce(0);
  const burst = useBounce(6);
  const size = fit(props.claim, 620, 170, 70);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(0, 280, 1080), display: "flex", justifyContent: "center" }}>
        <div style={{ padding: "12px 30px", background: "#FFFFFF", border: BORDER, borderRadius: 40, fontSize: 40, fontWeight: 900, color: INK, boxShadow: HARD, transform: `rotate(-3deg) scale(${Math.min(1.05, kick)})` }}>{props.kicker}</div>
      </div>
      <svg style={{ ...abs(0, 420), transform: `scale(${Math.min(1.05, burst)}) rotate(${frame * 0.3}deg)`, transformOrigin: "540px 340px" }} width={1080} height={680}>
        <polygon points={starPoints(540, 340, 380, 300)} fill={COLORS[2]} stroke={INK} strokeWidth={8} strokeLinejoin="round" />
      </svg>
      <div style={{ ...abs(0, 760 - size * 0.62, 1080), textAlign: "center", fontSize: size, fontWeight: 900, color: INK, letterSpacing: -4, transform: `scale(${Math.min(1.08, burst)}) rotate(-4deg)` }}>{props.claim}</div>
      {props.claimNote ? (
        <div style={{ ...abs(720, 520), padding: "8px 20px", background: COLORS[0], color: "#FFFFFF", border: BORDER, borderRadius: 18, fontSize: 36, fontWeight: 900, transform: `rotate(10deg) scale(${Math.min(1, burst)})` }}>{props.claimNote}</div>
      ) : null}
      {props.aside ? <div style={{ ...abs(0, 1110, 1080), textAlign: "center", fontSize: 44, fontWeight: 800, color: INK, opacity: phase(frame, durationInFrames, 0.3, 0.45) }}>{props.aside}</div> : null}
    </AbsoluteFill>
  );
};

const HookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ props }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = useBounce(0);
  const n = props.count;
  const w = Math.min(190, Math.floor((900 - (n - 1) * 20) / n));
  const total = n * w + (n - 1) * 20;
  const size = fit(props.headline, 940, 110, 60);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(0, 400, 1080), textAlign: "center", fontSize: size, fontWeight: 900, color: INK, letterSpacing: -3, transform: `scale(${Math.min(1.05, head)})` }}>
        <Highlighted text={props.headline} highlight={props.highlight} />
      </div>
      {Array.from({ length: n }, (_, i) => {
        const p = spring({ frame: Math.max(0, frame - 8 - i * 6), fps, config: { damping: 9, stiffness: 170, mass: 0.8 } });
        return (
          <div key={i} style={{ ...abs((1080 - total) / 2 + i * (w + 20), 700 + (i % 2) * 40, w, w * 1.2), background: COLORS[i % COLORS.length], border: BORDER, borderRadius: 26, boxShadow: HARD, display: "flex", alignItems: "center", justifyContent: "center", fontSize: w * 0.55, fontWeight: 900, color: "#FFFFFF", WebkitTextStroke: `3px ${INK}`, transform: `translateY(${(1 - Math.min(1, p)) * 200}px) rotate(${(i % 2 ? 6 : -6) * p}deg) scale(${Math.min(1.08, p)})` }}>
            {i + 1}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const ItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useBounce(0);
  const s = useIn(10);
  const nameSize = fit(props.name, 740, 100, 48, 2);
  const color = COLORS[(props.number - 1) % COLORS.length];
  return (
    <AbsoluteFill>
      <div style={{ ...abs(110, 560, 860, 500), background: "#FFFFFF", border: BORDER, borderRadius: 40, boxShadow: `12px 12px 0 ${INK}`, transform: `rotate(-2deg) scale(${0.8 + 0.2 * Math.min(1.05, p)})` }}>
        <div style={{ ...abs(50, 150, 760), fontSize: nameSize, fontWeight: 900, color: INK, lineHeight: 1.1, wordBreak: "keep-all" }}>{props.name}</div>
        {props.meta ? <div style={{ ...abs(50, 170 + nameSize * 1.2), padding: "6px 18px", background: tokens.gradientSoft, border: `3px solid ${INK}`, borderRadius: 20, fontSize: 28, fontWeight: 700, color: INK }}>{props.meta}</div> : null}
        {props.tagline ? <div style={{ ...abs(50, 400, 760), fontSize: fit(props.tagline, 740, 38, 24), fontWeight: 700, color: tokens.sub, opacity: phase(frame, durationInFrames, 0.15, 0.35) }}>{props.tagline}</div> : null}
      </div>
      <div style={{ ...abs(80, 470, 170, 170), borderRadius: 85, background: color, border: BORDER, boxShadow: HARD, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 80, fontWeight: 900, color: "#FFFFFF", WebkitTextStroke: `3px ${INK}`, transform: `scale(${Math.min(1.1, s)}) rotate(-10deg)` }}>{props.number}</div>
      {props.badge ? <div style={{ ...abs(760, 500), padding: "10px 22px", background: COLORS[2], border: BORDER, borderRadius: 24, fontSize: 32, fontWeight: 900, color: INK, transform: `rotate(8deg) scale(${Math.min(1, s)})`, boxShadow: `4px 4px 0 ${INK}` }}>{props.badge}</div> : null}
    </AbsoluteFill>
  );
};

const Recap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = useBounce(0);
  const n = props.items.length;
  const rowH = Math.min(120, Math.floor((1230 - 480) / n) - 18);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 250), padding: "6px 26px", background: COLORS[0], border: BORDER, borderRadius: 24, fontSize: fit(props.title, 800, 80, 48), fontWeight: 900, color: "#FFFFFF", boxShadow: HARD, transform: `rotate(-2deg) scale(${Math.min(1.05, head)})`, transformOrigin: "left" }}>{props.title}</div>
      {props.subtitle ? <div style={{ ...abs(L.side, 390), fontSize: 36, fontWeight: 800, color: INK }}>{props.subtitle}</div> : null}
      {props.items.map((it, i) => {
        const p = spring({ frame: Math.max(0, frame - 6 - Math.round((durationInFrames * 0.35 * i) / n)), fps, config: { damping: 9, stiffness: 170, mass: 0.8 } });
        return (
          <div key={it.name + i} style={{ ...abs(L.side, 480 + i * (rowH + 18), L.width, rowH), background: "#FFFFFF", border: BORDER, borderRadius: 26, boxShadow: `6px 6px 0 ${INK}`, display: "flex", alignItems: "center", gap: 22, padding: "0 24px", transform: `translateX(${(1 - Math.min(1, p)) * 400}px) rotate(${i % 2 ? 1 : -1}deg)` }}>
            <div style={{ width: rowH * 0.62, height: rowH * 0.62, borderRadius: rowH, background: COLORS[i % COLORS.length], border: `4px solid ${INK}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon name="check" size={rowH * 0.4} color="#FFFFFF" stroke={3.2} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: fit(it.name, 560, rowH * 0.38, 26), fontWeight: 900, color: INK, whiteSpace: "nowrap", overflow: "hidden" }}>{it.name}</div>
              {it.note ? <div style={{ fontSize: rowH * 0.22, color: tokens.sub, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden" }}>{it.note}</div> : null}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const Outro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useBounce(0);
  const size = fit(props.title, 860, 100, 52, 2);
  return (
    <AbsoluteFill>
      {Array.from({ length: 30 }, (_, i) => {
        const a = seeded(i) * Math.PI * 2;
        const r = (120 + seeded(i + 9) * 420) * Math.min(1, phase(frame, durationInFrames, 0, 0.4));
        return <div key={i} style={{ ...abs(540 + Math.cos(a) * r, 760 + Math.sin(a) * r, 22, 22), borderRadius: i % 3 ? 11 : 3, background: COLORS[i % COLORS.length], border: `3px solid ${INK}`, transform: `rotate(${i * 30 + frame * 4}deg)` }} />;
      })}
      <div style={{ ...abs(110, 620, 860), padding: "30px 20px", background: "#FFFFFF", border: BORDER, borderRadius: 36, boxShadow: HARD, textAlign: "center", fontSize: size, fontWeight: 900, color: INK, lineHeight: 1.2, wordBreak: "keep-all", transform: `rotate(-2deg) scale(${Math.min(1.06, p)})` }}>{props.title}</div>
      {props.subtitle ? <div style={{ ...abs(90, 700 + size * 2.6, 900), textAlign: "center", fontSize: fit(props.subtitle, 880, 44, 28), fontWeight: 800, color: INK, opacity: phase(frame, durationInFrames, 0.25, 0.45) }}>{props.subtitle}</div> : null}
    </AbsoluteFill>
  );
};

export const pop: ThemeSpec = {
  name: "pop",
  tokens,
  motion: { spring: { damping: 9, stiffness: 170, mass: 0.8 }, stagger: 6, float: 8 },
  Background,
  Progress,
  ItemHeader,
  Caption,
  scenes: { LHookClaim: HookClaim, LHookReveal: HookReveal, LItemCard: ItemCard, LRecap: Recap, LOutro: Outro },
};
