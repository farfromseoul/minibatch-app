"""tts-worker: 문장 목록 → 문장별 WAV (아키텍처 "구성 요소", 앱 설계 "TTS 작업자").

job-api 만 internal 망에서 부른다. 출력은 공유 데이터 폴더(/data) 안에만 쓴다.
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from .engines import Engine, load_engine

log = logging.getLogger("tts-worker")

SENTENCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class Sentence(BaseModel):
    id: str = Field(pattern=SENTENCE_ID.pattern)
    text: str

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("빈 문장")
        return v


class SynthesizeRequest(BaseModel):
    out_dir: str
    voice: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,32}$")  # 없으면 엔진 기본 목소리
    speed: Optional[float] = Field(default=None, ge=0.7, le=1.3)  # 말 빠르기 배수. 없으면 엔진 기본 (목록형 쇼츠 D42, 2026-10-31)
    sentences: list[Sentence] = Field(min_length=1)

    @field_validator("sentences")
    @classmethod
    def unique_ids(cls, v: list[Sentence]) -> list[Sentence]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("문장 id 가 겹친다")
        return v


class SentenceAudio(BaseModel):
    id: str
    path: str
    seconds: float


class SynthesizeResponse(BaseModel):
    sample_rate: int
    items: list[SentenceAudio]


def _inside(base: Path, target: Path) -> bool:
    base, target = base.resolve(), target.resolve()
    return target == base or base in target.parents


def create_app(engine: Optional[Engine] = None, data_dir: Optional[Path] = None) -> FastAPI:
    """engine·data_dir 를 주지 않으면 환경 변수로 정한다 (테스트는 가짜 엔진을 넣는다)."""
    state: dict = {"engine": engine,
                   "data_dir": Path(data_dir or os.environ.get("MINIBATCH_DATA_DIR", "/data"))}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if state["engine"] is None:
            state["engine"] = load_engine(
                os.environ.get("MINIBATCH_TTS_ENGINE", "supertonic"),
                Path(os.environ.get("MINIBATCH_TTS_MODEL_DIR", "/models/supertonic-3")),
                os.environ.get("MINIBATCH_TTS_VOICE", "M1"),
            )
            log.info("엔진 준비: %s, %s Hz", state["engine"].name, state["engine"].sample_rate)
        yield

    app = FastAPI(title="minibatch tts-worker", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict:
        eng = state["engine"]
        return {"status": "ok", "engine": eng.name, "sample_rate": eng.sample_rate}

    # 합성은 CPU 를 오래 쓰므로 일반 함수로 둔다 (FastAPI 가 스레드에서 실행한다)
    @app.post("/synthesize", response_model=SynthesizeResponse)
    def synthesize(req: SynthesizeRequest) -> SynthesizeResponse:
        out_dir = Path(req.out_dir)
        if not out_dir.is_absolute() or not _inside(state["data_dir"], out_dir):
            raise HTTPException(400, f"out_dir 는 데이터 폴더({state['data_dir']}) 안이어야 한다")
        eng = state["engine"]
        if req.voice and not eng.has_voice(req.voice):
            raise HTTPException(400, f"없는 목소리: {req.voice}")
        out_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for s in req.sentences:
            path = out_dir / f"{s.id}.wav"
            try:
                seconds = eng.synthesize(s.text, path, voice=req.voice, speed=req.speed)
            except Exception as e:  # 어느 문장에서 실패했는지 돌려준다. job-api 가 재시도를 정한다
                log.exception("합성 실패: %s", s.id)
                raise HTTPException(500, f"문장 {s.id} 합성 실패: {type(e).__name__}: {e}")
            items.append(SentenceAudio(id=s.id, path=str(path), seconds=round(seconds, 4)))
        return SynthesizeResponse(sample_rate=eng.sample_rate, items=items)

    return app


app = create_app()
