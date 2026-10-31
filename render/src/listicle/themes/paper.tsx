// 테마 paper (2026-10-31): 아이보리 종이, 검정 명조 굵은 글씨 + 주홍 포인트, 잡지 같은 큰 번호, 형광펜 자막, 또각또각 움직임.
// 어울리는 주제: 팁·방법, 개념 정리. 첫마디·소개 카드·정리·끝은 잡지 레이아웃으로 덮어쓴다.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../../lib/layout";
import { pad2, phase } from "../../lib/listicle";
import { fit, Highlighted, type LSceneProps } from "../scenes";
import { abs, L, rise } from "../style";
import { useIn } from "./context";
import { useCaptionNow } from "./shared";
import type { FrameProps, HeaderProps, ProgressProps, ThemeSpec, Tokens } from "./types";

const INK = "#161514";
const RED = "#D9381E";
const SERIF = "'Noto Serif CJK KR', 'Noto Serif KR', serif";

const tokens: Tokens = {
  bg: "#F3EEE4",
  surface: "#FFFDF7",
  surfaceStrong: "#FFFFFF",
  line: "rgba(22, 21, 20, 0.18)",
  text: INK,
  sub: "#57524A",
  muted: "#9A9286",
  accent: RED,
  accent2: "#1F3A93",
  warn: RED,
  onAccent: "#FFFFFF",
  gradient: `linear-gradient(${RED}, ${RED})`,
  gradientSoft: "rgba(217, 56, 30, 0.07)",
  font: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif",
  titleFont: SERIF,
  mono: "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace",
  titleWeight: 900,
  radius: 4,
  border: 2,
  cardShadow: `8px 8px 0 ${INK}`,
  activeBorder: INK,
  glow: () => "none",
  accentText: { color: RED },
};

const Background: React.FC = () => (
  <>
    <AbsoluteFill style={{ background: tokens.bg }} />
    {/* 종이 결: 아주 옅은 가로줄과 사선 */}
    <AbsoluteFill style={{ backgroundImage: "repeating-linear-gradient(0deg, rgba(22,21,20,0.035) 0 1px, transparent 1px 46px)" }} />
    <AbsoluteFill style={{ backgroundImage: "repeating-linear-gradient(115deg, rgba(120,90,40,0.025) 0 2px, transparent 2px 9px)" }} />
    {/* 잡지 머리 괘선 */}
    <div style={{ ...abs(L.side, 112, L.width, 6), background: INK }} />
    <div style={{ ...abs(L.side, 124, L.width, 2), background: INK }} />
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 40%, transparent 60%, rgba(120,90,40,0.10) 100%)" }} />
  </>
);

const Progress: React.FC<ProgressProps> = ({ t, index }) => {
  const n = t.tracker?.items.length ?? 0;
  return (
    <div style={{ ...abs(L.side, 140, L.width), display: "flex", alignItems: "center", justifyContent: "space-between", fontFamily: SERIF }}>
      <div style={{ fontSize: 28, letterSpacing: 8, color: INK, fontWeight: 700 }}>THE LIST</div>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        {Array.from({ length: n }, (_, i) => (
          <div key={i} style={{ width: 18, height: 18, border: `2px solid ${INK}`, background: i + 1 < index ? INK : i + 1 === index ? RED : "transparent", borderColor: i + 1 === index ? RED : INK }} />
        ))}
        <div style={{ marginLeft: 14, fontSize: 28, color: INK, fontWeight: 700 }}>No. {pad2(index)}</div>
      </div>
    </div>
  );
};

const ItemHeader: React.FC<HeaderProps> = ({ t, index, since }) => {
  const it = t.tracker?.items[index - 1];
  if (!it) return null;
  const p = interpolate(since, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const size = fitFontSize(it.name, L.width - 230, 70, 40, 1) ?? 40;
  return (
    <div style={{ ...abs(L.side, 214, L.width), display: "flex", alignItems: "flex-end", gap: 26, opacity: p }}>
      <div style={{ fontFamily: SERIF, fontSize: 170, fontWeight: 900, color: RED, lineHeight: 0.85, letterSpacing: -8 }}>{pad2(index)}</div>
      <div style={{ paddingBottom: 8, borderBottom: `3px solid ${INK}`, flex: 1 }}>
        <div style={{ fontFamily: SERIF, fontSize: size, fontWeight: 900, color: INK, whiteSpace: "nowrap" }}>{it.name}</div>
        {it.meta ? <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 26, color: tokens.sub, marginTop: 4 }}>{it.meta}</div> : null}
      </div>
    </div>
  );
};

