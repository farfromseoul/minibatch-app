// 목록형 쇼츠(D42) 장면 12종. 속성 모양은 src/lib/timeline.ts 의 검사, job-api app/schemas/templates.py 와 같다.
// 움직임은 모두 프레임에서 계산한다(spring·interpolate). 장면 길이가 달라도 같은 리듬이 되게 길이 비율(phase)을 쓴다.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../lib/layout";
import { countUp, pad2, phase, seeded, typed } from "../lib/listicle";
import { Asterisk, Icon } from "./icons";
import { abs, C, cardStyle, goldGlow, L, MONO } from "./style";

export type LSceneProps<P> = { durationInFrames: number; props: P };

const usePop = (delay = 0, damping = 13) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: Math.max(0, frame - delay), fps, config: { damping, stiffness: 170, mass: 0.9 } });
};

const fit = (text: string, width: number, base: number, min: number, lines = 1) => fitFontSize(text, width, base, min, lines) ?? min;

/** 맨 위 제목 줄 (✳ 클로드 스킬). 첫마디 두 장면이 같이 쓴다 */
const Kicker: React.FC<{ text: string; p: number }> = ({ text, p }) => {
  const size = fit(text, 800, 76, 44);
  return (
    <div style={{ ...abs(0, L.headerY - 20, 1080), display: "flex", justifyContent: "center", alignItems: "center", gap: 22, opacity: p, transform: `translateY(${(1 - p) * -24}px)` }}>
      <Asterisk size={Math.round(size * 0.85)} color={C.red} />
      <div style={{ fontSize: size, fontWeight: 800, color: C.text, letterSpacing: -1 }}>{text}</div>
    </div>
  );
};

/** 글자 안 일부(highlight)를 노란색으로 */
const Highlighted: React.FC<{ text: string; highlight?: string; color?: string }> = ({ text, highlight, color = C.gold }) => {
  if (!highlight || !text.includes(highlight)) return <>{text}</>;
  const i = text.indexOf(highlight);
  return (
    <>
      {text.slice(0, i)}
      <span style={{ color, textShadow: "0 0 40px rgba(255, 200, 61, 0.35)" }}>{highlight}</span>
      {text.slice(i + highlight.length)}
    </>
  );
};

// ---------- 첫마디

export const LHookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const kick = usePop(0, 16);
  const bubble = usePop(6, 11);
  const dim = interpolate(phase(frame, durationInFrames, 0.7, 1), [0, 1], [1, 0.35]);
  const cols = 9;
  const rows = 12;
  const cw = 96;
  const ch = 60;
  const gx = (1080 - cols * cw - (cols - 1) * 14) / 2;
  const zoom = interpolate(frame, [0, durationInFrames], [1.1, 1.0]);
  const claimSize = fit(props.claim, 640, 190, 90);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(0, 360, 1080, 1000), transform: `scale(${zoom})`, opacity: dim }}>
        {Array.from({ length: cols * rows }, (_, i) => {
          const r = seeded(i);
          const lit = r < 0.13;
          const tw = lit ? 0.55 + 0.45 * Math.sin((frame + i * 7) / 9) : 1;
          const appear = interpolate(frame, [i % 17, (i % 17) + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div
              key={i}
              style={{
                ...abs(gx + (i % cols) * (cw + 14), Math.floor(i / cols) * (ch + 22), cw, ch),
                borderRadius: 12,
                background: lit ? "rgba(255, 200, 61, 0.42)" : "#17171B",
                border: `2px solid ${lit ? "rgba(255, 200, 61, 0.65)" : "#232328"}`,
                opacity: appear * tw,
              }}
            >
              <div style={{ ...abs(12, 14, 40 + r * 30, 8), borderRadius: 4, background: lit ? "rgba(17,17,19,0.45)" : "#26262C" }} />
              <div style={{ ...abs(12, 32, 24 + r * 20, 8), borderRadius: 4, background: lit ? "rgba(17,17,19,0.3)" : "#202025" }} />
            </div>
          );
        })}
      </div>
      <Kicker text={props.kicker} p={kick} />
      <div style={{ ...abs(150, 560, 780, 250), transform: `scale(${0.55 + 0.45 * bubble}) rotate(${(1 - bubble) * -6}deg)`, opacity: Math.min(1, bubble * 1.4) }}>
        <div style={{ ...abs(0, 0, 780, 250), borderRadius: 34, border: `4px dashed ${C.gold}`, background: "rgba(11, 11, 13, 0.82)", boxShadow: goldGlow(0.8) }} />
        <div style={{ ...abs(26, -18), fontSize: 120, fontWeight: 900, color: C.gold, lineHeight: 1 }}>“</div>
        <div style={{ ...abs(0, 0, 780, 250), display: "flex", alignItems: "center", justifyContent: "center", fontSize: claimSize, fontWeight: 900, color: C.gold, letterSpacing: -4, textShadow: "0 0 50px rgba(255,200,61,0.35)" }}>
          {props.claim}
        </div>
        {props.claimNote ? (
          <div style={{ ...abs(600, -36), padding: "8px 22px", borderRadius: 16, background: C.text, color: C.ink, fontSize: 36, fontWeight: 800, transform: "rotate(10deg)", boxShadow: "0 10px 24px rgba(0,0,0,0.5)" }}>
            • {props.claimNote}
          </div>
        ) : null}
        <svg style={{ ...abs(90, 246) }} width={60} height={44}>
          <path d="M4 0 L52 0 L10 40 Z" fill="rgba(11,11,13,0.82)" stroke={C.gold} strokeWidth={4} strokeDasharray="10 8" />
        </svg>
      </div>
      {props.aside ? (
        <div style={{ ...abs(0, 860, 1080), textAlign: "center", fontSize: 40, color: C.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.25, 0.4) }}>{props.aside}</div>
      ) : null}
    </AbsoluteFill>
  );
};

