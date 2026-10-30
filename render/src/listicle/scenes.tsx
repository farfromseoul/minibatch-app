// 목록형 쇼츠(D42) 장면 12종. 속성 모양은 src/lib/timeline.ts 의 검사, job-api app/schemas/templates.py 와 같다.
// 2026-10-31 nova 디자인: 유리 카드, 민트·하늘·보라 그라데이션, 부드럽고 느린 움직임(빠르다는 피드백).
// 움직임은 모두 프레임에서 계산한다(spring·interpolate). 장면 길이가 달라도 같은 리듬이 되게 길이 비율(phase)을 쓴다.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../lib/layout";
import { countUp, pad2, phase, seeded, typed } from "../lib/listicle";
import { Icon } from "./icons";
import { abs, C, G, G_SOFT, glassStyle, glow, gradText, L, MONO } from "./style";

export type LSceneProps<P> = { durationInFrames: number; props: P };

/** 부드러운 등장 0→1 (2026-10-31: 튀는 spring 대신 느리고 차분하게) */
const useIn = (delay = 0, damping = 20, stiffness = 110) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: Math.max(0, frame - delay), fps, config: { damping, stiffness, mass: 1 } });
};

const fit = (text: string, width: number, base: number, min: number, lines = 1) => fitFontSize(text, width, base, min, lines) ?? min;
const rise = (p: number, px = 36): React.CSSProperties => ({ opacity: p, transform: `translateY(${(1 - p) * px}px)` });

/** 위쪽 주제 꼬리표 (첫마디 두 장면) */
const Kicker: React.FC<{ text: string; p: number }> = ({ text, p }) => {
  const size = fit(text, 700, 40, 28);
  return (
    <div style={{ ...abs(0, 250, 1080), display: "flex", justifyContent: "center", ...rise(p, -16) }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 30px", borderRadius: 40, ...glassStyle({ radius: 40 }) }}>
        <Icon name="sparkles" size={size} color={C.mint} />
        <div style={{ fontSize: size, fontWeight: 700, color: C.text, letterSpacing: -0.5 }}>{text}</div>
      </div>
    </div>
  );
};

/** 글자 안 일부(highlight)를 그라데이션으로 */
const Highlighted: React.FC<{ text: string; highlight?: string }> = ({ text, highlight }) => {
  if (!highlight || !text.includes(highlight)) return <>{text}</>;
  const i = text.indexOf(highlight);
  return (
    <>
      {text.slice(0, i)}
      <span style={gradText}>{highlight}</span>
      {text.slice(i + highlight.length)}
    </>
  );
};

// ---------- 첫마디

/** 가운데를 도는 궤도와 점들 (첫마디 배경) */
const Orbits: React.FC<{ frame: number; fade: number }> = ({ frame, fade }) => (
  <svg style={{ ...abs(0, 330), opacity: fade }} width={1080} height={900}>
    <defs>
      <radialGradient id="core" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="rgba(108,199,255,0.22)" />
        <stop offset="100%" stopColor="rgba(108,199,255,0)" />
      </radialGradient>
    </defs>
    <circle cx={540} cy={430} r={260} fill="url(#core)" />
    {[170, 260, 350, 440].map((r, k) => (
      <g key={r}>
        <circle cx={540} cy={430} r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={2} strokeDasharray={k % 2 ? "4 10" : undefined} />
        {Array.from({ length: 5 + k * 3 }, (_, i) => {
          const a = (i / (5 + k * 3)) * Math.PI * 2 + frame * (0.004 + k * 0.002) * (k % 2 ? -1 : 1) + seeded(i + k * 31) * 0.6;
          const lit = seeded(i * 7 + k) < 0.22;
          return <circle key={i} cx={540 + Math.cos(a) * r} cy={430 + Math.sin(a) * r} r={lit ? 7 : 4} fill={lit ? (k % 2 ? C.violet : C.mint) : "rgba(255,255,255,0.35)"} />;
        })}
      </g>
    ))}
  </svg>
);

export const LHookClaim: React.FC<LSceneProps<{ kicker: string; claim: string; claimNote?: string; aside?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const kick = useIn(0);
  const claim = useIn(8, 18, 90);
  const note = useIn(22);
  const fade = interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" });
  const size = fit(props.claim, 860, 220, 100);
  return (
    <AbsoluteFill>
      <Orbits frame={frame} fade={fade} />
      <Kicker text={props.kicker} p={kick} />
      <div style={{ ...abs(0, 760 - size * 0.62, 1080), textAlign: "center", fontSize: size, fontWeight: 900, letterSpacing: -6, lineHeight: 1.1, opacity: claim, transform: `scale(${0.92 + 0.08 * claim})`, filter: "drop-shadow(0 0 40px rgba(108,199,255,0.35))" }}>
        <span style={gradText}>{props.claim}</span>
      </div>
      {props.claimNote ? (
        <div style={{ ...abs(0, 760 + size * 0.5, 1080), display: "flex", justifyContent: "center", ...rise(note, 20) }}>
          <div style={{ padding: "8px 22px", borderRadius: 12, border: `2px solid ${C.coral}`, color: C.coral, fontSize: 32, fontWeight: 800, letterSpacing: 2 }}>{props.claimNote}</div>
        </div>
      ) : null}
      {props.aside ? (
        <div style={{ ...abs(0, 760 + size * 0.5 + (props.claimNote ? 90 : 10), 1080), textAlign: "center", fontSize: 42, color: C.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.3, 0.45) }}>{props.aside}</div>
      ) : null}
    </AbsoluteFill>
  );
};

