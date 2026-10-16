import React from "react";
import { useCurrentFrame } from "remotion";

import { entrance } from "../lib/layout";
import type { AnimationPreset } from "../lib/timeline";
import type { Theme } from "../theme";

// 모든 템플릿이 받는 바깥 속성 (앱 설계 "Remotion 템플릿 규격")
export type SceneProps<P> = {
  durationInFrames: number;
  animationPreset: AnimationPreset;
  theme: Theme;
  props: P;
};

/** 등장 애니메이션을 감싼다. pop 은 커지며, 나머지는 아래에서 올라오며 나타난다 */
export const Enter: React.FC<{ duration: number; preset: AnimationPreset; children: React.ReactNode; style?: React.CSSProperties }> = ({
  duration,
  preset,
  children,
  style,
}) => {
  const frame = useCurrentFrame();
  const p = entrance(frame, duration, preset);
  const transform = preset === "pop" ? `scale(${0.8 + 0.2 * p})` : `translateY(${(1 - p) * 40}px)`;
  return <div style={{ opacity: p, transform, ...style }}>{children}</div>;
};
