# MiniBatch job-api: 단계 API(FastAPI). 버전은 2026-10-16 조회 (실행계획 7단계).
FROM python:3.12.15-slim-bookworm

# uv: 잠금 파일(uv.lock) 그대로 설치하는 도구. 공식 이미지에서 실행 파일만 복사한다
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

# ffmpeg: qc 단계의 ffprobe·음량·무음 검사 (앱 설계 "품질 검사")
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 의존성만 먼저 설치한다. 코드만 바뀌면 이 층은 캐시를 그대로 쓴다
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . .

# root 가 아닌 사용자로 실행한다
RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8080
# 코드(app/main.py)는 작업 순서 20에서 생긴다. 빈 빌드에서는 실행하지 않는다
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
