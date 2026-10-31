# render-worker

`timeline.json`(장면·자막·음성 시각이 확정된 렌더 입력)과 음성 파일로 세로 쇼츠 MP4를 만든다. Remotion(React로 영상을 그리는 도구)을 쓴다. job-api만 internal 망에서 부른다.

Remotion 라이선스: 회사 단위로 쓰면 회사 라이선스가 필요할 수 있다(3명 이하 팀은 무료). [약관](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)

## 구조

```text
src/
  index.ts, Root.tsx       # Remotion 진입점. 구성(Composition) "Short" 하나. 길이·크기는 timeline 에서 정한다
  Short.tsx                # 장면(Sequence), 음성(Html5Audio), 자막 레이어
  scenes/                  # 템플릿 5종: TitleReveal, FlowDiagram, ComparisonCards, NeuralNetwork, SummaryScene
  listicle/                # 목록형 쇼츠(D42): 틀(Listicle), 공통 장면 12종(L*, 테마 tokens 로 그림), 아이콘, 글꼴 읽기
  listicle/themes/         # 화면 테마 템플릿(v1.3): nova·paper·terminal·pop. 새 테마 = 파일 하나 + names.ts·index.ts·theme.ts 등록 (docs 목록형쇼츠/02 '새 테마 더하는 방법')
  fonts/                   # Pretendard 1.3.9 가변 글꼴(woff2) + 라이선스(SIL OFL 1.1). src 에서 import 해 번들에 넣는다
  layers/Subtitle.tsx      # 자막 (아래 안전 영역 바로 위)
  lib/timeline.ts          # timeline 모양과 검증 (JSX 없음: Node 테스트가 바로 불러온다). 목록형: captions[].words, scenes[].section, tracker
  lib/listicle.ts          # 목록형 계산(단어 상태, 진행 표시 칸, 타자, 고정 난수)
  lib/layout.ts            # 흐름도 배치, 글자 크기 맞추기, 등장·순차 공개 계산 (프레임 기반)
  theme.ts                 # 색·글꼴 (Noto Sans CJK)
server/
  render-server.mts        # 진입점: 번들 확인 → 파일 서버 + API 서버
  app.ts                   # HTTP: POST /render, GET /healthz, 내부 파일 서버
  render.ts                # selectComposition + renderMedia, 임시 이름으로 렌더 후 이름 바꾸기
  request.ts               # 요청·경로 검사, 음성 주소 만들기
test/                      # node --test (*.test.mts), fixtures/sample-timeline.json
```

## API

| 메서드 | 경로 | 요청 → 응답 |
| --- | --- | --- |
| GET | `/healthz` | `{"status": "ok", "busy": false}` |
| POST | `/render` | `{"timeline": "/data/jobs/<id>/timeline.json", "out": "/data/jobs/<id>/render/final.mp4"}` → `{"path", "frames", "renderSec"}` |

- 경로는 데이터 폴더(`/data`) 안의 절대 경로만. 밖이면 400. `out`은 `.mp4`.
- timeline 검증 실패 422(이유 목록), 렌더 실패 500, 렌더링 중이면 409 `busy`(한 번에 하나).
- 음성은 timeline 의 상대 경로(`tts/s01.wav`)를 컨테이너 안 파일 서버(`127.0.0.1:8092`, 읽기 전용, 컨테이너 밖에서 닿지 않음)에서 헤드리스 Chrome 이 받는다.
- 출력: 1080×1920, h264 + aac.

## 설정 (환경 변수)

| 이름 | 기본값 |
| --- | --- |
| `MINIBATCH_DATA_DIR` | `/data` |
| `MINIBATCH_RENDER_PORT` / `MINIBATCH_RENDER_FILE_PORT` | 8091 / 8092 |
| `MINIBATCH_RENDER_CONCURRENCY` | 2 (아키텍처 D13, 메모리 예산) |

## 템플릿 규칙 (앱 설계 "Remotion 템플릿 규격")

- 시간에 따라 바뀌는 값은 `useCurrentFrame()`에서만 계산한다. `Math.random`, `Date.now`, CSS 애니메이션 금지 (렌더 재현성).
- 애니메이션 길이는 장면 길이의 비율 (`lib/layout.ts`의 `entrance`, `revealCount`).
- 안전 영역: 위 250px, 아래 400px (`SAFE`, 수치 미확인).
- 새 템플릿: `scenes/`에 컴포넌트, `scenes/index.ts`에 등록, `lib/timeline.ts`의 `TEMPLATES`와 속성 검사에 추가.
- 목록형 장면(L*)은 `listicle/scenes.tsx` 의 `LISTICLE_SCENES` 에 등록하고, `lib/timeline.ts` 의 `LISTICLE_TEMPLATES`·속성 검사, job-api `app/schemas/templates.py` 에 같은 규칙을 둔다. 목록형 장면은 등록된 목록형 테마(`listicle/themes/names.ts`)에서만 쓴다(검사가 막는다).
- 목록형 화면 미리 보기: `test/fixtures/listicle-timeline.json`(음성 없음)
- Node 의 TypeScript 실행은 타입만 지운다. `enum`, 생성자 매개변수 속성(`constructor(public x)`) 같은 문법은 쓰지 않는다(`tsconfig`의 `erasableSyntaxOnly`가 잡는다).

## 미리 보기 (Remotion Studio)

`npm run dev`는 브라우저 화면을 띄우는 개발 도구다. 이 프로젝트는 로컬에 Node 도구를 두지 않으므로, 쓰려면 컨테이너에서 포트를 열어 띄운다 (미확인).

## 테스트

```bash
cd ~/personal-projects/minibatch-app
TAG=$(git rev-parse --short=7 HEAD)
docker build -t minibatch-render-worker:$TAG render

# 타입 검사
docker run --rm -v "$PWD/render/test":/app/test:ro minibatch-render-worker:$TAG npx tsc -p .
# 단위·서버 테스트 + 실제 렌더링 (5초 영상)
docker run --rm -v "$PWD/render/test":/app/test:ro -e RENDER_INTEGRATION=1 \
  minibatch-render-worker:$TAG node --test "test/**/*.test.mts"
```

`node --test test/`처럼 폴더만 주면 테스트를 찾지 못한다. 파일 패턴을 따옴표로 준다.
