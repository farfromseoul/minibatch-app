import unittest

from llm_compare.validate import count_chars, validate_script


def valid_script():
    return {
        "hook": "LLM이 모르는 걸 물어보면 어떻게 될까요?",
        "body": [
            "RAG는 먼저 관련 문서를 찾습니다.",
            "찾은 내용을 질문과 함께 LLM에 넘깁니다.",
            "그래서 최신 정보도 답할 수 있습니다.",
        ],
        "summary": "검색하고, 붙이고, 답한다. 이게 RAG입니다.",
        "titleCandidates": ["RAG 30초 요약", "RAG란?", "검색 증강 생성"],
    }


class ValidateScriptTest(unittest.TestCase):
    def test_valid_script_has_no_problems(self):
        self.assertEqual(validate_script(valid_script()), [])

    def test_reports_missing_key(self):
        script = valid_script()
        del script["summary"]

        problems = validate_script(script)

        self.assertTrue(any("summary" in p for p in problems), problems)

    def test_reports_sentence_longer_than_limit(self):
        script = valid_script()
        script["body"][1] = "가" * 41

        problems = validate_script(script, max_sentence_chars=40)

        self.assertTrue(any("40" in p and "body[1]" in p for p in problems), problems)

    def test_reports_wrong_title_candidate_count(self):
        script = valid_script()
        script["titleCandidates"] = ["하나"]

        problems = validate_script(script)

        self.assertTrue(any("titleCandidates" in p for p in problems), problems)

    def test_reports_body_that_is_not_a_list_of_strings(self):
        script = valid_script()
        script["body"] = "문장 하나"

        problems = validate_script(script)

        self.assertTrue(any("body" in p for p in problems), problems)


class CountCharsTest(unittest.TestCase):
    def test_ignores_whitespace(self):
        self.assertEqual(count_chars("RAG 는\n좋다"), 6)  # R A G 는 좋 다

    def test_counts_all_spoken_parts_of_script(self):
        script = {"hook": "가나", "body": ["다라", "마"], "summary": "바", "titleCandidates": ["제목은 세지 않음"]}

        self.assertEqual(count_chars(script), 6)


if __name__ == "__main__":
    unittest.main()
