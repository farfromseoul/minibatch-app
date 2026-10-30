// 목록형 쇼츠(D42) 계산. JSX 없음: Node 테스트가 바로 불러온다.
// 시간에 따라 바뀌는 값은 모두 프레임으로 계산한다 (Math.random·Date.now·CSS 애니메이션 금지, 렌더 재현성).

export type CaptionWord = { text: string; fromFrame: number; emphasis?: boolean };
export type WordState = "done" | "current" | "next";

/** 구절 안 단어마다 읽은·지금·남은 상태. 단어 시각이 없으면 모두 지금(구절 통째 강조 없이 흰 글씨) */
export function wordStates(words: CaptionWord[], frame: number): WordState[] {
  let current = -1;
  for (let i = 0; i < words.length; i++) {
    if (frame >= words[i].fromFrame) current = i;
  }
  return words.map((_, i) => (i < current ? "done" : i === current ? "current" : "next"));
}

/** 0~1 로 자른 진행률: 장면 안 [start, start+len] 구간 */
export function progress(frame: number, start: number, len: number): number {
  if (len <= 0) return frame >= start ? 1 : 0;
  return Math.min(1, Math.max(0, (frame - start) / len));
}

/** 장면 길이의 비율로 정한 구간 진행률. 장면 길이가 달라도 같은 리듬 */
export function phase(frame: number, duration: number, from: number, to: number): number {
  return progress(frame, duration * from, duration * (to - from));
}

/** 타자 효과: 0~1 진행률이면 글자 수만큼 잘라 보여 준다 (한글·영문 같은 속도) */
export function typed(text: string, p: number): string {
  const chars = [...text];
  return chars.slice(0, Math.round(chars.length * Math.min(1, Math.max(0, p)))).join("");
}

/** 번호로 만든 고정 난수 0~1 (같은 입력 같은 값, 렌더 재현성) */
export function seeded(n: number): number {
  let x = (n + 1) * 2654435761;
  x = (x ^ (x >>> 16)) >>> 0;
  x = Math.imul(x, 2246822507) >>> 0;
  x = (x ^ (x >>> 13)) >>> 0;
  return (x % 100000) / 100000;
}

export type TrackerSlot = "done" | "current" | "next";

/** 진행 표시 칸 상태. index 는 지금 항목(1부터). 정리(recap)·끝(outro) 장면이면 모두 done */
export function trackerSlots(count: number, index: number | null): TrackerSlot[] {
  return Array.from({ length: count }, (_, i) => {
    if (index === null) return "done";
    const n = i + 1;
    return n < index ? "done" : n === index ? "current" : "next";
  });
}

/** 두 자리 번호 (01, 02 …) */
export const pad2 = (n: number): string => String(n).padStart(2, "0");

/** 숫자만 있으면 0부터 세어 올라가는 표시값. "3.5만", "10만+" 같은 글자는 그대로 */
export function countUp(value: string, p: number): string {
  const m = /^(\d+)(\.\d+)?$/.exec(value.trim());
  if (!m) return value;
  const target = Number(value);
  const decimals = m[2] ? m[2].length - 1 : 0;
  const eased = 1 - Math.pow(1 - Math.min(1, Math.max(0, p)), 3);
  return (target * eased).toFixed(decimals);
}