/** 형광펜 자막: 지금 단어 뒤로 노란 형광펜이 왼쪽부터 칠해진다 */
const Caption: React.FC<FrameProps> = ({ t }) => {
  const { fps } = useVideoConfig();
  const now = useCaptionNow(t, 62, 42);
  if (!now) return null;
  const { words, size, since, frame } = now;
  const enter = interpolate(since, [0, 6], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", columnGap: Math.round(size * 0.24), rowGap: 12, opacity: enter }}>
      {words.map((w, i) => {
        const mark = w.state === "current" ? spring({ frame: frame - w.fromFrame, fps, config: { damping: 30, stiffness: 220 } }) : w.state === "done" ? 1 : 0;
        const color = w.state === "next" ? "#B8B0A3" : w.emphasis ? RED : INK;
        return (
          <span key={i} style={{ position: "relative", isolation: "isolate", display: "inline-block", fontSize: size, fontWeight: 800, color, lineHeight: 1.3 }}>
            {w.state !== "next" ? (
              <span style={{ position: "absolute", left: -6, right: -6, bottom: size * 0.08, height: size * 0.42, background: "rgba(255, 214, 10, 0.75)", transform: `skewX(-8deg) scaleX(${mark})`, transformOrigin: "left", opacity: w.state === "current" ? 1 : 0.35, zIndex: -1 }} />
            ) : null}
            <span style={{ position: "relative" }}>{w.text}</span>
          </span>
        );
      })}
    </div>
  );
};

// ---------- 잡지 레이아웃 장면

const HookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useIn(0);
  const claim = useIn(6);
  const rule = phase(frame, durationInFrames, 0.15, 0.4);
  const size = fit(props.claim, 900, 230, 100);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(0, 300, 1080), textAlign: "center", fontFamily: SERIF, fontSize: 34, letterSpacing: 10, color: INK, fontWeight: 700, ...rise(p, -10) }}>— {props.kicker} —</div>
      <div style={{ ...abs(0, 720 - size * 0.62, 1080), textAlign: "center", fontFamily: SERIF, fontSize: size, fontWeight: 900, color: INK, letterSpacing: -6, lineHeight: 1.05, ...rise(claim, 24) }}>{props.claim}</div>
      <div style={{ ...abs(540 - 300 * rule, 720 + size * 0.5, 600 * rule, 8), background: RED }} />
      {props.claimNote ? (
        <div style={{ ...abs(760, 720 - size * 0.9), padding: "8px 18px", border: `4px solid ${RED}`, color: RED, fontFamily: SERIF, fontSize: 34, fontWeight: 900, transform: `rotate(-10deg) scale(${Math.min(1, claim)})` }}>{props.claimNote}</div>
      ) : null}
      {props.aside ? <div style={{ ...abs(0, 760 + size * 0.5, 1080), textAlign: "center", fontFamily: SERIF, fontStyle: "italic", fontSize: 44, color: tokens.sub, opacity: phase(frame, durationInFrames, 0.3, 0.45) }}>{props.aside}</div> : null}
    </AbsoluteFill>
  );
};

const HookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ props }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = useIn(0);
  const n = props.count;
  const w = Math.floor(L.width / n);
  const size = fit(props.headline, 940, 112, 60);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(0, 300, 1080), textAlign: "center", fontFamily: SERIF, fontSize: 34, letterSpacing: 10, color: INK, fontWeight: 700 }}>— {props.kicker} —</div>
      <div style={{ ...abs(0, 430, 1080), textAlign: "center", fontFamily: SERIF, fontSize: size, fontWeight: 900, color: INK, letterSpacing: -3, ...rise(head, 20) }}>
        <Highlighted text={props.headline} highlight={props.highlight} />
      </div>
      <div style={{ ...abs(L.side, 700, L.width, 3), background: INK }} />
      {Array.from({ length: n }, (_, i) => {
        const p = spring({ frame: Math.max(0, frame - 10 - i * 5), fps, config: { damping: 30, stiffness: 220 } });
        return (
          <div key={i} style={{ ...abs(L.side + i * w, 730, w, 260), borderLeft: i ? `2px solid ${tokens.line}` : undefined, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: SERIF, fontSize: Math.min(170, w * 0.8), fontWeight: 900, color: i === 0 ? RED : INK, letterSpacing: -6, opacity: Math.min(1, p), transform: `translateY(${(1 - p) * 30}px)` }}>
            {pad2(i + 1)}
          </div>
        );
      })}
      <div style={{ ...abs(L.side, 1010, L.width, 3), background: INK }} />
    </AbsoluteFill>
  );
};

const ItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useIn(0);
  const oneWord = !props.name.trim().includes(" ");  // 띄어쓰기 없는 이름(CLAUDE.md 등)은 한 줄로, 크기를 줄여 맞춘다
  const nameSize = fit(props.name, oneWord ? 380 : 470, 92, 36, oneWord ? 1 : 2);  // 명조 영문은 추정보다 넓다
  return (
    <AbsoluteFill>
      <div style={{ ...abs(90, 520, 900, 560), background: "#FFFFFF", border: `3px solid ${INK}`, boxShadow: `14px 14px 0 ${INK}`, ...rise(p, 40) }}>
        <div style={{ ...abs(40, 30), fontFamily: SERIF, fontSize: 300, fontWeight: 900, color: RED, lineHeight: 1, letterSpacing: -14 }}>{pad2(props.number)}</div>
        <div style={{ ...abs(330, 70, 2, 420), background: INK }} />
        <div style={{ ...abs(370, 70, 490) }}>
          <div style={{ fontFamily: SERIF, fontSize: 26, letterSpacing: 8, color: tokens.sub, fontWeight: 700 }}>No. {pad2(props.number)}</div>
          <div style={{ fontFamily: SERIF, fontSize: nameSize, fontWeight: 900, color: INK, lineHeight: 1.1, marginTop: 18, wordBreak: "keep-all", whiteSpace: oneWord ? "nowrap" : "normal" }}>{props.name}</div>
          {props.meta ? <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 28, color: tokens.sub, marginTop: 18 }}>{props.meta}</div> : null}
          <div style={{ width: 120, height: 4, background: RED, marginTop: 26 }} />
          {props.tagline ? <div style={{ fontSize: fit(props.tagline, 480, 36, 24, 2), color: INK, marginTop: 22, lineHeight: 1.4, opacity: phase(frame, durationInFrames, 0.15, 0.35) }}>{props.tagline}</div> : null}
        </div>
        {props.badge ? (
          <div style={{ ...abs(700, -34), padding: "10px 20px", background: RED, color: "#FFFFFF", fontFamily: SERIF, fontSize: 30, fontWeight: 900, transform: "rotate(6deg)", boxShadow: `4px 4px 0 ${INK}` }}>{props.badge}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/** 정리: 목차처럼 번호 …… 이름 */
const Recap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = useIn(0);
  const n = props.items.length;
  const rowH = Math.min(120, Math.floor((1230 - 500) / n));
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 250), fontFamily: SERIF, fontSize: 30, letterSpacing: 10, color: RED, fontWeight: 700, ...rise(head, 10) }}>CONTENTS</div>
      <div style={{ ...abs(L.side, 300), fontFamily: SERIF, fontSize: fit(props.title, 900, 96, 54), fontWeight: 900, color: INK, letterSpacing: -3, ...rise(head, 16) }}>{props.title}</div>
      {props.subtitle ? <div style={{ ...abs(L.side, 420), fontFamily: SERIF, fontStyle: "italic", fontSize: 36, color: tokens.sub }}>{props.subtitle}</div> : null}
      {props.items.map((it, i) => {
        const p = spring({ frame: Math.max(0, frame - 6 - Math.round((durationInFrames * 0.35 * i) / n)), fps, config: { damping: 30, stiffness: 220 } });
        const y = 500 + i * rowH;
        return (
          <div key={it.name + i} style={{ ...abs(L.side, y, L.width, rowH), display: "flex", alignItems: "baseline", gap: 18, borderBottom: `1px solid ${tokens.line}`, opacity: Math.min(1, p), transform: `translateX(${(1 - p) * -30}px)`, paddingTop: rowH * 0.22 }}>
            <div style={{ fontFamily: SERIF, fontSize: rowH * 0.42, fontWeight: 900, color: RED, width: rowH * 0.9 }}>{pad2(i + 1)}</div>
            <div style={{ fontFamily: SERIF, fontSize: fit(it.name, 420, rowH * 0.36, 26), fontWeight: 900, color: INK, whiteSpace: "nowrap" }}>{it.name}</div>
            <div style={{ flex: 1, borderBottom: `3px dotted ${tokens.muted}`, transform: "translateY(-8px)" }} />
            <div style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: rowH * 0.22, color: tokens.sub, whiteSpace: "nowrap", maxWidth: 300, overflow: "hidden" }}>{it.tag || it.note || ""}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const Outro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useIn(0);
  const rule = phase(frame, durationInFrames, 0.15, 0.45);
  const size = fit(props.title, 900, 104, 54, 2);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(90, 600, 900), textAlign: "center", fontFamily: SERIF, fontSize: size, fontWeight: 900, color: INK, lineHeight: 1.2, wordBreak: "keep-all", ...rise(p, 20) }}>{props.title}</div>
      <div style={{ ...abs(540 - 220 * rule, 640 + size * 2.3, 440 * rule, 6), background: RED }} />
      {props.subtitle ? <div style={{ ...abs(90, 690 + size * 2.3, 900), textAlign: "center", fontFamily: SERIF, fontStyle: "italic", fontSize: fit(props.subtitle, 880, 44, 28), color: tokens.sub, opacity: phase(frame, durationInFrames, 0.25, 0.45) }}>{props.subtitle}</div> : null}
      <div style={{ ...abs(0, 820 + size * 2.3, 1080), textAlign: "center", fontFamily: SERIF, fontSize: 30, letterSpacing: 12, color: tokens.muted, opacity: phase(frame, durationInFrames, 0.4, 0.6) }}>— FIN —</div>
    </AbsoluteFill>
  );
};

export const paper: ThemeSpec = {
  name: "paper",
  tokens,
  motion: { spring: { damping: 30, stiffness: 220, mass: 1 }, stagger: 5, float: 0 },
  Background,
  Progress,
  ItemHeader,
  Caption,
  scenes: { LHookClaim: HookClaim, LHookReveal: HookReveal, LItemCard: ItemCard, LRecap: Recap, LOutro: Outro },
};
