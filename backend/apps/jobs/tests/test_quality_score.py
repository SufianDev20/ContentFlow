import pytest

from apps.jobs.formats import FORMATS

WORD = "word "


def score(fmt, text):
    return FORMATS[fmt].score(text)


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("text", ["", "   \n"])
def test_blank_text_scores_zero(fmt, text):
    assert score(fmt, text) == 0


class TestTweetThread:
    def test_well_formed_thread_scores_full(self):
        assert score("tweet_thread", "1/ Hook\n2/ Point\n3/ Point\n4/ CTA") == 100

    def test_unnumbered_single_line_loses_marker_and_count_points(self):
        assert score("tweet_thread", "Just one plain sentence") == 50

    def test_tweet_over_280_characters_loses_points(self):
        assert score("tweet_thread", "1/ " + WORD * 100 + "\n2/ short\n3/ short") == 75

    def test_thread_over_3000_characters_loses_points(self):
        assert score("tweet_thread", "1/ " + WORD * 700) < 100


class TestLinkedin:
    def test_in_range_multiline_sentence_scores_full(self):
        assert score("linkedin", WORD * 200 + ".\nMore.") == 100

    def test_near_range_word_count_earns_partial_credit(self):
        assert score("linkedin", WORD * 120 + ".\nMore.") == 80

    def test_missing_paragraph_break_loses_points(self):
        assert score("linkedin", (WORD * 200).strip() + ".") == 70

    def test_unfinished_ending_loses_points(self):
        assert score("linkedin", WORD * 200 + "\nends abruptly") == 70


class TestEmail:
    def test_subject_body_range_and_breaks_score_full(self):
        assert score("email", "Subject: News\n" + WORD * 250 + ".\nSecond paragraph.") == 100

    def test_missing_subject_loses_points(self):
        assert score("email", WORD * 250 + ".\nSecond paragraph.") == 70

    def test_near_range_word_count_earns_partial_credit(self):
        assert score("email", "Subject: News\n" + WORD * 180 + ".\nMore text.") == 80

    def test_single_line_body_loses_points(self):
        assert score("email", "Subject: News\n" + (WORD * 250).strip() + ".") == 70


class TestTldr:
    def test_three_single_sentence_bullets_score_full(self):
        assert score("tldr", "• One.\n• Two.\n• Three.") == 90

    def test_no_bullets_scores_zero(self):
        assert score("tldr", "A paragraph, no bullets.") == 0

    @pytest.mark.parametrize("count", [2, 6])
    def test_one_bullet_off_target_range_earns_partial_credit(self, count):
        text = "\n".join(f"• Point {i}." for i in range(count))
        assert score("tldr", text) == 80

    def test_multi_sentence_bullet_loses_points(self):
        assert score("tldr", "• One. Extra.\n• Two.\n• Three.") == 60
