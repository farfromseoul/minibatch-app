// 등록된 목록형 테마 이름 (JSX 없음: timeline 검사·Node 테스트가 읽는다).
// 새 테마: themes/<이름>.tsx 를 만들고 여기와 themes/index.ts, src/theme.ts, job-api content/categories/listicle.yaml 에 한 줄씩 더한다.
export const LISTICLE_THEME_NAMES = ["nova", "paper", "terminal", "pop"] as const;
export type ListicleThemeName = (typeof LISTICLE_THEME_NAMES)[number];
