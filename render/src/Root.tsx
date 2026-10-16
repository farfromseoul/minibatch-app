import React from "react";
import { Composition } from "remotion";

import type { Timeline } from "./lib/timeline";
import { Short, type ShortProps } from "./Short";

// Remotion Studio 미리 보기용 기본값. 실제 렌더는 render-server 가 timeline.json 을 inputProps 로 넣는다.
const preview: Timeline = {
  schemaVersion: 1,
  fps: 30,
  width: 1080,
  height: 1920,
  durationInFrames: 90,
  theme: "default",
  scenes: [
    {
      id: "s01",
      fromFrame: 0,
      durationInFrames: 90,
      visual: { type: "template", component: "TitleReveal", props: { title: "RAG", subtitle: "검색 증강 생성" } },
      animationPreset: "pop",
    },
  ],
  audio: [],
  captions: [{ text: "LLM이 모르는 걸 물어보면?", fromFrame: 6, toFrame: 80 }],
  bgm: null,
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Short"
      component={Short}
      durationInFrames={preview.durationInFrames}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{ timeline: preview, assetBase: "" } satisfies ShortProps}
      // 길이·크기는 넘겨받은 timeline 에서 정한다
      calculateMetadata={({ props }) => ({
        durationInFrames: props.timeline.durationInFrames,
        fps: props.timeline.fps,
        width: props.timeline.width,
        height: props.timeline.height,
      })}
    />
  );
};
