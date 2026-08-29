from app.services.agent.token_estimation import estimate_input_tokens


def test_input_token_estimate_uses_four_serialized_characters_per_token() -> None:
    assert estimate_input_tokens({"prompt": "12345678"}) == 6


def test_input_token_estimate_is_always_positive() -> None:
    assert estimate_input_tokens({}) == 1