const TILT = [-9, -3, 3, -4, 8, -6, 5];

export const LHookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ props }) => {
  const frame = useCurrentFrame();
  const head = usePop(0, 14);
  const n = props.count;
  const tw = Math.min(190, Math.floor((900 - (n - 1) * -20) / n));
  const total = n * tw - (n - 1) * 22;
  const size = fit(props.headline, 940, 118, 64);
  return (
    <AbsoluteFill>
      <Kicker text={props.kicker} p={1} />
      <div style={{ ...abs(0, 420, 1080), textAlign: "center", fontSize: size, fontWeight: 900, color: C.text, letterSpacing: -3, opacity: head, transform: `scale(${0.85 + 0.15 * head})` }}>
        <Highlighted text={props.headline} highlight={props.highlight} />
      </div>
      {Array.from({ length: n }, (_, i) => {
        const p = spring({ frame: Math.max(0, frame - 8 - i * 4), fps: 30, config: { damping: 11, stiffness: 180 } });
        const float = Math.sin((frame + i * 11) / 14) * 6;
        return (
          <div
            key={i}
            style={{
              ...abs((1080 - total) / 2 + i * (tw - 22), 700 + (i % 2) * 18, tw, Math.round(tw * 1.22)),
              borderRadius: 26,
              background: `linear-gradient(160deg, #FFD966 0%, ${C.gold} 45%, ${C.goldDeep} 100%)`,
              boxShadow: "0 22px 40px rgba(0,0,0,0.55), inset 0 2px 0 rgba(255,255,255,0.5)",
              border: "3px solid rgba(255, 240, 190, 0.8)",
              transform: `translateY(${(1 - p) * 140 + float}px) rotate(${TILT[i % TILT.length] * p}deg) scale(${0.5 + 0.5 * p})`,
              opacity: Math.min(1, p * 1.5),
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: Math.round(tw * 0.62),
              fontWeight: 900,
              color: C.ink,
              zIndex: n - Math.abs(i - (n - 1) / 2),
            }}
          >
            {i + 1}
            <div style={{ ...abs(14, 10), fontSize: 26, color: "rgba(17,17,19,0.55)" }}>✦</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

// ---------- 항목 소개 카드

export const LItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ props }) => {
  const p = usePop(0, 12);
  const nameSize = fit(props.name, 680, 112, 56);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(130, 560, 820, 470), ...cardStyle({ border: C.gold, glow: true, radius: 38 }), transform: `scale(${0.82 + 0.18 * p}) translateY(${(1 - p) * 60}px)`, opacity: Math.min(1, p * 1.5) }}>
        <div style={{ ...abs(52, 34), fontSize: 120, fontWeight: 900, color: C.gold, letterSpacing: -4 }}>{pad2(props.number)}</div>
        {props.badge ? (
          <div style={{ ...abs(560, 58), padding: "8px 22px", borderRadius: 30, background: C.gold, color: C.ink, fontSize: 32, fontWeight: 800, transform: "rotate(4deg)" }}>{props.badge}</div>
        ) : null}
        <div style={{ ...abs(0, 190, 820), textAlign: "center", fontSize: nameSize, fontWeight: 900, color: C.text, letterSpacing: -2, lineHeight: 1.05 }}>{props.name}</div>
        {props.meta ? (
          <div style={{ ...abs(0, 190 + nameSize + 34, 820), textAlign: "center", fontFamily: MONO, fontSize: 32, color: C.sub }}>
            <Highlighted text={props.meta} highlight={props.meta.includes("★") ? props.meta.slice(props.meta.indexOf("★")) : undefined} />
          </div>
        ) : null}
        {props.tagline ? (
          <div style={{ ...abs(40, 380, 740), textAlign: "center", fontSize: fit(props.tagline, 720, 38, 26), color: C.sub, fontWeight: 600 }}>{props.tagline}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// ---------- 항목 설명 그림

export const LChat: React.FC<LSceneProps<{ prompt: string; results: string[]; status?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = usePop(0, 15);
  const typing = phase(frame, durationInFrames, 0.04, 0.36);
  const sent = typing >= 1;
  const resultsAt = props.status ? 0.4 : 0.42;
  const pick = phase(frame, durationInFrames, 0.66, 0.74);
  const statusP = props.status ? phase(frame, durationInFrames, 0.74, 0.98) : 0;
  const rows = props.results.slice(0, 4);
  const rowH = 112;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 500, L.width, 116), ...cardStyle({ border: sent ? C.gold : "#34343B", glow: sent, radius: 26 }), opacity: enter, transform: `translateY(${(1 - enter) * 40}px)`, display: "flex", alignItems: "center", padding: "0 34px", gap: 22 }}>
        <div style={{ fontFamily: MONO, fontSize: 40, color: C.gold, fontWeight: 700 }}>{">"}</div>
        <div style={{ flex: 1, fontSize: fit(props.prompt, 700, 42, 28), color: C.text, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden" }}>
          {typed(props.prompt, typing)}
          <span style={{ color: C.gold, opacity: !sent && frame % 24 < 12 ? 1 : 0 }}>|</span>
        </div>
        <Icon name="bolt" size={44} color={sent ? C.gold : C.muted} />
      </div>
      {rows.map((r, i) => {
        const p = spring({ frame: Math.max(0, frame - Math.round(durationInFrames * resultsAt) - i * 4), fps: 30, config: { damping: 14, stiffness: 170 } });
        const chosen = i === 0 && pick > 0;
        return (
          <div key={r + i} style={{ ...abs(L.side, 660 + i * (rowH + 18), L.width, rowH), ...cardStyle({ border: chosen ? C.gold : C.border, glow: chosen, radius: 22, bg: chosen ? "#1C1912" : C.card }), opacity: p, transform: `translateX(${(1 - p) * 80}px)`, display: "flex", alignItems: "center", padding: "0 30px", gap: 26 }}>
            <div style={{ width: 62, height: 62, borderRadius: 16, background: chosen ? C.gold : C.card2, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon name={chosen ? "check" : "search"} size={38} color={chosen ? C.ink : C.muted} />
            </div>
            <div style={{ flex: 1, fontSize: fit(r, 680, 42, 26), color: chosen ? C.text : C.sub, fontWeight: chosen ? 800 : 600 }}>{r}</div>
          </div>
        );
      })}
      {props.status ? (
        <div style={{ ...abs(L.side + 60, 1170, L.width - 120, 76), ...cardStyle({ radius: 38 }), opacity: Math.min(1, statusP * 4), display: "flex", alignItems: "center", gap: 20, padding: "0 28px" }}>
          <Icon name="gear" size={36} color={C.gold} style={{ transform: `rotate(${frame * 6}deg)` }} />
          <div style={{ fontSize: 32, color: C.text, fontWeight: 700, minWidth: 200 }}>{props.status}</div>
          <div style={{ flex: 1, height: 12, borderRadius: 6, background: C.dim }}>
            <div style={{ width: `${Math.round(statusP * 100)}%`, height: 12, borderRadius: 6, background: C.gold, boxShadow: goldGlow(0.4) }} />
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** 창 틀 (빨강·노랑·초록 점 + 제목) */
const Window: React.FC<{ x: number; y: number; w: number; h: number; title?: string; p: number; children: React.ReactNode; border?: string }> = ({ x, y, w, h, title, p, children, border }) => (
  <div style={{ ...abs(x, y, w, h), ...cardStyle({ radius: 26, border: border ?? C.border }), overflow: "hidden", opacity: p, transform: `translateY(${(1 - p) * 50}px) scale(${0.94 + 0.06 * p})` }}>
    <div style={{ height: 58, display: "flex", alignItems: "center", gap: 12, padding: "0 24px", borderBottom: `2px solid ${C.border}`, background: "#18181C" }}>
      {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
        <div key={c} style={{ width: 18, height: 18, borderRadius: 9, background: c }} />
      ))}
      {title ? <div style={{ marginLeft: 14, fontFamily: MONO, fontSize: 24, color: C.muted }}>{title}</div> : null}
    </div>
    <div style={{ position: "relative", padding: "26px 34px" }}>{children}</div>
  </div>
);

export const LSteps: React.FC<LSceneProps<{ steps: string[]; checks?: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = usePop(0, 15);
  const n = props.steps.length;
  const stepAt = (i: number) => durationInFrames * (0.08 + (0.72 * i) / n);
  const active = props.steps.filter((_, i) => frame >= stepAt(i)).length;
  const gap = 18;
  const chipW = Math.floor((L.width - gap * (n - 1)) / n);
  const checks = props.checks ?? [];
  const done = active >= n;
  const stamp = spring({ frame: Math.max(0, frame - Math.round(stepAt(n - 1)) - 6), fps: 30, config: { damping: 10, stiffness: 160 } });
  return (
    <AbsoluteFill>
      {props.steps.map((s, i) => {
        const on = i < active;
        const p = spring({ frame: Math.max(0, frame - Math.round(stepAt(i))), fps: 30, config: { damping: 12, stiffness: 200 } });
        return (
          <div key={s + i} style={{ ...abs(L.side + i * (chipW + gap), 500, chipW, 84), borderRadius: 42, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, background: on ? C.gold : C.card2, border: `3px solid ${on ? C.gold : "#34343B"}`, color: on ? C.ink : C.muted, fontSize: fit(s, chipW - 70, 36, 22), fontWeight: 800, opacity: enter, transform: `scale(${on ? 1 + 0.08 * Math.sin(Math.PI * Math.min(1, p)) : 1})`, boxShadow: on ? goldGlow(0.5) : "none" }}>
            {on ? <Icon name="check" size={32} color={C.ink} stroke={2.6} /> : <span style={{ fontFamily: MONO, fontSize: 26 }}>{i + 1}</span>}
            {s}
          </div>
        );
      })}
      <Window x={L.side} y={640} w={L.width} h={560} title={checks.length ? "checklist" : "app.js"} p={enter} border={done ? C.gold : C.border}>
        {checks.length
          ? checks.map((c, i) => {
              const on = frame >= stepAt(Math.min(n - 1, Math.floor(((i + 1) * n) / checks.length) - 1)) + 6;
              return (
                <div key={c + i} style={{ display: "flex", alignItems: "center", gap: 22, height: 100 }}>
                  <div style={{ width: 54, height: 54, borderRadius: 14, border: `3px solid ${on ? C.gold : "#44444B"}`, background: on ? C.gold : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {on ? <Icon name="check" size={40} color={C.ink} stroke={2.4} /> : null}
                  </div>
                  <div style={{ fontSize: fit(c, 720, 42, 26), color: on ? C.text : C.muted, fontWeight: 700 }}>{c}</div>
                </div>
              );
            })
          : Array.from({ length: 8 }, (_, i) => {
              const pass = done && i >= 5;
              const show = frame >= stepAt(Math.min(n - 1, Math.floor((i * n) / 8)));
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 16, height: 52, opacity: show ? 1 : 0.15 }}>
                  <div style={{ fontFamily: MONO, fontSize: 22, color: C.dim, width: 30 }}>{i + 1}</div>
                  {pass ? <Icon name="check" size={30} color={C.green} /> : null}
                  <div style={{ height: 14, borderRadius: 7, width: 120 + seeded(i) * 420, background: pass ? "rgba(61, 220, 132, 0.55)" : i % 3 === 0 ? "rgba(255, 200, 61, 0.7)" : "#3A3A42" }} />
                  {pass ? <div style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 24, fontWeight: 700, color: C.green }}>PASS</div> : null}
                </div>
              );
            })}
        {done ? (
          <div style={{ ...abs(L.width - 330, 250, 250, 250), borderRadius: 125, border: `8px solid ${C.gold}`, background: "rgba(11,11,13,0.88)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", transform: `scale(${0.4 + 0.6 * stamp}) rotate(${-12 * stamp}deg)`, opacity: stamp, boxShadow: goldGlow() }}>
            <Icon name="check" size={84} color={C.gold} stroke={2.4} />
            <div style={{ fontSize: fit(props.steps[n - 1], 190, 44, 24), fontWeight: 900, color: C.gold }}>{props.steps[n - 1]}</div>
          </div>
        ) : null}
      </Window>
    </AbsoluteFill>
  );
};

/** 전: 요란한 화면 / 후: 정돈된 화면 (실제 화면이 아니라 모양만) */
const BeforeMock: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: "linear-gradient(135deg, #6E5BFF 0%, #4BA3FF 60%, #FF6FD8 100%)" }}>
    <div style={{ ...abs(80, 60, 680, 120), borderRadius: 60, background: "rgba(255,255,255,0.85)", border: `6px solid ${C.red}` }}>
      <div style={{ ...abs(150, 34, 380, 22), borderRadius: 11, background: "#B7B4FF" }} />
      <div style={{ ...abs(250, 66, 200, 20), borderRadius: 10, background: "linear-gradient(90deg,#FF9A9E,#FAD0C4)" }} />
    </div>
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ ...abs(60 + i * 245, 230, 220, 230), borderRadius: 24, background: "#FFFFFF", border: `5px solid ${C.red}` }}>
        <div style={{ ...abs(75, 34, 70, 70), borderRadius: 35, background: "#6E5BFF" }} />
        <div style={{ ...abs(40, 130, 140, 14), borderRadius: 7, background: "#C9C6FF" }} />
        <div style={{ ...abs(60, 160, 100, 12), borderRadius: 6, background: "#E2E0FF" }} />
      </div>
    ))}
  </div>
);

