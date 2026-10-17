import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

import { entrance, fitFontSize, revealCount } from "../lib/layout";
import type { SceneProps } from "./common";

// 키노트 스타일 장면 (2026-10-17, 참고: 짙은 남색 배경에 빛나는 키워드·색 점·가는 선).
// 같은 장면 데이터를 지정한 영역(area) 안에 그린다. 전체 화면(keynote)과 레터박스 가운데 판(letterbox)이 같이 쓴다.
export type Area = { x: number; y: number; w: number; h: number };
export type KeynoteProps<P> = SceneProps<P> & { area: Area };

export const KEY = {
  cyan: "#5EE7FF",
  green: "#6FD3A8",
  blue: "#6BB8E6",
  orange: "#F2A65A",
  text: "#F2F5FA",
  muted: "#8C9BB5",
  line: "rgba(220, 230, 245, 0.75)",
};
const DOTS = [KEY.green, KEY.blue, KEY.orange, KEY.cyan];
export const glow = (c: string, s = 1) => `0 0 ${18 * s}px ${c}, 0 0 ${48 * s}px ${c}66`;

const box = (a: Area): React.CSSProperties => ({ position: "absolute", left: a.x, top: a.y, width: a.w, height: a.h });

/** 0~1 등장, 키노트는 조금 느리고 부드럽게 */
const useIn = (duration: number, delay = 0) => {
  const frame = useCurrentFrame();
  return entrance(Math.max(0, frame - delay), duration, "fade");
};

export const KTitle: React.FC<KeynoteProps<{ title: string; subtitle?: string }>> = ({ durationInFrames, props, area }) => {
  const frame = useCurrentFrame();
  const p = useIn(durationInFrames);
  // 줄바꿈은 단어 사이에서만 되므로(keep-all) 가장 긴 단어가 한 줄에 들어가는 크기와 함께 본다
  const longestWord = props.title.split(/\s+/).reduce((a, b) => (b.length > a.length ? b : a), "");
  const size = Math.min(
    fitFontSize(props.title, area.w * 0.92, Math.round(area.h * 0.2), Math.round(area.h * 0.08)) ?? Math.round(area.h * 0.08),
    fitFontSize(longestWord, area.w * 0.92, Math.round(area.h * 0.2), 24, 1) ?? 24,
  );
  const subSize = props.subtitle ? fitFontSize(props.subtitle, area.w * 0.9, Math.round(size * 0.38), 22) ?? 22 : 0;
  const lineW = interpolate(frame, [6, 30], [0, area.w * 0.42], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ ...box(area), display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", opacity: p }}>
      <div style={{ fontSize: size, fontWeight: 800, color: KEY.cyan, textShadow: glow(KEY.cyan), lineHeight: 1.1, textAlign: "center", wordBreak: "keep-all", transform: `scale(${0.94 + 0.06 * p})` }}>
        {props.title}
      </div>
      <div style={{ width: lineW, height: 3, background: KEY.cyan, boxShadow: glow(KEY.cyan, 0.6), margin: `${Math.round(size * 0.25)}px 0` }} />
      {props.subtitle ? <div style={{ fontSize: subSize, color: KEY.text, fontWeight: 500, textAlign: "center", wordBreak: "keep-all" }}>{props.subtitle}</div> : null}
    </div>
  );
};

