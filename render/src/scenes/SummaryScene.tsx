import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { revealCount, SAFE, SUBTITLE_ZONE } from "../lib/layout";
import type { SceneProps } from "./common";

type Props = { points: string[] };

export const SummaryScene: React.FC<SceneProps<Props>> = ({ durationInFrames, theme, props }) => {
  const frame = useCurrentFrame();
  const shown = revealCount(frame, durationInFrames, props.points.length);
  return (
    <AbsoluteFill style={{ padding: `${SAFE.top + 40}px ${SAFE.side + 20}px ${SAFE.bottom + SUBTITLE_ZONE}px`, justifyContent: "center", gap: 48 }}>
      <div style={{ fontSize: 72, fontWeight: 800, color: theme.accent2 }}>정리</div>
      {props.points.slice(0, shown).map((p, i) => (
        <div key={p} style={{ display: "flex", gap: 28, alignItems: "flex-start" }}>
          <div style={{ minWidth: 72, height: 72, borderRadius: 36, background: theme.accent, color: theme.text, fontSize: 44, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {i + 1}
          </div>
          <div style={{ fontSize: 54, color: theme.text, lineHeight: 1.35, wordBreak: "keep-all" }}>{p}</div>
        </div>
      ))}
    </AbsoluteFill>
  );
};
