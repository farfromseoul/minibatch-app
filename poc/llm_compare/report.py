"""모델별 결과 요약과 Markdown 표."""
from __future__ import annotations

from typing import List, Optional


def summarize(results: List[dict]) -> List[dict]:
    """결과를 모델별로 묶는다. 순서는 처음 나온 순서."""
    order: List[str] = []
    groups = {}
    for r in results:
        if r["model"] not in groups:
            order.append(r["model"])
            groups[r["model"]] = []
        groups[r["model"]].append(r)
    rows = []
    for model in order:
        items = groups[model]
        tokens = sum(r.get("completion_tokens") or 0 for r in items)
        seconds = sum(r.get("elapsed_sec") or 0.0 for r in items)
        speed: Optional[float] = tokens / seconds if tokens and seconds else None
        chars = [r["chars"] for r in items if r.get("chars")]
        rows.append({
            "model": model,
            "runs": len(items),
            "passed": sum(1 for r in items if r["ok"]),
            "fallbacks": sum(1 for r in items if r.get("source") == "reasoning_content"),
            "tokens_per_sec": speed,
            "avg_chars": sum(chars) / len(chars) if chars else None,
            "avg_sec": seconds / len(items) if items else None,
        })
    return rows


def render_markdown(rows: List[dict]) -> str:
    def num(v, fmt):
        return format(v, fmt) if v is not None else "-"

    lines = [
        "| 모델 | 스키마·규칙 통과 | reasoning 필드 회수 | 초당 토큰 | 편당 평균 시간(초) | 평균 글자 수 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['model']} | {r['passed']}/{r['runs']} | {r['fallbacks']}/{r['runs']} "
            f"| {num(r['tokens_per_sec'], '.1f')} | {num(r['avg_sec'], '.1f')} | {num(r['avg_chars'], '.0f')} |"
        )
    return "\n".join(lines) + "\n"
