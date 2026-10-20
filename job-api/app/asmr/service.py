"""ASMR 채널 (아키텍처 D38, ASMR쇼츠 기획서 2026-10-20).

사용자가 Google Flow 로 만든 영상을 inbox 에 넣으면(개발 PC 의 asmr-send.sh), 텔레그램 승인 두 번으로 올리고 공개한다.

- 확인(scan): n8n 이 1시간마다 부른다. 점(.)으로 시작하는 파일·폴더는 보지 않는다(보내는 중인 `.incoming/`).
  이름 `YYYYMMDD-NN_제목.mp4|mov`, 세로, 60초 이하만 받는다. 어긴 파일은 rejected/ 로 옮기고 이유를 알린다.
- [업로드 승인] → QUEUED → 비공개 업로드(합성 콘텐츠 표시) → UPLOADED → [공개 승인] → PUBLISHED. [버리기] → REJECTED.
- 하루 업로드 상한(기본 3)을 넘으면 다음 날(한국 날짜) 올린다. 채널 업로드 한도는 1시간 뒤, API 할당량은 리셋 뒤 다시.
- 올리기 전에 토큰의 채널이 설정한 ASMR 채널인지 확인한다. 다르거나 설정이 없으면 올리지 않는다.
- 상태는 DB, 파일 위치는 상태에 맞는 폴더(inbox → uploaded → published, rejected). 재시작해도 이어진다.
"""
from __future__ import annotations

import logging
import re
import shutil
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import func, select

from app.core.errors import ApiError
from app.core.timeutil import kst_day_start_utc
from app.db.models import AsmrVideo
from app.notify.telegram import TelegramError
from app.pipeline.steps.publishing import next_quota_reset
from app.youtube.client import YouTubeError

log = logging.getLogger("job-api.asmr")

NAME = re.compile(r"^(\d{8})-(\d{2})_(.+)\.(mp4|mov)$", re.IGNORECASE)
VIDEO_EXT = {".mp4", ".mov"}
MAX_SEC = 60
TELEGRAM_VIDEO_MAX_BYTES = 45 * 1024 * 1024  # 봇 업로드 한도 50MB 보다 조금 작게
REMIND_SEC = 6 * 3600
MAX_REMIND = 5
HEAD = "🎧 ASMR"
DESCRIPTION = "#ASMR #Shorts #satisfying"
TAGS = ["ASMR", "satisfying", "jelly", "shorts"]
CATEGORY_ID = "24"  # 엔터테인먼트
DISCLOSURE = "이 영상은 AI(Google Veo)로 만든 영상입니다."
FOLDER = {"WAITING_UPLOAD": "inbox", "QUEUED": "inbox", "FAILED": "inbox", "UPLOADED": "uploaded",
          "PUBLISHED": "published", "REJECTED": "rejected", "INVALID": "rejected"}


def summary(v: AsmrVideo) -> dict[str, Any]:
    iso = lambda t: t.isoformat() if t else None  # noqa: E731
    return {"id": v.id, "fileName": v.file_name, "title": v.title, "description": v.description, "status": v.status,
            "videoId": v.video_id, "error": v.error, "retryAt": iso(v.retry_at), "probe": v.probe,
            "uploadedAt": iso(v.uploaded_at), "publishedAt": iso(v.published_at), "createdAt": iso(v.created_at)}


