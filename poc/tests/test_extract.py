import unittest

from llm_compare.extract import ExtractError, extract_json


class ExtractJsonTest(unittest.TestCase):
    def test_reads_json_from_content(self):
        message = {"content": '{"a": 1}', "reasoning_content": ""}

        data, source = extract_json(message)

        self.assertEqual(data, {"a": 1})
        self.assertEqual(source, "content")

    def test_falls_back_to_reasoning_content_when_content_is_empty(self):
        # 2026-10-15 qwen/qwen3.8-27b 가 스키마 강제 요청에서 답을 reasoning_content 에 넣었다
        message = {"content": "", "reasoning_content": '{"sentences": ["가", "나", "다"]}'}

        data, source = extract_json(message)

        self.assertEqual(data, {"sentences": ["가", "나", "다"]})
        self.assertEqual(source, "reasoning_content")

    def test_strips_think_block_before_json_in_content(self):
        message = {"content": '<think>생각 중</think>\n{"a": 2}'}

        data, source = extract_json(message)

        self.assertEqual(data, {"a": 2})
        self.assertEqual(source, "content")

    def test_raises_when_no_field_has_json(self):
        message = {"content": "", "reasoning_content": "그냥 생각만 했다"}

        with self.assertRaises(ExtractError):
            extract_json(message)

    def test_raises_when_message_has_no_text(self):
        with self.assertRaises(ExtractError):
            extract_json({"content": None})


if __name__ == "__main__":
    unittest.main()
