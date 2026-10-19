// timeline.json 의 모양과 검증 (앱 설계 "timeline.json", "Remotion 템플릿 규격").
// render-worker 는 이 파일만 읽는다. 렌더링 전에 여기서 거르면 몇 분짜리 렌더가 중간에 깨지지 않는다.
// 이 파일은 JSX 를 쓰지 않는다: Node 테스트(node --test)가 바로 불러온다.

export type AnimationPreset = "pop" | "fade" | "sequential" | "draw";

export type TemplateVisual = { type: "template"; component: string; props: Record<string, unknown> };

export type TimelineScene = {
  id: string;
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
  captions: { text: string; fromFrame: number; toFrame: number }[];
  bgm: null;
};

export const TEMPLATES = ["TitleReveal", "FlowDiagram", "ComparisonCards", "NeuralNetwork", "SummaryScene"] as const;
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

function checkProps(component: string, p: Record<string, any>, where: string): string[] {
  const e: string[] = [];
  switch (component) {
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
    const v = s?.visual;
    if (!isObj(v) || v.type !== "template") {
      e.push(`${where}: visual.type 은 template (생성 클립은 Phase 2)`);
    } else if (!(TEMPLATES as readonly string[]).includes(v.component)) {
      e.push(`${where}: 등록되지 않은 템플릿 ${v.component}`);
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
  }
  if (t.bgm !== null && t.bgm !== undefined) e.push("bgm 은 아직 지원하지 않는다 (null)");
  if (t.header !== undefined && (!isObj(t.header) || ["brand", "title"].some((k) => t.header[k] !== undefined && !isStr(t.header[k])))) {
    e.push("header 는 {brand?, title?} 문자열");
  }
  return e;
}

/** 영상 위 브랜드 글자. header.brand 가 있을 때만 그린다 (기본 없음, 2026-10-18 사용자 피드백) */
export const headerBrand = (t: Pick<Timeline, "header">): string | null => t.header?.brand?.trim() || null;
