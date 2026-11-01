// 목록형 쇼츠(D42): 단어 상태·진행 표시 계산과 timeline 검사
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { countUp, phase, seeded, trackerSlots, typed, walkSchedule, wordStates, recapCells } from "../src/lib/listicle.ts";
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
    ["LHookReveal", { kicker: "k", headline: "h", count: 11 }, /LHookReveal/],
    ["LWalkthrough", { kind: "none", title: "", steps: [{ input: "ls", output: [] }] }, /LWalkthrough/],
    ["LArtifact", { image: "../../etc/passwd.png", title: "x", ok: true }, /LArtifact/],
    ["LArtifact", { image: "lab/t1/previews/a.png", title: "x", ok: "yes" }, /LArtifact/],
    ["LVerdict", { title: "t", pros: [], cons: [], forWhom: "x" }, /LVerdict/],
    ["LWalkthrough", { kind: "terminal", title: "", steps: [] }, /LWalkthrough/],
    ["LWalkthrough", { kind: "terminal", title: "", steps: [{ input: "ls", output: [] }], beats: [-1] }, /LWalkthrough/],
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

test("실습 장면: 올바른 LWalkthrough 는 통과 (v1.4)", () => {
  const t = sample();
  const s = t.scenes.find((x: any) => x.section?.kind === "item" && x.visual.component !== "LItemCard");
  s.visual = { type: "template", component: "LWalkthrough",
    props: { kind: "terminal", title: "터미널", steps: [{ input: "npx skills find pdf", output: ["pdf-to-xlsx"] }], beats: [6, 70] } };
  assert.deepEqual(validateTimeline(t), []);
});

test("실습 일정: 단계는 문장 시작(beats)에 타이핑을 시작하고, 다음 문장 전에 출력까지 끝난다", () => {
  const steps = [{ input: "npx skills find pdf", output: ["a", "b"] }, { input: "npx skills add x", output: ["ok"] }];
  const s = walkSchedule(steps, [6, 80, 150], 200);
  assert.equal(s.length, 2);
  assert.ok(s[0].typeFrom >= 6 && s[0].typeFrom < 20);
  assert.ok(s[1].typeFrom >= 80 && s[1].typeFrom < 94);
  for (const [i, x] of s.entries()) {
    assert.ok(x.typeTo > x.typeFrom);
    assert.equal(x.outFrom.length, steps[i].output.length);
    const next = i + 1 < s.length ? s[i + 1].typeFrom : 200;
    assert.ok(x.outFrom.every((f) => f >= x.typeTo && f < next), JSON.stringify(x));
  }
});

test("실습 일정: beats 가 없으면 장면을 고르게 나눈다", () => {
  const s = walkSchedule([{ input: "ls", output: [] }, { input: "pwd", output: ["/x"] }], undefined, 120);
  assert.ok(s[0].typeFrom < 20 && s[1].typeFrom >= 50 && s[1].typeFrom < 70);
});

test("정리 목록 칸: 6개까지 한 줄, 7~10개는 두 줄로 영역 안에 (v1.4)", () => {
  const area = { x: 72, y: 500, w: 936, h: 730 };
  for (const n of [1, 5, 6, 7, 10]) {
    const cells = recapCells(n, area);
    assert.equal(cells.length, n);
    assert.equal(new Set(cells.map((c) => c.x)).size, n >= 7 ? 2 : 1, String(n));
    for (const c of cells) {
      assert.ok(c.y >= area.y && c.y + c.h <= area.y + area.h + 0.5 && c.x + c.w <= area.x + area.w + 0.5, JSON.stringify(c));
      assert.ok(c.h >= 100, `${n}: 칸 높이 ${c.h}`);
    }
  }
  assert.deepEqual(recapCells(10, area).map((c) => c.x).slice(4, 6), [72, 72 + (936 - 18) / 2 + 18]);
});

test("실습 리뷰 장면: 올바른 LArtifact·LVerdict 는 통과 (D46)", () => {
  const t = sample();
  const items = t.scenes.filter((x: any) => x.section?.kind === "item" && x.visual.component !== "LItemCard");
  items[0].visual = { type: "template", component: "LArtifact", props: { image: "lab/t1/previews/chart.html.png", title: "chart.html", ok: true, meta: "41초" } };
  items[1].visual = { type: "template", component: "LVerdict", props: { title: "직접 써 보니", pros: ["a", "b"], cons: ["c"], forWhom: "누구" } };
  assert.deepEqual(validateTimeline(t), []);
});
