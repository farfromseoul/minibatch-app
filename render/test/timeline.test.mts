// timeline.json 검증 (앱 설계 "timeline.json", "Remotion 템플릿 규격"). 렌더링 전에 잘못된 입력을 거른다.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { validateTimeline } from "../src/lib/timeline.ts";

const sample = () => JSON.parse(readFileSync(new URL("./fixtures/sample-timeline.json", import.meta.url), "utf8"));

test("올바른 타임라인은 오류가 없다", () => {
  assert.deepEqual(validateTimeline(sample()), []);
});

test("장면 사이에 빈 프레임이 있으면 오류", () => {
  const t = sample();
  t.scenes[1].fromFrame = 61;
  assert.match(validateTimeline(t).join("\n"), /s02.*60/);
});

test("장면 길이 합이 전체 길이와 다르면 오류", () => {
  const t = sample();
  t.durationInFrames = 200;
  assert.match(validateTimeline(t).join("\n"), /durationInFrames/);
});

test("등록되지 않은 템플릿은 오류", () => {
  const t = sample();
  t.scenes[0].visual.component = "Fireworks";
  assert.match(validateTimeline(t).join("\n"), /Fireworks/);
});

test("오디오 경로는 작업 폴더 안의 상대 경로만", () => {
  for (const src of ["/etc/passwd", "../other/x.wav", "tts/../../x.wav", "http://evil/x.wav"]) {
    const t = sample();
    t.audio[0].src = src;
    assert.ok(validateTimeline(t).some((e) => e.includes("audio")), src);
  }
});

test("오디오 시작이 영상 밖이면 오류", () => {
  const t = sample();
  t.audio[0].fromFrame = 150;
  assert.ok(validateTimeline(t).length > 0);
});

test("자막이 겹치거나 끝을 넘으면 오류", () => {
  const overlap = sample();
  overlap.captions[1].fromFrame = 50;
  const past = sample();
  past.captions[1].toFrame = 151;
  assert.match(validateTimeline(overlap).join("\n"), /자막/);
  assert.match(validateTimeline(past).join("\n"), /자막/);
});

test("FlowDiagram: 노드 6개 초과, 없는 노드를 가리키는 화살표는 오류", () => {
  const many = sample();
  many.scenes[1].visual.props.nodes = Array.from({ length: 7 }, (_, i) => ({ id: `n${i}`, label: `${i}` }));
  many.scenes[1].visual.props.edges = [];
  many.scenes[1].visual.props.revealOrder = [];
  const dangling = sample();
  dangling.scenes[1].visual.props.edges.push(["a", "zzz"]);
  assert.match(validateTimeline(many).join("\n"), /6/);
  assert.match(validateTimeline(dangling).join("\n"), /zzz/);
});

test("SummaryScene: 요점은 1~3개", () => {
  const t = sample();
  t.scenes[0].visual = { type: "template", component: "SummaryScene", props: { points: ["a", "b", "c", "d"] } };
  assert.match(validateTimeline(t).join("\n"), /points/);
});

test("모양이 틀린 입력도 예외 없이 오류 목록을 돌려준다", () => {
  assert.ok(validateTimeline(null).length > 0);
  assert.ok(validateTimeline({ schemaVersion: 1 }).length > 0);
});
