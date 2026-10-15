import json
import pathlib
import tempfile
import unittest

from llm_compare.run import SCRIPT_SCHEMA, build_messages, run_all

GOOD = {
    "hook": "LLM이 모르는 걸 물어보면요?",
    "body": ["문서를 먼저 찾습니다.", "찾은 내용을 함께 넘깁니다.", "그래서 최신 정보도 답합니다."],
    "summary": "검색하고 답한다, 그게 RAG.",
    "titleCandidates": ["RAG 요약", "RAG란?", "검색 증강 생성"],
}


def fake_chat(answer_field="content", text=None):
    def _chat(base_url, model, messages, schema=None, extra=None, **kwargs):
        body = text if text is not None else json.dumps(GOOD, ensure_ascii=False)
        message = {"content": "", "reasoning_content": ""}
        message[answer_field] = body
        return {"message": message, "completion_tokens": 50, "elapsed_sec": 1.0, "raw": {}}
    return _chat


class BuildMessagesTest(unittest.TestCase):
    def test_prompt_names_topic_and_limits(self):
        text = build_messages("RAG", target_chars=300)[-1]["content"]

        self.assertIn("RAG", text)
        self.assertIn("300", text)
        self.assertIn("40자", text)


class RunAllTest(unittest.TestCase):
    def test_records_each_model_and_topic_and_writes_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = run_all(["m/a", "m/b"], ["RAG", "MCP"], chat_fn=fake_chat(), out_dir=pathlib.Path(tmp))

            self.assertEqual(len(results), 4)
            self.assertTrue(all(r["ok"] for r in results))
            saved = sorted(p.name for p in pathlib.Path(tmp).rglob("*.json"))
            self.assertEqual(len(saved), 4)

    def test_marks_reasoning_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = run_all(["m"], ["RAG"], chat_fn=fake_chat("reasoning_content"), out_dir=pathlib.Path(tmp))

        self.assertEqual(results[0]["source"], "reasoning_content")
        self.assertTrue(results[0]["ok"])

    def test_records_failure_when_no_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = run_all(["m"], ["RAG"], chat_fn=fake_chat(text="답 없음"), out_dir=pathlib.Path(tmp))

        self.assertFalse(results[0]["ok"])
        self.assertTrue(results[0]["problems"])

    def test_schema_requires_all_script_keys(self):
        self.assertEqual(set(SCRIPT_SCHEMA["required"]), {"hook", "body", "summary", "titleCandidates"})


if __name__ == "__main__":
    unittest.main()
