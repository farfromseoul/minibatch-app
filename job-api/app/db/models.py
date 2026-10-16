"""DB 테이블 (아키텍처 "데이터 모델링", D23~D25).

시각은 모두 UTC(시간대 정보 없는 값). 파일 자체는 데이터 폴더에 두고 DB 에는 경로와 해시만 둔다.
테이블을 바꾸면 app/db/migrations/versions/ 에 이전 파일을 더한다 (tests/test_migrations.py 가 어긋남을 잡는다).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Topic(Base):
    __tablename__ = "topic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    normalized_key: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(10))  # user | llm
    status: Mapped[str] = mapped_column(String(20))  # PROPOSED | READY | USED | REJECTED
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    bible: Mapped[dict[str, Any]] = mapped_column(JSON)
    plan_source: Mapped[str] = mapped_column(String(10))  # user | llm
    status: Mapped[str] = mapped_column(String(20))  # PROPOSED | APPROVED | ACTIVE | PAUSED | DONE
    created_at: Mapped[datetime] = mapped_column(DateTime)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Episode(Base):
    __tablename__ = "episode"
    __table_args__ = (UniqueConstraint("series_id", "number", name="uq_episode_series_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    outline: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_teaser: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # PLANNED | IN_PRODUCTION | APPROVED | REJECTED
    job_id: Mapped[Optional[str]] = mapped_column(ForeignKey("job.id"), nullable=True)


class Job(Base):
    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # short-YYYYMMDD-NNN
    topic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topic.id"), nullable=True)
    topic: Mapped[str] = mapped_column(String(200))
    topic_key: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(50))
    series_id: Mapped[Optional[str]] = mapped_column(ForeignKey("series.id"), nullable=True)
    episode_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    video_engine: Mapped[str] = mapped_column(String(20))
    input: Mapped[dict[str, Any]] = mapped_column(JSON)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class StepRun(Base):
    __tablename__ = "step_run"
    __table_args__ = (UniqueConstraint("job_id", "step", "attempt", name="uq_step_run_attempt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id"))
    step: Mapped[str] = mapped_column(String(20))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # running | succeeded | failed
    kind: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # transient | deterministic | quota | degraded
    retry_from: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    retry_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)  # reset 으로 무효가 된 시도
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Artifact(Base):
    __tablename__ = "artifact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id"))
    step: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))  # file | dir
    path: Mapped[str] = mapped_column(String(300))  # 작업 폴더 기준 상대 경로
    sha256: Mapped[str] = mapped_column(String(64))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)


class JobEvent(Base):
    """상태 전이 기록. 추가만 한다 (수정·삭제 없음)."""

    __tablename__ = "job_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id"))
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(100))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime)


class Publication(Base):
    """게시 정보와 승인 기록. approved_at 이 없으면 공개 전환 금지 (성공 기준 5)."""

    __tablename__ = "publication"

    job_id: Mapped[str] = mapped_column(ForeignKey("job.id"), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    video_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    visibility: Mapped[str] = mapped_column(String(20))
    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contains_synthetic_media: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
