// 생산 워크플로 "다음 행동" 판단. 작업 상세(GET /jobs/{id})와 단계 순서만 보고 정한다 (부작용 없음).
// 행동: run(단계 요청) · poll(다시 보기) · reset(되돌리기) · done(검토 대기) · fail(알림) · stop(조용히 끝)
//       next(이 작업은 기다리게 두고 다음 작업으로, D31: 업로드 한도·앞 화 업로드 대기 중에도 다음 화를 만든다)
export function decide(job, pipeline, opt) {
  const last = {};
  for (const r of job.steps || []) last[r.step] = r; // 시도 순서대로 오므로 마지막이 지금 시도
  const resets = (job.events || []).filter((e) => (e.reason || "").startsWith("reset from=")).length;
  const firstFailed = () => pipeline.map((s) => last[s]).find((r) => r && r.status === "failed");

  if (job.status === "REVIEW") return { action: "done" };
  if (["APPROVED", "SCHEDULED", "PUBLISHED"].includes(job.status)) return { action: "stop", message: `이미 검토를 지났다: ${job.status}` };
  if (job.status === "REJECTED") return { action: "stop", message: "반려된 작업" };
  if (opt.runIndex >= opt.maxRuns) return { action: "fail", message: `너무 오래 끝나지 않는다 (확인 ${opt.runIndex}번)` };

  if (job.status === "FAILED") {
    const f = firstFailed();
    if (!f) return { action: "fail", message: "FAILED 인데 실패한 단계를 찾지 못했다" };
    const what = `${f.step} ${f.kind === "deterministic" ? "결정적" : f.kind === "transient" ? "일시적" : f.kind} 실패`;
    if (f.kind === "deterministic" && f.retryFrom) {
      if (resets < opt.maxResets) {
        return { action: "reset", from: f.retryFrom, waitSec: 2, message: `${what} → ${f.retryFrom} 부터 다시 (${resets + 1}번째): ${f.error}` };
      }
      return { action: "fail", message: `${what}, 되돌리기 ${resets}번 뒤에도: ${f.error}` };
    }
    return { action: "fail", message: `${what}: ${f.error}` };
  }

  for (const step of pipeline) {
    const r = last[step];
    if (!r) return { action: "run", step, waitSec: 5 };
    if (r.status === "succeeded") continue;
    if (r.status === "running") return { action: "poll", step, waitSec: 10 };
    if (r.status === "failed") {
      if (r.kind === "quota") {
        if (r.retryAt && new Date(r.retryAt) > opt.now) return { action: "next", message: `할당량 초과, ${r.retryAt} 이후 다시 (그동안 다음 작업)` };
        return { action: "run", step, waitSec: 5 };
      }
      if (r.kind === "blocked") {
        if (job.blockedBy) return { action: "next", message: job.blockedBy };
        return { action: "run", step, waitSec: 5 }; // 앞 화가 올라갔다
      }
      if (r.kind === "transient") return { action: "run", step, waitSec: 60 };
      return { action: "fail", message: `${step} 실패(${r.kind}): ${r.error}` };
    }
  }
  return { action: "poll", waitSec: 10 }; // 모든 단계가 끝났는데 아직 REVIEW 가 아니면 잠시 뒤 다시
}
