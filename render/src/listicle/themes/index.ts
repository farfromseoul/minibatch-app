// 목록형 테마 등록부 (D42 v1.3). 새 테마: themes/<이름>.tsx 를 만들고 여기와 names.ts 에 한 줄씩 더한다.
import { air } from "./air";
import type { ListicleThemeName } from "./names";
import { noir } from "./noir";
import { nova } from "./nova";
import { paper } from "./paper";
import { pop } from "./pop";
import { slate } from "./slate";
import { terminal } from "./terminal";
import type { ThemeSpec } from "./types";

export const LISTICLE_THEMES: Record<ListicleThemeName, ThemeSpec> = { noir, air, slate, nova, paper, terminal, pop };

export const listicleTheme = (name: string): ThemeSpec => (LISTICLE_THEMES as Record<string, ThemeSpec>)[name] ?? nova;
