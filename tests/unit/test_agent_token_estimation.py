from app.services.agent.token_estimation import estimate_input_tokens
from app.services.agent.token_estimation import estimate_text_tokens


def test_text_token_estimate_accounts_for_words_numbers_and_punctuation() -> None:
    assert estimate_text_tokens("hello testosterone 123456, yes!") == 9


def test_input_token_estimate_includes_compact_json_structure() -> None:
    assert estimate_input_tokens({"prompt": "hello"}) > estimate_text_tokens("hello")


def test_non_ascii_text_costs_more_than_same_character_count_ascii_text() -> None:
    assert estimate_text_tokens("😀😀😀😀") > estimate_text_tokens("aaaa")


def test_input_token_estimate_is_always_positive() -> None:
    assert estimate_input_tokens({}) >= 1
