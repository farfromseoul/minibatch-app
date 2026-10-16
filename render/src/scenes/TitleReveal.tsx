import React from "react";
import { AbsoluteFill } from "remotion";

import { fitFontSize, SAFE } from "../lib/layout";
import { Enter, type SceneProps } from "./common";

type Props = { title: string; subtitle?: string };

export const TitleReveal: React.FC<SceneProps<Props>> = ({ durationInFrames, animationPreset, theme, props }) => {
  const maxWidth = 1080 - SAFE.side * 2;
  const titleSize = fitFontSize(props.title, maxWidth, 150, 64) ?? 64;
  const subSize = props.subtitle ? fitFontSize(props.subtitle, maxWidth, 64, 36) ?? 36 : 0;
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: `${SAFE.top}px ${SAFE.side}px ${SAFE.bottom}px` }}>
      <Enter duration={durationInFrames} preset={animationPreset} style={{ textAlign: "center" }}>
        <div style={{ fontSize: titleSize, fontWeight: 800, color: theme.text, lineHeight: 1.15, wordBreak: "keep-all" }}>{props.title}</div>
        {props.subtitle ? (
          <div style={{ marginTop: 32, fontSize: subSize, color: theme.accent2, fontWeight: 600, wordBreak: "keep-all" }}>{props.subtitle}</div>
        ) : null}
      </Enter>
    </AbsoluteFill>
  );
};
