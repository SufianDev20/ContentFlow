def test_job_word_count_follows_content(make_job):
    job = make_job(content="one two three four five")
    assert job.word_count == 5

    job.content = "one two"
    job.save()
    assert job.word_count == 2


def test_output_character_count_follows_text(make_output):
    output = make_output(text="12345")
    assert output.character_count == 5

    output.text = "1234567890"
    output.save()
    assert output.character_count == 10
