# MiniBatch tts-worker: 문장 → WAV (FastAPI). 기본 엔진 Supertonic 3 (아키텍처 D6).
# 1단계: 모델 가중치를 받는다. 저장소가 보관 처리돼 리비전을 고정한다 (기술 조사 R26)
# --include 는 패턴 하나씩 따로 쓴다 (hf 2.2.0: 이어 쓰면 파일 이름으로 해석되고 --include 가 무시된다)
FROM python:3.11.17-slim-bookworm AS model
ARG SUPERTONIC_REVISION=aafc6e32416a594460b32413efc49d7fe4ce6d46
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check huggingface_hub==2.2.0 \
 && hf download supertone-oss-archive/supertonic-3 \
      --revision "$SUPERTONIC_REVISION" \
      --include "onnx/*" --include "voice_styles/*" --include config.json --include LICENSE \
      --local-dir /models/supertonic-3

# 2단계: 실행 이미지
FROM python:3.11.17-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    MINIBATCH_TTS_MODEL_DIR=/models/supertonic-3

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# 모델(약 400MB)은 코드보다 덜 바뀌어 먼저 복사한다
COPY --from=model /models /models
COPY . .

RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8090
# 코드(app/main.py)는 작업 순서 20에서 생긴다
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
