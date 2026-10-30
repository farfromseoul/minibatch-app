// timeline.json 의 모양과 검증 (앱 설계 "timeline.json", "Remotion 템플릿 규격").
// render-worker 는 이 파일만 읽는다. 렌더링 전에 여기서 거르면 몇 분짜리 렌더가 중간에 깨지지 않는다.
// 이 파일은 JSX 를 쓰지 않는다: Node 테스트(node --test)가 바로 불러온다.

export type AnimationPreset = "pop" | "fade" | "sequential" | "draw";

export type TemplateVisual = { type: "template"; component: string; props: Record<string, unknown> };

/** 목록형(D42) 장면이 어느 부분인지. index 는 항목 번호(1부터) */
export type Section = { kind: "hook" | "item" | "recap" | "outro"; index?: number };

export type TimelineScene = {
  id: string;
  section?: Section;
  fromFrame: number;
  durationInFrames: number;
  visual: TemplateVisual;
  animationPreset: AnimationPreset;
  /** 레터박스 가운데 판에 깔 스톡 소재 (작업 폴더 기준 경로). 영상은 길이 프레임, 사진은 장면 내내 천천히 확대. 없으면 도식 */
  media?: { type: "video"; src: string; durationInFrames: number } | { type: "image"; src: string };
};

export type Timeline = {
  schemaVersion: 1;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  theme: string;
  /** 화면 위 고정 글자 (letterbox 스타일). 없으면 첫 TitleReveal 제목 */
  header?: { brand?: string; title?: string };
  scenes: TimelineScene[];
  audio: { src: string; fromFrame: number }[];
  /** 목록형(D42): words 가 있으면 몇 단어씩 보이며 지금 단어를 강조한다 */
  captions: { text: string; fromFrame: number; toFrame: number; words?: { text: string; fromFrame: number; emphasis?: boolean }[] }[];
  bgm: null;
  /** 목록형(D42) 위쪽 진행 표시 */
  tracker?: { items: { name: string; meta?: string }[] };
};

export const LISTICLE_TEMPLATES = ["LHookClaim", "LHookReveal", "LItemCard", "LChat", "LSteps", "LBeforeAfter", "LTerminal",
  "LStat", "LIcon", "LCompare", "LRecap", "LOutro"] as const;
export const TEMPLATES = ["TitleReveal", "FlowDiagram", "ComparisonCards", "NeuralNetwork", "SummaryScene", ...LISTICLE_TEMPLATES] as const;
export const ICONS = ["search", "memory", "shield", "bolt", "clock", "code", "chat", "check", "warning", "lock", "globe", "terminal",
  "chart", "sparkles", "book", "gear"] as const;
const SECTION_KINDS = ["hook", "item", "recap", "outro"];
/** 목록형 장면은 목록형 테마에서만 그린다 (다른 스타일의 장면 등록부에는 없다) */
export const LISTICLE_THEMES = ["gold"];
export const PRESETS: AnimationPreset[] = ["pop", "fade", "sequential", "draw"];
export const MAX_FLOW_NODES = 6;

const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);
const isStr = (v: unknown): v is string => typeof v === "string" && v.trim().length > 0;
const isObj = (v: unknown): v is Record<string, any> => typeof v === "object" && v !== null && !Array.isArray(v);

/** 작업 폴더 안의 상대 경로인지 (절대 경로, ../, URL 금지) */
export function isSafeRelative(src: unknown): boolean {
  if (!isStr(src) || src.startsWith("/") || src.includes("\\") || /^[a-z]+:/i.test(src)) return false;
  return src.split("/").every((part) => part !== ".." && part !== "");
}

const strList = (v: unknown, min: number, max: number): boolean =>
  Array.isArray(v) && v.length >= min && v.length <= max && v.every(isStr);
const optStr = (v: unknown): boolean => v === undefined || isStr(v);

