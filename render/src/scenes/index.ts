// 템플릿 등록부. 이름은 src/lib/timeline.ts 의 TEMPLATES 와 같아야 한다 (scenes 단계가 고를 수 있는 목록).
import type React from "react";

import type { SceneProps } from "./common";
import { ComparisonCards } from "./ComparisonCards";
import { FlowDiagram } from "./FlowDiagram";
import { NeuralNetwork } from "./NeuralNetwork";
import { SummaryScene } from "./SummaryScene";
import { TitleReveal } from "./TitleReveal";

export const SCENES: Record<string, React.FC<SceneProps<any>>> = {
  TitleReveal,
  FlowDiagram,
  ComparisonCards,
  NeuralNetwork,
  SummaryScene,
};
