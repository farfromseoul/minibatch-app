import React from "react";
import { AbsoluteFill, Html5Audio, Loop, OffthreadVideo, Sequence, useCurrentFrame } from "remotion";

import { Subtitle } from "./layers/Subtitle";
import { fitFontSize, SAFE } from "./lib/layout";
import type { Timeline } from "./lib/timeline";
import { SCENES } from "./scenes";
import { type Area, KEY, KEYNOTE_BG, KEYNOTE_SCENES } from "./scenes/keynote";
import { type Theme, themeOf } from "./theme";

// 쇼츠 한 편. timeline.json 하나와 음성 파일 주소(assetBase)만으로 그린다.
// 시각은 timeline 단계가 정한 정수 프레임을 그대로 쓴다 (다시 계산하지 않는다, 앱 설계 "타임라인 계산").
// 화면 틀은 theme 의 style 로 고른다: card(처음), keynote, letterbox (2026-10-17)
export type ShortProps = { timeline: Timeline; assetBase: string };

/** 키노트 전체 화면에서 장면이 쓰는 영역 (자막 상자 위까지) */
const KEYNOTE_AREA: Area = { x: SAFE.side, y: SAFE.top + 30, w: 1080 - SAFE.side * 2, h: 1920 - SAFE.top - SAFE.bottom - 230 };
/** 레터박스 가운데 16:9 판 */
const PANEL = { top: 640, height: 608 };
const PANEL_AREA: Area = { x: 50, y: PANEL.top + 40, w: 980, h: PANEL.height - 80 };

const Audio: React.FC<{ timeline: Timeline; assetBase: string }> = ({ timeline, assetBase }) => (
  <>
    {timeline.audio.map((a) => (
      <Sequence key={a.src} from={a.fromFrame} name={a.src}>
        <Html5Audio src={assetBase + a.src} />
      </Sequence>
    ))}
  </>
);

const KeynoteScenes: React.FC<{ timeline: Timeline; theme: Theme; area: Area }> = ({ timeline, theme, area }) => (
  <>
    {timeline.scenes.map((s) => {
      const Scene = KEYNOTE_SCENES[s.visual.component];
      return (
        <Sequence key={s.id} from={s.fromFrame} durationInFrames={s.durationInFrames} name={s.id}>
          <Scene durationInFrames={s.durationInFrames} animationPreset={s.animationPreset} theme={theme} props={s.visual.props} area={area} />
        </Sequence>
      );
    })}
  </>
);

/** 레터박스 가운데 판: 스톡 영상이 있는 장면은 영상(소리 없음, 짧으면 반복), 없으면 키노트 도식 */
const PanelScenes: React.FC<{ timeline: Timeline; theme: Theme; assetBase: string }> = ({ timeline, theme, assetBase }) => (
  <>
    {timeline.scenes.map((s) => {
      const Scene = KEYNOTE_SCENES[s.visual.component];
      return (
        <Sequence key={s.id} from={s.fromFrame} durationInFrames={s.durationInFrames} name={s.id}>
          {s.media ? (
            <div style={{ position: "absolute", left: 0, top: PANEL.top, width: 1080, height: PANEL.height, overflow: "hidden" }}>
              <Loop durationInFrames={s.media.durationInFrames}>
                <OffthreadVideo src={assetBase + s.media.src} muted style={{ width: 1080, height: PANEL.height, objectFit: "cover" }} />
              </Loop>
            </div>
          ) : (
            <Scene durationInFrames={s.durationInFrames} animationPreset={s.animationPreset} theme={theme} props={s.visual.props} area={PANEL_AREA} />
          )}
        </Sequence>
      );
    })}
  </>
);

const useCaption = (timeline: Timeline) => {
  const frame = useCurrentFrame();
  return timeline.captions.find((c) => frame >= c.fromFrame && frame < c.toFrame);
};

