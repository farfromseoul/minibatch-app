// 미니멀 테마 틀 (v1.4 L27, 2026-11-01 사용자: 참고 영상처럼 단순하되 더 세련되게. 색이 복잡하고 올드해 보이지 않게).
// 색은 세 가지(바탕·글자·강조 하나)와 그 옅은 단계만. 그라데이션·빛·그림자 없음, 얇은 선, 넉넉한 여백, 큰 글자 위계.
// noir·air·slate 가 색만 바꿔 이 틀을 쓴다. 설명 그림(공통 장면)은 tokens 로 같은 톤이 된다.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../../lib/layout";
import { pad2, phase, recapCells, trackerSlots } from "../../lib/listicle";
import type { LSceneProps } from "../scenes";
import { abs, L, rise } from "../style";
import { useIn } from "./context";
import { itemSpan, useCaptionNow } from "./shared";
import type { FrameProps, HeaderProps, ProgressProps, ThemeSpec, Tokens } from "./types";

export type Palette = {
  name: string;
  bg: string;
  surface: string;       // 카드 바탕 (바탕보다 한 단계)
  line: string;          // 얇은 선
  text: string;
  sub: string;
  muted: string;
  accent: string;        // 강조색 하나
  accentSoft: string;    // 강조색 옅은 면 (12% 안팎)
  onAccent: string;
};

const FONT = "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif";
const MONO = "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace";

const ease = (frame: number, a: number, b: number) =>
  interpolate(frame, [a, b], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: (x) => 1 - Math.pow(1 - x, 3) });

