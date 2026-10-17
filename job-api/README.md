# job-api

MiniBatch의 중심 백엔드. 작업 상태(SQLite), 단계 하나씩 실행(단계 API), 승인 기록, 시리즈·주제를 맡는다. 단계의 **순서는 n8n이 지휘**하고 job-api는 요청받은 단계 하나를 규칙대로 실행한다(아키텍처 절충안 C, D2·D21).

## 구조

```text
app/
  main.py               # create_app(): 설정, DB 이전, 실행기, 재시작 복구
  core/                 # 설정(환경 변수), 토큰 인증, 오류 응답 형식, 시각
  db/                   # 테이블(models.py), 연결(session.py), Alembic 이전(migrations/)
  domain/               # 작업 만들기·중복 검사·자동 선정, 상태 바꾸기, 승인·반려, 시리즈, 주제
  pipeline/
    pipeline.py         # 단계 순서 PIPELINE
    runner.py           # 단계 실행 규칙 1~8
    files.py            # 해시 (멱등 판정)
    steps/              # 단계 구현: topic, script, review, scenes, tts, timeline, visuals, render, qc, upload
  media/ffmpeg.py       # ffprobe·ffmpeg 측정 (qc)
  youtube/client.py     # YouTube Data API: 갱신 토큰, 재개 가능한 업로드, 재생목록, 공개 범위, 설명란
  publish/approve.py    # 승인 뒤 공개 전환, 앞 화 설명란 다음 화 링크 (승인 기록 검사는 YouTube 호출 바로 앞)
  llm/                  # LLM 연결부, 재요청, 프롬프트 파일
  providers.py          # providers.yaml 읽기·검사
  schemas/templates.py  # 템플릿 속성 규격
  api/                  # HTTP 경로와 응답 모양
content/categories/     # 카테고리 설정 묶음 (D23). 지금은 ai-it 하나
tests/                  # 단위 테스트 (unittest)
```

## 단계 실행 규칙 (`POST /jobs/{id}/steps/{step}`)

| 규칙 | 동작 | 응답 |
| --- | --- | --- |
| 1 순서 | 앞 단계가 모두 성공해야 실행 | `409 previous_step_incomplete` |
| 2 한 번에 하나 | 전역 잠금. 다른 단계가 돌면 거절 | `409 busy` |
| 3 멱등 | 입력 해시가 같고 출력 파일이 기록과 같으면 다시 하지 않음 | `200 already_done` |
| 4 비동기 | 시작하고 바로 응답. 끝나면 `resumeUrl`(n8n)을 부름 | `202 started` |
| 5 원자적 쓰기 | 임시 이름으로 쓰고 이름 바꾸기. 실패하면 이번 시도가 쓴 파일을 지움 | |
| 6 기록 | 출력 해시를 `artifact`, 시도 결과를 `step_run`에. 마지막 단계면 `REVIEW` | |
| 7 되돌리기 | `POST /jobs/{id}/reset?from=X`: X부터의 출력을 `attempt-N/`으로 옮기고 "아직 안 함"으로 | |
| 8 재시작 복구 | 시작할 때 `running`으로 남은 시도를 `transient` 실패로 | |

실패 종류: `deterministic`(작업 FAILED, `retryFrom` 제안), `quota`(WAITING, `retryAt`), `transient`(같은 단계 3번째면 FAILED), `degraded`(성공으로 치고 기록만). FAILED·REJECTED 작업은 reset 뒤에 다시 실행한다.

## 경로

