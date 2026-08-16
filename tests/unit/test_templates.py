from pathlib import Path

from app.presentation.templates import get_templates


def test_templates_render_inheritance_directly_from_source_directory(tmp_path: Path) -> None:
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    (template_directory / "base.html").write_text(
        "<html>${self.body()}</html>\n",
        encoding="utf-8",
    )
    (template_directory / "index.html").write_text(
        '<%inherit file="base.html"/><p>generation</p>\n',
        encoding="utf-8",
    )

    templates = get_templates(template_directory=template_directory)

    assert templates.get_template("index.html").render() == "<html><p>generation</p>\n</html>\n"
    assert templates.get_template("index.html").render() == "<html><p>generation</p>\n</html>\n"
