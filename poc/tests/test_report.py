import unittest

from llm_compare.report import render_markdown, summarize


def result(model, ok=True, source="content", tokens=100, seconds=2.0, chars=300):
    return {
        "model": model,
        "topic": "RAG",
        "ok": ok,
        "source": source,
        "completion_tokens": tokens,
        "elapsed_sec": seconds,
        "chars": chars,
        "problems": [] if ok else ["문제"],
    }


class SummarizeTest(unittest.TestCase):
    def test_groups_results_by_model_in_first_seen_order(self):
        rows = summarize([result("b"), result("a"), result("b")])

        self.assertEqual([r["model"] for r in rows], ["b", "a"])
        self.assertEqual(rows[0]["runs"], 2)

    def test_counts_passes_and_reasoning_fallbacks(self):
        rows = summarize([
            result("m", ok=True, source="content"),
            result("m", ok=True, source="reasoning_content"),
            result("m", ok=False, source="reasoning_content"),
        ])

        self.assertEqual(rows[0]["passed"], 2)
        self.assertEqual(rows[0]["fallbacks"], 2)

    def test_tokens_per_second_uses_totals(self):
        rows = summarize([result("m", tokens=100, seconds=2.0), result("m", tokens=300, seconds=2.0)])

        self.assertAlmostEqual(rows[0]["tokens_per_sec"], 100.0)

    def test_skips_results_without_timing_in_speed(self):
        rows = summarize([result("m", tokens=0, seconds=0.0)])

        self.assertIsNone(rows[0]["tokens_per_sec"])


class RenderMarkdownTest(unittest.TestCase):
    def test_renders_header_and_one_line_per_model(self):
        text = render_markdown(summarize([result("qwen/x"), result("qwen/y", ok=False)]))

        lines = [l for l in text.splitlines() if l.startswith("|")]
        self.assertEqual(len(lines), 4)  # 머리글, 구분선, 모델 2줄
        self.assertIn("qwen/x", text)
        self.assertIn("1/1", text)
        self.assertIn("0/1", text)


if __name__ == "__main__":
    unittest.main()
