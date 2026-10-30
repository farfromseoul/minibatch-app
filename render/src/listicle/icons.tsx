// 아이콘 16종. 24×24 격자에 직접 그린 선 아이콘 (외부 아이콘 묶음 없이, 이름은 lib/timeline.ts 의 ICONS 와 같다)
import React from "react";

const PATHS: Record<string, React.ReactNode> = {
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M15.5 15.5 21 21" />
    </>
  ),
  memory: (
    <>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" />
      <path d="M4.5 5.5v6.5c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8V5.5" />
      <path d="M4.5 12v6.5c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8V12" />
    </>
  ),
  shield: (
    <>
      <path d="M12 2.8 4.5 5.8v5.6c0 4.6 3.1 8.4 7.5 9.8 4.4-1.4 7.5-5.2 7.5-9.8V5.8z" />
      <path d="m8.8 12 2.2 2.2 4.4-4.6" />
    </>
  ),
  bolt: <path d="M13.2 2.5 4.8 13.4h6.4l-1.4 8.1 8.4-10.9h-6.4z" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.8" />
      <path d="M12 7.2V12l3.3 2" />
    </>
  ),
  code: (
    <>
      <path d="m8.5 7-5 5 5 5" />
      <path d="m15.5 7 5 5-5 5" />
      <path d="m13.4 4.5-2.8 15" />
    </>
  ),
  chat: (
    <>
      <path d="M20.5 12c0 4-3.8 7.2-8.5 7.2-1.2 0-2.3-.2-3.3-.5L4 20l1.2-3.6C4.1 15.1 3.5 13.6 3.5 12c0-4 3.8-7.2 8.5-7.2s8.5 3.2 8.5 7.2z" />
      <path d="M8.4 12h.01M12 12h.01M15.6 12h.01" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="8.8" />
      <path d="m7.8 12.3 2.8 2.8 5.6-5.8" />
    </>
  ),
  warning: (
    <>
      <path d="M12 3.6 2.6 19.8h18.8z" />
      <path d="M12 9.6v4.6M12 17h.01" />
    </>
  ),
  lock: (
    <>
      <rect x="4.8" y="10.5" width="14.4" height="10" rx="2" />
      <path d="M8 10.5V7.6a4 4 0 0 1 8 0v2.9" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8.8" />
      <path d="M3.2 12h17.6M12 3.2c2.4 2.4 3.6 5.4 3.6 8.8s-1.2 6.4-3.6 8.8c-2.4-2.4-3.6-5.4-3.6-8.8s1.2-6.4 3.6-8.8z" />
    </>
  ),
  terminal: (
    <>
      <rect x="2.8" y="4.2" width="18.4" height="15.6" rx="2.2" />
      <path d="m6.6 9.2 3 2.8-3 2.8M12 15h5.2" />
    </>
  ),
  chart: (
    <>
      <path d="M3.5 20.5h17" />
      <path d="M6.5 16.5v-4M11 16.5V8.5M15.5 16.5v-6M20 16.5V5" />
    </>
  ),
  sparkles: (
    <>
      <path d="M11 3.5 12.8 8.7 18 10.5l-5.2 1.8L11 17.5l-1.8-5.2L4 10.5l5.2-1.8z" />
      <path d="M18.5 15.5 19.3 17.7 21.5 18.5l-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
    </>
  ),
  book: (
    <>
      <path d="M12 6.5c-1.8-1.6-4.6-2.2-8-2v13.8c3.4-.2 6.2.4 8 2 1.8-1.6 4.6-2.2 8-2V4.5c-3.4-.2-6.2.4-8 2z" />
      <path d="M12 6.5v13.8" />
    </>
  ),
  gear: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 2.8v2.6M12 18.6v2.6M21.2 12h-2.6M5.4 12H2.8M18.5 5.5l-1.8 1.8M7.3 16.7l-1.8 1.8M18.5 18.5l-1.8-1.8M7.3 7.3 5.5 5.5" />
    </>
  ),
};

export const Icon: React.FC<{ name: string; size: number; color: string; stroke?: number; style?: React.CSSProperties }> = ({ name, size, color, stroke = 2, style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style}>
    {PATHS[name] ?? PATHS.sparkles}
  </svg>
);

/** 참고 영상 제목 앞의 별꽃 표시 (✳) */
export const Asterisk: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={3} strokeLinecap="round">
    <path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4" />
  </svg>
);
