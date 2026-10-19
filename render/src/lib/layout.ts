// 배치·애니메이션 계산. 시간에 따라 바뀌는 값은 모두 프레임 번호로 계산한다
// (Math.random, Date.now, CSS 애니메이션 금지: 렌더링 재현성, 앱 설계 "Remotion 템플릿 규격").

import type { AnimationPreset } from "./timeline.ts";

/** 쇼츠 화면에서 제목·버튼이 가리는 위·아래 영역 (수치 미확인, 실제 업로드 화면으로 확인) */
export const SAFE = { top: 250, bottom: 400, side: 60 };

/** 자막(최대 두 줄) 자리. 화면 내용은 SAFE.bottom + SUBTITLE_ZONE 위에 둔다
 *  (2026-10-16 첫 전체 영상: 두 줄 자막이 흐름도 맨 아래 상자를 가림) */
export const SUBTITLE_ZONE = 300;
export const CONTENT_BOTTOM = (height: number) => height - SAFE.bottom - SUBTITLE_ZONE;

export type Point = { id: string; x: number; y: number };

/** 화살표 방향으로 층(rank)을 나눠 위→아래로 놓는다. 세로 화면 기본 배치 (앱 설계 FlowDiagram) */
export function flowLayout(ids: string[], edges: [string, string][], size: { width: number; height: number }): Point[] {
  const rank = new Map(ids.map((id) => [id, 0]));
  // 가장 긴 경로로 층을 정한다. 순환이 있어도 노드 수만큼만 돌아 멈춘다
  for (let i = 0; i < ids.length; i++) {
    let changed = false;
    for (const [from, to] of edges) {
      const next = (rank.get(from) ?? 0) + 1;
      if (rank.has(to) && next > (rank.get(to) ?? 0) && next < ids.length) {
        rank.set(to, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const levels = Math.max(...rank.values()) + 1;
  const top = SAFE.top + 120;
  const bottom = CONTENT_BOTTOM(size.height) - 80; // 상자 높이 절반 + 여유
  const stepY = levels > 1 ? (bottom - top) / (levels - 1) : 0;
  const byLevel = new Map<number, string[]>();
  for (const id of ids) {
    const r = rank.get(id) ?? 0;
    byLevel.set(r, [...(byLevel.get(r) ?? []), id]);
  }
  const out: Point[] = [];
  for (const [level, members] of byLevel) {
    const usable = size.width - SAFE.side * 2;
    members.forEach((id, i) => {
      out.push({ id, x: Math.round(SAFE.side + (usable * (i + 1)) / (members.length + 1)), y: Math.round(levels > 1 ? top + stepY * level : (top + bottom) / 2) });
    });
  }
  return ids.map((id) => out.find((p) => p.id === id)!);
}

/** 한 줄 기준 글자 폭 추정 (한글·전각 1em, 그 밖 0.55em). 줄바꿈은 maxLines 까지 허용 */
export function fitFontSize(text: string, maxWidth: number, base: number, min: number, maxLines = 2): number | null {
  const ems = [...text].reduce((sum, ch) => sum + (/[ᄀ-ᇿ　-鿿가-힯＀-￯]/.test(ch) ? 1 : 0.55), 0);
  for (let size = base; size >= min; size -= 2) {
    if (ems * size <= maxWidth * maxLines) return size;
  }
  return null;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOut = (v: number) => 1 - Math.pow(1 - v, 3);

/** 등장 진행률 0~1. 장면 길이의 20%(최대 15프레임) 동안 들어온다. 장면 길이가 달라도 같은 리듬 */
export function entrance(frame: number, duration: number, preset: AnimationPreset): number {
  const span = Math.max(1, Math.min(15, Math.round(duration * 0.2)));
  const v = clamp01(frame / span);
  return preset === "fade" ? v : easeOut(v);
}

/** 순차 공개: 장면 앞 70% 동안 1개 → count 개 */
export function revealCount(frame: number, duration: number, count: number): number {
  if (count <= 1) return count;
  const window = Math.max(1, duration * 0.7);
  return Math.min(count, 1 + Math.floor(clamp01(frame / window) * count));
}

/** 사진 장면의 천천히 확대·이동(켄 번스). 장면 처음 1.0배 → 끝 1.08배, 이동 방향은 장면 순번으로 돌린다 (2026-10-19) */
export function kenBurns(frame: number, duration: number, index: number): { scale: number; x: number; y: number } {
  const t = duration > 0 ? Math.min(1, Math.max(0, frame / duration)) : 0;
  const dirs = [[-1, 0], [1, 0], [0, -1], [0, 1]] as const;
  const [dx, dy] = dirs[((index % dirs.length) + dirs.length) % dirs.length];
  const round = (n: number) => Math.round(n * 1000) / 1000;
  return { scale: round(1 + 0.08 * t), x: round(dx * 30 * t) || 0, y: round(dy * 18 * t) || 0 };
}