export const LHookReveal: React.FC<LSceneProps<{ kicker: string; headline: string; highlight?: string; count: number }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const head = useIn(0, 20, 100);
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
      <div style={{ ...abs(0, 430, 1080), textAlign: "center", fontSize: size, fontWeight: 900, color: C.text, letterSpacing: -3, ...rise(head, 30) }}>
        <Highlighted text={props.headline} highlight={props.highlight} />
      </div>
      <svg style={{ ...abs(0, 0) }} width={1080} height={1920}>
        <defs>
          <linearGradient id="rail" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor={C.mint} />
            <stop offset="50%" stopColor={C.sky} />
            <stop offset="100%" stopColor={C.violet} />
          </linearGradient>
        </defs>
        <line x1={x0 + d / 2} y1={cy} x2={x0 + d / 2 + (total - d) * line} y2={cy} stroke="url(#rail)" strokeWidth={6} strokeLinecap="round" />
      </svg>
      {Array.from({ length: n }, (_, i) => {
        const p = spring({ frame: Math.max(0, frame - 10 - i * 7), fps: 30, config: { damping: 16, stiffness: 120 } });
        const float = Math.sin((frame + i * 13) / 22) * 5;
        return (
          <div key={i} style={{ ...abs(x0 + i * (d + 34), cy - d / 2, d, d), borderRadius: d / 2, padding: 4, background: G, boxShadow: glow(undefined, 0.6), opacity: p, transform: `translateY(${(1 - p) * 60 + float}px) scale(${0.7 + 0.3 * p})` }}>
            <div style={{ width: "100%", height: "100%", borderRadius: d / 2, background: "rgba(14, 17, 28, 0.94)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(d * 0.44), fontWeight: 900, color: C.text }}>
              {pad2(i + 1)}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

// ---------- 항목 소개 카드

export const LItemCard: React.FC<LSceneProps<{ number: number; name: string; meta?: string; tagline?: string; badge?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useIn(0, 20, 100);
  const inner = useIn(8);
  const nameSize = fit(props.name, 720, 104, 52);
  const drift = interpolate(frame, [0, durationInFrames], [0, -18]);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(96, 520, 888, 560), borderRadius: 44, padding: 3, background: G, boxShadow: glow(undefined, 0.8), ...rise(p, 60) }}>
        <div style={{ position: "relative", width: "100%", height: "100%", borderRadius: 41, background: "rgba(13, 16, 27, 0.96)", overflow: "hidden" }}>
          <div style={{ ...abs(0, 0, 882, 554), background: G_SOFT, opacity: 0.55 }} />
          <div style={{ ...abs(470, -60 + drift), fontSize: 380, fontWeight: 900, color: "transparent", WebkitTextStroke: "3px rgba(255,255,255,0.10)", letterSpacing: -20 }}>{pad2(props.number)}</div>
          <div style={{ ...abs(64, 70), fontFamily: MONO, fontSize: 28, letterSpacing: 6, color: C.mint, fontWeight: 700, ...rise(inner, 14) }}>ITEM {pad2(props.number)}</div>
          {props.badge ? (
            <div style={{ ...abs(64, 120), padding: "6px 20px", borderRadius: 30, background: G, color: C.ink, fontSize: 28, fontWeight: 800, ...rise(inner, 14) }}>{props.badge}</div>
          ) : null}
          <div style={{ ...abs(64, 214, 760), fontSize: nameSize, fontWeight: 900, color: C.text, letterSpacing: -2.5, lineHeight: 1.05, ...rise(inner, 22) }}>{props.name}</div>
          {props.meta ? (
            <div style={{ ...abs(64, 214 + nameSize + 34), display: "flex", alignItems: "center", gap: 10, padding: "8px 18px", borderRadius: 14, background: C.glass2, border: `1px solid ${C.line}`, fontFamily: MONO, fontSize: 26, color: C.sub, ...rise(inner, 16) }}>
              <Icon name="code" size={26} color={C.sky} />
              {props.meta}
            </div>
          ) : null}
          {props.tagline ? (
            <div style={{ ...abs(64, 456, 760), fontSize: fit(props.tagline, 740, 40, 26), color: C.text, fontWeight: 600, opacity: 0.86 * phase(frame, durationInFrames, 0.15, 0.35) }}>{props.tagline}</div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- 항목 설명 그림

/** 창 틀 (점 세 개 + 제목) */
const Window: React.FC<{ x: number; y: number; w: number; h: number; title?: string; p: number; children: React.ReactNode; active?: boolean }> = ({ x, y, w, h, title, p, children, active }) => (
  <div style={{ ...abs(x, y, w, h), ...glassStyle({ radius: 28, active, strong: true }), overflow: "hidden", ...rise(p, 44) }}>
    <div style={{ height: 60, display: "flex", alignItems: "center", gap: 12, padding: "0 26px", borderBottom: `1px solid ${C.line}` }}>
      {[C.coral, "#F7C66B", C.mint].map((c) => (
        <div key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c, opacity: 0.85 }} />
      ))}
      {title ? <div style={{ marginLeft: 14, fontFamily: MONO, fontSize: 24, color: C.muted }}>{title}</div> : null}
    </div>
    <div style={{ position: "relative", padding: "28px 36px" }}>{children}</div>
  </div>
);

export const LChat: React.FC<LSceneProps<{ prompt: string; results: string[]; status?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = useIn(0);
  const typing = phase(frame, durationInFrames, 0.04, 0.42);
  const sent = typing >= 1;
  const pick = phase(frame, durationInFrames, 0.72, 0.8);
  const statusP = props.status ? phase(frame, durationInFrames, 0.78, 0.98) : 0;
  const rows = props.results.slice(0, 4);
  const rowH = 108;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 500, L.width, 120), ...glassStyle({ radius: 30, active: sent, strong: true }), display: "flex", alignItems: "center", padding: "0 34px", gap: 22, ...rise(enter, 30) }}>
        <Icon name="chat" size={44} color={sent ? C.mint : C.muted} />
        <div style={{ flex: 1, fontSize: fit(props.prompt, 690, 42, 28), color: C.text, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden" }}>
          {typed(props.prompt, typing)}
          <span style={{ color: C.mint, opacity: !sent && frame % 30 < 15 ? 1 : 0 }}>▏</span>
        </div>
        <div style={{ width: 64, height: 64, borderRadius: 32, background: sent ? G : C.glass2, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="bolt" size={34} color={sent ? C.ink : C.muted} />
        </div>
      </div>
      {rows.map((r, i) => {
        const p = spring({ frame: Math.max(0, frame - Math.round(durationInFrames * 0.46) - i * 7), fps: 30, config: { damping: 20, stiffness: 120 } });
        const chosen = i === 0 && pick > 0;
        return (
          <div key={r + i} style={{ ...abs(L.side + 40, 670 + i * (rowH + 20), L.width - 40, rowH), ...glassStyle({ radius: 24, active: chosen }), display: "flex", alignItems: "center", padding: "0 30px", gap: 24, opacity: p, transform: `translateX(${(1 - p) * 50}px)` }}>
            <div style={{ width: 58, height: 58, borderRadius: 29, background: chosen ? G : C.glass2, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon name={chosen ? "check" : "search"} size={34} color={chosen ? C.ink : C.muted} />
            </div>
            <div style={{ flex: 1, fontSize: fit(r, 640, 40, 26), color: chosen ? C.text : C.sub, fontWeight: chosen ? 800 : 600 }}>{r}</div>
          </div>
        );
      })}
      <div style={{ ...abs(L.side + 16, 670, 4, rows.length * (rowH + 20) - 20), borderRadius: 2, background: G, opacity: 0.5 * phase(frame, durationInFrames, 0.44, 0.6) }} />
      {props.status ? (
        <div style={{ ...abs(L.side + 80, 1170, L.width - 160, 72), ...glassStyle({ radius: 36 }), opacity: Math.min(1, statusP * 4), display: "flex", alignItems: "center", gap: 18, padding: "0 28px" }}>
          <Icon name="gear" size={32} color={C.mint} style={{ transform: `rotate(${frame * 3}deg)` }} />
          <div style={{ fontSize: 30, color: C.text, fontWeight: 700, minWidth: 190 }}>{props.status}</div>
          <div style={{ flex: 1, height: 10, borderRadius: 5, background: C.dim }}>
            <div style={{ width: `${Math.round(statusP * 100)}%`, height: 10, borderRadius: 5, background: G }} />
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const LSteps: React.FC<LSceneProps<{ steps: string[]; checks?: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = useIn(0);
  const n = props.steps.length;
  const stepAt = (i: number) => durationInFrames * (0.1 + (0.66 * i) / n);
  const active = props.steps.filter((_, i) => frame >= stepAt(i)).length;
  const gap = 20;
  const chipW = Math.floor((L.width - gap * (n - 1)) / n);
  const checks = props.checks ?? [];
  const done = active >= n;
  const stamp = spring({ frame: Math.max(0, frame - Math.round(stepAt(n - 1)) - 10), fps: 30, config: { damping: 16, stiffness: 110 } });
  return (
    <AbsoluteFill>
      {props.steps.map((s, i) => {
        const on = i < active;
        return (
          <div key={s + i} style={{ ...abs(L.side + i * (chipW + gap), 500, chipW, 88), borderRadius: 44, padding: 2, background: on ? G : C.line, ...rise(enter, 24) }}>
            <div style={{ width: "100%", height: "100%", borderRadius: 42, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, background: on ? "rgba(13,16,27,0.55)" : "rgba(13,16,27,0.92)", color: on ? C.text : C.muted, fontSize: fit(s, chipW - 80, 34, 22), fontWeight: 800 }}>
              {on ? <Icon name="check" size={30} color={C.mint} stroke={2.4} /> : <span style={{ fontFamily: MONO, fontSize: 24 }}>{i + 1}</span>}
              {s}
            </div>
          </div>
        );
      })}
      <Window x={L.side} y={640} w={L.width} h={560} title={checks.length ? "checklist" : "workflow"} p={enter} active={done}>
        {checks.length
          ? checks.map((c, i) => {
              const on = frame >= stepAt(Math.min(n - 1, Math.floor(((i + 1) * n) / checks.length) - 1)) + 8;
              return (
                <div key={c + i} style={{ display: "flex", alignItems: "center", gap: 22, height: 104 }}>
                  <div style={{ width: 52, height: 52, borderRadius: 26, border: `3px solid ${on ? C.mint : "rgba(255,255,255,0.22)"}`, background: on ? "rgba(92,242,196,0.16)" : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {on ? <Icon name="check" size={38} color={C.mint} stroke={2.4} /> : null}
                  </div>
                  <div style={{ fontSize: fit(c, 700, 42, 26), color: on ? C.text : C.muted, fontWeight: 700 }}>{c}</div>
                </div>
              );
            })
          : Array.from({ length: 8 }, (_, i) => {
              const pass = done && i >= 5;
              const show = frame >= stepAt(Math.min(n - 1, Math.floor((i * n) / 8)));
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 16, height: 52, opacity: show ? 1 : 0.15 }}>
                  <div style={{ fontFamily: MONO, fontSize: 22, color: C.muted, width: 30 }}>{i + 1}</div>
                  <div style={{ height: 14, borderRadius: 7, width: 120 + seeded(i) * 420, background: pass ? C.mint : i % 3 === 0 ? "rgba(142,123,255,0.65)" : "rgba(255,255,255,0.16)" }} />
                  {pass ? <div style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 24, fontWeight: 700, color: C.mint }}>PASS</div> : null}
                </div>
              );
            })}
        {done ? (
          <div style={{ ...abs(L.width - 320, 250, 230, 230), borderRadius: 115, padding: 5, background: G, transform: `scale(${0.6 + 0.4 * stamp})`, opacity: stamp, boxShadow: glow() }}>
            <div style={{ width: "100%", height: "100%", borderRadius: 110, background: "rgba(13,16,27,0.95)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <Icon name="check" size={76} color={C.mint} stroke={2.4} />
              <div style={{ fontSize: fit(props.steps[n - 1], 170, 40, 22), fontWeight: 900, ...gradText }}>{props.steps[n - 1]}</div>
            </div>
          </div>
        ) : null}
      </Window>
    </AbsoluteFill>
  );
};

/** 전: 어수선한 화면 / 후: 정돈된 화면 (실제 화면이 아니라 모양만) */
const BeforeMock: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: "#1B1E2B" }}>
    {Array.from({ length: 9 }, (_, i) => (
      <div key={i} style={{ ...abs(30 + seeded(i) * 620, 24 + seeded(i + 9) * 330, 120 + seeded(i + 3) * 110, 44 + seeded(i + 5) * 60), borderRadius: 10, background: ["#FF7A70", "#F7C66B", "#8E7BFF", "#6CC7FF"][i % 4], opacity: 0.5, transform: `rotate(${(seeded(i + 2) - 0.5) * 14}deg)` }} />
    ))}
    <div style={{ ...abs(40, 380, 260, 14), borderRadius: 7, background: "rgba(255,255,255,0.3)" }} />
    <div style={{ ...abs(330, 400, 360, 14), borderRadius: 7, background: "rgba(255,255,255,0.2)", transform: "rotate(3deg)" }} />
  </div>
);

const AfterMock: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: "#10131F" }}>
    <div style={{ ...abs(40, 36, 300, 26), borderRadius: 8, background: "rgba(255,255,255,0.85)" }} />
    <div style={{ ...abs(40, 78, 200, 14), borderRadius: 7, background: "rgba(255,255,255,0.3)" }} />
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ ...abs(40 + i * 254, 130, 230, 170), borderRadius: 18, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)" }}>
        <div style={{ ...abs(22, 22, 44, 44), borderRadius: 22, background: [C.mint, C.sky, C.violet][i] }} />
        <div style={{ ...abs(22, 90, 150, 12), borderRadius: 6, background: "rgba(255,255,255,0.6)" }} />
        <div style={{ ...abs(22, 116, 110, 10), borderRadius: 5, background: "rgba(255,255,255,0.25)" }} />
      </div>
    ))}
    <div style={{ ...abs(40, 330, 750, 10), borderRadius: 5, background: "rgba(255,255,255,0.1)" }} />
    <div style={{ ...abs(40, 330, 520, 10), borderRadius: 5, background: G }} />
    <div style={{ ...abs(40, 370, 600, 10), borderRadius: 5, background: "rgba(255,255,255,0.18)" }} />
  </div>
);

