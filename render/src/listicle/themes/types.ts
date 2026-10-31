// 목록형 테마 템플릿 (D42 v1.3, 2026-10-31). 테마 = 톤앤매너 한 벌.
// 공통 장면 12종은 tokens·motion 으로 그리고, 테마는 틀 부품(바탕·진행 표시·항목 제목·자막)을 정하며
// 원하면 첫마디·소개 카드·정리 같은 장면을 자기 레이아웃으로 덮어쓴다(scenes).
import type React from "react";

import type { Timeline } from "../../lib/timeline";

export type Tokens = {
  bg: string;
  surface: string;        // 카드 바탕
  surfaceStrong: string;  // 창·진한 카드 바탕
  line: string;           // 얇은 테두리
  text: string;
  sub: string;
  muted: string;
  accent: string;         // 주 강조색 (체크, 강조 단어)
  accent2: string;        // 보조 강조색
  warn: string;           // 경고·잘못된 예
  onAccent: string;       // 강조색 위 글자
  gradient: string;       // 강조 면 (그라데이션이거나 단색)
  gradientSoft: string;   // 옅은 강조 면
  font: string;
  titleFont: string;
  mono: string;
  titleWeight: number;
  radius: number;         // 카드 모서리
  border: number;         // 카드 테두리 두께
  cardShadow: string;
  activeBorder: string;   // 강조된 카드 테두리 색
  glow: (s?: number) => string; // 빛(없는 테마는 "none")
  accentText: React.CSSProperties; // 강조 글자 모양(그라데이션 글자·단색 등)
};

export type Motion = {
  spring: { damping: number; stiffness: number; mass: number };
  stagger: number; // 차례로 나올 때 간격(프레임)
  float: number;   // 둥실 움직임 크기(px). 0 이면 없음
};

export type FrameProps = { t: Timeline };
export type ProgressProps = { t: Timeline; index: number };
export type HeaderProps = { t: Timeline; index: number; since: number };

export type ThemeSpec = {
  name: string;
  tokens: Tokens;
  motion: Motion;
  Background: React.FC;
  Progress: React.FC<ProgressProps>;
  ItemHeader: React.FC<HeaderProps>;
  Caption: React.FC<FrameProps>;
  /** 장면 덮어쓰기: 컴포넌트 이름 → 이 테마만의 레이아웃 (없으면 공통 장면) */
  scenes?: Partial<Record<string, React.FC<{ durationInFrames: number; props: any }>>>;
};
