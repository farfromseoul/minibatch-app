// 목록형 쇼츠(D42): 단어 상태·진행 표시 계산과 timeline 검사
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { countUp, phase, seeded, trackerSlots, typed, wordStates } from "../src/lib/listicle.ts";
import { validateTimeline } from "../src/lib/timeline.ts";

const sample = () => JSON.parse(readFileSync(new URL("./fixtures/listicle-timeline.json", import.meta.url), "utf8"));

test("목록형 샘플 timeline 은 오류가 없다", () => {
  assert.deepEqual(validateTimeline(sample()), []);
});

test("단어 상태: 지금 단어 앞은 읽음, 뒤는 남음", () => {
  const words = [{ text: "하고", fromFrame: 10 }, { text: "싶은", fromFrame: 20 }, { text: "일을", fromFrame: 30 }];
  assert.deepEqual(wordStates(words, 5), ["next", "next", "next"]);
  assert.deepEqual(wordStates(words, 20), ["done", "current", "next"]);
  assert.deepEqual(wordStates(words, 99), ["done", "done", "current"]);
});

test("진행 표시: 지금 항목 앞은 done, 정리 장면(null)은 모두 done", () => {
  assert.deepEqual(trackerSlots(4, 2), ["done", "current", "next", "next"]);
  assert.deepEqual(trackerSlots(3, null), ["done", "done", "done"]);
});

test("타자·구간·숫자 세기·고정 난수", () => {
  assert.equal(typed("안녕하세요", 0.4), "안녕");
  assert.equal(phase(50, 100, 0.25, 0.75), 0.5);
  assert.equal(countUp("10", 1), "10");
  assert.equal(countUp("3.5만", 0.3), "3.5만");
  assert.equal(seeded(7), seeded(7));
  assert.ok(seeded(7) >= 0 && seeded(7) < 1);
});

test("목록형 장면은 목록형 테마에서만, 다른 테마의 장면은 목록형 테마에서 못 쓴다", () => {
  const t = sample();
  t.theme = "letterbox";
  assert.match(validateTimeline(t).join("\n"), /LHookClaim.*letterbox/);
  const u = sample();
  u.scenes[0].visual = { type: "template", component: "TitleReveal", props: { title: "x" } };
  assert.match(validateTimeline(u).join("\n"), /TitleReveal.*nova/);
});

test("항목 장면의 번호가 진행 표시 밖이면 오류", () => {
  const t = sample();
  const item = t.scenes.find((s: any) => s.section?.kind === "item");
  item.section.index = 9;
  assert.match(validateTimeline(t).join("\n"), /tracker/);
});

test("단어 시각이 자막 밖이거나 거꾸로면 오류", () => {
  const t = sample();
  const c = t.captions[0];
  c.words = [{ text: "a", fromFrame: c.toFrame }];
  const u = sample();
  u.captions[0].words = [{ text: "a", fromFrame: u.captions[0].fromFrame + 3 }, { text: "b", fromFrame: u.captions[0].fromFrame + 1 }];
  assert.match(validateTimeline(t).join("\n"), /words/);
  assert.match(validateTimeline(u).join("\n"), /words/);
});

test("장면 속성 검사: 그림 장면 모양이 틀리면 오류", () => {
  const cases: [string, Record<string, unknown>, RegExp][] = [
    ["LChat", { prompt: "x", results: [] }, /LChat/],
    ["LSteps", { steps: ["하나"] }, /LSteps/],
    ["LIcon", { icon: "rocket", title: "x" }, /LIcon/],
    ["LCompare", { left: { title: "a", points: ["1"] }, right: { title: "b", points: [] } }, /LCompare/],
    ["LRecap", { title: "x", items: [] }, /LRecap/],
    ["LHookReveal", { kicker: "k", headline: "h", count: 9 }, /LHookReveal/],
  ];
  for (const [component, props, re] of cases) {
    const t = sample();
    const s = t.scenes.find((x: any) => x.section?.kind === "item" && x.visual.component !== "LItemCard");
    s.visual = { type: "template", component, props };
    assert.match(validateTimeline(t).join("\n"), re, component);
  }
});

test("tracker 모양 검사", () => {
  const t = sample();
  t.tracker = { items: [] };
  assert.match(validateTimeline(t).join("\n"), /tracker/);
});
