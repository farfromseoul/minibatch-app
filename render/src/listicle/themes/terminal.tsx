// 테마 terminal (2026-10-31): 검정 + 형광 초록, 고정폭 글꼴, 터미널 창 틀·주사선, 타자 효과, 즉각적인 움직임. 개발자 감성.
// 어울리는 주제: CLI 도구·명령어·개발 팁. 첫마디·소개 카드·정리·끝은 터미널 출력처럼 덮어쓴다.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

import { fitFontSize } from "../../lib/layout";
import { pad2, phase, typed } from "../../lib/listicle";
import { fit, type LSceneProps } from "../scenes";
import { abs, L } from "../style";
import { itemSpan, useCaptionNow } from "./shared";
import type { FrameProps, HeaderProps, ProgressProps, ThemeSpec, Tokens } from "./types";

const GREEN = "#39FF8C";
const AMBER = "#FFB000";
const MONO = "'Noto Sans Mono CJK KR', 'DejaVu Sans Mono', monospace";
const glowText = (s = 1) => `0 0 ${Math.round(10 * s)}px rgba(57,255,140,0.55)`;

const tokens: Tokens = {
  bg: "#050807",
  surface: "rgba(10, 18, 13, 0.88)",
  surfaceStrong: "#08100C",
  line: "rgba(57, 255, 140, 0.22)",
  text: "#D2FFE1",
  sub: "#86D7A2",
  muted: "#4C7A5C",
  accent: GREEN,
  accent2: AMBER,
  warn: "#FF5F56",
  onAccent: "#031008",
  gradient: `linear-gradient(${GREEN}, ${GREEN})`,
  gradientSoft: "rgba(57, 255, 140, 0.08)",
  font: MONO,
  titleFont: MONO,
  mono: MONO,
  titleWeight: 800,
  radius: 6,
  border: 2,
  cardShadow: "0 0 0 1px rgba(57,255,140,0.10)",
  activeBorder: GREEN,
  glow: (s = 1) => `0 0 ${Math.round(16 * s)}px rgba(57, 255, 140, 0.35)`,
  accentText: { color: GREEN, textShadow: glowText() },
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const flicker = 0.92 + 0.08 * Math.sin(frame / 3.1) * Math.sin(frame / 7.3);
  return (
    <>
      <AbsoluteFill style={{ background: tokens.bg }} />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 35%, rgba(57,255,140,0.10), transparent 65%)", opacity: flicker }} />
      <div style={{ ...abs(28, 84, 1024, 1810), border: `2px solid ${tokens.line}`, borderRadius: 10 }} />
      <div style={{ ...abs(28, 84, 1024, 50), borderBottom: `2px solid ${tokens.line}`, display: "flex", alignItems: "center", gap: 12, padding: "0 22px", fontFamily: MONO, fontSize: 22, color: tokens.muted }}>
        <span style={{ color: "#FF5F56" }}>●</span>
        <span style={{ color: AMBER }}>●</span>
        <span style={{ color: GREEN }}>●</span>
        <span style={{ marginLeft: 16 }}>minibatch@shorts: ~/top</span>
      </div>
      <AbsoluteFill style={{ backgroundImage: "repeating-linear-gradient(0deg, rgba(0,0,0,0.28) 0 2px, transparent 2px 4px)" }} />
    </>
  );
};

