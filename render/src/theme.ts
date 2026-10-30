// 화면 색·글꼴. 한국어 글꼴은 이미지의 Noto Sans CJK (render/Dockerfile 의 fonts-noto-cjk).
// 디자인 글꼴(Pretendard 등)은 public/fonts/ 로 넣을 때 여기만 바꾼다.

export type Theme = {
  /** 화면 틀: card(처음 스타일), keynote(전체 화면 남색·빛나는 키워드), letterbox(검정 + 위 제목 + 가운데 16:9 판 + 아래 큰 자막),
   *  listicle(목록형 쇼츠 D42: 검정·노랑 모션 그래픽, 위 진행 표시, 단어 단위 자막) */
  style: "card" | "keynote" | "letterbox" | "listicle";
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
    style: "card",
    background: "#0f1222",
    surface: "#1c2140",
    text: "#f5f7ff",
    muted: "#9aa3c7",
    accent: "#5b8cff",
    accent2: "#ffb547",
    font: "'Noto Sans CJK KR', 'Noto Sans KR', sans-serif",
  },
  // 2026-10-17 시험: 참고 쇼츠 두 가지 느낌
  keynote: {
    style: "keynote",
    background: "#03060D",
    surface: "#0A1428",
    text: "#F2F5FA",
    muted: "#8C9BB5",
    accent: "#5EE7FF",
    accent2: "#F2A65A",
    font: "'Noto Sans CJK KR', 'Noto Sans KR', sans-serif",
  },
  letterbox: {
    style: "letterbox",
    background: "#000000",
    surface: "#0A1428",
    text: "#FFFFFF",
    muted: "#9AA3B5",
    accent: "#5EE7FF",
    accent2: "#FFD54A",
    font: "'Noto Sans CJK KR', 'Noto Sans KR', sans-serif",
  },
  // 2026-10-30 목록형 쇼츠(D42): 참고 영상의 검정 + 노랑 하나. 글꼴은 src/listicle/fonts.ts 가 Pretendard 를 읽는다
  gold: {
    style: "listicle",
    background: "#0B0B0D",
    surface: "#151518",
    text: "#FFFFFF",
    muted: "#77777E",
    accent: "#FFC83D",
    accent2: "#FF5A4E",
    font: "'Pretendard Variable', 'Noto Sans CJK KR', sans-serif",
  },
};

export const themeOf = (key: string): Theme => THEMES[key] ?? THEMES.default;