/** 화살표 방향으로 층을 나눈다 (가장 긴 경로). 층마다 노드 목록 */
function levelsOf(ids: string[], edges: [string, string][]): string[][] {
  const rank = new Map(ids.map((id) => [id, 0]));
  for (let i = 0; i < ids.length; i++) {
    let changed = false;
    for (const [a, b] of edges) {
      const next = (rank.get(a) ?? 0) + 1;
      if (rank.has(b) && next > (rank.get(b) ?? 0) && next < ids.length) {
        rank.set(b, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const out: string[][] = [];
  for (const id of ids) (out[rank.get(id) ?? 0] ??= []).push(id);
  return out.filter(Boolean);
}

export const KFlow: React.FC<KeynoteProps<{ nodes: { id: string; label: string }[]; edges: [string, string][]; revealOrder?: string[] }>> = ({
  durationInFrames,
  props,
  area,
}) => {
  const frame = useCurrentFrame();
  const ids = props.nodes.map((n) => n.id);
  const label = Object.fromEntries(props.nodes.map((n) => [n.id, n.label]));
  const levels = levelsOf(ids, props.edges);
  const order = props.revealOrder && props.revealOrder.length ? props.revealOrder : levels.flat();
  const shown = new Set(order.slice(0, revealCount(frame, durationInFrames, order.length)));
  const rowH = area.h / levels.length;
  const longest = Math.max(...props.nodes.map((n) => n.label.length));
  const perRow = Math.max(...levels.map((l) => l.length));
  const size = Math.min(Math.round(rowH * 0.42), fitFontSize("가".repeat(longest), (area.w / perRow) * 0.9, 110, 26, 1) ?? 26);
  const pos = (id: string) => {
    const li = levels.findIndex((l) => l.includes(id));
    const row = levels[li];
    return { x: area.x + (area.w * (row.indexOf(id) + 1)) / (row.length + 1), y: area.y + rowH * (li + 0.5) };
  };
  return (
    <>
      <svg width={1080} height={1920} style={{ position: "absolute", left: 0, top: 0 }}>
        {props.edges
          .filter(([a, b]) => shown.has(a) && shown.has(b))
          .map(([a, b]) => {
            const p1 = pos(a);
            const p2 = pos(b);
            const y1 = p1.y + size * 0.75;
            const y2 = p2.y - size * 0.85;
            return (
              <g key={`${a}-${b}`} stroke={KEY.line} strokeWidth={4} fill="none" strokeLinecap="round">
                <line x1={p1.x} y1={y1} x2={p2.x} y2={y2} />
                <polyline points={`${p2.x - 14},${y2 - 14} ${p2.x},${y2} ${p2.x + 14},${y2 - 14}`} />
              </g>
            );
          })}
      </svg>
      {props.nodes
        .filter((n) => shown.has(n.id))
        .map((n, i) => {
          const p = pos(n.id);
          const c = [KEY.cyan, KEY.green, KEY.orange, KEY.blue][i % 4];
          return (
            <div
              key={n.id}
              style={{ position: "absolute", left: p.x - area.w / 2, top: p.y - size * 0.7, width: area.w, textAlign: "center", fontSize: size, fontWeight: 800, color: c, textShadow: glow(c, 0.8), wordBreak: "keep-all", lineHeight: 1.2 }}
            >
              {label[n.id]}
            </div>
          );
        })}
    </>
  );
};

/** 색 점 무리 (마름모 4개) */
const Cluster: React.FC<{ cx: number; cy: number; r: number; color: string; p: number }> = ({ cx, cy, r, color, p }) => (
  <>
    {[
      [0, -1.4],
      [-1.4, 0],
      [1.4, 0],
      [0, 1.4],
    ].map(([dx, dy], i) => (
      <div key={i} style={{ position: "absolute", left: cx + dx * r * 1.6 - r, top: cy + dy * r * 1.6 - r, width: r * 2, height: r * 2, borderRadius: r, background: color, opacity: p, transform: `scale(${p})` }} />
    ))}
  </>
);

export const KCompare: React.FC<KeynoteProps<{ left: { title: string; points: string[] }; right: { title: string; points: string[] } }>> = ({ durationInFrames, props, area }) => {
  const pl = useIn(durationInFrames);
  const pr = useIn(durationInFrames, 8);
  const colW = area.w / 2;
  const r = Math.round(Math.min(colW, area.h) * 0.055);
  const title = Math.min(Math.round(area.h * 0.1), ...[props.left.title, props.right.title].map((t) => fitFontSize(t, colW * 0.9, 90, 26) ?? 26));
  const point = Math.max(Math.round(title * 0.55), 26);
  const side = (s: { title: string; points: string[] }, i: number, p: number) => {
    const color = i === 0 ? KEY.green : KEY.orange;
    const cx = area.x + colW * (i + 0.5);
    return (
      <React.Fragment key={i}>
        <Cluster cx={cx} cy={area.y + area.h * 0.24} r={r} color={color} p={p} />
        <div style={{ position: "absolute", left: area.x + colW * i, top: area.y + area.h * 0.46, width: colW, textAlign: "center", opacity: p }}>
          <div style={{ fontSize: title, fontWeight: 800, color, textShadow: glow(color, 0.6), wordBreak: "keep-all" }}>{s.title}</div>
          {s.points.map((t) => (
            <div key={t} style={{ fontSize: point, color: KEY.text, marginTop: point * 0.5, padding: "0 12px", wordBreak: "keep-all", lineHeight: 1.35 }}>
              {t}
            </div>
          ))}
        </div>
      </React.Fragment>
    );
  };
  return (
    <>
      {side(props.left, 0, pl)}
      <div style={{ position: "absolute", left: area.x + colW - 1, top: area.y + area.h * 0.12, width: 2, height: area.h * 0.76, background: KEY.line, opacity: 0.35 }} />
      {side(props.right, 1, pr)}
    </>
  );
};

export const KNetwork: React.FC<KeynoteProps<{ layers: number[]; labels?: string[] }>> = ({ durationInFrames, props, area }) => {
  const frame = useCurrentFrame();
  const visible = revealCount(frame, durationInFrames, props.layers.length);
  const n = props.layers.length;
  const colX = (i: number) => area.x + (area.w * (i + 0.5)) / n;
  const nodeY = (count: number, j: number) => area.y + area.h * 0.08 + ((area.h * 0.72) * (j + 0.5)) / count;
  const r = Math.round(Math.min(area.w / n, (area.h * 0.72) / Math.max(...props.layers)) * 0.22);
  return (
    <>
      <svg width={1080} height={1920} style={{ position: "absolute", left: 0, top: 0 }}>
        {props.layers.slice(0, visible - 1).map((count, i) =>
          Array.from({ length: count }, (_, a) =>
            Array.from({ length: props.layers[i + 1] }, (_, b) => (
              <line key={`${i}-${a}-${b}`} x1={colX(i)} y1={nodeY(count, a)} x2={colX(i + 1)} y2={nodeY(props.layers[i + 1], b)} stroke={KEY.line} strokeOpacity={0.28} strokeWidth={2} />
            )),
          ),
        )}
        {props.layers.slice(0, visible).map((count, i) =>
          Array.from({ length: count }, (_, j) => <circle key={`${i}-${j}`} cx={colX(i)} cy={nodeY(count, j)} r={r} fill={DOTS[i % DOTS.length]} />),
        )}
      </svg>
      {(props.labels ?? []).slice(0, visible).map((t, i) => (
        <div key={t + i} style={{ position: "absolute", left: colX(i) - area.w / n / 2, top: area.y + area.h * 0.84, width: area.w / n, textAlign: "center", fontSize: Math.round(area.h * 0.05), color: KEY.text, wordBreak: "keep-all" }}>
          {t}
        </div>
      ))}
    </>
  );
};

export const KSummary: React.FC<KeynoteProps<{ points: string[] }>> = ({ durationInFrames, props, area }) => {
  const frame = useCurrentFrame();
  const shown = revealCount(frame, durationInFrames, props.points.length);
  const rowH = area.h / (props.points.length + 1);
  const size = Math.min(Math.round(rowH * 0.32), ...props.points.map((t) => fitFontSize(t, area.w * 0.78, 64, 24) ?? 24));
  const badge = Math.round(size * 1.5);
  return (
    <>
      <div style={{ position: "absolute", left: area.x, top: area.y + rowH * 0.25, width: area.w, textAlign: "center", fontSize: Math.round(size * 0.9), color: KEY.muted, letterSpacing: 6, fontWeight: 700 }}>핵심 정리</div>
      {props.points.slice(0, shown).map((t, i) => (
        <div key={t} style={{ position: "absolute", left: area.x + area.w * 0.04, top: area.y + rowH * (i + 1) + (rowH - badge) / 2, width: area.w * 0.92, display: "flex", alignItems: "center", gap: size * 0.7 }}>
          <div style={{ minWidth: badge, height: badge, borderRadius: badge / 2, border: `3px solid ${KEY.cyan}`, color: KEY.cyan, boxShadow: glow(KEY.cyan, 0.5), fontSize: Math.round(size * 0.9), fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {i + 1}
          </div>
          <div style={{ fontSize: size, color: KEY.text, fontWeight: 600, lineHeight: 1.35, wordBreak: "keep-all" }}>{t}</div>
        </div>
      ))}
    </>
  );
};

export const KEYNOTE_SCENES: Record<string, React.FC<KeynoteProps<any>>> = {
  TitleReveal: KTitle,
  FlowDiagram: KFlow,
  ComparisonCards: KCompare,
  NeuralNetwork: KNetwork,
  SummaryScene: KSummary,
};

/** 키노트 배경: 짙은 남색 방사형 그라데이션 */
export const KEYNOTE_BG = "radial-gradient(ellipse at 50% 42%, #13284A 0%, #0A1428 45%, #03060D 100%)";
