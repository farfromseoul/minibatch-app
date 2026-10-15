"""0주 차 LLM 비교 실행.

모델 × 주제마다 대본 JSON 을 한 번씩 요청하고, 답·검증 결과·속도를 out 폴더에 남긴다.
모델은 LM Studio 의 JIT 로딩으로 올라가고 ttl 이 지나면 내려간다. 순서대로 하나씩 돌린다.

사용 예 (poc 폴더에서):
    python3 -I -m llm_compare.run --model qwen/qwen3.8-27b --model <8B MLX 키> --model <8B GGUF 키>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Callable, List, Optional

from .client import chat
from .extract import ExtractError, extract_json
from .report import render_markdown, summarize
from .validate import count_chars, validate_script

DEFAULT_TOPICS = ["RAG", "딥러닝", "MCP(Model Context Protocol)", "쿠버네티스", "임베딩"]

# 앱 설계(04) "LLM 사용"의 script 출력과 같은 모양 (해시태그는 비교에서 뺐다)
SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "body": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
        "summary": {"type": "string"},
        "titleCandidates": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
    },
    "required": ["hook", "body", "summary", "titleCandidates"],
    "additionalProperties": False,
}


def build_messages(topic: str, target_chars: int) -> List[dict]:
    prompt = (
        f"'{topic}'을(를) 비전공 개발 입문자에게 설명하는 60초 유튜브 쇼츠 대본을 써 줘.\n"
        "- 구조: hook(관심을 끄는 질문이나 문장 1개) → body(설명 3~8문장) → summary(정리 1문장)\n"
        "- 모든 문장은 40자 이내\n"
        f"- hook·body·summary 를 합쳐 공백 빼고 {target_chars}자 안팎\n"
        "- 출처 없는 수치·통계, 과장 표현(완벽하게, 100% 등)은 쓰지 않는다\n"
        "- titleCandidates 에 제목 후보 3개"
    )
    return [{"role": "user", "content": prompt}]


def _slug(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", text).strip("_")


def run_all(
    models: List[str],
    topics: List[str],
    chat_fn: Callable = chat,
    out_dir: pathlib.Path = pathlib.Path("out/llm"),
    base_url: str = "http://127.0.0.1:1234/v1",
    target_chars: int = 300,
    ttl: Optional[int] = 120,
) -> List[dict]:
    results = []
    for model in models:
        for topic in topics:
            record = {"model": model, "topic": topic, "ok": False, "source": None,
                      "completion_tokens": None, "elapsed_sec": None, "chars": None, "problems": []}
            try:
                reply = chat_fn(base_url, model, build_messages(topic, target_chars),
                                schema=SCRIPT_SCHEMA, extra={"ttl": ttl} if ttl else None)
                record["completion_tokens"] = reply.get("completion_tokens")
                record["elapsed_sec"] = reply.get("elapsed_sec")
                script, record["source"] = extract_json(reply["message"])
                record["problems"] = validate_script(script)
                record["chars"] = count_chars(script)
                record["ok"] = not record["problems"]
                record["script"] = script
            except ExtractError as e:
                record["problems"] = [str(e)]
                record["message"] = reply.get("message")
            except Exception as e:  # 서버 오류, 시간 초과 등도 기록하고 다음으로 간다
                record["problems"] = [f"{type(e).__name__}: {e}"]
            target = out_dir / _slug(model) / f"{_slug(topic)}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            results.append(record)
            print(f"{model} | {topic} | {'통과' if record['ok'] else '실패'} | {record['source']} | {record['problems'][:1]}")
    return results


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="0주 차 LLM 비교")
    parser.add_argument("--model", action="append", required=True, help="LM Studio 모델 키 (lms ls 의 이름). 여러 번 쓸 수 있다")
    parser.add_argument("--topic", action="append", help="주제. 생략하면 기본 5개")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--out", default="out/llm")
    parser.add_argument("--target-chars", type=int, default=300)
    parser.add_argument("--ttl", type=int, default=120)
    args = parser.parse_args(argv)

    out_dir = pathlib.Path(args.out)
    results = run_all(args.model, args.topic or DEFAULT_TOPICS, out_dir=out_dir,
                      base_url=args.base_url, target_chars=args.target_chars, ttl=args.ttl)
    table = render_markdown(summarize(results))
    (out_dir / "summary.md").write_text(table)
    print("\n" + table)
    print(f"대본 원문: {out_dir}/<모델>/<주제>.json  (기술 오류는 사람이 읽고 판단한다)")


if __name__ == "__main__":
    main()
