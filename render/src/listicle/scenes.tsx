// 목록형 쇼츠(D42) 공통 장면 13종(v1.4 실습 장면 LWalkthrough 포함). 속성 모양은 src/lib/timeline.ts 의 검사, job-api app/schemas/templates.py 와 같다.
// 2026-10-31 v1.3: 색·글꼴·모서리·그림자·움직임은 테마 템플릿(useTheme)에서 받는다. 테마가 덮어쓰지 않은 장면은 여기 것을 쓴다.
// 움직임은 모두 프레임에서 계산한다(spring·interpolate). 장면 길이가 달라도 같은 리듬이 되게 길이 비율(phase)을 쓴다.
import React from "react";
import { AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../lib/layout";
import { countUp, pad2, phase, recapCells, seeded, typed, walkSchedule } from "../lib/listicle";
import type { WalkStep, WalkTiming } from "../lib/listicle";
import { Icon } from "./icons";
import { abs, L, rise } from "./style";
import { Accent, AssetContext, cardStyle, useIn, useTheme, useTokens } from "./themes/context";
import type { Tokens } from "./themes/types";

export type LSceneProps<P> = { durationInFrames: number; props: P };

export const fit = (text: string, width: number, base: number, min: number, lines = 1) => fitFontSize(text, width, base, min, lines) ?? min;

/** 차례로 나오는 것의 i 번째 등장 */
const useStagger = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { motion } = useTheme();
  return (i: number, start = 0) => spring({ frame: Math.max(0, frame - start - i * motion.stagger), fps, config: motion.spring });
};

/** 글자 안 일부(highlight)를 강조 */
export const Highlighted: React.FC<{ text: string; highlight?: string }> = ({ text, highlight }) => {
  if (!highlight || !text.includes(highlight)) return <>{text}</>;
  const i = text.indexOf(highlight);
  return (
    <>
      {text.slice(0, i)}
      <Accent>{highlight}</Accent>
      {text.slice(i + highlight.length)}
    </>
  );
};

/** 위쪽 주제 꼬리표 (첫마디 두 장면) */
export const Kicker: React.FC<{ text: string; p: number }> = ({ text, p }) => {
  const k = useTokens();
  const size = fit(text, 700, 40, 28);
  return (
    <div style={{ ...abs(0, 250, 1080), display: "flex", justifyContent: "center", ...rise(p, -16) }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 30px", ...cardStyle(k, { radius: Math.max(k.radius, 40) }) }}>
        <Icon name="sparkles" size={size} color={k.accent} />
        <div style={{ fontSize: size, fontWeight: 700, color: k.text, fontFamily: k.font }}>{text}</div>
      </div>
    </div>
  );
};

/** 강조 면 테두리 안에 내용 (그라데이션 테두리 원·카드) */
const Ring: React.FC<{ k: Tokens; size: number; pad?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({ k, size, pad = 4, style, children }) => (
  <div style={{ width: size, height: size, borderRadius: size / 2, padding: pad, background: k.gradient, boxShadow: k.glow(0.6), ...style }}>
    <div style={{ width: "100%", height: "100%", borderRadius: size / 2, background: k.surfaceStrong, display: "flex", alignItems: "center", justifyContent: "center" }}>{children}</div>
  </div>
);

// ---------- 첫마디

const Orbits: React.FC<{ frame: number; fade: number; k: Tokens }> = ({ frame, fade, k }) => (
  <svg style={{ ...abs(0, 330), opacity: fade }} width={1080} height={900}>
    {[170, 260, 350, 440].map((r, j) => (
      <g key={r}>
        <circle cx={540} cy={430} r={r} fill="none" stroke={k.line} strokeWidth={2} strokeDasharray={j % 2 ? "4 10" : undefined} />
        {Array.from({ length: 5 + j * 3 }, (_, i) => {
          const a = (i / (5 + j * 3)) * Math.PI * 2 + frame * (0.004 + j * 0.002) * (j % 2 ? -1 : 1) + seeded(i + j * 31) * 0.6;
          const lit = seeded(i * 7 + j) < 0.22;
          return <circle key={i} cx={540 + Math.cos(a) * r} cy={430 + Math.sin(a) * r} r={lit ? 7 : 4} fill={lit ? (j % 2 ? k.accent2 : k.accent) : k.muted} />;
        })}
      </g>
    ))}
  </svg>
);

export const LHookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const kick = useIn(0);
  const claim = useIn(8);
  const note = useIn(22);
  const fade = interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" });
  const size = fit(props.claim, 860, 220, 100);
  return (
    <AbsoluteFill>
      <Orbits frame={frame} fade={fade} k={k} />
      <Kicker text={props.kicker} p={kick} />
      <div style={{ ...abs(0, 760 - size * 0.62, 1080), textAlign: "center", fontSize: size, fontWeight: 900, fontFamily: k.titleFont, letterSpacing: -6, lineHeight: 1.1, opacity: Math.min(1, claim), transform: `scale(${0.92 + 0.08 * claim})` }}>
        <Accent>{props.claim}</Accent>
      </div>
      {props.claimNote ? (
        <div style={{ ...abs(0, 760 + size * 0.5, 1080), display: "flex", justifyContent: "center", ...rise(note, 20) }}>
          <div style={{ padding: "8px 22px", borderRadius: 12, border: `2px solid ${k.warn}`, color: k.warn, fontSize: 32, fontWeight: 800 }}>{props.claimNote}</div>
        </div>
      ) : null}
      {props.aside ? (
        <div style={{ ...abs(0, 760 + size * 0.5 + (props.claimNote ? 90 : 10), 1080), textAlign: "center", fontSize: 42, color: k.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.3, 0.45) }}>{props.aside}</div>
      ) : null}
    </AbsoluteFill>
  );
};

