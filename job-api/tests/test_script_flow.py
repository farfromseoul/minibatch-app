"""대본을 자연스럽게 (2026-10-18 사용자 피드백: 지난 화 문장이 두 번 나오고, 전체가 덜 자연스럽다).

실제 대본(시리즈 1번째 10화): recap '지난 화에선 AI가 틀린 말도 자연스럽게 만든다고 봤죠.' 가 body 첫 문장에 그대로 또 나왔다.
qwen 대본은 summary 가 body 첫 문장을 거의 그대로 되풀이했다(지시가 '정의를 다시 말하듯' 이었다).
- 말하는 순서: 질문(hook) → 지난 화 연결(recap) → 설명 → 정리 → 다음 화 예고. 첫 문장은 질문이다
- 같은 문장, 앞부분이 길게 같은 문장이 있으면 다시 쓰게 한다
- 프롬프트: 문장끼리 이어지게, 정의를 연달아 나열하지 않게, 정리는 hook 질문에 답하는 결론으로
"""
from app.text.sentences import repeated_sentences, script_sentences
from tests.fakes import script_of
from tests.test_llm_steps import SeriesScriptTest
from tests.test_script_quality import QualityCase

RECAP = "지난 화에선 AI가 틀린 말도 자연스럽게 만든다고 봤죠."


class OrderTest(QualityCase):
    def test_question_comes_first_then_link_to_last_episode(self):
        s = {"recap": "지난 화 연결.", "hook": "질문?", "body": ["설명."], "summary": "정리.", "nextTeaser": "예고?"}

        self.assertEqual(script_sentences(s), ["질문?", "지난 화 연결.", "설명.", "정리.", "예고?"])


class RepeatTest(QualityCase):
    def test_same_or_long_shared_opening_is_found(self):
        lines = ["AI는 문장을 단어 단위로 쪼개서 의미를 계산합니다.", RECAP, "학습 데이터는 답변 방식을 익히는 자료입니다.",
                 "지난 화에선 AI가 틀린 말도 자연스럽게 만든다고 봤죠", "AI는 문장을 단어 단위로 쪼개서 의미를 계산하는 자연어 처리로 말을 이해합니다."]

        pairs = repeated_sentences(lines)

        self.assertEqual(pairs, [(1, 3), (0, 4)])  # 문장부호 차이는 같은 문장, 앞 16글자 이상 같으면 되풀이

    def test_similar_test_sentences_are_not_repeats(self):
        self.assertEqual(repeated_sentences(script_sentences(script_of(30, 10))), [])

    def test_repeated_sentence_is_written_again(self):
        bad = script_of(30, 10)
        bad["summary"] = bad["body"][0]
        self.llm.responses = [bad, script_of(30, 10)]
        job_id = self.new_job("AI는 어떻게 이미지를 만들까?")

        self.run_until(job_id, "script")

        self.assertEqual(len(self.llm.requests), 2)
        self.assertIn("되풀이", self.llm.last_user_text())


class FlowPromptTest(QualityCase):
    def test_prompt_asks_for_connected_sentences_and_a_conclusion(self):
        self.llm.responses = [script_of(30, 10)]
        job_id = self.new_job("AI는 어떻게 이미지를 만들까?")

        self.run_until(job_id, "script")

        system, user = self.llm.requests[0]["messages"][:2]
        self.assertIn("앞 문장을 받아", system["content"])
        self.assertIn("정의 문장을 연달아", system["content"])
        self.assertIn("같은 어미", system["content"])
        self.assertIn("hook 질문에 답", user["content"])
        self.assertNotIn("정의를 다시 말하듯", user["content"])


class SeriesFlowTest(SeriesScriptTest):
    def test_recap_follows_the_question_and_is_not_repeated_in_body(self):
        job2 = self.episode2_job()
        bad = script_of(38, 8, recap=RECAP, episodeSummary="머신러닝을 배움")
        bad["body"][0] = RECAP
        self.llm.responses = [bad, script_of(38, 8, recap=RECAP, episodeSummary="머신러닝을 배움")]

        self.run_until(job2, "script")

        first_prompt = self.llm.requests[-2]["messages"][-1]["content"]
        self.assertIn("hook 바로 다음", first_prompt)
        self.assertIn("되풀이", self.llm.last_user_text())  # body 에 recap 을 또 써서 다시 요청
        self.assertNotIn(RECAP, self.read(job2, "script.json")["body"])