const Progress: React.FC<ProgressProps> = ({ t, index }) => {
  const frame = useCurrentFrame();
  const n = t.tracker?.items.length ?? 0;
  const [s0, s1] = itemSpan(t, index);
  const p = interpolate(frame, [s0, s1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const cells = 20;
  const filled = Math.round(((index - 1 + p) / Math.max(1, n)) * cells);
  return (
    <div style={{ ...abs(L.side, 152), fontFamily: MONO, fontSize: 30, color: tokens.sub }}>
      <span style={{ color: GREEN, textShadow: glowText(0.6) }}>[{"█".repeat(filled)}{"░".repeat(cells - filled)}]</span>
      <span style={{ marginLeft: 18 }}>{index}/{n}</span>
    </div>
  );
};

const ItemHeader: React.FC<HeaderProps> = ({ t, index, since }) => {
  const it = t.tracker?.items[index - 1];
  if (!it) return null;
  const cmd = `$ cat ${pad2(index)}-${it.name.replace(/\s+/g, "-")}.md`;
  const size = fitFontSize(it.name, L.width, 66, 38, 1) ?? 38;
  return (
    <div style={{ ...abs(L.side, 214, L.width), fontFamily: MONO }}>
      <div style={{ fontSize: 26, color: tokens.muted }}>{typed(cmd, interpolate(since, [0, 14], [0, 1], { extrapolateRight: "clamp" }))}</div>
      <div style={{ fontSize: size, fontWeight: 800, color: GREEN, textShadow: glowText(), marginTop: 10, opacity: since > 10 ? 1 : 0 }}>{it.name}</div>
      {it.meta ? <div style={{ fontSize: 24, color: tokens.muted, marginTop: 6, opacity: since > 14 ? 1 : 0 }}># {it.meta}</div> : null}
    </div>
  );
};

/** 반전 커서 자막: 지금 단어는 초록 바탕(반전), 읽은 단어 연두, 남은 단어는 어둡게, 깜빡이는 커서 */
const Caption: React.FC<FrameProps> = ({ t }) => {
  const now = useCaptionNow(t, 56, 38);
  if (!now) return null;
  const { words, size, frame } = now;
  return (
    <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "center", columnGap: Math.round(size * 0.3), rowGap: 12, fontFamily: MONO }}>
      <span style={{ fontSize: size * 0.9, color: tokens.muted }}>{">"}</span>
      {words.map((w, i) => {
        if (w.state === "current") {
          return (
            <span key={i} style={{ fontSize: size, fontWeight: 800, color: tokens.onAccent, background: GREEN, padding: "0 8px", boxShadow: tokens.glow(0.8) }}>
              {w.text}
            </span>
          );
        }
        return (
          <span key={i} style={{ fontSize: size, fontWeight: 700, color: w.state === "next" ? "#2F5A3E" : w.emphasis ? AMBER : tokens.text }}>
            {w.text}
          </span>
        );
      })}
      <span style={{ width: size * 0.5, height: size * 0.95, background: GREEN, opacity: frame % 30 < 15 ? 0.9 : 0 }} />
    </div>
  );
};

// ---------- 터미널 출력 장면

const Line: React.FC<{ y: number; children: React.ReactNode; size?: number; color?: string }> = ({ y, children, size = 34, color = tokens.sub }) => (
  <div style={{ ...abs(L.side, y, L.width), fontFamily: MONO, fontSize: size, color, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{children}</div>
);

const HookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const cmd = `$ ls ~/${props.kicker.replace(/\s+/g, "-")} | wc -l`;
  const t1 = phase(frame, durationInFrames, 0.02, 0.25);
  const size = fit(props.claim, 900, 170, 80);
  return (
    <AbsoluteFill>
      <Line y={300} color={tokens.muted}>{typed(cmd, t1)}</Line>
      {t1 >= 1 ? (
        <div style={{ ...abs(L.side, 560, L.width), fontFamily: MONO, fontSize: size, fontWeight: 800, color: GREEN, textShadow: glowText(1.4), letterSpacing: -4 }}>{typed(props.claim, phase(frame, durationInFrames, 0.25, 0.45))}</div>
      ) : null}
      {props.claimNote && phase(frame, durationInFrames, 0.45, 0.5) > 0 ? (
        <Line y={600 + size} color={AMBER}>[WARN] {props.claimNote}</Line>
      ) : null}
      {props.aside && phase(frame, durationInFrames, 0.5, 0.55) > 0 ? <Line y={660 + size} color={tokens.muted}># {props.aside}</Line> : null}
    </AbsoluteFill>
  );
};

const HookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const size = fit(props.headline, 940, 84, 48);
  return (
    <AbsoluteFill>
      <Line y={300} color={tokens.muted}>{typed(`$ top -n ${props.count}`, phase(frame, durationInFrames, 0, 0.15))}</Line>
      <div style={{ ...abs(L.side, 380, L.width), fontFamily: MONO, fontSize: size, fontWeight: 800, color: tokens.text, opacity: phase(frame, durationInFrames, 0.15, 0.2) }}>
        {props.highlight && props.headline.includes(props.highlight) ? (
          <>
            {props.headline.slice(0, props.headline.indexOf(props.highlight))}
            <span style={{ color: GREEN, textShadow: glowText() }}>{props.highlight}</span>
            {props.headline.slice(props.headline.indexOf(props.highlight) + props.highlight.length)}
          </>
        ) : props.headline}
      </div>
      {Array.from({ length: props.count }, (_, i) => {
        const on = phase(frame, durationInFrames, 0.25 + i * 0.08, 0.27 + i * 0.08) > 0;
        return on ? (
          <Line key={i} y={560 + i * 92} size={40} color={i === 0 ? GREEN : tokens.sub}>
            {`PID ${String(1000 + i * 17)}  ${pad2(i + 1)}  ${"▮".repeat(10 - i)}${"▯".repeat(i)}  ready`}
          </Line>
        ) : null;
      })}
    </AbsoluteFill>
  );
};

const ItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const show = (a: number) => phase(frame, durationInFrames, a, a + 0.02) > 0;
  const nameSize = fit(props.name, 820, 96, 44);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 540, L.width, 520), border: `2px solid ${GREEN}`, boxShadow: tokens.glow(0.6), borderRadius: 6 }}>
        <div style={{ ...abs(40, -24), padding: "0 14px", background: tokens.bg, fontFamily: MONO, fontSize: 34, color: GREEN, textShadow: glowText() }}>[ {pad2(props.number)} ]</div>
        <div style={{ ...abs(50, 110, 840), fontFamily: MONO, fontSize: nameSize, fontWeight: 800, color: GREEN, textShadow: glowText(1.2), wordBreak: "break-all" }}>{typed(props.name, phase(frame, durationInFrames, 0.02, 0.3))}</div>
        {props.meta && show(0.3) ? <div style={{ ...abs(50, 140 + nameSize), fontFamily: MONO, fontSize: 28, color: tokens.muted }}># {props.meta}</div> : null}
        {props.tagline && show(0.4) ? <div style={{ ...abs(50, 330, 840), fontFamily: MONO, fontSize: fit(props.tagline, 820, 38, 24), color: tokens.text }}>{">"} {props.tagline}</div> : null}
        {props.badge && show(0.45) ? <div style={{ ...abs(50, 420), fontFamily: MONO, fontSize: 30, color: AMBER }}>[{props.badge}]</div> : null}
      </div>
    </AbsoluteFill>
  );
};