export const LBeforeAfter: React.FC<LSceneProps<{ before: { label: string; note?: string }; after: { label: string; note?: string } }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = useIn(0);
  const wipe = phase(frame, durationInFrames, 0.42, 0.62);
  const afterOn = wipe >= 0.5;
  const side = afterOn ? props.after : props.before;
  const W = 840;
  const H = 440;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(120, 560, W, H + 60), borderRadius: 30, overflow: "hidden", ...glassStyle({ radius: 30, active: afterOn, strong: true }), ...rise(enter, 50) }}>
        <div style={{ height: 60, display: "flex", alignItems: "center", gap: 12, padding: "0 24px", borderBottom: `1px solid ${C.line}` }}>
          {[C.coral, "#F7C66B", C.mint].map((c) => (
            <div key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c, opacity: 0.85 }} />
          ))}
        </div>
        <div style={{ position: "relative", width: W, height: H }}>
          <BeforeMock />
          <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${Math.round((1 - wipe) * 100)}% 0 0)` }}>
            <AfterMock />
          </div>
          {wipe > 0 && wipe < 1 ? <div style={{ ...abs(Math.round(W * wipe) - 3, 0, 6, H), background: G, boxShadow: glow() }} /> : null}
        </div>
      </div>
      <div style={{ ...abs(120, 470, W), display: "flex", gap: 16 }}>
        {[props.before, props.after].map((s, i) => {
          const on = (i === 1) === afterOn;
          return (
            <div key={i} style={{ padding: "10px 24px", borderRadius: 30, fontSize: fit(s.label, 330, 34, 22), fontWeight: 800, ...(on ? (i ? { background: G, color: C.ink } : { background: "rgba(255,122,112,0.18)", color: C.coral, border: `2px solid ${C.coral}` }) : { background: C.glass, color: C.muted, border: `1px solid ${C.line}` }) }}>
              {i ? "AFTER · " : "BEFORE · "}
              {s.label}
            </div>
          );
        })}
      </div>
      {side.note ? <div style={{ ...abs(120, 1100, W), textAlign: "center", fontSize: fit(side.note, 820, 38, 24), color: C.sub, fontWeight: 600 }}>{side.note}</div> : null}
    </AbsoluteFill>
  );
};

export const LTerminal: React.FC<LSceneProps<{ command: string; output: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const enter = useIn(0);
  const typing = phase(frame, durationInFrames, 0.06, 0.45);
  const outs = props.output.slice(0, 4);
  const size = fit(props.command, 760, 40, 24);
  return (
    <AbsoluteFill>
      <Window x={L.side} y={520} w={L.width} h={640} title="~/project — zsh" p={enter}>
        <div style={{ fontFamily: MONO, fontSize: size, color: C.text, lineHeight: 1.5, wordBreak: "break-all" }}>
          <span style={{ color: C.mint, fontWeight: 700 }}>❯ </span>
          {typed(props.command, typing)}
          <span style={{ color: C.mint, opacity: typing < 1 && frame % 30 < 15 ? 1 : 0 }}>▌</span>
        </div>
        {outs.map((o, i) => {
          const at = durationInFrames * (0.5 + (0.36 * i) / outs.length);
          const last = i === outs.length - 1;
          const show = interpolate(frame, [at, at + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={o + i} style={{ marginTop: 22, fontFamily: MONO, fontSize: fit(o, 800, 34, 22), color: last ? C.mint : C.sub, fontWeight: last ? 700 : 400, opacity: show, transform: `translateY(${(1 - show) * 12}px)` }}>
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
  const p = useIn(0, 20, 90);
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
        <defs>
          <linearGradient id="ring" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor={C.mint} />
            <stop offset="50%" stopColor={C.sky} />
            <stop offset="100%" stopColor={C.violet} />
          </linearGradient>
        </defs>
        <circle cx={r + 30} cy={r + 30} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth={16} fill="none" />
        <circle cx={r + 30} cy={r + 30} r={r} stroke="url(#ring)" strokeWidth={16} fill="none" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - ring)} transform={`rotate(-90 ${r + 30} ${r + 30})`} />
      </svg>
      <div style={{ ...abs(0, cy - valueSize * 0.66, 1080), textAlign: "center", fontWeight: 900, fontSize: valueSize, letterSpacing: -6, transform: `scale(${0.85 + 0.15 * p})` }}>
        <span style={gradText}>{shown}</span>
        {props.unit ? <span style={{ fontSize: Math.round(valueSize * 0.4), color: C.text, marginLeft: 10, letterSpacing: 0 }}>{props.unit}</span> : null}
      </div>
      <div style={{ ...abs(180, cy + valueSize * 0.5, 720), textAlign: "center", fontSize: fit(props.label, 700, 46, 28), color: C.text, fontWeight: 700, opacity: phase(frame, durationInFrames, 0.2, 0.4) }}>{props.label}</div>
    </AbsoluteFill>
  );
};

export const LIcon: React.FC<LSceneProps<{ icon: string; title: string; lines?: string[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useIn(0, 18, 90);
  const lines = props.lines ?? [];
  const cy = 760;
  return (
    <AbsoluteFill>
      {[230, 300].map((r, k) => (
        <div key={r} style={{ ...abs(540 - r, cy - r, r * 2, r * 2), borderRadius: r, border: `2px ${k ? "dashed" : "solid"} rgba(255,255,255,${k ? 0.12 : 0.08})`, transform: `rotate(${frame * (k ? -0.4 : 0.25)}deg) scale(${0.85 + 0.15 * p})`, opacity: p }} />
      ))}
      <div style={{ ...abs(540 - 150, cy - 150, 300, 300), borderRadius: 150, padding: 5, background: G, boxShadow: glow(undefined, 1.1), transform: `scale(${0.6 + 0.4 * p})`, opacity: p }}>
        <div style={{ width: "100%", height: "100%", borderRadius: 145, background: "rgba(13,16,27,0.94)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name={props.icon} size={150} color={C.mint} stroke={1.8} />
        </div>
      </div>
      <div style={{ ...abs(L.side, 1000, L.width), textAlign: "center", fontSize: fit(props.title, L.width, 74, 40), fontWeight: 900, color: C.text, letterSpacing: -2, opacity: phase(frame, durationInFrames, 0.1, 0.25) }}>{props.title}</div>
      <div style={{ ...abs(L.side, 1110, L.width), display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 14 }}>
        {lines.map((t, i) => {
          const s = phase(frame, durationInFrames, 0.25 + i * 0.12, 0.38 + i * 0.12);
          return (
            <div key={t + i} style={{ padding: "10px 24px", borderRadius: 30, ...glassStyle({ radius: 30 }), fontSize: fit(t, 400, 32, 22), color: C.sub, fontWeight: 700, ...rise(s, 14) }}>
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
  const a = useIn(0);
  const b = useIn(8);
  const judge = phase(frame, durationInFrames, 0.6, 0.72);
  const w = (L.width - 40) / 2;
  const side = (s: { title: string; points: string[] }, i: number, p: number) => {
    const win = props.winner === (i === 0 ? "left" : "right");
    const lose = props.winner !== undefined && !win;
    return (
      <div key={i} style={{ ...abs(L.side + i * (w + 40), 540, w, 620), ...glassStyle({ radius: 32, active: win && judge > 0, strong: true }), opacity: p * (lose ? 1 - 0.5 * judge : 1), transform: `translateY(${(1 - p) * 50}px) scale(${win ? 1 + 0.03 * judge : 1})`, padding: "44px 34px" }}>
        <div style={{ fontFamily: MONO, fontSize: 24, letterSpacing: 4, color: win ? C.mint : C.muted, marginBottom: 14 }}>{i === 0 ? "A" : "B"}</div>
        <div style={{ fontSize: fit(s.title, w - 70, 54, 30), fontWeight: 900, marginBottom: 22, ...(win && judge > 0 ? gradText : { color: C.text }) }}>{s.title}</div>
        {s.points.slice(0, 3).map((pt) => (
          <div key={pt} style={{ display: "flex", gap: 14, alignItems: "flex-start", marginTop: 22 }}>
            <div style={{ width: 12, height: 12, borderRadius: 6, background: win ? C.mint : C.muted, marginTop: 16, flexShrink: 0 }} />
            <div style={{ fontSize: fit(pt, (w - 100) * 2, 34, 24, 2), color: C.sub, fontWeight: 600, lineHeight: 1.4, wordBreak: "keep-all" }}>{pt}</div>
          </div>
        ))}
      </div>
    );
  };
  return (
    <AbsoluteFill>
      {side(props.left, 0, a)}
      {side(props.right, 1, b)}
      <div style={{ ...abs(540 - 48, 802, 96, 96), borderRadius: 48, padding: 3, background: G, opacity: b }}>
        <div style={{ width: "100%", height: "100%", borderRadius: 45, background: C.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, fontWeight: 900, color: C.text }}>VS</div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- 정리·끝

/** 정리: 세로 타임라인 (2026-10-31: 노란 바탕 목록 대신) */
export const LRecap: React.FC<LSceneProps<{ title: string; subtitle?: string; items: { name: string; note?: string; tag?: string }[] }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const head = useIn(0);
  const n = props.items.length;
  const top = 500;
  const rowH = Math.min(118, Math.floor((1230 - top) / n) - 18);
  const rail = phase(frame, durationInFrames, 0.05, 0.6);
  return (
    <AbsoluteFill>
      <div style={{ ...abs(L.side, 262), fontSize: fit(props.title, 900, 92, 54), fontWeight: 900, letterSpacing: -3, ...rise(head, 24) }}>
        <span style={gradText}>{props.title}</span>
      </div>
      {props.subtitle ? <div style={{ ...abs(L.side, 384), fontSize: 36, color: C.sub, fontWeight: 600, ...rise(head, 18) }}>{props.subtitle}</div> : null}
      <div style={{ ...abs(L.side + 36, top + rowH / 2, 4, (n - 1) * (rowH + 18) * rail), borderRadius: 2, background: G }} />
      {props.items.map((it, i) => {
        const p = spring({ frame: Math.max(0, frame - 6 - Math.round((durationInFrames * 0.5 * i) / n)), fps: 30, config: { damping: 20, stiffness: 120 } });
        const y = top + i * (rowH + 18);
        return (
          <React.Fragment key={it.name + i}>
            <div style={{ ...abs(L.side + 16, y + rowH / 2 - 22, 44, 44), borderRadius: 22, padding: 3, background: G, opacity: p, transform: `scale(${0.5 + 0.5 * p})` }}>
              <div style={{ width: "100%", height: "100%", borderRadius: 19, background: C.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, fontWeight: 900, color: C.text }}>{i + 1}</div>
            </div>
            <div style={{ ...abs(L.side + 96, y, L.width - 96, rowH), ...glassStyle({ radius: 24 }), display: "flex", alignItems: "center", gap: 20, padding: "0 30px", opacity: p, transform: `translateX(${(1 - p) * 60}px)` }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: fit(it.name, 520, Math.round(rowH * 0.38), 26), fontWeight: 800, color: C.text, whiteSpace: "nowrap", overflow: "hidden" }}>{it.name}</div>
                {it.note ? <div style={{ fontSize: Math.round(rowH * 0.22), color: C.sub, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden" }}>{it.note}</div> : null}
              </div>
              {it.tag ? <div style={{ padding: "6px 16px", borderRadius: 20, background: G, color: C.ink, fontSize: 24, fontWeight: 800, whiteSpace: "nowrap" }}>{it.tag}</div> : null}
            </div>
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};

export const LOutro: React.FC<LSceneProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props }) => {
  const frame = useCurrentFrame();
  const p = useIn(0, 20, 90);
  const line = phase(frame, durationInFrames, 0.15, 0.5);
  const size = fit(props.title, 900, 100, 52, 2);
  const cy = 760;
  return (
    <AbsoluteFill>
      <div style={{ ...abs(540 - 70, cy - 230, 140, 140), borderRadius: 70, padding: 4, background: G, opacity: p, transform: `scale(${0.6 + 0.4 * p})`, boxShadow: glow() }}>
        <div style={{ width: "100%", height: "100%", borderRadius: 66, background: C.bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="book" size={70} color={C.mint} />
        </div>
      </div>
      <div style={{ ...abs(90, cy - 40, 900), textAlign: "center", fontSize: size, fontWeight: 900, letterSpacing: -3, lineHeight: 1.15, wordBreak: "keep-all", ...rise(p, 30) }}>
        <span style={gradText}>{props.title}</span>
      </div>
      <div style={{ ...abs(540 - 200 * line, cy - 20 + size * 1.3, 400 * line, 5), borderRadius: 3, background: G }} />
      {props.subtitle ? <div style={{ ...abs(90, cy + 20 + size * 1.3, 900), textAlign: "center", fontSize: fit(props.subtitle, 880, 44, 28), color: C.sub, fontWeight: 600, opacity: phase(frame, durationInFrames, 0.25, 0.45) }}>{props.subtitle}</div> : null}
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
