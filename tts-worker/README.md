# tts-worker

문장 목록을 받아 문장별 WAV를 만든다. 기본 엔진은 Supertonic 3 (아키텍처 D6). job-api만 internal 망에서 부른다.

## API

| 메서드 | 경로 | 요청 | 응답 |
| --- | --- | --- | --- |
| GET | `/healthz` | - | `{"status": "ok", "engine": "supertonic", "sample_rate": 44100}` |
| POST | `/synthesize` | `{"out_dir": "/data/jobs/<id>/tts", "sentences": [{"id": "s01", "text": "..."}]}` | `{"sample_rate": 44100, "items": [{"id": "s01", "path": ".../s01.wav", "seconds": 3.26}]}` |

- `out_dir`는 데이터 폴더(`MINIBATCH_DATA_DIR`, 기본 `/data`) 안의 절대 경로만 받는다. 밖이면 400.
- 문장 `id`는 영문·숫자·`_`·`-` 64자 이내, 파일 이름이 된다(`<id>.wav`). 겹치거나 빈 문장이면 422.
- 합성에 실패하면 500, `detail`에 실패한 문장 id. 재시도는 job-api가 정한다.
- 출력: 44.1kHz 모노 16비트 WAV.

## 설정 (환경 변수)

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `MINIBATCH_TTS_ENGINE` | `supertonic` | 엔진 이름 |
| `MINIBATCH_TTS_MODEL_DIR` | `/models/supertonic-3` | 모델 폴더 (이미지에 들어 있다) |
| `MINIBATCH_TTS_VOICE` | `M1` | 목소리 (`voice_styles/` 의 F1~F5, M1~M5) |
| `MINIBATCH_DATA_DIR` | `/data` | 출력을 허용하는 폴더 |

## 테스트

API 테스트(가짜 엔진)는 모델 없이 돈다. 실제 모델 테스트는 모델이 있는 이미지 안에서만 돌고, 없으면 건너뛴다.

```bash
cd ~/personal-projects/minibatch-app
docker build -t minibatch-tts-worker:devtest tts-worker
docker run --rm -v "$PWD/tts-worker/tests":/app/tests:ro -e PYTHONDONTWRITEBYTECODE=1 \
  minibatch-tts-worker:devtest python -m unittest discover -s tests -t .
docker image rm minibatch-tts-worker:devtest
```

`app/vendor/supertonic/`은 원본 저장소(보관 처리됨)의 예제 코드를 그대로 복사한 것이다(MIT). 고치지 않는다.