function checkProps(component: string, p: Record<string, any>, where: string): string[] {
  const e: string[] = [];
  const need = (ok: boolean, what: string) => {
    if (!ok) e.push(`${where}: ${component} ${what}`);
  };
  switch (component) {
    case "LHookClaim":
      need(isStr(p.kicker) && isStr(p.claim) && optStr(p.claimNote) && optStr(p.aside), "는 {kicker, claim, claimNote?, aside?}");
      break;
    case "LHookReveal":
      need(isStr(p.kicker) && isStr(p.headline) && optStr(p.highlight) && isInt(p.count) && p.count >= 2 && p.count <= 7,
        "는 {kicker, headline, highlight?, count 2~7}");
      break;
    case "LItemCard":
      need(isInt(p.number) && p.number >= 1 && isStr(p.name) && optStr(p.meta) && optStr(p.tagline) && optStr(p.badge),
        "는 {number, name, meta?, tagline?, badge?}");
      break;
    case "LChat":
      need(isStr(p.prompt) && strList(p.results, 1, 4) && optStr(p.status), "는 {prompt, results[1~4], status?}");
      break;
    case "LSteps":
      need(strList(p.steps, 2, 4) && (p.checks === undefined || strList(p.checks, 0, 4)), "는 {steps[2~4], checks?[0~4]}");
      break;
    case "LBeforeAfter":
      need(["before", "after"].every((k) => isObj(p[k]) && isStr(p[k].label) && optStr(p[k].note)),
        "는 {before: {label, note?}, after: {label, note?}}");
      break;
    case "LTerminal":
      need(isStr(p.command) && strList(p.output, 1, 4), "는 {command, output[1~4]}");
      break;
    case "LStat":
      need(isStr(p.value) && optStr(p.unit) && isStr(p.label), "는 {value, unit?, label}");
      break;
    case "LIcon":
      need((ICONS as readonly string[]).includes(p.icon) && isStr(p.title) && (p.lines === undefined || strList(p.lines, 0, 3)),
        `는 {icon(${ICONS.join("|")}), title, lines?[0~3]}`);
      break;
    case "LCompare":
      need(["left", "right"].every((k) => isObj(p[k]) && isStr(p[k].title) && strList(p[k].points, 1, 3))
        && (p.winner === undefined || p.winner === "left" || p.winner === "right"),
        "는 {left: {title, points[1~3]}, right: {…}, winner?: left|right}");
      break;
    case "LRecap":
      need(isStr(p.title) && optStr(p.subtitle) && Array.isArray(p.items) && p.items.length >= 1 && p.items.length <= 7
        && p.items.every((it: any) => isObj(it) && isStr(it.name) && optStr(it.note) && optStr(it.tag)),
        "는 {title, subtitle?, items[1~7]: {name, note?, tag?}}");
      break;
    case "LOutro":
      need(isStr(p.title) && optStr(p.subtitle), "는 {title, subtitle?}");
      break;
    case "TitleReveal":
      if (!isStr(p.title)) e.push(`${where}: title 필요`);
      break;
    case "FlowDiagram": {
      const nodes = Array.isArray(p.nodes) ? p.nodes : [];
      if (nodes.length < 2 || nodes.length > MAX_FLOW_NODES) e.push(`${where}: nodes 는 2~${MAX_FLOW_NODES}개`);
      const ids = new Set(nodes.map((n: any) => n?.id));
      if (nodes.some((n: any) => !isStr(n?.id) || !isStr(n?.label))) e.push(`${where}: 노드마다 id·label 필요`);
      for (const edge of Array.isArray(p.edges) ? p.edges : []) {
        for (const id of Array.isArray(edge) ? edge : [edge]) {
          if (!ids.has(id)) e.push(`${where}: edges 가 없는 노드 ${id} 를 가리킨다`);
        }
      }
      for (const id of Array.isArray(p.revealOrder) ? p.revealOrder : []) {
        if (!ids.has(id)) e.push(`${where}: revealOrder 에 없는 노드 ${id}`);
      }
      break;
    }
    case "ComparisonCards":
      for (const side of ["left", "right"]) {
        const s = p[side];
        if (!isObj(s) || !isStr(s.title) || !Array.isArray(s.points) || s.points.length < 1 || s.points.length > 4) {
          e.push(`${where}: ${side} 는 {title, points[1~4]}`);
        }
      }
      break;
    case "NeuralNetwork":
      if (!Array.isArray(p.layers) || p.layers.length < 2 || p.layers.length > 6 || !p.layers.every((n: unknown) => isInt(n) && n >= 1 && n <= 8)) {
        e.push(`${where}: layers 는 2~6층, 층마다 1~8개`);
      }
      break;
    case "SummaryScene":
      if (!Array.isArray(p.points) || p.points.length < 1 || p.points.length > 3 || !p.points.every(isStr)) {
        e.push(`${where}: points 는 1~3개 문장`);
      }
      break;
  }
  return e;
}