class AsmrService:
    def __init__(self, settings, *, db: Callable, clock: Callable, youtube_factory: Callable, probe: Callable, bot=None):
        self.settings, self.db, self.clock = settings, db, clock
        self.youtube_factory, self.probe, self.bot = youtube_factory, probe, bot
        self._lock = threading.Lock()  # n8n 확인(API)과 텔레그램 버튼(받기 루프)이 같은 영상을 동시에 올리지 않게

    # ---------- 폴더

    def _dir(self, name: str) -> Path:
        return Path(self.settings.asmr_dir) / name

    def _move(self, v: AsmrVideo, to_status: str) -> None:
        """영상과 같은 이름의 .txt 를 새 상태의 폴더로 옮긴다. 같은 이름이 있으면 뒤에 번호를 붙인다"""
        src_dir, dst_dir = self._dir(FOLDER[v.status]), self._dir(FOLDER[to_status])
        if src_dir == dst_dir:
            return
        for src in (src_dir / v.file_name, (src_dir / v.file_name).with_suffix(".txt")):
            if src.exists():
                _move_file(src, dst_dir)

    # ---------- 확인

    def scan(self) -> dict[str, int]:
        found = invalid = 0
        inbox = self._dir("inbox")
        inbox.mkdir(parents=True, exist_ok=True)
        with self._lock:
            for path in sorted(inbox.iterdir()):
                if path.name.startswith(".") or not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
                    continue
                name = unicodedata.normalize("NFC", path.name)
                m = NAME.match(name)
                if not m:
                    for f in (path, path.with_suffix(".txt")):
                        if f.exists():
                            _move_file(f, self._dir("rejected"))
                    self._send(f"⚠️ {HEAD} 이름 규칙(YYYYMMDD-NN_제목.mp4)에 맞지 않아 rejected 로 옮겼습니다: {name}")
                    invalid += 1
                    continue
                vid = f"asmr-{m.group(1)}-{m.group(2)}"
                with self.db() as s:
                    if s.get(AsmrVideo, vid) is not None:
                        continue  # 이미 아는 영상 (같은 번호로 다시 넣은 파일은 그대로 둔다)
                    v = self._record(s, vid, path, m.group(3).strip())
                    s.commit()
                    if v.status == "INVALID":
                        invalid += 1
                        self._send(f"⚠️ {HEAD} 올리지 않음: {v.title}\n{v.error}\n파일은 rejected 로 옮겼습니다.")
                    else:
                        found += 1
                        self._notify(s, v)
                        s.commit()
        uploaded = self.process_queue()
        return {"found": found, "invalid": invalid, "uploaded": uploaded}

    def _record(self, s, vid: str, path: Path, title: str) -> AsmrVideo:
        now = self.clock()
        txt = path.with_suffix(".txt")
        description = txt.read_text(encoding="utf-8").strip() if txt.exists() else DESCRIPTION
        try:
            probe = self.probe(path)
            problems = _problems(probe)
        except Exception as e:  # 깨진 파일 등
            probe, problems = {}, [f"영상을 읽지 못했습니다({type(e).__name__})"]
        v = AsmrVideo(id=vid, file_name=path.name, title=title[:200], description=description, size=path.stat().st_size,
                      probe=probe, status="WAITING_UPLOAD", created_at=now, updated_at=now)
        s.add(v)
        if problems:
            v.error = "; ".join(problems)
            self._move(v, "INVALID")
            v.status = "INVALID"
        return v

    # ---------- 버튼 (텔레그램·API 같은 규칙)

    def _get(self, s, vid: str) -> AsmrVideo:
        v = s.get(AsmrVideo, vid)
        if v is None:
            raise ApiError(404, "asmr_not_found", f"영상이 없다: {vid}")
        return v

    def approve_upload(self, vid: str, who: str) -> str:
        with self._lock, self.db() as s:
            v = self._get(s, vid)
            if v.status not in ("WAITING_UPLOAD", "FAILED"):
                raise ApiError(409, "asmr_state", f"업로드 승인 대기가 아니다. 지금: {v.status}")
            now = self.clock()
            v.status, v.approved_by, v.upload_approved_at, v.retry_at, v.error, v.updated_at = "QUEUED", who, now, None, None, now
            s.commit()
            return f"✅ 업로드 승인: {v.title}. 곧 비공개로 올립니다"

    def publish(self, vid: str, who: str) -> str:
        with self._lock, self.db() as s:
            v = self._get(s, vid)
            if v.status != "UPLOADED" or not v.video_id:
                raise ApiError(409, "asmr_not_uploaded", f"비공개 업로드가 끝난 영상만 공개한다. 지금: {v.status}")
            try:
                self.youtube_factory(self.settings).set_privacy(v.video_id, "public")
            except YouTubeError as e:  # 버튼을 남겨 다시 누를 수 있게
                raise ApiError(502, f"youtube_{e.kind}", e.message) from e
            now = self.clock()
            self._move(v, "PUBLISHED")
            v.status, v.published_at, v.updated_at = "PUBLISHED", now, now
            s.commit()
            return f"✅ 공개: {v.title}\nhttps://www.youtube.com/shorts/{v.video_id}"

    def reject(self, vid: str, who: str) -> str:
        with self._lock, self.db() as s:
            v = self._get(s, vid)
            if v.status not in ("WAITING_UPLOAD", "QUEUED", "FAILED", "UPLOADED"):
                raise ApiError(409, "asmr_state", f"버릴 수 없는 상태다: {v.status}")
            tail = " (YouTube 의 비공개 영상은 그대로 둡니다)" if v.status == "UPLOADED" else ""
            now = self.clock()
            self._move(v, "REJECTED")
            v.status, v.rejected_at, v.updated_at = "REJECTED", now, now
            s.commit()
            return f"🗑 버림: {v.title}{tail}"

    # ---------- 올리기

    def process_queue(self) -> int:
        """승인된 영상을 올린다. 하루 상한·다시 할 시각을 지킨다"""
        done = 0
        with self._lock, self.db() as s:
            now = self.clock()
            day = kst_day_start_utc(now)
            count = s.scalar(select(func.count()).select_from(AsmrVideo).where(AsmrVideo.uploaded_at >= day)) or 0
            queue = s.scalars(select(AsmrVideo).where(AsmrVideo.status == "QUEUED")
                              .order_by(AsmrVideo.upload_approved_at, AsmrVideo.id)).all()
            for v in queue:
                if v.retry_at is not None and v.retry_at > now:
                    continue
                if count >= self.settings.asmr_daily_upload_limit:
                    v.retry_at, v.updated_at = day + timedelta(days=1), now
                    self._send(f"{HEAD} 오늘 {count}편을 올려 내일 올립니다: {v.title}")
                    continue
                if self._upload(s, v, now):
                    count += 1
                    done += 1
                s.commit()
            s.commit()
        return done

    def _upload(self, s, v: AsmrVideo, now: datetime) -> bool:
        path = self._dir("inbox") / v.file_name
        try:
            if not path.exists():
                raise YouTubeError("deterministic", f"파일이 없다: inbox/{v.file_name}")
            youtube = self.youtube_factory(self.settings)
            self._check_channel(youtube)
            res = youtube.upload_video(path, title=v.title, description=v.description, disclosure=DISCLOSURE,
                                       category_id=CATEGORY_ID, tags=TAGS, synthetic=True,
                                       content_type="video/quicktime" if path.suffix.lower() == ".mov" else "video/mp4")
        except YouTubeError as e:
            self._failed(v, e, now)
            return False
        self._move(v, "UPLOADED")
        v.status, v.video_id, v.uploaded_at, v.error, v.retry_at, v.updated_at = "UPLOADED", res["id"], now, None, None, now
        self._notify(s, v)
        return True

    def _check_channel(self, youtube) -> None:
        want = self.settings.asmr_channel_id
        if not want:
            raise YouTubeError("deterministic", "ASMR 채널 ID 설정(MINIBATCH_ASMR_CHANNEL_ID)이 없어 올리지 않았다")
        got = youtube.my_channel_id()
        if got != want:
            raise YouTubeError("deterministic", f"토큰의 채널({got})이 ASMR 채널({want})과 달라 올리지 않았다")

    def _failed(self, v: AsmrVideo, e: YouTubeError, now: datetime) -> None:
        first = v.error != e.message
        v.error, v.updated_at = e.message, now
        if e.kind == "deterministic":
            v.status = "FAILED"
            self._send(f"⚠️ {HEAD} 업로드 실패: {v.title}\n{e.message}",
                       [("다시 업로드", f"ua:{v.id}"), ("버리기", f"ux:{v.id}")])
            return
        if e.kind == "quota" and e.reason != "uploadLimitExceeded":
            v.retry_at = datetime.strptime(next_quota_reset(now.replace(tzinfo=timezone.utc)), "%Y-%m-%dT%H:%M:%SZ")
        else:  # 채널 업로드 한도는 지난 24시간 기준이라 1시간마다 (MiniBatch 2026-10-19 실제), 일시 오류도 1시간 뒤
            v.retry_at = now + timedelta(hours=1)
        if first:
            self._send(f"{HEAD} 업로드를 미룹니다({e.kind}): {v.title}\n{e.message}\n다음 시도: 한국 시각 "
                       f"{(v.retry_at + timedelta(hours=9)).strftime('%m-%d %H:%M')}")

    # ---------- 알림

    def _send(self, text: str, buttons=None) -> None:
        if self.bot is None:
            return
        try:
            self.bot.send(text, buttons)
        except TelegramError as e:
            log.warning("텔레그램 보내기 실패: %s", e)

    def _notify(self, s, v: AsmrVideo, reminder: bool = False) -> None:
        """지금 상태의 승인 요청(업로드 승인 또는 공개 승인)을 보낸다"""
        prefix = "⏰ 다시 알림 · " if reminder else ""
        if v.status == "UPLOADED":
            text = (f"{prefix}{HEAD} 비공개로 올렸습니다: {v.title}\nhttps://www.youtube.com/shorts/{v.video_id}\n"
                    "확인한 뒤 공개하세요.")
            self._send(text, [("공개 승인", f"up:{v.id}"), ("버리기", f"ux:{v.id}")])
        else:
            p = v.probe or {}
            lines = [f"{prefix}{HEAD} 업로드 승인 대기: {v.title}", f"파일: {v.file_name}",
                     f"{float(p.get('durationSec', 0)):.1f}초 · {p.get('width')}x{p.get('height')}"]
            if not p.get("audio"):
                lines.append("⚠️ 소리 없음")
            lines.append(f"설명: {v.description[:300]}")
            text, buttons = "\n".join(lines), [("업로드 승인", f"ua:{v.id}"), ("버리기", f"ux:{v.id}")]
            path = self._dir("inbox") / v.file_name
            sent = False
            if not reminder and self.bot is not None and path.exists() and path.stat().st_size <= TELEGRAM_VIDEO_MAX_BYTES:
                try:
                    self.bot.send_video(path, text, buttons)
                    sent = True
                except TelegramError as e:  # 미리보기가 실패하면 글로만
                    log.warning("텔레그램 영상 보내기 실패: %s", e)
            if not sent:
                self._send(text, buttons)
        v.notified_at = self.clock()

    def remind_due(self) -> None:
        """승인 대기(업로드·공개)가 6시간 넘게 남으면 다시 알린다 (영상마다 6시간에 한 번, 한 번에 최대 5개)"""
        with self._lock, self.db() as s:
            now = self.clock()
            waiting = s.scalars(select(AsmrVideo).where(AsmrVideo.status.in_(["WAITING_UPLOAD", "UPLOADED"]))
                                .order_by(AsmrVideo.created_at, AsmrVideo.id)).all()
            due = [v for v in waiting if (now - (v.notified_at or v.updated_at)).total_seconds() >= REMIND_SEC]
            for v in due[:MAX_REMIND]:
                self._notify(s, v, reminder=True)
            s.commit()

    # ---------- 조회

    def counts(self) -> dict[str, Any]:
        with self.db() as s:
            rows = s.execute(select(AsmrVideo.status, func.count()).group_by(AsmrVideo.status)).all()
            today = s.scalar(select(func.count()).select_from(AsmrVideo)
                             .where(AsmrVideo.uploaded_at >= kst_day_start_utc(self.clock()))) or 0
        return {"counts": {k: n for k, n in rows}, "uploadedToday": today, "limit": self.settings.asmr_daily_upload_limit}

    def list(self, status: Optional[str]) -> list[dict[str, Any]]:
        with self.db() as s:
            q = select(AsmrVideo).order_by(AsmrVideo.created_at, AsmrVideo.id)
            if status:
                q = q.where(AsmrVideo.status == status)
            return [summary(v) for v in s.scalars(q)]

    def get(self, vid: str) -> dict[str, Any]:
        with self.db() as s:
            return summary(self._get(s, vid))


def _problems(probe: dict[str, Any]) -> list[str]:
    out = []
    w, h, sec = int(probe.get("width") or 0), int(probe.get("height") or 0), float(probe.get("durationSec") or 0)
    if not w or not h:
        out.append("영상 트랙이 없습니다")
    elif h <= w:
        out.append(f"세로 영상이 아닙니다({w}x{h}). 9:16 으로 만들어 주세요")
    if sec <= 0 or sec > MAX_SEC:
        out.append(f"길이가 {sec:.1f}초입니다. {MAX_SEC}초 이하만 올립니다")
    return out


def _move_file(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    n = 1
    while dst.exists():  # 덮어쓰지 않는다
        dst = dst_dir / f"{src.stem}-{n}{src.suffix}"
        n += 1
    shutil.move(str(src), str(dst))
    return dst
