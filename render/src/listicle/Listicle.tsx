// 목록형 쇼츠(D42) 화면 틀: 테마(timeline.theme)를 골라 바탕 → 장면 → 진행 표시·항목 제목 → 자막 순으로 그린다.
// 2026-10-31 v1.3: 색·모양·틀 부품은 테마 템플릿(themes/), 장면은 테마가 덮어쓴 것 또는 공통 장면.
// 시각은 timeline 단계가 정한 정수 프레임을 그대로 쓴다 (앱 설계 "타임라인 계산").
import React from "react";
import { AbsoluteFill, Html5Audio, Sequence, useCurrentFrame } from "remotion";

import type { Timeline, TimelineScene } from "../lib/timeline";
import { loadFonts } from "./fonts";
import { LISTICLE_SCENES } from "./scenes";
import { ThemeContext } from "./themes/context";
import { listicleTheme } from "./themes";

loadFonts();

const sceneAt = (t: Timeline, frame: number): TimelineScene | undefined =>
  t.scenes.find((s) => frame >= s.fromFrame && frame < s.fromFrame + s.durationInFrames) ?? t.scenes[t.scenes.length - 1];

export const Listicle: React.FC<{ timeline: Timeline; assetBase: string }> = ({ timeline: t, assetBase }) => {
  const frame = useCurrentFrame();
  const theme = listicleTheme(t.theme);
  const { Background, Progress, ItemHeader, Caption } = theme;
  const scene = sceneAt(t, frame);
  const sec = scene?.section;
  const index = sec?.kind === "item" ? sec.index ?? null : null;
  // 항목 제목은 그 항목의 첫 설명 장면에서 한 번만 들어온다 (소개 카드 장면에서는 카드가 제목)
  const showHeader = index !== null && scene?.visual.component !== "LItemCard";
  const firstDetail = showHeader ? t.scenes.find((s) => s.section?.kind === "item" && s.section.index === index && s.visual.component !== "LItemCard") : undefined;
  return (
    <ThemeContext.Provider value={theme}>
      <AbsoluteFill style={{ fontFamily: theme.tokens.font, color: theme.tokens.text }}>
        <Background />
        {t.scenes.map((s) => {
          const Scene = theme.scenes?.[s.visual.component] ?? LISTICLE_SCENES[s.visual.component];
          return (
            <Sequence key={s.id} from={s.fromFrame} durationInFrames={s.durationInFrames} name={s.id}>
              <Scene durationInFrames={s.durationInFrames} props={s.visual.props} />
            </Sequence>
          );
        })}
        {index !== null && (t.tracker?.items.length ?? 0) > 0 ? <Progress t={t} index={index} /> : null}
        {showHeader && index !== null && firstDetail ? <ItemHeader t={t} index={index} since={frame - firstDetail.fromFrame} /> : null}
        {t.audio.map((a) => (
          <Sequence key={a.src} from={a.fromFrame} name={a.src}>
            <Html5Audio src={assetBase + a.src} />
          </Sequence>
        ))}
        <Caption t={t} />
      </AbsoluteFill>
    </ThemeContext.Provider>
  );
};
