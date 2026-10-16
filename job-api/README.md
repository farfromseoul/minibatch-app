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
    steps/              # 단계 구현. 지금은 topic 만 (나머지는 작업 순서 20-d)
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
| GET | `/healthz` | DB, 디스크 여유 |
| GET | `/pipeline` | 단계 순서 |
| POST | `/jobs` | `{topic}` 직접, `{seriesId}` 다음 화, `{}` 자동 선정(시리즈 → 승인된 주제). 중복 주제 409, 앞 화 미승인 409, 하루 한도·검토 적체 409 |
| GET | `/jobs`, `/jobs?status=REVIEW`, `/jobs/{id}` | 조회 (상세에 단계 시도, 산출물, 상태 기록, 게시 정보) |
| POST·GET | `/jobs/{id}/steps/{step}` | 단계 실행 / 상태 |
| POST | `/jobs/{id}/reset?from=<단계>` | 되돌리기 |
| POST | `/jobs/{id}/approve` `{approvedBy, publishAt?}`, `/reject` `{rejectedBy, reason}` | REVIEW 에서만. 시리즈 화면 화·시리즈 상태도 바꾼다 |
| POST·GET | `/series`, `/series/{id}`, `/series/{id}/resume` | 사용자 작성 시리즈 등록(바로 APPROVED), 조회, 멈춘 시리즈 다시 진행 |
| POST·GET | `/topics`, `/topics?status=`, `/topics/{id}/approve`, `/reject` | 사용자 주제 추가(READY), 조회, 자동 생성 주제 승인·반려 |
| POST | `/topics/generate`, `/series`(계획 없이) | 501. LLM 자동 생성은 작업 순서 20-d |

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