const AfterMock: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: C.paper }}>
    <div style={{ ...abs(50, 40), fontFamily: MONO, fontSize: 20, color: "#8B8576", letterSpacing: 4 }}>N°04 — STUDIO</div>
    <div style={{ ...abs(50, 90, 400, 48), background: "#141414" }} />
    <div style={{ ...abs(50, 150, 300, 48), background: "#141414" }} />
    <div style={{ ...abs(50, 220, 380, 10), background: C.goldDeep }} />
    <div style={{ ...abs(520, 0, 320, 300), background: "repeating-linear-gradient(135deg, #1A1A1A 0 6px, transparent 6px 22px)" }} />
    <div style={{ ...abs(640, 190, 120, 120), borderRadius: 60, background: "#D9A21B" }} />
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ ...abs(50 + i * 260, 340, 230, 110) }}>
        <div style={{ fontFamily: MONO, fontSize: 18, color: "#8B8576" }}>0{i + 1}</div>
        <div style={{ ...abs(0, 36, 200, 12), background: "#1A1A1A" }} />
        <div style={{ ...abs(0, 62, 150, 10), background: "#9B9586" }} />
      </div>
    ))}
  </div>
);

export const LBeforeAfter: React.FC<LSceneProps<{ before: { label: string; note?: string }; after: { label: string; note?: string } }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = usePop(0, 14);
  const wipe = phase(frame, durationInFrames, 0.45, 0.6);
  const afterOn = wipe > 0;
  const tag = spring({ frame: Math.max(0, frame - (afterOn ? Math.round(durationInFrames * 0.6) : 6)), fps: 30, config: { damping: 11, stiffness: 190 } });
  const side = afterOn ? props.after : props.before;
  const color = afterOn ? C.gold : C.red;
  const meter = afterOn ? 1 - 0.85 * phase(frame, durationInFrames, 0.6, 0.8) : phase(frame, durationInFrames, 0.05, 0.35);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(110, 520, 860, 520), borderRadius: 30, overflow: "hidden", border: `4px solid ${color}`, boxShadow: afterOn ? goldGlow(0.7) : "0 0 40px rgba(255,90,78,0.35)", opacity: enter, transform: `translateY(${(1 - enter) * 60}px)` }}>
        <div style={{ ...abs(0, 0, 860, 58), background: "#202024", display: "flex", alignItems: "center", gap: 12, padding: "0 22px", zIndex: 2 }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <div key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c }} />
          ))}
        </div>
        <div style={{ ...abs(0, 58, 860, 462) }}>
          <BeforeMock />
          <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${Math.round((1 - wipe) * 100)}% 0 0)` }}>
            <AfterMock />
          </div>
          {wipe > 0 && wipe < 1 ? <div style={{ ...abs(Math.round(860 * wipe) - 3, 0, 6, 462), background: C.gold, boxShadow: goldGlow() }} /> : null}
        </div>
      </div>
      <div style={{ ...abs(700, 490), padding: "10px 26px", borderRadius: 18, background: color, color: afterOn ? C.ink : C.text, fontSize: fit(side.label, 300, 40, 24), fontWeight: 900, transform: `scale(${0.5 + 0.5 * tag}) rotate(${afterOn ? 6 : -6}deg)`, opacity: tag, boxShadow: "0 12px 26px rgba(0,0,0,0.5)" }}>
        {afterOn ? "✓ " : ""}
        {side.label}
      </div>
      <div style={{ ...abs(110, 1080, 860), display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ fontSize: 30, fontWeight: 800, color, minWidth: 120 }}>{afterOn ? "AFTER" : "BEFORE"}</div>
        <div style={{ flex: 1, height: 18, borderRadius: 9, background: C.dim }}>
          <div style={{ width: `${Math.round(meter * 100)}%`, height: 18, borderRadius: 9, background: color }} />
        </div>
      </div>
      {side.note ? <div style={{ ...abs(110, 1130, 860), textAlign: "center", fontSize: fit(side.note, 840, 36, 24), color: C.sub, fontWeight: 600 }}>{side.note}</div> : null}
    </AbsoluteFill>
  );
};

export const LTerminal: React.FC<LSceneProps<{ command: string; output: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = usePop(0, 15);
  const typing = phase(frame, durationInFrames, 0.05, 0.4);
  const outs = props.output.slice(0, 4);
  const size = fit(props.command, 760, 40, 24);
  return (
    <AbsoluteFill>
      <Window x={L.side} y={520} w={L.width} h={640} title="terminal" p={enter}>
        <div style={{ fontFamily: MONO, fontSize: size, color: C.text, lineHeight: 1.5, wordBreak: "break-all" }}>
          <span style={{ color: C.gold, fontWeight: 700 }}>$ </span>
          {typed(props.command, typing)}
          <span style={{ color: C.gold, opacity: typing < 1 && frame % 24 < 12 ? 1 : 0 }}>▌</span>
        </div>
        {outs.map((o, i) => {
          const at = durationInFrames * (0.45 + (0.4 * i) / outs.length);
          const last = i === outs.length - 1;
          const show = interpolate(frame, [at, at + 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={o + i} style={{ marginTop: 22, fontFamily: MONO, fontSize: fit(o, 800, 34, 22), color: last ? C.gold : C.sub, fontWeight: last ? 700 : 400, opacity: show, transform: `translateY(${(1 - show) * 12}px)` }}>
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
  const p = usePop(0, 12);
  const count = phase(frame, durationInFrames, 0.05, 0.55);
  const ring = phase(frame, durationInFrames, 0.0, 0.6);
  const r = 280;
  const circ = 2 * Math.PI * r;
  const shown = countUp(props.value, count);
  const valueSize = fit(shown + (props.unit ?? ""), 640, 230, 90);
  return (
    <AbsoluteFill>
      <svg style={{ ...abs(540 - r - 20, 830 - r - 20) }} width={2 * r + 40} height={2 * r + 40}>
        <circle cx={r + 20} cy={r + 20} r={r} stroke={C.dim} strokeWidth={14} fill="none" />
        <circle cx={r + 20} cy={r + 20} r={r} stroke={C.gold} strokeWidth={14} fill="none" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - ring)} transform={`rotate(-90 ${r + 20} ${r + 20})`} style={{ filter: "drop-shadow(0 0 18px rgba(255,200,61,0.6))" }} />
      </svg>
      <div style={{ ...abs(0, 830 - valueSize * 0.62, 1080), textAlign: "center", fontWeight: 900, color: C.gold, fontSize: valueSize, letterSpacing: -6, transform: `scale(${0.7 + 0.3 * p})`, textShadow: "0 0 60px rgba(255,200,61,0.35)" }}>
        {shown}
        {props.unit ? <span style={{ fontSize: Math.round(valueSize * 0.42), color: C.text, marginLeft: 10, letterSpacing: 0 }}>{props.unit}</span> : null}
      </div>
      <div style={{ ...abs(170, 830 + valueSize * 0.5, 740), textAlign: "center", fontSize: fit(props.label, 700, 48, 28), color: C.text, fontWeight: 700, opacity: phase(frame, durationInFrames, 0.2, 0.35) }}>{props.label}</div>
    </AbsoluteFill>
  );
};

export const LIcon: React.FC<LSceneProps<{ icon: string; title: string; lines?: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = usePop(0, 11);
  const lines = props.lines ?? [];
  return (
    <AbsoluteFill>
      <div style={{ ...abs(540 - 210, 520, 420, 420), borderRadius: 210, border: `4px dashed rgba(255,200,61,0.45)`, transform: `rotate(${frame * 0.8}deg) scale(${p})` }} />
      <div style={{ ...abs(540 - 160, 570, 320, 320), borderRadius: 160, background: `radial-gradient(circle at 35% 30%, #FFE08A 0%, ${C.gold} 45%, ${C.goldDeep} 100%)`, boxShadow: goldGlow(1.2), display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${0.4 + 0.6 * p})`, opacity: Math.min(1, p * 1.5) }}>
        <Icon name={props.icon} size={170} color={C.ink} stroke={2.2} />
      </div>
      <div style={{ ...abs(L.side, 960, L.width), textAlign: "center", fontSize: fit(props.title, L.width, 78, 40), fontWeight: 900, color: C.text, letterSpacing: -2, opacity: phase(frame, durationInFrames, 0.08, 0.2) }}>{props.title}</div>
      <div style={{ ...abs(L.side, 1080, L.width), display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 16 }}>
        {lines.map((t, i) => {
          const s = phase(frame, durationInFrames, 0.2 + i * 0.12, 0.3 + i * 0.12);
          return (
            <div key={t + i} style={{ padding: "10px 24px", borderRadius: 30, border: `2px solid ${C.border}`, background: C.card, fontSize: fit(t, 400, 34, 24), color: C.sub, fontWeight: 700, opacity: s, transform: `translateY(${(1 - s) * 16}px)` }}>
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
  const a = usePop(0, 14);
  const b = usePop(6, 14);
  const judge = phase(frame, durationInFrames, 0.6, 0.7);
  const w = (L.width - 40) / 2;
  const side = (s: { title: string; points: string[] }, i: number, p: number) => {
    const win = props.winner === (i === 0 ? "left" : "right");
    const lose = props.winner !== undefined && !win;
    return (
      <div key={i} style={{ ...abs(L.side + i * (w + 40), 560, w, 600), ...cardStyle({ border: win && judge > 0 ? C.gold : C.border, glow: win && judge > 0, radius: 30 }), opacity: p * (lose ? 1 - 0.55 * judge : 1), transform: `translateY(${(1 - p) * 60}px) scale(${win ? 1 + 0.04 * judge : 1})`, padding: "40px 34px" }}>
        <div style={{ fontSize: fit(s.title, w - 70, 56, 30), fontWeight: 900, color: win && judge > 0 ? C.gold : C.text, marginBottom: 26 }}>{s.title}</div>
        {s.points.slice(0, 3).map((pt) => (
          <div key={pt} style={{ display: "flex", gap: 14, alignItems: "flex-start", marginTop: 20 }}>
            <div style={{ width: 14, height: 14, borderRadius: 7, background: win ? C.gold : C.muted, marginTop: 16, flexShrink: 0 }} />
            <div style={{ fontSize: fit(pt, (w - 100) * 2, 36, 24, 2), color: C.sub, fontWeight: 600, lineHeight: 1.35, wordBreak: "keep-all" }}>{pt}</div>
          </div>
        ))}
        {win && judge > 0 ? <div style={{ ...abs(w - 96, -34, 86, 86), borderRadius: 43, background: C.gold, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${judge})` }}><Icon name="check" size={56} color={C.ink} stroke={2.6} /></div> : null}
      </div>
    );
  };
  return (
    <AbsoluteFill>
      {side(props.left, 0, a)}
      {side(props.right, 1, b)}
      <div style={{ ...abs(540 - 50, 800, 100, 100), borderRadius: 50, background: C.bg, border: `3px solid ${C.gold}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 38, fontWeight: 900, color: C.gold, opacity: b }}>VS</div>
    </AbsoluteFill>
  );
};

// ---------- 정리·끝

export const LRecap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const head = usePop(0, 14);
  const n = props.items.length;
  const rowH = Math.min(124, Math.floor((1240 - 500) / n) - 16);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: C.recapBg }} />
      <AbsoluteFill style={{ backgroundImage: "radial-gradient(rgba(0,0,0,0.09) 2px, transparent 2.5px)", backgroundSize: "30px 30px" }} />
      <div style={{ ...abs(80, 250), fontSize: fit(props.title, 900, 96, 54), fontWeight: 900, color: C.ink, letterSpacing: -3, opacity: head, transform: `translateX(${(1 - head) * -40}px)` }}>{props.title}</div>
      {props.subtitle ? (
        <div style={{ ...abs(80, 372), padding: "8px 22px", borderRadius: 14, background: C.ink, color: C.gold, fontSize: 34, fontWeight: 800, opacity: head }}>{props.subtitle}</div>
      ) : null}
      {props.items.map((it, i) => {
        const p = spring({ frame: Math.max(0, frame - 4 - Math.round((durationInFrames * 0.35 * i) / n)), fps: 30, config: { damping: 14, stiffness: 190 } });
        return (
          <div key={it.name + i} style={{ ...abs(80, 470 + i * (rowH + 16), 920, rowH), borderRadius: 22, background: C.ink, boxShadow: "0 12px 26px rgba(0,0,0,0.25)", display: "flex", alignItems: "center", gap: 26, padding: "0 30px", opacity: p, transform: `translateX(${(1 - p) * 120}px)` }}>
            <div style={{ fontSize: Math.round(rowH * 0.46), fontWeight: 900, color: C.gold, width: Math.round(rowH * 0.8) }}>{pad2(i + 1)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: fit(it.name, 560, Math.round(rowH * 0.4), 26), fontWeight: 800, color: C.text, whiteSpace: "nowrap", overflow: "hidden" }}>{it.name}</div>
              {it.note ? <div style={{ fontFamily: MONO, fontSize: Math.round(rowH * 0.2), color: C.muted, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden" }}>{it.note}</div> : null}
            </div>
            {it.tag ? <div style={{ padding: "6px 16px", borderRadius: 14, background: C.gold, color: C.ink, fontSize: 24, fontWeight: 800, whiteSpace: "nowrap" }}>{it.tag}</div> : null}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const LOutro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = usePop(0, 12);
  const line = phase(frame, durationInFrames, 0.15, 0.5);
  const size = fit(props.title, 900, 100, 52, 2);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(90, 640, 900), textAlign: "center", fontSize: size, fontWeight: 900, color: C.gold, letterSpacing: -3, lineHeight: 1.15, wordBreak: "keep-all", opacity: p, transform: `scale(${0.85 + 0.15 * p})`, textShadow: "0 0 50px rgba(255,200,61,0.3)" }}>{props.title}</div>
      <div style={{ ...abs(540 - 220 * line, 660 + size * 2.4, 440 * line, 6), borderRadius: 3, background: C.gold, boxShadow: goldGlow(0.5) }} />
      {props.subtitle ? <div style={{ ...abs(90, 700 + size * 2.4, 900), textAlign: "center", fontSize: fit(props.subtitle, 880, 46, 28), color: C.text, fontWeight: 700, opacity: phase(frame, durationInFrames, 0.2, 0.4) }}>{props.subtitle}</div> : null}
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
};
