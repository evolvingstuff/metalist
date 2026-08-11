from pathlib import Path

from app.presentation.frontend_snapshot import create_frontend_snapshot


def test_frontend_snapshot_is_immutable_after_source_files_change(tmp_path: Path) -> None:
    source_app_directory = tmp_path / "app"
    source_static_directory = source_app_directory / "static"
    source_template_directory = source_app_directory / "templates"
    source_static_directory.mkdir(parents=True)
    source_template_directory.mkdir(parents=True)
    source_javascript = source_static_directory / "main.js"
    source_template = source_template_directory / "index.html"
    source_javascript.write_text("const generation = 'old';\n", encoding="utf-8")
    source_template.write_text("<p>old template</p>\n", encoding="utf-8")

    snapshot = create_frontend_snapshot(source_app_directory)

    source_javascript.write_text("const generation = 'new';\n", encoding="utf-8")
    source_template.write_text("<p>new template</p>\n", encoding="utf-8")
    (source_static_directory / "added-later.js").write_text("new file\n", encoding="utf-8")

    assert (snapshot.static_directory / "main.js").read_text(encoding="utf-8") == "const generation = 'old';\n"
    assert (snapshot.template_directory / "index.html").read_text(encoding="utf-8") == "<p>old template</p>\n"
    assert not (snapshot.static_directory / "added-later.js").exists()
    assert snapshot.mako_module_directory.is_dir()
