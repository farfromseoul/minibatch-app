// 테마 noir (v1.4, 2026-11-01): 검정 + 흰 글자 + 노랑 하나. 참고 영상의 단순한 구성을 더 정돈한 기본 추천 테마.
import { makeMinimal } from "./minimal";

export const noir = makeMinimal({
  name: "noir", bg: "#0C0C0D", surface: "#161618", line: "rgba(255,255,255,0.12)", text: "#F4F4F1", sub: "#B5B5AF", muted: "#6E6E6A",
  accent: "#FFD43B", accentSoft: "rgba(255,212,59,0.12)", onAccent: "#0C0C0D",
});
