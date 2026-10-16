// 화면 배치·애니메이션 계산. 시간 의존 값은 프레임에서만 계산한다 (앱 설계 "Remotion 템플릿 규격").
import assert from "node:assert/strict";
import { test } from "node:test";

import { entrance, fitFontSize, flowLayout, revealCount, SAFE } from "../src/lib/layout.ts";

test("흐름도는 화살표 방향으로 위에서 아래로 층을 나눈다", () => {
  const pos = flowLayout(
    ["q", "r", "l", "a"],
    [["q", "r"], ["r", "l"], ["q", "l"], ["l", "a"]],
    { width: 1080, height: 1920 },
  );
  const y = Object.fromEntries(pos.map((p) => [p.id, p.y]));
  assert.ok(y.q < y.r && y.r < y.l && y.l < y.a);
});

test("같은 층의 노드는 가로로 나란히, 화면 안에 놓인다", () => {
  const pos = flowLayout(["a", "b", "c"], [["a", "b"], ["a", "c"]], { width: 1080, height: 1920 });
  const b = pos.find((p) => p.id === "b")!;
  const c = pos.find((p) => p.id === "c")!;
  assert.equal(b.y, c.y);
  assert.notEqual(b.x, c.x);
  for (const p of pos) {
    assert.ok(p.x > 0 && p.x < 1080);
    assert.ok(p.y >= SAFE.top && p.y <= 1920 - SAFE.bottom, `${p.id} y=${p.y}`);
  }
});

test("순환이 있어도 멈추지 않는다", () => {
  const pos = flowLayout(["a", "b"], [["a", "b"], ["b", "a"]], { width: 1080, height: 1920 });
  assert.equal(pos.length, 2);
});

test("긴 글은 글자 크기를 줄이고, 최소 크기 아래면 null", () => {
  const short = fitFontSize("RAG", 900, 120, 40);
  const long = fitFontSize("검색 증강 생성이라는 아주 긴 제목을 한 줄에 넣으면", 900, 120, 40);
  const tooLong = fitFontSize("가".repeat(200), 900, 120, 40);
  assert.equal(short, 120);
  assert.ok(long !== null && long < 120 && long >= 40);
  assert.equal(tooLong, null);
});

test("등장 애니메이션은 0~1 사이이고 장면 길이에 비례해 끝난다", () => {
  assert.equal(entrance(0, 90, "pop"), 0);
  assert.equal(entrance(89, 90, "pop"), 1);
  for (let f = 0; f < 90; f++) {
    const v = entrance(f, 90, "fade");
    assert.ok(v >= 0 && v <= 1);
  }
  assert.ok(entrance(5, 90, "fade") < entrance(10, 90, "fade"));
});

test("순차 공개는 장면 앞 70% 동안 하나씩 늘어난다", () => {
  assert.equal(revealCount(0, 100, 4), 1);
  assert.equal(revealCount(69, 100, 4), 4);
  assert.equal(revealCount(99, 100, 4), 4);
  assert.ok(revealCount(30, 100, 4) >= 2);
});