모두 `Authorization: Bearer <토큰>`이 필요하다(`/healthz` 제외). 오류는 `{"error": {"code", "message"}}`.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/healthz` | DB, 디스크 여유, LLM 서버·tts-worker·render-worker 응답, YouTube 갱신 토큰(없음·6일 지남 경고). 작업자가 죽어도 200 + 경고 |
| GET | `/pipeline` | 단계 순서 |
| POST | `/jobs` | `{topic}` 직접, `{seriesId}` 다음 화, `{}` 자동 선정(시리즈 → 승인된 주제). 중복 주제 409, 앞 화가 아직 다 만들어지지 않음(REVIEW 전) 409 `previous_episode_not_ready`(D27: 승인 전이라도 다음 화를 미리 만든다), 하루 한도·검토 적체 409 |
| GET | `/jobs`, `/jobs?status=REVIEW`, `/jobs/{id}` | 조회 (상세에 단계 시도, 산출물, 상태 기록, 게시 정보) |
| POST·GET | `/jobs/{id}/steps/{step}` | 단계 실행 / 상태 |
| POST | `/jobs/{id}/reset?from=<단계>` | 되돌리기 |
| POST | `/jobs/{id}/approve` `{approvedBy, publishAt?}`, `/reject` `{rejectedBy, reason}` | REVIEW 에서만. 시리즈 화면 화·시리즈 상태도 바꾼다. 시리즈 N화는 N-1화가 승인된 뒤에만 승인(409 `previous_episode_not_approved`). N화를 반려하면 시리즈 PAUSED, 미리 만든 N+1화 이후는 REJECTED 로 정리(resume 하면 N화부터 다시). 승인은 영상이 올라가 있으면 바로 공개 전환(`publishAt`이 미래면 예약): 응답 `publish` = `{ok, status}` 또는 `{ok: false, kind, error}`(승인은 남고 APPROVED) |
| POST | `/jobs/{id}/cancel` `{cancelledBy, reason}` | 공개 전 작업 취소 → CANCELLED (다시 실행 안 함, 올린 비공개 영상은 그대로). 시리즈 화면 화 CANCELLED·시리즈 PAUSED. 공개된 작업 409 `not_cancellable` (D29) |
| POST | `/series/{id}/cancel` `{cancelledBy, reason}` | 시리즈 취소 → CANCELLED. 승인 안 된 화·공개 전 작업도 CANCELLED, 공개된 화는 그대로. 취소된 시리즈로 작업을 만들면 409 `series_cancelled` |
| POST | `/jobs/{id}/publish` | APPROVED 작업의 공개 전환을 다시 한다. 시리즈 N화면 N-1화 설명란에 다음 화 링크(실패하면 `warnings`). 승인 기록 없음 409 `not_approved`, YouTube 실패 502 `youtube_<transient\|quota\|deterministic>` |
| POST·GET | `/series`, `/series/{id}`, `/series/{id}/resume` | 사용자 작성 시리즈 등록(바로 APPROVED), 조회, 멈춘 시리즈 다시 진행 |
| GET | `/series`, `/series?status=` | 시리즈 목록과 화 상태별 개수 `counts {total, planned, inProduction, approved, rejected}`. n8n 이 남은 화가 부족한지 본다 |
| POST·GET | `/topics`, `/topics?status=`, `/topics/{id}/approve`, `/reject` | 사용자 주제 추가(READY), 조회, 자동 생성 주제 승인·반려 |
| POST | `/topics/generate` `{category, count}` | LLM 이 주제 후보를 만들어 PROPOSED 로 저장 (기존·중복 제외). 단계와 같은 전역 잠금(409 busy), LLM 없음 503 |
| POST | `/series` `{episodeCount, key?, title?}` (계획 없이) | LLM 이 설정(bible)·화별 계획을 만들어 PROPOSED. title 이 없으면 LLM 이 예전 시리즈와 겹치지 않는 제목도 정하고, key 가 없으면 `s<한국 날짜>-<순번>` |
| POST | `/series/{id}/approve` `{approvedBy, episodes?, bible?}` | 승인 대기 시리즈 승인 (고친 계획 반영) |

## LLM 단계 (script · review · scenes)

| 단계 | 하는 일 | 실패 |
| --- | --- | --- |
| script | 카테고리 파일(대상·구조·금지)과 시리즈의 지난 이야기로 대본. 목표 글자 수 = 60초 × `chars_per_sec` × 0.9. 문장을 넉넉히 받고 길면 코드가 끝 설명 문장부터 뺀다 | 문장 40자 초과·시리즈 필드 누락이 3번 남으면 deterministic(`retry_from=script`). 글자 수만 모자라면 degraded |
| review | 규칙 검사(금칙어·숫자 경고, 문장 길이) + LLM 자기 검토 | critical → deterministic(`retry_from=script`) |
| scenes | 문장 **번호**를 장면에 나누고 템플릿·속성 선택. 문장은 코드가 채운다 | 번호 누락·순서, 장면당 1~4문장, 첫 hook·끝 summary, 템플릿 3연속, 속성 규격 → 3번 남으면 deterministic(`retry_from=scenes`) |

- LLM 연결부: `app/llm/openai_compatible.py` (LM Studio). 답이 `content`가 아니라 `reasoning_content`에 와도 회수한다. 서버 오류·시간 초과는 transient.
- 프롬프트: `app/llm/prompts/*.md`. 해시가 산출물 `meta.promptVersion`.
- 템플릿 속성 규격: `app/schemas/templates.py` (render 의 `src/lib/timeline.ts`와 같은 규칙. 바꿀 때 함께).
- 제공자: `providers.yaml`(`MINIBATCH_PROVIDERS_FILE`). 시작할 때 검사하고 틀리면 시작하지 않는다. TTS 에 `chars_per_sec` 필요.

## 작업자 단계 (tts · timeline · visuals · render)

| 단계 | 하는 일 | 실패 |
| --- | --- | --- |
| tts | 발음 사전(`content/pronunciation.yaml`) 적용 → tts-worker `POST /synthesize`(카테고리 목소리) → `tts/`, `tts.json`(원문·읽는 문장·길이) | 연결 실패·시간 초과·5xx transient, 4xx deterministic |
| timeline | 음성 길이로 장면·자막·음성 시작 프레임 확정(`app/pipeline/timeline_calc.py`) | 55~65초 밖이면 deterministic `retry_from=script` |
| visuals | 생성 클립 장면만 처리. `clip_engine: none`이면 그대로 통과 | 생성기는 Phase 2 |
| render | render-worker `POST /render`(`MINIBATCH_RENDER_WORKER_URL`) → `render/final.mp4` → job-api 가 ffmpeg `loudnorm`(두 번: 재고 바꾸기)으로 오디오만 -14 LUFS·최대 -1.5 dBTP 로 맞춤(영상은 복사) | 409·5xx transient, 422 deterministic `retry_from=scenes`, 음량 맞추기 실패 deterministic `retry_from=render` |

## 게시 단계 (qc · upload)

| 단계 | 하는 일 | 실패 |
| --- | --- | --- |
| qc | ffprobe·ffmpeg(`ebur128`, `silencedetect`)로 길이 55~65초, 1080×1920·30fps, 프레임 수 ±1, AAC 1개, 무음 2.5초 이하, 자막이 영상 안·겹침 없음, 음량 -14±2 LUFS → `qc.json` | deterministic. `retry_from` = 길이 script, 자막 scenes, 무음 tts, 해상도·프레임·오디오·음량 render (어긋난 것 중 가장 앞) |
| upload | 비공개 업로드(제목: 시리즈면 `시리즈 N화: 화 제목`, 아니면 제목 후보 1번. 설명: 후킹·요약·해시태그·시리즈 재생목록 링크, 끝에 고지 문구는 연결부가 항상 붙임). 시리즈면 재생목록(공개)을 처음 한 번 만들고 끝에 넣음 → `upload.json` | 할당량 quota(`retryAt` 태평양 자정 5분 뒤), 연결·5xx transient, 토큰 만료·4xx deterministic. 같은 파일은 다시 올리지 않음(`publication.uploaded_sha256`), 다시 렌더하면 새로 올리고 `replaces`에 앞 영상 ID |

## 텔레그램 승인 (D28)

작업이 REVIEW 가 되면 영상 링크와 [승인(공개)] [반려] 버튼, LLM 시리즈 계획이 만들어지면 [계획 승인] 버튼을 텔레그램으로 보낸다. 버튼 응답은 getUpdates(30초 롱 폴링)로 가져온다. 나가는 연결만 쓴다. `MINIBATCH_TELEGRAM_CHAT_ID` 대화에서 온 응답만 처리하고, 승인은 API 와 같은 함수(`app/publish/approve.py` `approve_and_publish`)로 한다. 처리 결과는 같은 메시지를 고쳐 버튼을 없앤다. 토큰 파일이나 chat id 가 없으면 이 기능만 꺼진다.

## 설정 (환경 변수)

| 이름 | 기본값 |
| --- | --- |
| `MINIBATCH_DATA_DIR` | `/data` |
| `MINIBATCH_DB_PATH` | `/data/db/minibatch.sqlite` |
| `MINIBATCH_JOB_API_TOKEN_FILE` | `/run/secrets/job_api_token` (없거나 16자 미만이면 시작하지 않음) |
| `MINIBATCH_CONTENT_DIR` | `/app/content` |
| `MINIBATCH_DAILY_JOB_LIMIT` / `MINIBATCH_REVIEW_BACKLOG_LIMIT` | 3 / 6 (자동 선정에만 적용) |
| `MINIBATCH_DISK_FREE_WARN_GB` | 50 |
| `MINIBATCH_RESUME_URL_PREFIX` | `http://n8n:5678/` (재개 주소는 이 주소로 시작해야 함) |
| `MINIBATCH_PROVIDERS_FILE` | `/etc/minibatch/providers.yaml` (없거나 틀리면 시작하지 않음) |
| `MINIBATCH_RENDER_WORKER_URL` | `http://render-worker:8091` |
| `MINIBATCH_YOUTUBE_CLIENT_FILE` | `/run/secrets/youtube_client` (데스크톱 앱 클라이언트 JSON) |
| `MINIBATCH_TELEGRAM_TOKEN_FILE` / `MINIBATCH_TELEGRAM_CHAT_ID` | `/run/secrets/telegram_bot_token` / 빈 값 (둘 다 있어야 텔레그램 승인이 켜짐) |
| `MINIBATCH_YOUTUBE_TOKEN_FILE` | `/run/minibatch/youtube-token/youtube_token.json` (실행계획 15번에서 만든 갱신 토큰. 없어도 서버는 뜨고 upload·publish 가 deterministic 실패) |

uvicorn 작업자(worker)는 하나로 띄운다. 전역 잠금이 프로세스 안의 잠금이다.

## 테스트

```bash
cd ~/personal-projects/minibatch-app/job-api

# ① 빠른 테스트 (일반 Python 컨테이너)
docker run --rm -v "$PWD":/src:ro -w /src -v minibatch-dev-uv-cache:/root/.cache/uv \
  -e UV_PROJECT_ENVIRONMENT=/tmp/venv -e PYTHONDONTWRITEBYTECODE=1 -e UV_LINK_MODE=copy \
  python:3.12.15-slim-bookworm sh -c '
    pip install -q --root-user-action=ignore --disable-pip-version-check uv==0.13.1 &&
    uv sync -q --locked --no-install-project &&
    /tmp/venv/bin/python -m unittest discover -s tests -t .'

# ② 이미지 안
cd ..
docker build -q -t minibatch-job-api:devtest job-api
docker run --rm -v "$PWD/job-api/tests":/app/tests:ro -e PYTHONDONTWRITEBYTECODE=1 \
  minibatch-job-api:devtest python -m unittest discover -s tests -t .
docker image rm minibatch-job-api:devtest
```

테이블을 바꾸면 `app/db/migrations/versions/`에 이전 파일을 더한다. `tests/test_migrations.py`가 이전 파일과 `models.py`의 어긋남을 잡는다.
