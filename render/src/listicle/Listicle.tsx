// 목록형 쇼츠(D42) 화면 틀: 바탕 → 장면 → 위 진행 표시·항목 제목 → 아래 단어 단위 자막.
// 시각은 timeline 단계가 정한 정수 프레임을 그대로 쓴다 (앱 설계 "타임라인 계산").
import React from "react";
import { AbsoluteFill, Html5Audio, interpolate, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { fitFontSize } from "../lib/layout";
import { pad2, trackerSlots, wordStates } from "../lib/listicle";
import type { Timeline, TimelineScene } from "../lib/timeline";
import { loadFonts } from "./fonts";
import { LISTICLE_SCENES } from "./scenes";
import { abs, C, goldGlow, L, MONO } from "./style";

loadFonts();

const Background: React.FC = () => (
  <>
    <AbsoluteFill style={{ background: C.bg }} />
    <AbsoluteFill
      style={{
        backgroundImage: "linear-gradient(rgba(255,255,255,0.032) 2px, transparent 2px), linear-gradient(90deg, rgba(255,255,255,0.032) 2px, transparent 2px)",
        backgroundSize: "60px 60px",
      }}
    />
    <AbsoluteFill style={{ background: "radial-gradient(ellipse 75% 38% at 50% 34%, rgba(255,200,61,0.10), transparent 72%)" }} />
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, transparent 55%, rgba(0,0,0,0.7) 100%)" }} />
  </>
);

const sceneAt = (t: Timeline, frame: number): TimelineScene | undefined =>
  t.scenes.find((s) => frame >= s.fromFrame && frame < s.fromFrame + s.durationInFrames) ?? t.scenes[t.scenes.length - 1];

/** 위 진행 표시: 지난 항목은 이름, 지금 항목은 빛나는 테두리, 남은 칸은 노란 번호 */
const Tracker: React.FC<{ t: Timeline; scene: TimelineScene; since: number }> = ({ t, scene, since }) => {
  const { fps } = useVideoConfig();
  const items = t.tracker?.items ?? [];
  const sec = scene.section;
  if (!items.length || !sec || sec.kind !== "item") return null;
  const slots = trackerSlots(items.length, sec.index ?? null);
  const gap = 14;
  const w = Math.floor((L.width - gap * (items.length - 1)) / items.length);
  const pop = spring({ frame: since, fps, config: { damping: 12, stiffness: 200 } });
  return (
    <>
      {items.map((it, i) => {
        const st = slots[i];
        const cur = st === "current";
        const style: React.CSSProperties =
          st === "next"
            ? { background: "linear-gradient(160deg, #FFD966, #E9B21F)", border: "2px solid rgba(255,240,190,0.7)", opacity: 0.88 }
            : { background: cur ? "#17150F" : C.card, border: `3px solid ${cur ? C.gold : C.border}`, boxShadow: cur ? goldGlow(0.6) : "none" };
        return (
          <div key={it.name + i} style={{ ...abs(L.side + i * (w + gap), L.trackerY, w, L.trackerH), borderRadius: 16, overflow: "hidden", transform: cur ? `scale(${1 + 0.08 * (1 - pop)})` : undefined, ...style }}>
            {st === "next" ? (
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 46, fontWeight: 900, color: C.ink }}>{i + 1}</div>
            ) : (
              <>
                <div style={{ ...abs(14, 8), fontSize: 24, fontWeight: 900, color: cur ? C.gold : C.muted }}>{pad2(i + 1)}</div>
                <div style={{ ...abs(14, 46, w - 24), fontSize: fitFontSize(it.name, w - 24, 22, 14, 1) ?? 14, fontWeight: 700, color: cur ? C.text : C.sub, whiteSpace: "nowrap", overflow: "hidden" }}>{it.name}</div>
              </>
            )}
          </div>
        );
      })}
    </>
  );
};

