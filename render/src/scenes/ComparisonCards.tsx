import React from "react";
import { AbsoluteFill } from "remotion";

import { SAFE, SUBTITLE_ZONE } from "../lib/layout";
import { Enter, type SceneProps } from "./common";

type Side = { title: string; points: string[] };
type Props = { left: Side; right: Side };

export const ComparisonCards: React.FC<SceneProps<Props>> = ({ durationInFrames, animationPreset, theme, props }) => {
  const card = (side: Side, color: string) => (
    <div style={{ background: theme.surface, borderTop: `10px solid ${color}`, borderRadius: 24, padding: 40, width: "100%" }}>
      <div style={{ fontSize: 64, fontWeight: 800, color, marginBottom: 24 }}>{side.title}</div>
      {side.points.map((p) => (
        <div key={p} style={{ fontSize: 44, color: theme.text, lineHeight: 1.4, wordBreak: "keep-all" }}>
          • {p}
        </div>
      ))}
    </div>
  );
  return (
    <AbsoluteFill style={{ padding: `${SAFE.top + 40}px ${SAFE.side}px ${SAFE.bottom + SUBTITLE_ZONE}px`, gap: 40, justifyContent: "center" }}>
      <Enter duration={durationInFrames} preset={animationPreset}>{card(props.left, theme.accent)}</Enter>
      <Enter duration={durationInFrames} preset={animationPreset}>{card(props.right, theme.accent2)}</Enter>
    </AbsoluteFill>
  );
};
