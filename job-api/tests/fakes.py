"""LLM 단계 테스트용 가짜: 미리 넣어 둔 응답을 차례로 돌려주고, 받은 요청을 기록한다."""
from __future__ import annotations

import json

from app.llm.base import LlmError, LlmResult


class FakeLlm:
    name = "fake"

    def __init__(self, *responses):
        self.responses = list(responses)  # dict(답) 또는 LlmError
        self.requests = []

    def generate_json(self, messages, schema, schema_name):
        self.requests.append({"messages": messages, "schema": schema, "schema_name": schema_name})
        if not self.responses:
            raise AssertionError("준비한 응답이 더 없다")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LlmResult(data=r, model="fake-model", input_tokens=100, output_tokens=200, source="content",
                         raw=json.dumps(r, ensure_ascii=False))

    def last_user_text(self):
        return self.requests[-1]["messages"][-1]["content"]


class FakeRegistry:
    def __init__(self, llm, chars_per_sec=5.6, tts_url="http://tts-worker:8090"):
        self._llm = llm
        self.chars_per_sec = chars_per_sec
        self.tts_url = tts_url
        self.clip_engine = "none"

    def llm(self, step):
        return self._llm

    def tts_settings(self):
        return {"kind": "http-worker", "url": self.tts_url, "engine": "supertonic", "voice": "M1",
                "sample_rate": 44100, "chars_per_sec": self.chars_per_sec, "timeout_sec": 30}


# 검토 응답의 점수 (2026-10-17 검토 기준). 2점 이하가 있으면 대본부터 다시
GOOD_SCORES = {"accuracy": 5, "clarity": 4, "concreteness": 4, "naturalness": 4}


def transient(msg="LM Studio 응답 없음"):
    return LlmError("transient", msg)


def script_of(chars_per_sentence=30, sentences=8, **extra):
    """글자 수를 맞춘 대본. 문장마다 공백 빼고 chars_per_sentence 글자."""
    def sent(i):
        base = f"문장{i}번은" + "가" * max(0, chars_per_sentence - 6)
        return base[:chars_per_sentence] + "."
    body = [sent(i) for i in range(sentences - 2)]
    data = {"hook": sent(90), "body": body, "summary": sent(91),
            "titleCandidates": ["제목 하나", "제목 둘", "제목 셋"], "hashtags": ["#AI"]}
    data.update(extra)
    return data
