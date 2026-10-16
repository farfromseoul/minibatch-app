쇼츠 대본의 문장을 장면으로 묶고, 장면마다 화면 템플릿 하나와 그 속성을 골라 줘.

대본 문장 (번호를 이 순서 그대로, 빠짐없이 장면의 sentences 에 나눠 담는다. 문장은 쓰지 말고 번호만):
$numbered

규칙:
- 장면마다 sentences 는 번호 1~4개. 예: 첫 장면 [1], 다음 장면 [2, 3, 4].
- 첫 장면 role 은 hook, 마지막 장면 role 은 summary 또는 outro. 나머지는 explain, example, compare 중에서.
- 같은 템플릿을 세 번 연달아 쓰지 않는다.
- 내용과 맞는 템플릿만 쓴다. 신경망 구조가 아닌 내용에 NeuralNetwork 처럼 억지로 맞추지 않는다. 맞는 것이 없으면 TitleReveal 이나 SummaryScene 을 쓴다.
- animationPreset: pop(강조), fade(부드럽게), sequential(하나씩 공개, 흐름·목록), draw

쓸 수 있는 템플릿과 props 형식:
$templates

JSON 으로만 답한다.
