# 0주 차 비교 (PoC)

설계 문서 `~/projects/minibatch/docs/03-실행계획.md` 5단계의 TTS·LLM 품질 게이트에 쓰는 스크립트다. 결과는 `poc/out/`에 생기고 저장소에는 올라가지 않는다(`.gitignore`).

| 폴더 | 내용 |
| --- | --- |
| `llm_compare/` | LM Studio(OpenAI 호환)로 주제 5개의 대본 JSON을 모델마다 만들고, 스키마·규칙 통과, `reasoning_content` 회수, 속도를 비교 |
| `tts_compare/` | 같은 문장 3개를 TTS 엔진마다 합성하고 RTF(합성 시간 ÷ 음성 길이)를 비교 |
| `tests/` | 표준 라이브러리 `unittest` 단위 테스트 (외부 서비스 없이 돈다) |

`llm_compare/extract.py`(응답에서 JSON 꺼내기, reasoning 필드 회수)와 `validate.py`(대본 검증)는 나중에 job-api의 LLM 어댑터로 옮겨 간다.

## 단위 테스트

```bash
cd ~/personal-projects/minibatch-app/poc
docker run --rm -v "$PWD":/poc:ro -w /poc -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim \
  python -m unittest discover -s tests -t .
```

확인: 마지막에 `OK`. (2026-10-15 python:3.12-slim, python:3.9-slim 에서 29개 통과)

## 1. LLM 비교

할 일: 후보 모델을 받고 모델 키를 확인한다. 생각(thinking) 모델은 답이 `reasoning_content`에 오기도 하는데 스크립트가 회수하고 표에 따로 센다.

```bash
~/.lmstudio/bin/lms get qwen3-8b --mlx --select
~/.lmstudio/bin/lms get qwen3-8b --gguf --select
~/.lmstudio/bin/lms ls --llm          # 모델 키 확인
~/.lmstudio/bin/lms unload --all      # 손으로 올린 모델이 있으면 내린다 (TTL 이 없다)
```

명령 (컨테이너에서 실행. job-api가 LM Studio를 부르는 길과 같다):

```bash
cd ~/personal-projects/minibatch-app/poc
docker run --rm -v "$PWD":/poc -w /poc -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim \
  python -m llm_compare.run --base-url http://host.docker.internal:1234/v1 \
    --model qwen/qwen3.8-27b \
    --model <8B MLX 모델 키> \
    --model <8B GGUF 모델 키>
```

- 모델마다 주제 5개를 순서대로 요청한다. LM Studio가 요청 때 모델을 올리고(JIT) 다음 모델을 올릴 때 이전 모델을 내린다. 27B는 처음 올릴 때 시간이 걸린다.
- 확인: 끝에 모델별 표가 나오고 `out/llm/summary.md`에 저장된다. 대본 원문은 `out/llm/<모델>/<주제>.json`.
- 사람이 할 일: 대본 원문을 읽고 명백한 기술 오류를 센다. 27B(기준선)와 8B의 차이를 본다.
- 실패하면: 표의 통과 열이 0이면 `out/llm/<모델>/<주제>.json`의 `problems`와 `message`를 붙여 준다.

## 2. TTS 비교

엔진마다 설치가 무겁고 의존성이 달라 각자 일회용 컨테이너에서 돌린다. 아래 명령은 공식 저장소 README를 따랐고 실행해 보지 않았다(미확인). 모델 가중치는 처음 한 번 내려받으므로 캐시를 이름 있는 볼륨에 둔다.

### MeloTTS (MIT)

```bash
cd ~/personal-projects/minibatch-app/poc
docker run --rm -v "$PWD":/poc -w /poc -v minibatch-poc-cache:/root/.cache python:3.9-slim bash -c '
  apt-get update -qq && apt-get install -y -qq git build-essential >/dev/null &&
  git clone -q https://github.com/myshell-ai/MeloTTS.git /opt/MeloTTS &&
  pip install -q -e /opt/MeloTTS &&
  python -m unidic download &&
  python -m tts_compare.run --engine melotts'
```

- 공식 문서: Ubuntu·Python 3.9에서 개발·시험, 설치는 저장소를 받아 `pip install -e .` 후 `python -m unidic download`. 한국어는 `TTS(language="KR")`, 화자 `spk2id["KR"]`.

### Supertonic 3 (코드 MIT, 모델 OpenRAIL-M, 저장소 보관 처리됨)

```bash
cd ~/personal-projects/minibatch-app/poc
docker run --rm -v "$PWD":/poc -w /poc -v minibatch-poc-cache:/root/.cache python:3.11-slim bash -c '
  apt-get update -qq && apt-get install -y -qq git >/dev/null &&
  git clone -q https://github.com/supertone-oss-archive/supertonic.git /opt/supertonic &&
  pip install -q huggingface_hub -r /opt/supertonic/py/requirements.txt &&
  cd /opt/supertonic &&
  hf download supertone-oss-archive/supertonic-3 --revision aafc6e32416a594460b32413efc49d7fe4ce6d46 --local-dir assets &&
  cd /poc && python -m tts_compare.run --engine supertonic --supertonic-dir /opt/supertonic'
```

- 공식 저장소: 개발과 지원이 끝난 보관 저장소다. 채택하면 보안 패치가 없다.
- 목소리(스타일) 선택 인자는 확인하지 못해 예제 기본값을 쓴다.

### 확인

- 끝에 엔진 표(성공 수, 평균 RTF)가 나오고 `out/tts/summary-<엔진>.md`에 저장된다.
- 음성: `out/tts/<엔진>/s01.wav` ~ `s03.wav`를 직접 들어 본다. 점수 기준(발음, 자연스러움 5점 중 3점 이상, RTF 1 미만, 라이선스)은 실행계획 5단계 표.
- 실패하면: 컨테이너 출력의 마지막 오류를 그대로 붙여 준다.
