// 화면 색·글꼴. 한국어 글꼴은 이미지의 Noto Sans CJK (render/Dockerfile 의 fonts-noto-cjk).
// 디자인 글꼴(Pretendard 등)은 public/fonts/ 로 넣을 때 여기만 바꾼다.

export type Theme = {
  background: string;
  surface: string;
  text: string;
  muted: string;
  accent: string;
  accent2: string;
  font: string;
};

export const THEMES: Record<string, Theme> = {
  default: {
    background: "#0f1222",
    surface: "#1c2140",
    text: "#f5f7ff",
    muted: "#9aa3c7",
    accent: "#5b8cff",
    accent2: "#ffb547",
    font: "'Noto Sans CJK KR', 'Noto Sans KR', sans-serif",
  },
};

export const themeOf = (key: string): Theme => THEMES[key] ?? THEMES.default;
