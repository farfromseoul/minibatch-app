// 테마 slate (v1.4, 2026-11-01): 짙은 회색 + 밝은 글자 + 라임 하나. 차분한 개발 도구 느낌, 명령어·설정 실습에.
import { makeMinimal } from "./minimal";

export const slate = makeMinimal({
  name: "slate", bg: "#15171C", surface: "#1D2027", line: "rgba(236,238,242,0.12)", text: "#ECEEF2", sub: "#A8AEBB", muted: "#6B7280",
  accent: "#C5F536", accentSoft: "rgba(197,245,54,0.12)", onAccent: "#15171C",
});
