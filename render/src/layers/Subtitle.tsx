import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { fitFontSize, SAFE } from "../lib/layout";
import type { Timeline } from "../lib/timeline";
import type { Theme } from "../theme";

// 자막은 화면 아래 안전 영역 바로 위에 고정한다 (앱 설계 "Remotion 템플릿 규격")
export const Subtitle: React.FC<{ captions: Timeline["captions"]; theme: Theme }> = ({ captions, theme }) => {
  const frame = useCurrentFrame();
  const current = captions.find((c) => frame >= c.fromFrame && frame < c.toFrame);
  if (!current) return null;
  const size = fitFontSize(current.text, 1080 - SAFE.side * 2 - 64, 58, 36) ?? 36;
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: SAFE.bottom + 20 }}>
      <div
        style={{
          maxWidth: 1080 - SAFE.side * 2,
          padding: "18px 32px",
          borderRadius: 18,
          background: "rgba(0, 0, 0, 0.6)",
          color: theme.text,
          fontSize: size,
          fontWeight: 700,
          textAlign: "center",
          lineHeight: 1.35,
          wordBreak: "keep-all",
        }}
      >
        {current.text}
      </div>
    </AbsoluteFill>
  );
};