export function makeMinimal(c: Palette): ThemeSpec {
  const tokens: Tokens = {
    bg: c.bg,
    surface: c.surface,
    surfaceStrong: c.surface,
    line: c.line,
    text: c.text,
    sub: c.sub,
    muted: c.muted,
    accent: c.accent,
    accent2: c.accent,
    warn: c.muted,
    onAccent: c.onAccent,
    gradient: c.accent,
    gradientSoft: c.accentSoft,
    font: FONT,
    titleFont: FONT,
    mono: MONO,
    titleWeight: 800,
    radius: 18,
    border: 1.5,
    cardShadow: "none",
    activeBorder: c.accent,
    glow: () => "none",
    accentText: { color: c.accent },
    windowDots: [c.line, c.line, c.line],
  };

  const Background: React.FC = () => <AbsoluteFill style={{ background: c.bg }} />;

  /** 왼쪽 위 '03 / 10', 아래 얇은 선 하나가 항목 진행만큼 찬다 */
  const Progress: React.FC<ProgressProps> = ({ t, index }) => {
    const frame = useCurrentFrame();
    const items = t.tracker?.items ?? [];
    const slots = trackerSlots(items.length, index);
    const [s0, s1] = itemSpan(t, index);
    const fill = interpolate(frame, [s0, s1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const done = slots.filter((s) => s === "done").length;
    const w = L.width * ((done + fill) / Math.max(1, items.length));
    return (
      <>
        <div style={{ ...abs(L.side, L.counterY), display: "flex", alignItems: "baseline", gap: 10, fontFamily: MONO, fontSize: 28, letterSpacing: 2 }}>
          <span style={{ color: c.accent, fontWeight: 700 }}>{pad2(index)}</span>
          <span style={{ color: c.muted }}>/ {pad2(items.length)}</span>
        </div>
        <div style={{ ...abs(L.side, L.barY, L.width, 2), background: c.line }} />
        <div style={{ ...abs(L.side, L.barY, w, 2), background: c.accent }} />
      </>
    );
  };

  const ItemHeader: React.FC<HeaderProps> = ({ t, index, since }) => {
    const it = t.tracker?.items[index - 1];
    if (!it) return null;
    const p = ease(since, 0, 12);
    const size = fitFontSize(it.name, L.width, 80, 44, 1) ?? 44;
    return (
      <div style={{ ...abs(L.side, L.headerY, L.width), opacity: p, transform: `translateY(${(1 - p) * 12}px)` }}>
        <div style={{ fontSize: size, fontWeight: 800, color: c.text, letterSpacing: -1.5, whiteSpace: "nowrap", lineHeight: 1.1 }}>{it.name}</div>
        {it.meta ? <div style={{ marginTop: 12, fontFamily: MONO, fontSize: 26, color: c.muted }}>{it.meta}</div> : null}
      </div>
    );
  };

  /** 지금 단어만 강조색, 읽은 단어 글자색, 남은 단어 옅게. 밑줄·그림자 없음 */
  const Caption: React.FC<FrameProps> = ({ t }) => {
    const { fps } = useVideoConfig();
    const now = useCaptionNow(t);
    if (!now) return null;
    const { words, size, since } = now;
    const enter = spring({ frame: since, fps, config: { damping: 26, stiffness: 160 } });
    return (
      <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "flex-end", columnGap: Math.round(size * 0.26), rowGap: 12, opacity: Math.min(1, enter * 1.4), transform: `translateY(${(1 - enter) * 10}px)` }}>
        {words.map((w, i) => (
          <span key={i} style={{ fontSize: size, fontWeight: 700, lineHeight: 1.3, letterSpacing: -0.5, color: w.state === "current" || (w.emphasis && w.state === "done") ? c.accent : w.state === "done" ? c.text : c.muted }}>
            {w.text}
          </span>
        ))}
      </div>
    );
  };

  // ---------- 장면 (틀 장면만 이 테마의 레이아웃으로)

  const HookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
    const frame = useCurrentFrame();
    const a = useIn(0);
    const b = useIn(6);
    const size = fit(props.claim, L.width, 200, 96, 2);
    const line = ease(frame, 4, 4 + Math.round(durationInFrames * 0.3));
    return (
      <AbsoluteFill>
        <div style={{ ...abs(L.side, 470), fontFamily: MONO, fontSize: 28, color: c.muted, letterSpacing: 3, ...rise(a, 10) }}>{props.kicker}</div>
        <div style={{ ...abs(L.side, 530, L.width * line, 2), background: c.accent }} />
        <div style={{ ...abs(L.side, 590, L.width), fontSize: size, fontWeight: 800, color: c.text, letterSpacing: -4, lineHeight: 1.05, wordBreak: "keep-all", ...rise(b, 24) }}>
          {props.claim}
          {props.claimNote ? <span style={{ fontSize: size * 0.32, color: c.accent, marginLeft: 18, letterSpacing: 0, verticalAlign: "top" }}>{props.claimNote}</span> : null}
        </div>
        {props.aside ? <div style={{ ...abs(L.side, 620 + size * 1.15, L.width), fontSize: 40, color: c.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.3, 0.45) }}>{props.aside}</div> : null}
      </AbsoluteFill>
    );
  };

  const HookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ durationInFrames, props }) => {
    const frame = useCurrentFrame();
    const a = useIn(0);
    const n = props.count;
    const size = fit(props.headline, L.width, 112, 64, 2);
    const cell = Math.min(84, Math.floor((L.width - 12 * (n - 1)) / n));
    const hl = props.highlight && props.headline.includes(props.highlight) ? props.highlight : "";
    const i = hl ? props.headline.indexOf(hl) : -1;
    return (
      <AbsoluteFill>
        <div style={{ ...abs(L.side, 470), fontFamily: MONO, fontSize: 28, color: c.muted, letterSpacing: 3, ...rise(a, 10) }}>{props.kicker}</div>
        <div style={{ ...abs(L.side, 540, L.width), fontSize: size, fontWeight: 800, color: c.text, letterSpacing: -3, lineHeight: 1.1, wordBreak: "keep-all", ...rise(a, 20) }}>
          {i >= 0 ? (
            <>
              {props.headline.slice(0, i)}
              <span style={{ color: c.accent }}>{hl}</span>
              {props.headline.slice(i + hl.length)}
            </>
          ) : props.headline}
        </div>
        <div style={{ ...abs(L.side, 600 + size * 2.4, L.width), display: "flex", gap: 12 }}>
          {Array.from({ length: n }, (_, k) => {
            const p = ease(frame, 8 + k * Math.max(2, Math.round(24 / n)), 16 + k * Math.max(2, Math.round(24 / n)));
            return (
              <div key={k} style={{ width: cell, height: cell, borderRadius: 12, border: `1.5px solid ${k === 0 ? c.accent : c.line}`, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: Math.round(cell * 0.36), color: k === 0 ? c.accent : c.sub, opacity: p, transform: `translateY(${(1 - p) * 12}px)` }}>
                {pad2(k + 1)}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    );
  };

  const ItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ durationInFrames, props }) => {
    const frame = useCurrentFrame();
    const a = useIn(0);
    const b = useIn(5);
    const nameSize = fit(props.name, L.width, 120, 60, 2);
    const line = ease(frame, 6, 6 + Math.round(durationInFrames * 0.35));
    return (
      <AbsoluteFill>
        <div style={{ ...abs(L.side - 8, 360), fontFamily: MONO, fontSize: 260, fontWeight: 700, color: "transparent", WebkitTextStroke: `2px ${c.accent}`, lineHeight: 1, ...rise(a, 16) }}>{pad2(props.number)}</div>
        <div style={{ ...abs(L.side, 660, L.width), fontSize: nameSize, fontWeight: 800, color: c.text, letterSpacing: -3, lineHeight: 1.08, wordBreak: "break-word", ...rise(b, 22) }}>{props.name}</div>
        <div style={{ ...abs(L.side, 700 + nameSize * 1.1 * (nameSize < 90 ? 2 : 1), L.width * line, 2), background: c.line }} />
        <div style={{ ...abs(L.side, 730 + nameSize * 1.1 * (nameSize < 90 ? 2 : 1), L.width), opacity: phase(frame, durationInFrames, 0.15, 0.3) }}>
          {props.tagline ? <div style={{ fontSize: fit(props.tagline, L.width, 46, 30), color: c.sub, fontWeight: 600 }}>{props.tagline}</div> : null}
          <div style={{ display: "flex", gap: 14, marginTop: 22, alignItems: "center" }}>
            {props.badge ? <div style={{ padding: "6px 16px", borderRadius: 999, background: c.accent, color: c.onAccent, fontSize: 26, fontWeight: 800 }}>{props.badge}</div> : null}
            {props.meta ? <div style={{ fontFamily: MONO, fontSize: 26, color: c.muted }}>{props.meta}</div> : null}
          </div>
        </div>
      </AbsoluteFill>
    );
  };

  const Recap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
    const frame = useCurrentFrame();
    const a = useIn(0);
    const n = props.items.length;
    const cells = recapCells(n, { x: L.side, y: 480, w: L.width, h: 760 }, n >= 7 ? 28 : 0, 110);
    return (
      <AbsoluteFill>
        {/* 제목·부제는 한 묶음: 부제가 제목 크기를 따라 내려간다 (2026-11-02: 부제가 큰 제목에 붙어 보였다) */}
        <div style={{ ...abs(L.side, 250, L.width), display: "flex", flexDirection: "column", gap: 18, ...rise(a, 18) }}>
          <div style={{ fontSize: fit(props.title, L.width, 96, 56), fontWeight: 800, color: c.text, letterSpacing: -3, lineHeight: 1.1 }}>{props.title}</div>
          {props.subtitle ? <div style={{ fontSize: 34, color: c.sub, fontWeight: 600, lineHeight: 1.3 }}>{props.subtitle}</div> : null}
        </div>
        {props.items.map((it, i) => {
          const cell = cells[i];
          const p = ease(frame, 6 + Math.round((durationInFrames * 0.35 * i) / n), 16 + Math.round((durationInFrames * 0.35 * i) / n));
          const numW = 64;
          return (
            <div key={it.name + i} style={{ ...abs(cell.x, cell.y, cell.w, cell.h), borderTop: `1.5px solid ${c.line}`, display: "flex", alignItems: "center", gap: 18, opacity: p, transform: `translateY(${(1 - p) * 10}px)` }}>
              <div style={{ width: numW, fontFamily: MONO, fontSize: 28, color: c.accent }}>{pad2(i + 1)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: fit(it.name, cell.w - numW - 30, Math.round(cell.h * 0.36), 26), fontWeight: 800, color: c.text, whiteSpace: "nowrap", overflow: "hidden" }}>{it.name}</div>
                {it.note && cell.h >= 90 ? <div style={{ fontSize: n >= 7 ? 22 : 26, color: c.muted, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden" }}>{it.note}</div> : null}
              </div>
              {it.tag && n < 7 ? <div style={{ fontSize: 24, color: c.accent, fontWeight: 700 }}>{it.tag}</div> : null}
            </div>
          );
        })}
      </AbsoluteFill>
    );
  };

  const Outro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
    const frame = useCurrentFrame();
    const a = useIn(0);
    const size = fit(props.title, L.width, 110, 56, 2);
    return (
      <AbsoluteFill>
        <div style={{ ...abs(L.side, 600, 80, 6), background: c.accent, transform: `scaleX(${ease(frame, 0, 14)})`, transformOrigin: "left" }} />
        <div style={{ ...abs(L.side, 650, L.width), fontSize: size, fontWeight: 800, color: c.text, letterSpacing: -3, lineHeight: 1.12, wordBreak: "keep-all", ...rise(a, 20) }}>{props.title}</div>
        {props.subtitle ? <div style={{ ...abs(L.side, 690 + size * 2.3, L.width), fontSize: 38, color: c.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.25, 0.4) }}>{props.subtitle}</div> : null}
      </AbsoluteFill>
    );
  };

  return {
    name: c.name,
    tokens,
    motion: { spring: { damping: 26, stiffness: 150, mass: 0.9 }, stagger: 5, float: 0 },
    Background,
    Progress,
    ItemHeader,
    Caption,
    scenes: { LHookClaim: HookClaim, LHookReveal: HookReveal, LItemCard: ItemCard, LRecap: Recap, LOutro: Outro },
  };
}

const fit = (text: string, width: number, base: number, min: number, lines = 1) => fitFontSize(text, width, base, min, lines) ?? min;