export const LHookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const { motion } = useTheme();
  const head = useIn(0);
  const at = useStagger();
  const n = props.count;
  const d = Math.min(156, Math.floor((900 - (n - 1) * 34) / n));
  const total = n * d + (n - 1) * 34;
  const x0 = (1080 - total) / 2;
  const cy = 820;
  const line = phase(frame, durationInFrames, 0.12, 0.55);
  const size = fit(props.headline, 940, 116, 64);
  return (
    <AbsoluteFill>
      <Kicker text={props.kicker} p={1} />
      <div style={{ ...abs(0, 430, 1080), textAlign: "center", fontSize: size, fontWeight: k.titleWeight, fontFamily: k.titleFont, color: k.text, letterSpacing: -3, ...rise(head, 30) }}>
        <Highlighted text={props.headline} highlight={props.highlight} />
      </div>
      <div style={{ ...abs(x0 + d / 2, cy - 3, (total - d) * line, 6), borderRadius: 3, background: k.gradient }} />
      {Array.from({ length: n }, (_, i) => {
        const p = at(i, 10);
        const float = motion.float ? Math.sin((frame + i * 13) / 22) * motion.float : 0;
        return (
          <Ring key={i} k={k} size={d} style={{ ...abs(x0 + i * (d + 34), cy - d / 2), opacity: Math.min(1, p), transform: `translateY(${(1 - p) * 60 + float}px) scale(${0.7 + 0.3 * p})` }}>
            <div style={{ fontSize: Math.round(d * 0.44), fontWeight: 900, color: k.text, fontFamily: k.titleFont }}>{pad2(i + 1)}</div>
          </Ring>
        );
      })}
    </AbsoluteFill>
  );
};

// ---------- 항목 소개 카드

