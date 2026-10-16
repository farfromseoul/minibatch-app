import React from "react";
import { AbsoluteFill, Html5Audio, Sequence } from "remotion";

import { Subtitle } from "./layers/Subtitle";
import type { Timeline } from "./lib/timeline";
import { SCENES } from "./scenes";
import { themeOf } from "./theme";

// 쇼츠 한 편. timeline.json 하나와 음성 파일 주소(assetBase)만으로 그린다.
// 시각은 timeline 단계가 정한 정수 프레임을 그대로 쓴다 (다시 계산하지 않는다, 앱 설계 "타임라인 계산").
export type ShortProps = { timeline: Timeline; assetBase: string };

export const Short: React.FC<ShortProps> = ({ timeline, assetBase }) => {
  const theme = themeOf(timeline.theme);
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
      {timeline.audio.map((a) => (
        <Sequence key={a.src} from={a.fromFrame} name={a.src}>
          <Html5Audio src={assetBase + a.src} />
        </Sequence>
      ))}
      <Subtitle captions={timeline.captions} theme={theme} />
    </AbsoluteFill>
  );
};