/** 항목 설명 장면 위 제목: 01 find-skills + 출처 줄 */
const ItemHeader: React.FC<{ t: Timeline; index: number; since: number }> = ({ t, index, since }) => {
  const it = t.tracker?.items[index - 1];
  if (!it) return null;
  const p = interpolate(since, [0, 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const size = fitFontSize(`${pad2(index)} ${it.name}`, L.width, 86, 48, 1) ?? 48;
  return (
    <div style={{ ...abs(L.side, L.headerY, L.width), opacity: p, transform: `translateY(${(1 - p) * 20}px)` }}>
      <div style={{ fontSize: size, fontWeight: 900, letterSpacing: -2, whiteSpace: "nowrap" }}>
        <span style={{ color: C.gold }}>{pad2(index)}</span>
        <span style={{ color: C.text, marginLeft: 20 }}>{it.name}</span>
      </div>
      {it.meta ? <div style={{ fontFamily: MONO, fontSize: 28, color: C.muted, marginTop: 6 }}>{it.meta}</div> : null}
    </div>
  );
};

/** 자막: 구절 하나씩. 지금 단어 노란 상자, 읽은 단어 흰색(강조 단어는 노랑), 남은 단어 회색. 정리 화면(노란 바탕)에서는 색을 뒤집는다 */
const Caption: React.FC<{ t: Timeline; light: boolean }> = ({ t, light }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const c = t.captions.find((x) => frame >= x.fromFrame && frame < x.toFrame);
  if (!c) return null;
  const words = c.words && c.words.length ? c.words : [{ text: c.text, fromFrame: c.fromFrame }];
  const states = c.words && c.words.length ? wordStates(words, frame) : words.map(() => "done" as const);
  const size = fitFontSize(c.text, L.width - 40, 66, 44, 2) ?? 44;
  const enter = spring({ frame: frame - c.fromFrame, fps, config: { damping: 15, stiffness: 220 } });
  const ink = light ? C.ink : C.text;
  const next = light ? "rgba(17,17,19,0.38)" : "#5C5C64";
  const emph = light ? "#C0271D" : C.gold;
  return (
    <div style={{ ...abs(L.side, L.captionY - size, L.width), display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "center", columnGap: Math.round(size * 0.24), rowGap: 10, opacity: Math.min(1, enter * 1.4), transform: `translateY(${(1 - enter) * 18}px)` }}>
      {words.map((w, i) => {
        const st = states[i];
        if (st === "current") {
          const pop = spring({ frame: frame - w.fromFrame, fps, config: { damping: 12, stiffness: 260 } });
          return (
            <span key={i} style={{ fontSize: size, fontWeight: 800, color: light ? C.gold : C.ink, background: light ? C.ink : C.gold, borderRadius: 14, padding: `0 ${Math.round(size * 0.2)}px`, lineHeight: 1.3, transform: `scale(${0.9 + 0.1 * pop})`, boxShadow: light ? "none" : goldGlow(0.45) }}>
              {w.text}
            </span>
          );
        }
        const color = st === "next" ? next : "emphasis" in w && w.emphasis ? emph : ink;
        return (
          <span key={i} style={{ fontSize: size, fontWeight: 800, color, lineHeight: 1.3 }}>
            {w.text}
          </span>
        );
      })}
    </div>
  );
};

export const Listicle: React.FC<{ timeline: Timeline; assetBase: string }> = ({ timeline: t, assetBase }) => {
  const frame = useCurrentFrame();
  const scene = sceneAt(t, frame);
  const since = scene ? frame - scene.fromFrame : 0;
  // 항목 제목은 그 항목의 첫 설명 장면에서 한 번만 들어온다
  const sec = scene?.section;
  const showHeader = sec?.kind === "item" && scene?.visual.component !== "LItemCard";
  const firstDetail = showHeader ? t.scenes.find((s) => s.section?.kind === "item" && s.section.index === sec?.index && s.visual.component !== "LItemCard") : undefined;
  const light = scene?.visual.component === "LRecap";
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
      {scene ? <Tracker t={t} scene={scene} since={since} /> : null}
      {showHeader && sec?.index && firstDetail ? <ItemHeader t={t} index={sec.index} since={frame - firstDetail.fromFrame} /> : null}
      {t.audio.map((a) => (
        <Sequence key={a.src} from={a.fromFrame} name={a.src}>
          <Html5Audio src={assetBase + a.src} />
        </Sequence>
      ))}
      <Caption t={t} light={light} />
    </AbsoluteFill>
  );
};