export const LItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const p = useIn(0);
  const inner = useIn(8);
  const nameSize = fit(props.name, 720, 104, 52);
  const drift = interpolate(frame, [0, durationInFrames], [0, -18]);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(96, 520, 888, 560), borderRadius: k.radius + 16, padding: 3, background: k.gradient, boxShadow: k.glow(0.8), ...rise(p, 60) }}>
        <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: k.radius + 13, background: k.surfaceStrong, overflow: "hidden" }}>
          <div style={{ ...abs(0, 0, 882, 554), background: k.gradientSoft, opacity: 0.55 }} />
          <div style={{ ...abs(470, -60 + drift), fontSize: 380, fontWeight: 900, fontFamily: k.titleFont, color: "transparent", WebkitTextStroke: `3px ${k.line}`, letterSpacing: -20 }}>{pad2(props.number)}</div>
          <div style={{ ...abs(64, 70), fontFamily: k.mono, fontSize: 28, letterSpacing: 6, color: k.accent, fontWeight: 700, ...rise(inner, 14) }}>ITEM {pad2(props.number)}</div>
          {props.badge ? (
            <div style={{ ...abs(64, 120), padding: "6px 20px", borderRadius: 30, background: k.gradient, color: k.onAccent, fontSize: 28, fontWeight: 800, ...rise(inner, 14) }}>{props.badge}</div>
          ) : null}
          <div style={{ ...abs(64, 214, 760), fontSize: nameSize, fontWeight: 900, fontFamily: k.titleFont, color: k.text, letterSpacing: -2.5, lineHeight: 1.05, ...rise(inner, 22) }}>{props.name}</div>
          {props.meta ? (
            <div style={{ ...abs(64, 214 + nameSize + 34), display: "flex", alignItems: "center", gap: 10, padding: "8px 18px", borderRadius: 14, background: k.gradientSoft, border: `1px solid ${k.line}`, fontFamily: k.mono, fontSize: 26, color: k.sub, ...rise(inner, 16) }}>
              <Icon name="code" size={26} color={k.accent2} />
              {props.meta}
            </div>
          ) : null}
          {props.tagline ? (
            <div style={{ ...abs(64, 456, 760), fontSize: fit(props.tagline, 740, 40, 26), color: k.text, fontWeight: 600, opacity: 0.86 * phase(frame, durationInFrames, 0.15, 0.35) }}>{props.tagline}</div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- 항목 설명 그림 (모든 테마가 같이 쓴다)

export const Window: React.FC<{ x: number; y: number; w: number; h: number; title?: string; p: number; children: React.ReactNode; active?: boolean }> = ({ x, y, w, h, title, p, children, active }) => {
  const k = useTokens();
  return (
    <div style={{ ...abs(x, y, w, h), ...cardStyle(k, { active, strong: true }), overflow: "hidden", ...rise(p, 44) }}>
      <div style={{ height: 60, display: "flex", alignItems: "center", gap: 12, padding: "0 26px", borderBottom: `1px solid ${k.line}` }}>
        {(k.windowDots ?? ["#FF6159", "#FEBC2E", "#28C840"]).map((c, i) => (
          <div key={i} style={{ width: 16, height: 16, borderRadius: 8, background: c, opacity: 0.85 }} />
        ))}
        {title ? <div style={{ marginLeft: 14, fontFamily: k.mono, fontSize: 24, color: k.muted }}>{title}</div> : null}
      </div>
      <div style={{ position: "relative", padding: "28px 36px" }}>{children}</div>
    </div>
  );
};

export const LChat: React.FC<LSceneProps<{ prompt: string; results: string[]; status?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const enter = useIn(0);
  const at = useStagger();
  const typing = phase(frame, durationInFrames, 0.04, 0.42);
  const sent = typing >= 1;
  const pick = phase(frame, durationInFrames, 0.72, 0.8);
  const statusP = props.status ? phase(frame, durationInFrames, 0.78, 0.98) : 0;
  const rows = props.results.slice(0, 4);
  const rowH = 108;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 500, L.width, 120), ...cardStyle(k, { active: sent, strong: true }), display: "flex", alignItems: "center", padding: "0 34px", gap: 22, ...rise(enter, 30) }}>
        <Icon name="chat" size={44} color={sent ? k.accent : k.muted} />
        <div style={{ flex: 1, fontSize: fit(props.prompt, 690, 42, 28), color: k.text, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden" }}>
          {typed(props.prompt, typing)}
          <span style={{ color: k.accent, opacity: !sent && frame % 30 < 15 ? 1 : 0 }}>▏</span>
        </div>
        <div style={{ width: 64, height: 64, borderRadius: 32, background: sent ? k.gradient : k.gradientSoft, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="bolt" size={34} color={sent ? k.onAccent : k.muted} />
        </div>
      </div>
      {rows.map((r, i) => {
        const p = at(i, Math.round(durationInFrames * 0.46));
        const chosen = i === 0 && pick > 0;
        return (
          <div key={r + i} style={{ ...abs(L.side + 40, 670 + i * (rowH + 20), L.width - 40, rowH), ...cardStyle(k, { active: chosen }), display: "flex", alignItems: "center", padding: "0 30px", gap: 24, opacity: Math.min(1, p), transform: `translateX(${(1 - p) * 50}px)` }}>
            <div style={{ width: 58, height: 58, borderRadius: 29, background: chosen ? k.gradient : k.gradientSoft, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon name={chosen ? "check" : "search"} size={34} color={chosen ? k.onAccent : k.muted} />
            </div>
            <div style={{ flex: 1, fontSize: fit(r, 640, 40, 26), color: chosen ? k.text : k.sub, fontWeight: chosen ? 800 : 600 }}>{r}</div>
          </div>
        );
      })}
      {props.status ? (
        <div style={{ ...abs(L.side + 80, 1170, L.width - 160, 72), ...cardStyle(k, { radius: 36 }), opacity: Math.min(1, statusP * 4), display: "flex", alignItems: "center", gap: 18, padding: "0 28px" }}>
          <Icon name="gear" size={32} color={k.accent} style={{ transform: `rotate(${frame * 3}deg)` }} />
          <div style={{ fontSize: 30, color: k.text, fontWeight: 700, minWidth: 190 }}>{props.status}</div>
          <div style={{ flex: 1, height: 10, borderRadius: 5, background: k.line }}>
            <div style={{ width: `${Math.round(statusP * 100)}%`, height: 10, borderRadius: 5, background: k.gradient }} />
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const LSteps: React.FC<LSceneProps<{ steps: string[]; checks?: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const { motion } = useTheme();
  const { fps } = useVideoConfig();
  const enter = useIn(0);
  const n = props.steps.length;
  const stepAt = (i: number) => durationInFrames * (0.1 + (0.66 * i) / n);
  const active = props.steps.filter((_, i) => frame >= stepAt(i)).length;
  const gap = 20;
  const chipW = Math.floor((L.width - gap * (n - 1)) / n);
  const checks = props.checks ?? [];
  const done = active >= n;
  const stamp = spring({ frame: Math.max(0, frame - Math.round(stepAt(n - 1)) - 10), fps, config: motion.spring });
  return (
    <AbsoluteFill>
      {props.steps.map((s, i) => {
        const on = i < active;
        return (
          <div key={s + i} style={{ ...abs(L.side + i * (chipW + gap), 500, chipW, 88), borderRadius: 44, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, background: on ? k.gradient : k.surfaceStrong, border: `${k.border}px solid ${on ? k.activeBorder : k.line}`, color: on ? k.onAccent : k.muted, fontSize: fit(s, chipW - 80, 34, 22), fontWeight: 800, ...rise(enter, 24) }}>
            {on ? <Icon name="check" size={30} color={k.onAccent} stroke={2.4} /> : <span style={{ fontFamily: k.mono, fontSize: 24 }}>{i + 1}</span>}
            {s}
          </div>
        );
      })}
      <Window x={L.side} y={640} w={L.width} h={560} title={checks.length ? "checklist" : "workflow"} p={enter} active={done}>
        {checks.length
          ? checks.map((c, i) => {
              const on = frame >= stepAt(Math.min(n - 1, Math.floor(((i + 1) * n) / checks.length) - 1)) + 8;
              return (
                <div key={c + i} style={{ display: "flex", alignItems: "center", gap: 22, height: 104 }}>
                  <div style={{ width: 52, height: 52, borderRadius: Math.min(26, k.radius), border: `3px solid ${on ? k.accent : k.line}`, background: on ? k.gradientSoft : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {on ? <Icon name="check" size={38} color={k.accent} stroke={2.4} /> : null}
                  </div>
                  <div style={{ fontSize: fit(c, 700, 42, 26), color: on ? k.text : k.muted, fontWeight: 700 }}>{c}</div>
                </div>
              );
            })
          : Array.from({ length: 8 }, (_, i) => {
              const pass = done && i >= 5;
              const show = frame >= stepAt(Math.min(n - 1, Math.floor((i * n) / 8)));
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 16, height: 52, opacity: show ? 1 : 0.15 }}>
                  <div style={{ fontFamily: k.mono, fontSize: 22, color: k.muted, width: 30 }}>{i + 1}</div>
                  <div style={{ height: 14, borderRadius: 7, width: 120 + seeded(i) * 420, background: pass ? k.accent : i % 3 === 0 ? k.accent2 : k.line }} />
                  {pass ? <div style={{ marginLeft: "auto", fontFamily: k.mono, fontSize: 24, fontWeight: 700, color: k.accent }}>PASS</div> : null}
                </div>
              );
            })}
        {done ? (
          <Ring k={k} size={230} pad={5} style={{ ...abs(L.width - 320, 250), transform: `scale(${0.6 + 0.4 * stamp})`, opacity: Math.min(1, stamp) }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <Icon name="check" size={76} color={k.accent} stroke={2.4} />
              <div style={{ fontSize: fit(props.steps[n - 1], 170, 40, 22), fontWeight: 900 }}>
                <Accent>{props.steps[n - 1]}</Accent>
              </div>
            </div>
          </Ring>
        ) : null}
      </Window>
    </AbsoluteFill>
  );
};

const BeforeMock: React.FC<{ k: Tokens }> = ({ k }) => (
  <div style={{ position: "absolute", inset: 0, background: k.surfaceStrong }}>
    {Array.from({ length: 9 }, (_, i) => (
      <div key={i} style={{ ...abs(30 + seeded(i) * 620, 24 + seeded(i + 9) * 330, 120 + seeded(i + 3) * 110, 44 + seeded(i + 5) * 60), borderRadius: 10, background: [k.warn, "#F7C66B", k.accent2, k.accent][i % 4], opacity: 0.5, transform: `rotate(${(seeded(i + 2) - 0.5) * 14}deg)` }} />
    ))}
    <div style={{ ...abs(40, 380, 260, 14), borderRadius: 7, background: k.muted }} />
  </div>
);

const AfterMock: React.FC<{ k: Tokens }> = ({ k }) => (
  <div style={{ position: "absolute", inset: 0, background: k.surface }}>
    <div style={{ ...abs(40, 36, 300, 26), borderRadius: 8, background: k.text, opacity: 0.85 }} />
    <div style={{ ...abs(40, 78, 200, 14), borderRadius: 7, background: k.muted }} />
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ ...abs(40 + i * 254, 130, 230, 170), borderRadius: Math.min(18, k.radius), background: k.surfaceStrong, border: `1px solid ${k.line}` }}>
        <div style={{ ...abs(22, 22, 44, 44), borderRadius: 22, background: [k.accent, k.accent2, k.warn][i] }} />
        <div style={{ ...abs(22, 90, 150, 12), borderRadius: 6, background: k.sub }} />
        <div style={{ ...abs(22, 116, 110, 10), borderRadius: 5, background: k.muted }} />
      </div>
    ))}
    <div style={{ ...abs(40, 330, 750, 10), borderRadius: 5, background: k.line }} />
    <div style={{ ...abs(40, 330, 520, 10), borderRadius: 5, background: k.gradient }} />
  </div>
);

export const LBeforeAfter: React.FC<LSceneProps<{ before: { label: string; note?: string }; after: { label: string; note?: string } }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const enter = useIn(0);
  const wipe = phase(frame, durationInFrames, 0.42, 0.62);
  const afterOn = wipe >= 0.5;
  const side = afterOn ? props.after : props.before;
  const W = 840;
  const H = 440;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(120, 560, W, H + 60), ...cardStyle(k, { active: afterOn, strong: true }), overflow: "hidden", ...rise(enter, 50) }}>
        <div style={{ height: 60, display: "flex", alignItems: "center", gap: 12, padding: "0 24px", borderBottom: `1px solid ${k.line}` }}>
          {["#FF6159", "#FEBC2E", "#28C840"].map((c) => (
            <div key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c, opacity: 0.85 }} />
          ))}
        </div>
        <div style={{ position: "relative", width: W, height: H }}>
          <BeforeMock k={k} />
          <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${Math.round((1 - wipe) * 100)}% 0 0)` }}>
            <AfterMock k={k} />
          </div>
          {wipe > 0 && wipe < 1 ? <div style={{ ...abs(Math.round(W * wipe) - 3, 0, 6, H), background: k.gradient }} /> : null}
        </div>
      </div>
      <div style={{ ...abs(120, 470, W), display: "flex", gap: 16 }}>
        {[props.before, props.after].map((s, i) => {
          const on = (i === 1) === afterOn;
          const look: React.CSSProperties = on
            ? i ? { background: k.gradient, color: k.onAccent } : { color: k.warn, border: `2px solid ${k.warn}` }
            : { background: k.surface, color: k.muted, border: `1px solid ${k.line}` };
          return (
            <div key={i} style={{ padding: "10px 24px", borderRadius: 30, fontSize: fit(s.label, 330, 34, 22), fontWeight: 800, ...look }}>
              {i ? "AFTER · " : "BEFORE · "}
              {s.label}
            </div>
          );
        })}
      </div>
      {side.note ? <div style={{ ...abs(120, 1100, W), textAlign: "center", fontSize: fit(side.note, 820, 38, 24), color: k.sub, fontWeight: 600 }}>{side.note}</div> : null}
    </AbsoluteFill>
  );
};

export const LTerminal: React.FC<LSceneProps<{ command: string; output: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const enter = useIn(0);
  const typing = phase(frame, durationInFrames, 0.06, 0.45);
  const outs = props.output.slice(0, 4);
  const size = fit(props.command, 760, 40, 24);
  return (
    <AbsoluteFill>
      <Window x={L.side} y={520} w={L.width} h={640} title="~/project — zsh" p={enter}>
        <div style={{ fontFamily: k.mono, fontSize: size, color: k.text, lineHeight: 1.5, wordBreak: "break-all" }}>
          <span style={{ color: k.accent, fontWeight: 700 }}>❯ </span>
          {typed(props.command, typing)}
          <span style={{ color: k.accent, opacity: typing < 1 && frame % 30 < 15 ? 1 : 0 }}>▌</span>
        </div>
        {outs.map((o, i) => {
          const at = durationInFrames * (0.5 + (0.36 * i) / outs.length);
          const last = i === outs.length - 1;
          const show = interpolate(frame, [at, at + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={o + i} style={{ marginTop: 22, fontFamily: k.mono, fontSize: fit(o, 800, 34, 22), color: last ? k.accent : k.sub, fontWeight: last ? 700 : 400, opacity: show, transform: `translateY(${(1 - show) * 12}px)` }}>
              {last ? "✓ " : "  "}
              {o}
            </div>
          );
        })}
      </Window>
    </AbsoluteFill>
  );
};

export const LStat: React.FC<LSceneProps<{ value: string; unit?: string; label: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const p = useIn(0);
  const count = phase(frame, durationInFrames, 0.05, 0.6);
  const ring = phase(frame, durationInFrames, 0.0, 0.65);
  const r = 270;
  const circ = 2 * Math.PI * r;
  const shown = countUp(props.value, count);
  const valueSize = fit(shown + (props.unit ?? ""), 600, 210, 90);
  const cy = 820;
  return (
    <AbsoluteFill>
      <svg style={{ ...abs(540 - r - 30, cy - r - 30) }} width={2 * r + 60} height={2 * r + 60}>
        <circle cx={r + 30} cy={r + 30} r={r} stroke={k.line} strokeWidth={16} fill="none" />
        <circle cx={r + 30} cy={r + 30} r={r} stroke={k.accent} strokeWidth={16} fill="none" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - ring)} transform={`rotate(-90 ${r + 30} ${r + 30})`} />
      </svg>
      <div style={{ ...abs(0, cy - valueSize * 0.66, 1080), textAlign: "center", fontWeight: 900, fontFamily: k.titleFont, fontSize: valueSize, letterSpacing: -6, transform: `scale(${0.85 + 0.15 * Math.min(1, p)})` }}>
        <Accent>{shown}</Accent>
        {props.unit ? <span style={{ fontSize: Math.round(valueSize * 0.4), color: k.text, marginLeft: 10, letterSpacing: 0 }}>{props.unit}</span> : null}
      </div>
      <div style={{ ...abs(180, cy + valueSize * 0.5, 720), textAlign: "center", fontSize: fit(props.label, 700, 46, 28), color: k.text, fontWeight: 700, opacity: phase(frame, durationInFrames, 0.2, 0.4) }}>{props.label}</div>
    </AbsoluteFill>
  );
};

export const LIcon: React.FC<LSceneProps<{ icon: string; title: string; lines?: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const p = useIn(0);
  const lines = props.lines ?? [];
  const cy = 760;
  return (
    <AbsoluteFill>
      {[230, 300].map((r, j) => (
        <div key={r} style={{ ...abs(540 - r, cy - r, r * 2, r * 2), borderRadius: r, border: `2px ${j ? "dashed" : "solid"} ${k.line}`, transform: `rotate(${frame * (j ? -0.4 : 0.25)}deg) scale(${0.85 + 0.15 * Math.min(1, p)})`, opacity: Math.min(1, p) }} />
      ))}
      <Ring k={k} size={300} pad={5} style={{ ...abs(540 - 150, cy - 150), transform: `scale(${0.6 + 0.4 * p})`, opacity: Math.min(1, p) }}>
        <Icon name={props.icon} size={150} color={k.accent} stroke={1.8} />
      </Ring>
      <div style={{ ...abs(L.side, 1000, L.width), textAlign: "center", fontSize: fit(props.title, L.width, 74, 40), fontWeight: k.titleWeight, fontFamily: k.titleFont, color: k.text, letterSpacing: -2, opacity: phase(frame, durationInFrames, 0.1, 0.25) }}>{props.title}</div>
      <div style={{ ...abs(L.side, 1110, L.width), display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 14 }}>
        {lines.map((t, i) => {
          const s = phase(frame, durationInFrames, 0.25 + i * 0.12, 0.38 + i * 0.12);
          return (
            <div key={t + i} style={{ padding: "10px 24px", ...cardStyle(k, { radius: 30 }), fontSize: fit(t, 400, 32, 22), color: k.sub, fontWeight: 700, ...rise(s, 14) }}>
              {t}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const LCompare: React.FC<LSceneProps<{ left: { title: string; points: string[] }; right: { title: string; points: string[] }; winner?: "left" | "right" }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const a = useIn(0);
  const b = useIn(8);
  const judge = phase(frame, durationInFrames, 0.6, 0.72);
  const w = (L.width - 40) / 2;
  const side = (s: { title: string; points: string[] }, i: number, p: number) => {
    const win = props.winner === (i === 0 ? "left" : "right");
    const lose = props.winner !== undefined && !win;
    return (
      <div key={i} style={{ ...abs(L.side + i * (w + 40), 540, w, 620), ...cardStyle(k, { active: win && judge > 0, strong: true }), opacity: Math.min(1, p) * (lose ? 1 - 0.5 * judge : 1), transform: `translateY(${(1 - p) * 50}px) scale(${win ? 1 + 0.03 * judge : 1})`, padding: "44px 34px" }}>
        <div style={{ fontFamily: k.mono, fontSize: 24, letterSpacing: 4, color: win ? k.accent : k.muted, marginBottom: 14 }}>{i === 0 ? "A" : "B"}</div>
        <div style={{ fontSize: fit(s.title, w - 70, 54, 30), fontWeight: 900, fontFamily: k.titleFont, marginBottom: 22, color: k.text }}>{win && judge > 0 ? <Accent>{s.title}</Accent> : s.title}</div>
        {s.points.slice(0, 3).map((pt) => (
          <div key={pt} style={{ display: "flex", gap: 14, alignItems: "flex-start", marginTop: 22 }}>
            <div style={{ width: 12, height: 12, borderRadius: 6, background: win ? k.accent : k.muted, marginTop: 16, flexShrink: 0 }} />
            <div style={{ fontSize: fit(pt, (w - 100) * 2, 34, 24, 2), color: k.sub, fontWeight: 600, lineHeight: 1.4, wordBreak: "keep-all" }}>{pt}</div>
          </div>
        ))}
      </div>
    );
  };
  return (
    <AbsoluteFill>
      {side(props.left, 0, a)}
      {side(props.right, 1, b)}
      <Ring k={k} size={96} pad={3} style={{ ...abs(540 - 48, 802), opacity: Math.min(1, b) }}>
        <div style={{ fontSize: 32, fontWeight: 900, color: k.text }}>VS</div>
      </Ring>
    </AbsoluteFill>
  );
};

// ---------- 정리·끝

export const LRecap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const head = useIn(0);
  const at = useStagger();
  const n = props.items.length;
  const top = 500;
  const cells = recapCells(n, { x: L.side + 96, y: top, w: L.width - 96, h: 730 });
  const rowH = cells[0]?.h ?? 118;
  const twoCols = n >= 7;
  const rail = twoCols ? 0 : phase(frame, durationInFrames, 0.05, 0.6);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 262), fontSize: fit(props.title, 900, 92, 54), fontWeight: 900, fontFamily: k.titleFont, letterSpacing: -3, ...rise(head, 24) }}>
        <Accent>{props.title}</Accent>
      </div>
      {props.subtitle ? <div style={{ ...abs(L.side, 384), fontSize: 36, color: k.sub, fontWeight: 600, ...rise(head, 18) }}>{props.subtitle}</div> : null}
      <div style={{ ...abs(L.side + 36, top + rowH / 2, 4, (n - 1) * (rowH + 18) * rail), borderRadius: 2, background: k.gradient }} />
      {props.items.map((it, i) => {
        const p = at(i, 6 + Math.round((durationInFrames * 0.3 * i) / n));
        const c = cells[i];
        const x = twoCols ? c.x - 96 : c.x;
        const w = twoCols ? c.w + (c.x - 96 > L.side ? 0 : 96) - 70 : c.w;
        return (
          <React.Fragment key={it.name + i}>
            <Ring k={k} size={44} pad={3} style={{ ...abs(twoCols ? x : L.side + 16, c.y + rowH / 2 - 22), opacity: Math.min(1, p), transform: `scale(${0.5 + 0.5 * p})` }}>
              <div style={{ fontSize: 18, fontWeight: 900, color: k.text }}>{i + 1}</div>
            </Ring>
            <div style={{ ...abs(twoCols ? x + 60 : c.x, c.y, twoCols ? w : c.w, rowH), ...cardStyle(k), display: "flex", alignItems: "center", gap: 20, padding: twoCols ? "0 20px" : "0 30px", opacity: Math.min(1, p), transform: `translateX(${(1 - p) * 60}px)` }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: fit(it.name, twoCols ? 300 : 520, Math.round(rowH * 0.34), 26), fontWeight: 800, color: k.text, whiteSpace: "nowrap", overflow: "hidden" }}>{it.name}</div>
                {it.note ? <div style={{ fontSize: Math.round(rowH * 0.22), color: k.sub, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden" }}>{it.note}</div> : null}
              </div>
              {it.tag ? <div style={{ padding: "6px 16px", borderRadius: 20, background: k.gradient, color: k.onAccent, fontSize: 24, fontWeight: 800, whiteSpace: "nowrap" }}>{it.tag}</div> : null}
            </div>
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};

export const LOutro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const p = useIn(0);
  const line = phase(frame, durationInFrames, 0.15, 0.5);
  const size = fit(props.title, 900, 100, 52, 2);
  const cy = 760;
  return (
    <AbsoluteFill>
      <Ring k={k} size={140} style={{ ...abs(540 - 70, cy - 230), opacity: Math.min(1, p), transform: `scale(${0.6 + 0.4 * p})` }}>
        <Icon name="book" size={70} color={k.accent} />
      </Ring>
      <div style={{ ...abs(90, cy - 40, 900), textAlign: "center", fontSize: size, fontWeight: 900, fontFamily: k.titleFont, letterSpacing: -3, lineHeight: 1.15, wordBreak: "keep-all", ...rise(p, 30) }}>
        <Accent>{props.title}</Accent>
      </div>
      <div style={{ ...abs(540 - 200 * line, cy - 20 + size * 1.3, 400 * line, 5), borderRadius: 3, background: k.gradient }} />
      {props.subtitle ? <div style={{ ...abs(90, cy + 20 + size * 1.3, 900), textAlign: "center", fontSize: fit(props.subtitle, 880, 44, 28), color: k.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.25, 0.45) }}>{props.subtitle}</div> : null}
    </AbsoluteFill>
  );
};

// ---------- 실습 (v1.4 L21): 대본이 말하는 입력을 문장마다 한 단계씩 쳐 보인다. 시각은 timeline 이 넣은 beats(문장 시작)

type WalkProps = { kind: "terminal" | "code" | "chat" | "settings"; title: string; steps: WalkStep[]; beats?: number[] };

const show = (frame: number, at: number) => interpolate(frame, [at, at + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

/** 단계 표시: 01 ─ 02 ─ 03, 지금 단계만 강조색 */
const StepRail: React.FC<{ count: number; current: number; p: number }> = ({ count, current, p }) => {
  const k = useTokens();
  if (count < 2) return null;
  return (
    <div style={{ ...abs(L.side, 492, L.width, 48), display: "flex", alignItems: "center", gap: 14, ...rise(p, -10) }}>
      {Array.from({ length: count }, (_, i) => {
        const on = i === current;
        const done = i < current;
        return (
          <React.Fragment key={i}>
            {i ? <div style={{ flex: "0 0 36px", height: 2, background: done || on ? k.accent : k.line }} /> : null}
            <div style={{ fontFamily: k.mono, fontSize: 24, fontWeight: 700, letterSpacing: 1, padding: "6px 16px", borderRadius: 24,
              color: on ? k.onAccent : done ? k.text : k.muted, background: on ? k.accent : "transparent", border: `${k.border || 1}px solid ${on ? k.accent : k.line}` }}>
              STEP {pad2(i + 1)}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
};

/** 터미널·코드: 줄이 아래로 쌓이고 넘치면 위로 밀린다 */
const WalkConsole: React.FC<{ props: WalkProps; times: WalkTiming[]; frame: number }> = ({ props, times, frame }) => {
  const k = useTokens();
  const code = props.kind === "code";
  const rows = props.steps.reduce((n, st) => n + 1 + st.output.length, 0);
  const size = Math.max(24, Math.min(40, Math.floor(540 / (rows * 1.6))));
  let lineNo = 0;
  return (
    <div style={{ height: 560, display: "flex", flexDirection: "column", justifyContent: rows * size * 1.6 > 540 ? "flex-end" : "flex-start", overflow: "hidden", fontFamily: k.mono, fontSize: size, lineHeight: 1.55 }}>
      {props.steps.map((st, j) => {
        const tm = times[j];
        if (frame < tm.typeFrom) return null;
        const p = progress01(frame, tm.typeFrom, tm.typeTo);
        const past = j < times.length - 1 && frame >= times[j + 1].typeFrom;
        const no = ++lineNo;
        return (
          <div key={j} style={{ opacity: past ? 0.5 : 1, marginTop: j ? size * 0.5 : 0 }}>
            <div style={{ color: k.text, wordBreak: "break-all", whiteSpace: "pre-wrap" }}>
              {code ? <span style={{ color: k.muted, display: "inline-block", width: size * 1.6 }}>{no}</span> : <span style={{ color: k.accent, fontWeight: 700 }}>❯ </span>}
              {typed(st.input, p)}
              <span style={{ color: k.accent, opacity: p < 1 && frame % 30 < 15 ? 1 : 0 }}>▌</span>
            </div>
            {st.output.map((o, i) => {
              const v = show(frame, tm.outFrom[i]);
              const n = code ? ++lineNo : 0;
              return (
                <div key={i} style={{ color: code ? k.text : i === st.output.length - 1 ? k.accent : k.sub, opacity: v, transform: `translateY(${(1 - v) * 10}px)`, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {code ? <span style={{ color: k.muted, display: "inline-block", width: size * 1.6 }}>{n}</span> : "  "}
                  {o}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

const progress01 = (frame: number, a: number, b: number) => Math.min(1, Math.max(0, (frame - a) / Math.max(1, b - a)));

/** 채팅: 내가 친 요청(오른쪽) → 답(왼쪽). 새 대화가 아래에 붙고 위로 밀린다 */
const WalkChat: React.FC<{ props: WalkProps; times: WalkTiming[]; frame: number }> = ({ props, times, frame }) => {
  const k = useTokens();
  return (
    <div style={{ ...abs(L.side, 560, L.width, 680), display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 22, overflow: "hidden" }}>
      {props.steps.map((st, j) => {
        const tm = times[j];
        if (frame < tm.typeFrom) return null;
        const p = progress01(frame, tm.typeFrom, tm.typeTo);
        const reply = st.output.length ? show(frame, tm.outFrom[0]) : 0;
        return (
          <React.Fragment key={j}>
            <div style={{ alignSelf: "flex-end", maxWidth: 760, padding: "22px 30px", borderRadius: Math.max(k.radius, 24), background: k.accent, color: k.onAccent,
              fontSize: fit(st.input, 700, 38, 28, 2), fontWeight: 700, lineHeight: 1.35 }}>
              {typed(st.input, p)}
              {p < 1 ? <span style={{ opacity: frame % 30 < 15 ? 1 : 0 }}>▏</span> : null}
            </div>
            {st.output.length ? (
              <div style={{ alignSelf: "flex-start", maxWidth: 820, padding: "22px 30px", ...cardStyle(k, { strong: true, radius: Math.max(k.radius, 24) }), opacity: reply, transform: `translateY(${(1 - reply) * 14}px)` }}>
                {st.output.map((o, i) => {
                  const v = show(frame, tm.outFrom[i]);
                  return (
                    <div key={i} style={{ fontSize: fit(o, 740, 34, 24, 2), color: i ? k.sub : k.text, fontWeight: i ? 500 : 700, lineHeight: 1.4, marginTop: i ? 10 : 0, opacity: v }}>
                      {o}
                    </div>
                  );
                })}
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};

/** 설정: 메뉴 경로(input 'A > B > C')를 차례로 누르고, 출력 줄은 켜지는 스위치로 */
const WalkSettings: React.FC<{ props: WalkProps; times: WalkTiming[]; frame: number }> = ({ props, times, frame }) => {
  const k = useTokens();
  const j = Math.max(0, times.reduce((c, tm, i) => (frame >= tm.typeFrom ? i : c), 0));
  const st = props.steps[j];
  const tm = times[j];
  const parts = st.input.split(/\s*[>›»]\s*/).filter(Boolean);
  const p = progress01(frame, tm.typeFrom, tm.typeTo);
  const lit = Math.ceil(p * parts.length);
  return (
    <div style={{ height: 560, display: "flex", flexDirection: "column", gap: 26 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
        {parts.map((x, i) => (
          <React.Fragment key={i}>
            {i ? <span style={{ color: k.muted, fontSize: 30 }}>›</span> : null}
            <span style={{ fontSize: fit(x, 300, 32, 22), fontWeight: 700, padding: "8px 18px", borderRadius: 14,
              color: i < lit ? (i === parts.length - 1 ? k.onAccent : k.text) : k.muted,
              background: i < lit && i === parts.length - 1 ? k.accent : "transparent", border: `1px solid ${i < lit ? k.accent : k.line}` }}>{x}</span>
          </React.Fragment>
        ))}
      </div>
      {st.output.map((o, i) => {
        const v = show(frame, tm.outFrom[i]);
        const on = show(frame, tm.outFrom[i] + 10);
        return (
          <div key={j + "-" + i} style={{ display: "flex", alignItems: "center", gap: 24, padding: "20px 26px", ...cardStyle(k, { active: on > 0.5 }), opacity: v, transform: `translateY(${(1 - v) * 12}px)` }}>
            <div style={{ flex: 1, fontSize: fit(o, 600, 34, 24), color: k.text, fontWeight: 600 }}>{o}</div>
            <div style={{ width: 84, height: 46, borderRadius: 23, background: on > 0.5 ? k.accent : k.line, position: "relative" }}>
              <div style={{ position: "absolute", top: 5, left: 5 + on * 38, width: 36, height: 36, borderRadius: 18, background: on > 0.5 ? k.onAccent : k.surfaceStrong }} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const LWalkthrough: React.FC<LSceneProps<WalkProps>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = useIn(0);
  const times = walkSchedule(props.steps, props.beats, durationInFrames);
  const current = Math.max(0, times.reduce((c, tm, i) => (frame >= tm.typeFrom ? i : c), 0));
  const title = props.title || { terminal: "~/project — zsh", code: "editor", chat: "chat", settings: "Settings" }[props.kind];
  return (
    <AbsoluteFill>
      <StepRail count={props.steps.length} current={current} p={enter} />
      {props.kind === "chat" ? (
        <WalkChat props={props} times={times} frame={frame} />
      ) : (
        <Window x={L.side} y={560} w={L.width} h={680} title={title} p={enter}>
          {props.kind === "settings" ? <WalkSettings props={props} times={times} frame={frame} /> : <WalkConsole props={props} times={times} frame={frame} />}
        </Window>
      )}
    </AbsoluteFill>
  );
};

// ---------- 실습 리뷰 (D46): 실험 결과물 캡처와 평가

/** 결과물 화면: 실험이 만든 파일의 캡처 그림을 카드에 담고, 파일 이름·성공/실패·걸린 시간 */
export const LArtifact: React.FC<LSceneProps<{ image: string; title: string; ok: boolean; meta?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const base = React.useContext(AssetContext);
  const enter = useIn(0);
  const badge = phase(frame, durationInFrames, 0.15, 0.3);
  const zoom = 1 + phase(frame, durationInFrames, 0, 1) * 0.04;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 500, L.width, 640), ...cardStyle(k, { strong: true }), overflow: "hidden", ...rise(enter, 30) }}>
        <div style={{ height: 56, display: "flex", alignItems: "center", gap: 14, padding: "0 24px", borderBottom: `1px solid ${k.line}` }}>
          <div style={{ fontFamily: k.mono, fontSize: 24, color: k.sub, flex: 1, whiteSpace: "nowrap", overflow: "hidden" }}>{props.title}</div>
          <div style={{ padding: "4px 14px", borderRadius: 999, fontSize: 22, fontWeight: 800, opacity: badge,
            background: props.ok ? k.accent : "transparent", color: props.ok ? k.onAccent : k.muted, border: `1.5px solid ${props.ok ? k.accent : k.muted}` }}>
            {props.ok ? "✓ 성공" : "✗ 실패"}
          </div>
        </div>
        <div style={{ position: "absolute", top: 56, left: 0, right: 0, bottom: 0, background: "#FFFFFF", overflow: "hidden" }}>
          <Img src={base + props.image} style={{ width: "100%", height: "100%", objectFit: "contain", transform: `scale(${zoom})` }} />
        </div>
      </div>
      {props.meta ? (
        <div style={{ ...abs(L.side, 1162, L.width), fontFamily: k.mono, fontSize: 26, color: k.muted, opacity: badge }}>{props.meta}</div>
      ) : null}
    </AbsoluteFill>
  );
};

/** 평가: 좋은 점(✓)·아쉬운 점(–)·추천 대상 */
export const LVerdict: React.FC<LSceneProps<{ title: string; pros: string[]; cons: string[]; forWhom: string; meta?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const k = useTokens();
  const head = useIn(0);
  const rows = [...props.pros.map((t) => ({ t, good: true })), ...props.cons.map((t) => ({ t, good: false }))];
  const who = phase(frame, durationInFrames, 0.45, 0.6);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 270, L.width), fontSize: fit(props.title, L.width, 92, 56), fontWeight: k.titleWeight, color: k.text, letterSpacing: -3, ...rise(head, 18) }}>
        {props.title}
      </div>
      {props.meta ? <div style={{ ...abs(L.side, 392), fontFamily: k.mono, fontSize: 26, color: k.muted, ...rise(head, 12) }}>{props.meta}</div> : null}
      {rows.map((r, i) => {
        const p = phase(frame, durationInFrames, 0.06 + i * 0.08, 0.14 + i * 0.08);
        return (
          <div key={r.t + i} style={{ ...abs(L.side, 500 + i * 128, L.width, 108), ...cardStyle(k, { active: r.good && i === 0 }), display: "flex", alignItems: "center", gap: 24,
            padding: "0 30px", opacity: p, transform: `translateX(${(1 - p) * 40}px)` }}>
            <div style={{ width: 52, height: 52, borderRadius: 26, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30, fontWeight: 900,
              background: r.good ? k.accent : "transparent", color: r.good ? k.onAccent : k.muted, border: r.good ? "none" : `2px solid ${k.muted}` }}>{r.good ? "✓" : "–"}</div>
            <div style={{ flex: 1, fontSize: fit(r.t, 700, 40, 28), fontWeight: 700, color: r.good ? k.text : k.sub }}>{r.t}</div>
          </div>
        );
      })}
      <div style={{ ...abs(L.side, 520 + rows.length * 128, L.width), opacity: who, transform: `translateY(${(1 - who) * 12}px)` }}>
        <div style={{ fontFamily: k.mono, fontSize: 24, color: k.muted, letterSpacing: 2 }}>추천</div>
        <div style={{ marginTop: 8, fontSize: fit(props.forWhom, L.width, 48, 32), fontWeight: 800 }}><Accent>{props.forWhom}</Accent></div>
      </div>
    </AbsoluteFill>
  );
};

export const LISTICLE_SCENES: Record<string, React.FC<LSceneProps<any>>> = {
  LHookClaim,
  LHookReveal,
  LItemCard,
  LChat,
  LSteps,
  LBeforeAfter,
  LTerminal,
  LStat,
  LIcon,
  LCompare,
  LRecap,
  LOutro,
  LWalkthrough,
  LArtifact,
  LVerdict,
};