/** 오류 목록을 돌려준다. 비어 있으면 렌더링해도 된다. 모양이 틀린 입력에도 예외를 던지지 않는다. */
export function validateTimeline(t: unknown): string[] {
  if (!isObj(t)) return ["timeline 이 객체가 아니다"];
  const e: string[] = [];
  if (t.schemaVersion !== 1) e.push("schemaVersion 은 1");
  for (const k of ["fps", "width", "height", "durationInFrames"]) {
    if (!isInt(t[k]) || t[k] <= 0) e.push(`${k} 는 양의 정수`);
  }
  const scenes: any[] = Array.isArray(t.scenes) ? t.scenes : [];
  if (scenes.length === 0) e.push("scenes 가 비어 있다");
  let expected = 0;
  for (const s of scenes) {
    const where = `장면 ${s?.id ?? "?"}`;
    if (!isStr(s?.id)) e.push(`${where}: id 필요`);
    if (!isInt(s?.fromFrame) || s.fromFrame !== expected) e.push(`${where}: fromFrame 은 ${expected} 이어야 한다 (장면은 빈틈 없이 이어진다)`);
    if (!isInt(s?.durationInFrames) || s.durationInFrames <= 0) e.push(`${where}: durationInFrames 는 양의 정수`);
    expected = (isInt(s?.fromFrame) ? s.fromFrame : expected) + (isInt(s?.durationInFrames) ? s.durationInFrames : 0);
    if (!PRESETS.includes(s?.animationPreset)) e.push(`${where}: animationPreset 은 ${PRESETS.join("|")}`);
    if (s?.media !== undefined) {
      const m = s.media;
      const video = isObj(m) && m.type === "video" && isSafeRelative(m.src) && isInt(m.durationInFrames) && m.durationInFrames > 0;
      const image = isObj(m) && m.type === "image" && isSafeRelative(m.src);
      if (!video && !image) {
        e.push(`${where}: media 는 {type: video, src: 작업 폴더 안 경로, durationInFrames: 양의 정수} 또는 {type: image, src: 작업 폴더 안 경로}`);
      }
    }
    if (s?.section !== undefined) {
      const sec = s.section;
      if (!isObj(sec) || !SECTION_KINDS.includes(sec.kind) || (sec.index !== undefined && (!isInt(sec.index) || sec.index < 1))) {
        e.push(`${where}: section 은 {kind: ${SECTION_KINDS.join("|")}, index?: 1 이상}`);
      } else if (sec.kind === "item" && (!isInt(sec.index) || !isObj(t.tracker) || sec.index > (t.tracker.items?.length ?? 0))) {
        e.push(`${where}: 항목 장면의 section.index 가 진행 표시(tracker) 밖이다`);
      }
    }
    const v = s?.visual;
    if (!isObj(v) || v.type !== "template") {
      e.push(`${where}: visual.type 은 template (생성 클립은 Phase 2)`);
    } else if (!(TEMPLATES as readonly string[]).includes(v.component)) {
      e.push(`${where}: 등록되지 않은 템플릿 ${v.component}`);
    } else if ((LISTICLE_TEMPLATES as readonly string[]).includes(v.component) !== LISTICLE_THEMES.includes(t.theme)) {
      e.push(`${where}: ${v.component} 는 테마 ${t.theme} 에서 쓸 수 없다 (목록형 장면 ↔ 목록형 테마 ${LISTICLE_THEMES.join("|")})`);
    } else {
      e.push(...checkProps(v.component, isObj(v.props) ? v.props : {}, where));
    }
  }
  if (isInt(t.durationInFrames) && scenes.length > 0 && expected !== t.durationInFrames) {
    e.push(`durationInFrames(${t.durationInFrames}) 가 장면 길이 합(${expected})과 다르다`);
  }
  const total = isInt(t.durationInFrames) ? t.durationInFrames : 0;
  for (const a of Array.isArray(t.audio) ? t.audio : []) {
    if (!isSafeRelative(a?.src)) e.push(`audio ${a?.src}: 작업 폴더 안의 상대 경로만`);
    if (!isInt(a?.fromFrame) || a.fromFrame < 0 || a.fromFrame >= total) e.push(`audio ${a?.src}: fromFrame 이 영상 밖`);
  }
  let lastEnd = 0;
  for (const c of Array.isArray(t.captions) ? t.captions : []) {
    if (!isStr(c?.text) || !isInt(c?.fromFrame) || !isInt(c?.toFrame) || c.fromFrame >= c.toFrame) {
      e.push(`자막 "${c?.text}": text 와 fromFrame < toFrame 필요`);
      continue;
    }
    if (c.fromFrame < lastEnd) e.push(`자막 "${c.text}": 앞 자막과 겹친다`);
    if (c.toFrame > total) e.push(`자막 "${c.text}": 영상 끝을 넘는다`);
    lastEnd = c.toFrame;
    if (c.words !== undefined) {
      const ws: any[] = Array.isArray(c.words) ? c.words : [];
      let prev = c.fromFrame;
      const ok = ws.length > 0 && ws.every((w) => {
        const good = isStr(w?.text) && isInt(w?.fromFrame) && w.fromFrame >= prev && w.fromFrame < c.toFrame
          && (w.emphasis === undefined || typeof w.emphasis === "boolean");
        prev = isInt(w?.fromFrame) ? w.fromFrame : prev;
        return good;
      });
      if (!ok) e.push(`자막 "${c.text}": words 는 [{text, fromFrame(자막 안, 차례대로), emphasis?}]`);
    }
  }
  if (t.tracker !== undefined) {
    const items: any[] = isObj(t.tracker) && Array.isArray(t.tracker.items) ? t.tracker.items : [];
    if (items.length < 1 || items.length > 7 || !items.every((it) => isObj(it) && isStr(it.name) && optStr(it.meta))) {
      e.push("tracker 는 {items[1~7]: {name, meta?}}");
    }
  }
  if (t.bgm !== null && t.bgm !== undefined) e.push("bgm 은 아직 지원하지 않는다 (null)");
  if (t.header !== undefined && (!isObj(t.header) || ["brand", "title"].some((k) => t.header[k] !== undefined && !isStr(t.header[k])))) {
    e.push("header 는 {brand?, title?} 문자열");
  }
  return e;
}

/** 영상 위 브랜드 글자. header.brand 가 있을 때만 그린다 (기본 없음, 2026-10-18 사용자 피드백) */
export const headerBrand = (t: Pick<Timeline, "header">): string | null => t.header?.brand?.trim() || null;
