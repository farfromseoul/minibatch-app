import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { flowLayout, revealCount } from "../lib/layout";
import type { SceneProps } from "./common";

type Props = { nodes: { id: string; label: string }[]; edges: [string, string][]; revealOrder?: string[] };

const BOX = { w: 300, h: 120 };

export const FlowDiagram: React.FC<SceneProps<Props>> = ({ durationInFrames, animationPreset, theme, props }) => {
  const frame = useCurrentFrame();
  const ids = props.nodes.map((n) => n.id);
  const pos = Object.fromEntries(flowLayout(ids, props.edges, { width: 1080, height: 1920 }).map((p) => [p.id, p]));
  const order = props.revealOrder && props.revealOrder.length ? props.revealOrder : ids;
  // sequential 이 아니면 처음부터 모두 보인다
  const shown = new Set(animationPreset === "sequential" ? order.slice(0, revealCount(frame, durationInFrames, order.length)) : ids);
  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{ position: "absolute" }}>
        <defs>
          <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
            <path d="M0,0 L12,6 L0,12 z" fill={theme.muted} />
          </marker>
        </defs>
        {props.edges
          .filter(([a, b]) => shown.has(a) && shown.has(b))
          .map(([a, b]) => (
            <line
              key={`${a}-${b}`}
              x1={pos[a].x}
              y1={pos[a].y + BOX.h / 2}
              x2={pos[b].x}
              y2={pos[b].y - BOX.h / 2 - 8}
              stroke={theme.muted}
              strokeWidth={6}
              markerEnd="url(#arrow)"
            />
          ))}
      </svg>
      {props.nodes
        .filter((n) => shown.has(n.id))
        .map((n) => (
          <div
            key={n.id}
            style={{
              position: "absolute",
              left: pos[n.id].x - BOX.w / 2,
              top: pos[n.id].y - BOX.h / 2,
              width: BOX.w,
              height: BOX.h,
              borderRadius: 24,
              background: theme.surface,
              border: `4px solid ${theme.accent}`,
              color: theme.text,
              fontSize: 52,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {n.label}
          </div>
        ))}
    </AbsoluteFill>
  );
};
