// 테마 air (v1.4, 2026-11-01): 밝은 흰 바탕 + 검정 글자 + 파랑 하나. 깨끗한 문서 느낌, 개념·방법 정리에.
import { makeMinimal } from "./minimal";

export const air = makeMinimal({
  name: "air", bg: "#F6F6F3", surface: "#FFFFFF", line: "rgba(17,18,22,0.12)", text: "#111216", sub: "#4A4D57", muted: "#9A9DA6",
  accent: "#2F5BFF", accentSoft: "rgba(47,91,255,0.10)", onAccent: "#FFFFFF",
});