const Recap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const n = props.items.length;
  return (
    <AbsoluteFill>
      <Line y={250} color={tokens.muted}>{typed("$ cat summary.txt", phase(frame, durationInFrames, 0, 0.12))}</Line>
      <div style={{ ...abs(L.side, 320, L.width), fontFamily: MONO, fontSize: fit(props.title, 900, 84, 48), fontWeight: 800, color: GREEN, textShadow: glowText(1.2), opacity: phase(frame, durationInFrames, 0.12, 0.16) }}>{props.title}</div>
      {props.subtitle ? <Line y={430} color={tokens.muted}># {props.subtitle}</Line> : null}
      {props.items.map((it, i) => {
        const on = phase(frame, durationInFrames, 0.18 + (0.4 * i) / n, 0.2 + (0.4 * i) / n) > 0;
        return on ? (
          <Line key={it.name + i} y={520 + i * 120} size={40} color={tokens.text}>
            <span style={{ color: GREEN }}>[x]</span> {pad2(i + 1)} <span style={{ color: GREEN, textShadow: glowText(0.6) }}>{it.name}</span>
            <span style={{ color: tokens.muted, fontSize: 28 }}>{it.note ? `\n     ${it.note}` : ""}</span>
          </Line>
        ) : null;
      })}
    </AbsoluteFill>
  );
};

const Outro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const size = fit(props.title, 900, 92, 48, 2);
  return (
    <AbsoluteFill>
      <Line y={520} color={tokens.muted}>{typed("$ exit", phase(frame, durationInFrames, 0, 0.15))}</Line>
      <div style={{ ...abs(L.side, 620, L.width), fontFamily: MONO, fontSize: size, fontWeight: 800, color: GREEN, textShadow: glowText(1.3), lineHeight: 1.25, wordBreak: "keep-all" }}>{typed(props.title, phase(frame, durationInFrames, 0.15, 0.45))}</div>
      {props.subtitle && phase(frame, durationInFrames, 0.5, 0.52) > 0 ? <Line y={660 + size * 2.4} color={tokens.sub}># {props.subtitle}</Line> : null}
      {phase(frame, durationInFrames, 0.6, 0.62) > 0 ? (
        <Line y={760 + size * 2.4} color={tokens.muted}>
          Process completed <span style={{ color: GREEN }}>✓</span> <span style={{ background: GREEN, opacity: frame % 30 < 15 ? 1 : 0 }}>{"  "}</span>
        </Line>
      ) : null}
    </AbsoluteFill>
  );
};

export const terminal: ThemeSpec = {
  name: "terminal",
  tokens,
  motion: { spring: { damping: 32, stiffness: 320, mass: 0.8 }, stagger: 4, float: 0 },
  Background,
  Progress,
  ItemHeader,
  Caption,
  scenes: { LHookClaim: HookClaim, LHookReveal: HookReveal, LItemCard: ItemCard, LRecap: Recap, LOutro: Outro },
};
