import unittest

from motif_gepa_ko.scoring import score_response


class ScoringTests(unittest.TestCase):
    def test_reasoning_number_does_not_count_as_final_answer(self):
        score, _, parsed = score_response("16", "중간 계산은 16입니다.\n정답: 3")
        self.assertEqual((score, parsed), (0.0, "3"))

    def test_last_line_format_is_required(self):
        score, _, parsed = score_response("16", "정답: 16\n계산을 마쳤습니다.")
        self.assertEqual((score, parsed), (0.0, None))

    def test_thousands_separator_and_decimal_are_equivalent(self):
        score, _, parsed = score_response("1600", "풀이\n정답: 1,600.0")
        self.assertEqual((score, parsed), (1.0, "1600.0"))

    def test_wrong_substring_is_not_accepted(self):
        score, _, parsed = score_response("16", "정답: 160")
        self.assertEqual((score, parsed), (0.0, "160"))


if __name__ == "__main__":
    unittest.main()
