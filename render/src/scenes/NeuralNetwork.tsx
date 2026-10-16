import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { CONTENT_BOTTOM, revealCount, SAFE } from "../lib/layout";
import type { SceneProps } from "./common";

type Props = { layers: number[]; highlight?: { layer: number; node: number }; labels?: string[] };

export const NeuralNetwork: React.FC<SceneProps<Props>> = ({ durationInFrames, theme, props }) => {
  const frame = useCurrentFrame();
  const visibleLayers = revealCount(frame, durationInFrames, props.layers.length); // 층이 하나씩 켜진다
  const top = SAFE.top + 160;
  const bottom = CONTENT_BOTTOM(1920) - 50;
  const layerY = (i: number) => top + ((bottom - top) * i) / Math.max(1, props.layers.length - 1);
  const nodeX = (count: number, j: number) => SAFE.side + ((1080 - SAFE.side * 2) * (j + 1)) / (count + 1);
  const r = 34;
  return (
    <AbsoluteFill>
      <svg width={1080} height={1920}>
        {props.layers.slice(0, visibleLayers - 1).map((count, i) =>
          Array.from({ length: count }, (_, a) =>
            Array.from({ length: props.layers[i + 1] }, (_, b) => (
              <line
                key={`${i}-${a}-${b}`}
                x1={nodeX(count, a)}
                y1={layerY(i)}
                x2={nodeX(props.layers[i + 1], b)}
                y2={layerY(i + 1)}
                stroke={theme.muted}
                strokeOpacity={0.5}
                strokeWidth={3}
              />
            )),
          ),
        )}
        {props.layers.slice(0, visibleLayers).map((count, i) =>
          Array.from({ length: count }, (_, j) => {
            const hot = props.highlight && props.highlight.layer === i && props.highlight.node === j;
            return <circle key={`${i}-${j}`} cx={nodeX(count, j)} cy={layerY(i)} r={r} fill={hot ? theme.accent2 : theme.accent} />;
          }),
        )}
      </svg>
      {(props.labels ?? []).slice(0, visibleLayers).map((label, i) => (
        <div key={label + i} style={{ position: "absolute", left: SAFE.side, top: layerY(i) - 90, fontSize: 40, color: theme.muted }}>
          {label}
        </div>
      ))}
    </AbsoluteFill>
  );
};
