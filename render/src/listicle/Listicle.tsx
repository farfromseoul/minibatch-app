// 목록형 쇼츠(D42) 화면 틀: 바탕(오로라·점 무늬) → 장면 → 위 진행 막대·항목 제목 → 아래 단어 단위 자막.
// 2026-10-31 nova: 참고 영상의 노란 칸·노란 상자 대신 분할 진행 막대, 그라데이션 밑줄 자막.
// 시각은 timeline 단계가 정한 정수 프레임을 그대로 쓴다 (앱 설계 "타임라인 계산").
import React from "react";
import { AbsoluteFill, Html5Audio, interpolate, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../lib/layout";
import { pad2, trackerSlots, wordStates } from "../lib/listicle";
import type { Timeline, TimelineScene } from "../lib/timeline";
import { loadFonts } from "./fonts";
import { Icon } from "./icons";
import { LISTICLE_SCENES } from "./scenes";
import { abs, C, G, glow, L, MONO } from "./style";

loadFonts();

/** 바탕: 짙은 남색 + 천천히 떠다니는 민트·보라 빛 + 점 무늬(아래로 갈수록 옅게) */
const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const a = Math.sin(frame / 160);
  const b = Math.cos(frame / 200);
  return (
    <>
      <AbsoluteFill style={{ background: C.bg }} />
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

const sceneAt = (t: Timeline, frame: number): TimelineScene | undefined =>
  t.scenes.find((s) => frame >= s.fromFrame && frame < s.fromFrame + s.durationInFrames) ?? t.scenes[t.scenes.length - 1];

/** 항목 하나가 차지하는 구간 (첫 장면 시작 ~ 마지막 장면 끝) */
const itemSpan = (t: Timeline, index: number): [number, number] => {
  const ss = t.scenes.filter((s) => s.section?.kind === "item" && s.section.index === index);
  if (!ss.length) return [0, 1];
  const last = ss[ss.length - 1];
  return [ss[0].fromFrame, last.fromFrame + last.durationInFrames];
};

/** 위 진행: "ITEM 02 / 05" + 분할 막대. 지금 항목 칸은 항목이 진행되는 만큼 차오른다 */
const Progress: React.FC<{ t: Timeline; index: number }> = ({ t, index }) => {
  const frame = useCurrentFrame();
  const items = t.tracker?.items ?? [];
  if (!items.length) return null;
  const slots = trackerSlots(items.length, index);
  const [s0, s1] = itemSpan(t, index);
  const fill = interpolate(frame, [s0, s1], [0.04, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const gap = 10;
  const w = (L.width - gap * (items.length - 1)) / items.length;
  return (
    <>
      <div style={{ ...abs(L.side, L.counterY), display: "flex", alignItems: "baseline", gap: 12, fontFamily: MONO }}>
        <span style={{ fontSize: 26, letterSpacing: 6, color: C.mint, fontWeight: 700 }}>ITEM</span>
        <span style={{ fontSize: 30, color: C.text, fontWeight: 700 }}>{pad2(index)}</span>
        <span style={{ fontSize: 26, color: C.muted }}>/ {pad2(items.length)}</span>
      </div>
      {items.map((it, i) => {
        const st = slots[i];
        return (
          <div key={it.name + i} style={{ ...abs(L.side + i * (w + gap), L.barY, w, 10), borderRadius: 5, background: "rgba(255,255,255,0.12)", overflow: "hidden" }}>
            <div style={{ width: st === "done" ? "100%" : st === "current" ? `${fill * 100}%` : "0%", height: "100%", borderRadius: 5, background: st === "done" ? "rgba(92,242,196,0.55)" : G, boxShadow: st === "current" ? glow(undefined, 0.4) : undefined }} />
          </div>
        );
      })}
    </>
  );
};

/** 항목 설명 장면 위 제목: [02] 이름 + 출처 칩 */
const ItemHeader: React.FC<{ t: Timeline; index: number; since: number }> = ({ t, index, since }) => {
  const it = t.tracker?.items[index - 1];
  if (!it) return null;
  const p = interpolate(since, [0, 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const size = fitFontSize(it.name, L.width - 130, 76, 44, 1) ?? 44;
  return (
    <div style={{ ...abs(L.side, L.headerY, L.width), opacity: p, transform: `translateY(${(1 - p) * 16}px)` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ padding: "4px 16px", borderRadius: 14, background: G, color: C.ink, fontSize: 38, fontWeight: 900 }}>{pad2(index)}</div>
        <div style={{ fontSize: size, fontWeight: 900, color: C.text, letterSpacing: -2, whiteSpace: "nowrap" }}>{it.name}</div>
      </div>
      {it.meta ? (
        <div style={{ marginTop: 14, display: "inline-flex", alignItems: "center", gap: 10, padding: "6px 16px", borderRadius: 12, background: C.glass2, border: `1px solid ${C.line}`, fontFamily: MONO, fontSize: 24, color: C.sub }}>
          <Icon name="code" size={24} color={C.sky} />
          {it.meta}
        </div>
      ) : null}
    </div>
  );
};

/** 자막: 구절 하나씩. 지금 단어는 흰 글자 + 그라데이션 밑줄, 읽은 단어는 흰색(강조 단어는 민트), 남은 단어는 옅게 */
const Caption: React.FC<{ t: Timeline }> = ({ t }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const c = t.captions.find((x) => frame >= x.fromFrame && frame < x.toFrame);
  if (!c) return null;
  const words = c.words && c.words.length ? c.words : [{ text: c.text, fromFrame: c.fromFrame }];
  const states = c.words && c.words.length ? wordStates(words, frame) : words.map(() => "done" as const);
  const size = fitFontSize(c.text, L.width - 40, 64, 44, 2) ?? 44;
  const enter = spring({ frame: frame - c.fromFrame, fps, config: { damping: 22, stiffness: 140 } });
  return (
    <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "flex-end", columnGap: Math.round(size * 0.26), rowGap: 14, opacity: Math.min(1, enter * 1.3), transform: `translateY(${(1 - enter) * 14}px)` }}>
      {words.map((w, i) => {
        const st = states[i];
        const emph = "emphasis" in w && w.emphasis;
        const color = st === "next" ? "rgba(243,245,251,0.30)" : emph ? C.mint : C.text;
        const bar = st === "current" ? spring({ frame: frame - w.fromFrame, fps, config: { damping: 20, stiffness: 160 } }) : 0;
        return (
          <span key={i} style={{ position: "relative", fontSize: size, fontWeight: 800, color, lineHeight: 1.3, letterSpacing: -0.5, textShadow: "0 4px 24px rgba(0,0,0,0.6)", transform: st === "current" ? `translateY(${-4 * bar}px)` : undefined, display: "inline-block" }}>
            {w.text}
            {st === "current" ? <span style={{ position: "absolute", left: 0, bottom: -8, height: 7, width: `${bar * 100}%`, borderRadius: 4, background: G, boxShadow: glow(undefined, 0.35) }} /> : null}
          </span>
        );
      })}
    </div>
  );
};

export const Listicle: React.FC<{ timeline: Timeline; assetBase: string }> = ({ timeline: t, assetBase }) => {
  const frame = useCurrentFrame();
  const scene = sceneAt(t, frame);
  const sec = scene?.section;
  const index = sec?.kind === "item" ? sec.index ?? null : null;
  // 항목 제목은 그 항목의 첫 설명 장면에서 한 번만 들어온다 (소개 카드 장면에서는 카드가 제목)
  const showHeader = index !== null && scene?.visual.component !== "LItemCard";
  const firstDetail = showHeader ? t.scenes.find((s) => s.section?.kind === "item" && s.section.index === index && s.visual.component !== "LItemCard") : undefined;
  return (
    <AbsoluteFill style={{ fontFamily: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif", color: C.text }}>
      <Background />
      {t.scenes.map((s) => {
        const Scene = LISTICLE_SCENES[s.visual.component];
        return (
          <Sequence key={s.id} from={s.fromFrame} durationInFrames={s.durationInFrames} name={s.id}>
            <Scene durationInFrames={s.durationInFrames} props={s.visual.props} />
          </Sequence>
        );
      })}
      {index !== null ? <Progress t={t} index={index} /> : null}
      {showHeader && index !== null && firstDetail ? <ItemHeader t={t} index={index} since={frame - firstDetail.fromFrame} /> : null}
      {t.audio.map((a) => (
        <Sequence key={a.src} from={a.fromFrame} name={a.src}>
          <Html5Audio src={assetBase + a.src} />
        </Sequence>
      ))}
      <Caption t={t} />
    </AbsoluteFill>
  );
};
