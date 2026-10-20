"""현황 한눈에 보기 (2026-10-20 사용자).

n8n 실행 기록만으로는 "몇 화까지 만들었나, 만들었는데 업로드에서 막혔나, 새 계획은 보냈나·승인됐나"를 알기 어렵다.
GET /overview(n8n 0번 현황 폼)와 텔레그램 /status 가 이 모듈 하나로 같은 내용을 보여 준다. 읽기만 한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import iso, kst_day_start_utc
from app.db.models import Episode, Job, Publication, Series, StepRun
from app.domain import series_order

STEP_KO = {"topic": "주제", "script": "대본", "review": "대본 검토", "scenes": "장면", "tts": "음성",
           "timeline": "타임라인", "visuals": "소재", "render": "렌더", "qc": "품질 검사", "upload": "업로드"}
SERIES_KO = {"PROPOSED": "📝 계획 승인 대기", "APPROVED": "승인됨(앞 시리즈가 끝나면 시작)", "ACTIVE": "진행 중",
             "PAUSED": "⏸ 멈춤"}
OPEN_SERIES = ("PROPOSED", "APPROVED", "ACTIVE", "PAUSED")
CLOSED_JOBS = ("PUBLISHED", "SCHEDULED", "CANCELLED", "REJECTED")


def kst(value: Any) -> str:
    """UTC(시간대 없는 값 또는 ...Z 문자열) → 한국 시각 'MM-DD HH:MM'"""
    if value is None:
        return "?"
    if isinstance(value, str):
        value = datetime.strptime(value.rstrip("Z")[:19], "%Y-%m-%dT%H:%M:%S")
    return (value + timedelta(hours=9)).strftime("%m-%d %H:%M")


def _last_run(s: Session, job_id: str) -> Optional[StepRun]:
    return s.scalar(select(StepRun).where(StepRun.job_id == job_id, StepRun.superseded.is_(False))
                    .order_by(StepRun.started_at.desc(), StepRun.id.desc()).limit(1))


def job_label(s: Session, job: Job) -> str:
    st = job.status
    pub = s.get(Publication, job.id)
    step = STEP_KO.get(job.current_step or "", job.current_step or "")
    if st == "PUBLISHED":
        return "✅ 공개"
    if st == "SCHEDULED":
        return f"🕒 예약 공개 {kst(pub.publish_at if pub else None)}"
    if st == "APPROVED":
        return "🟢 승인됨, 공개 전환이 안 됨 (n8n 2번 폼 또는 POST /jobs/{id}/publish 로 다시)"
    if st == "REVIEW":
        return "🟠 검토 대기: 비공개로 올라감, 텔레그램 [승인(공개)] 필요" if pub and pub.video_id else "🟠 검토 대기"
    if st == "RUNNING":
        return f"🔵 만드는 중 ({step} 단계)"
    if st == "PENDING":
        return "🟡 만들 차례 (다음 생산 시각에 이어서)"
    if st == "WAITING":
        run = _last_run(s, job.id)
        if run is not None and run.kind == "quota":
            return f"⏳ {STEP_KO.get(run.step, run.step)} 한도 대기 · 다음 시도 {kst(run.retry_at)}"
        if run is not None and run.kind == "blocked":
            return f"⏳ 앞 화를 기다림: {run.error or ''}"
        return f"⏳ 기다림: {job.error_summary or ''}"
    if st == "FAILED":
        return f"🔴 실패 ({step} 단계): {(job.error_summary or '')[:120]}"
    if st == "REJECTED":
        return "❌ 반려"
    if st == "CANCELLED":
        return "⛔ 취소"
    return st


def _episode(s: Session, e: Episode) -> dict[str, Any]:
    job = s.get(Job, e.job_id) if e.job_id else None
    if job is not None:
        state, label = job.status, job_label(s, job)
    else:
        state = e.status
        label = {"PLANNED": "⚪ 아직 안 만듦", "REJECTED": "❌ 반려"}.get(e.status, e.status)
    pub = s.get(Publication, job.id) if job else None
    return {"number": e.number, "title": e.title, "state": state, "label": label, "jobId": e.job_id,
            "url": f"https://www.youtube.com/shorts/{pub.video_id}" if pub and pub.video_id else None}


def build(s: Session, now: datetime, *, plan_sent: dict[str, str], question: dict[str, Any],
          asmr: Optional[dict[str, Any]]) -> dict[str, Any]:
    series = []
    for x in s.scalars(select(Series).where(Series.status.in_(OPEN_SERIES)).order_by(Series.created_at, Series.id)):
        eps = s.scalars(select(Episode).where(Episode.series_id == x.id).order_by(Episode.number)).all()
        series.append({"id": x.id, "title": x.title, "status": x.status, "sequence": series_order.sequence(s, x),
                       "createdAt": iso(x.created_at), "approvedAt": iso(x.approved_at),
                       "telegramSentAt": plan_sent.get(x.id), "episodes": [_episode(s, e) for e in eps]})
    standalone = [{"id": j.id, "topic": j.topic, "state": j.status, "label": job_label(s, j)}
                  for j in s.scalars(select(Job).where(Job.series_id.is_(None), Job.status.notin_(CLOSED_JOBS))
                                     .order_by(Job.created_at))]
    uploads = s.scalar(select(func.count()).select_from(StepRun).where(
        StepRun.step == "upload", StepRun.status == "succeeded", StepRun.finished_at >= kst_day_start_utc(now))) or 0
    out = {"at": iso(now), "uploadsToday": uploads, "series": series, "standalone": standalone,
           "question": question, "asmr": asmr}
    out["text"] = render(out, now)
    return out


def render(ov: dict[str, Any], now: datetime) -> str:
    lines = [f"📊 MiniBatch 현황 · {kst(now)}", f"오늘 업로드 {ov['uploadsToday']}편"]
    for x in ov["series"]:
        head = f"{x['sequence']}번째 시리즈" if x.get("sequence") else "시리즈"
        if x["status"] == "PROPOSED":
            sent = f"텔레그램 보냄 {kst(datetime.fromisoformat(x['telegramSentAt']))}" if x.get("telegramSentAt") else "텔레그램 보낸 기록 없음"
            lines += ["", f"[다음 계획] {x['title']} ({x['id']}, {len(x['episodes'])}화)",
                      f"  📝 승인 대기 · {sent}", "  승인: 텔레그램 [계획 승인] 또는 n8n 3번 계획 폼 · 취소: n8n 5번 폼"]
            continue
        lines += ["", f"[{head}] {x['title']} ({x['id']}) · {SERIES_KO.get(x['status'], x['status'])}"]
        lines += [f"  {e['number']}화 {e['title']} — {e['label']}" for e in x["episodes"]]
    if ov["standalone"]:
        lines += ["", "[단독 영상]"] + [f"  {j['topic']} ({j['id']}) — {j['label']}" for j in ov["standalone"]]
    lines += ["", f"[주제 질문] {ov['question'].get('label', '')}"]
    a = ov.get("asmr")
    if a:
        c = a["counts"]
        lines += ["", f"[ASMR] 업로드 승인 대기 {c.get('WAITING_UPLOAD', 0)} · 올릴 차례 {c.get('QUEUED', 0)} · "
                      f"공개 승인 대기 {c.get('UPLOADED', 0)} · 실패 {c.get('FAILED', 0)} · 오늘 업로드 {a['uploadedToday']}/{a['limit']}"]
    return "\n".join(lines)


def collect(db: Callable, clock: Callable, telegram=None, asmr=None) -> dict[str, Any]:
    """API 와 텔레그램 /status 가 같이 쓴다"""
    now = clock()
    question = telegram.question_state() if telegram is not None else {"label": "텔레그램 꺼짐"}
    plan_sent = telegram.plan_sent() if telegram is not None else {}
    with db() as s:
        return build(s, now, plan_sent=plan_sent, question=question, asmr=asmr.counts() if asmr is not None else None)
