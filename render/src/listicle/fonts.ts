// Pretendard 가변 글꼴(1.3.9, SIL OFL 1.1: src/fonts/Pretendard-LICENSE.txt)을 읽고 나서 그린다.
// 글꼴을 다 읽기 전에 프레임을 찍으면 Noto 로 그려진 프레임이 섞인다 → delayRender 로 기다린다.
// 번들에 넣으려고 public/ 대신 src/ 에서 import 한다 (Dockerfile 이 public/ 을 복사하지 않는다, 아키텍처 L-D5).
import { continueRender, delayRender } from "remotion";

import pretendard from "../fonts/PretendardVariable.woff2";

export const FONT_FAMILY = "Pretendard Variable";

let started = false;

export function loadFonts(): void {
  if (started || typeof document === "undefined" || typeof FontFace === "undefined") return;
  started = true;
  const handle = delayRender("Pretendard 글꼴 읽기");
  const face = new FontFace(FONT_FAMILY, `url(${pretendard}) format("woff2")`, { weight: "45 920", style: "normal" });
  face
    .load()
    .then((loaded) => {
      document.fonts.add(loaded);
      continueRender(handle);
    })
    .catch(() => continueRender(handle)); // 못 읽으면 Noto CJK 로 그린다 (영상은 계속)
}