/** 키노트 자막: 가운데 아래 반투명 상자, 작게 */
const KeynoteCaption: React.FC<{ timeline: Timeline }> = ({ timeline }) => {
  const c = useCaption(timeline);
  if (!c) return null;
  const size = fitFontSize(c.text, 900, 46, 32) ?? 32;
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: SAFE.bottom + 40 }}>
      <div style={{ maxWidth: 940, padding: "10px 22px", background: "rgba(0, 0, 0, 0.62)", color: KEY.text, fontSize: size, fontWeight: 500, textAlign: "center", lineHeight: 1.4, wordBreak: "keep-all" }}>
        {c.text}
      </div>
    </AbsoluteFill>
  );
};

/** 레터박스 자막: 가운데 판 아래, 아주 크고 굵은 흰 글씨 */
const LetterboxCaption: React.FC<{ timeline: Timeline; theme: Theme }> = ({ timeline, theme }) => {
  const c = useCaption(timeline);
  if (!c) return null;
  const size = fitFontSize(c.text, 980, 74, 48) ?? 48;
  return (
    <div style={{ position: "absolute", left: 50, width: 980, top: PANEL.top + PANEL.height + 70, textAlign: "center", color: theme.text, fontSize: size, fontWeight: 800, lineHeight: 1.3, wordBreak: "keep-all", textShadow: "0 4px 18px rgba(0,0,0,0.6)" }}>
      {c.text}
    </div>
  );
};

const headerTitle = (t: Timeline): string => {
  if (t.header?.title) return t.header.title;
  const s = t.scenes.find((x) => x.visual.component === "TitleReveal");
  return s ? String((s.visual.props as { title?: string }).title ?? "") : "";
};

export const Short: React.FC<ShortProps> = ({ timeline, assetBase }) => {
  const theme = themeOf(timeline.theme);

  if (theme.style === "keynote") {
    return (
      <AbsoluteFill style={{ background: KEYNOTE_BG, fontFamily: theme.font }}>
        <KeynoteScenes timeline={timeline} theme={theme} area={KEYNOTE_AREA} />
        <Audio timeline={timeline} assetBase={assetBase} />
        <KeynoteCaption timeline={timeline} />
      </AbsoluteFill>
    );
  }

  if (theme.style === "letterbox") {
    const title = headerTitle(timeline);
    const titleSize = fitFontSize(title, 960, 84, 52) ?? 52;
    return (
      <AbsoluteFill style={{ background: theme.background, fontFamily: theme.font }}>
        <div style={{ position: "absolute", top: SAFE.top - 150, width: 1080, textAlign: "center", color: theme.text, fontSize: 34, fontWeight: 700, letterSpacing: 1 }}>
          {timeline.header?.brand ?? "MiniBatch"}
        </div>
        <div style={{ position: "absolute", top: SAFE.top + 90, left: 60, width: 960, textAlign: "center", color: theme.text, fontSize: titleSize, fontWeight: 800, lineHeight: 1.2, wordBreak: "keep-all" }}>
          {title}
        </div>
        <div style={{ position: "absolute", left: 0, top: PANEL.top, width: 1080, height: PANEL.height, background: KEYNOTE_BG }} />
        <PanelScenes timeline={timeline} theme={theme} assetBase={assetBase} />
        <Audio timeline={timeline} assetBase={assetBase} />
        <LetterboxCaption timeline={timeline} theme={theme} />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ background: theme.background, fontFamily: theme.font }}>
      {timeline.scenes.map((s) => {
        const Scene = SCENES[s.visual.component];
        return (
          <Sequence key={s.id} from={s.fromFrame} durationInFrames={s.durationInFrames} name={s.id}>
            <Scene durationInFrames={s.durationInFrames} animationPreset={s.animationPreset} theme={theme} props={s.visual.props} />
          </Sequence>
        );
      })}
      <Audio timeline={timeline} assetBase={assetBase} />
      <Subtitle captions={timeline.captions} theme={theme} />
    </AbsoluteFill>
  );
};
