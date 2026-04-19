from app.services.latex_rendering import render_latex_to_html


def test_render_latex_to_html_without_delimiters_uses_block_math() -> None:
    rendered = render_latex_to_html(r"\frac{1}{2}")
    assert rendered.has_error is False
    assert rendered.error_message == ""
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">' in rendered.html
    assert "<mfrac>" in rendered.html


def test_render_latex_to_html_with_inline_and_display_segments() -> None:
    rendered = render_latex_to_html("before $x^2$ middle $$y^2$$ after")
    assert rendered.has_error is False
    assert "before " in rendered.html
    assert " middle " in rendered.html
    assert " after" in rendered.html
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML" display="inline">' in rendered.html
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">' in rendered.html


def test_render_latex_to_html_invalid_input_returns_error_markup() -> None:
    rendered = render_latex_to_html(r"\begin{matrix}1&2")
    assert rendered.has_error is True
    assert rendered.error_message == ""
    assert "Invalid LaTeX" in rendered.html
    assert r"\begin{matrix}1&amp;2" in rendered.html
