from __future__ import annotations

import argparse
import io
import os
import token
import tokenize
from dataclasses import dataclass
from pathlib import Path


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "js",
    ".css": "css",
}

EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "vendor",
}

EXCLUDED_PATH_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "vendor",
    "__pycache__",
}


@dataclass
class LanguageStats:
    file_count: int = 0
    physical_line_count: int = 0
    code_line_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count project lines of code by language, excluding vendor/dependency directories.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root to scan. Defaults to the current directory.",
    )
    return parser.parse_args()


def should_skip_relative_parts(relative_parts: tuple[str, ...]) -> bool:
    if len(relative_parts) == 0:
        return False
    if relative_parts[0] in EXCLUDED_DIRECTORY_NAMES:
        return True
    for part in relative_parts:
        if part in EXCLUDED_PATH_PARTS:
            return True
    return False


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def count_physical_lines(text: str) -> int:
    return len(text.splitlines())


def count_python_code_lines(text: str) -> int:
    code_lines: set[int] = set()
    ignored_token_types = {
        token.NEWLINE,
        tokenize.NL,
        token.INDENT,
        token.DEDENT,
        token.ENDMARKER,
        tokenize.COMMENT,
    }

    token_stream = tokenize.generate_tokens(io.StringIO(text).readline)
    for token_info in token_stream:
        if token_info.type in ignored_token_types:
            continue
        code_lines.add(token_info.start[0])

    return len(code_lines)


def count_c_style_code_lines(text: str) -> int:
    code_line_count = 0
    in_block_comment = False
    string_delimiter: str | None = None
    string_escape_active = False

    for raw_line in text.splitlines():
        line_has_code = False
        index = 0

        while index < len(raw_line):
            char = raw_line[index]
            next_char = ""
            if index + 1 < len(raw_line):
                next_char = raw_line[index + 1]

            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if string_delimiter is not None:
                if string_escape_active:
                    string_escape_active = False
                    if not char.isspace():
                        line_has_code = True
                    index += 1
                    continue

                if char == "\\":
                    string_escape_active = True
                    line_has_code = True
                    index += 1
                    continue

                if char == string_delimiter:
                    string_delimiter = None
                    line_has_code = True
                    index += 1
                    continue

                if not char.isspace():
                    line_has_code = True
                index += 1
                continue

            if char == "/" and next_char == "/":
                break

            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue

            if char in {'"', "'", "`"}:
                string_delimiter = char
                line_has_code = True
                index += 1
                continue

            if not char.isspace():
                line_has_code = True

            index += 1

        if string_delimiter is not None and string_delimiter != "`" and not string_escape_active:
            string_delimiter = None

        if line_has_code:
            code_line_count += 1

    return code_line_count


def count_code_lines(language: str, text: str) -> int:
    if language == "python":
        return count_python_code_lines(text)
    if language in {"js", "css"}:
        return count_c_style_code_lines(text)
    raise ValueError(f"Unsupported language: {language}")


def collect_stats(root: Path) -> dict[str, LanguageStats]:
    stats_by_language = {
        language: LanguageStats()
        for language in sorted(set(LANGUAGE_BY_SUFFIX.values()))
    }

    for current_root, directory_names, file_names in os.walk(root, topdown=True):
        current_root_path = Path(current_root)
        relative_dir_parts = current_root_path.relative_to(root).parts
        if should_skip_relative_parts(relative_dir_parts):
            directory_names[:] = []
            continue

        directory_names[:] = [
            directory_name
            for directory_name in directory_names
            if directory_name not in EXCLUDED_DIRECTORY_NAMES
        ]

        for file_name in file_names:
            path = current_root_path / file_name
            relative_file_parts = path.relative_to(root).parts
            if should_skip_relative_parts(relative_file_parts):
                continue

            if path.suffix not in LANGUAGE_BY_SUFFIX:
                continue
            language = LANGUAGE_BY_SUFFIX[path.suffix]

            text = read_text(path)
            language_stats = stats_by_language[language]
            language_stats.file_count += 1
            language_stats.physical_line_count += count_physical_lines(text)
            language_stats.code_line_count += count_code_lines(language, text)

    return stats_by_language


def render_summary(root: Path, stats_by_language: dict[str, LanguageStats]) -> str:
    total_files = 0
    total_physical_lines = 0
    total_code_lines = 0

    output_lines = [f"LOC summary for {root.resolve()}"]
    output_lines.append("")
    output_lines.append(f"{'language':<8} {'files':>8} {'physical':>10} {'code':>10}")
    output_lines.append(f"{'-' * 8:<8} {'-' * 8:>8} {'-' * 10:>10} {'-' * 10:>10}")

    for language in ("python", "js", "css"):
        stats = stats_by_language[language]
        total_files += stats.file_count
        total_physical_lines += stats.physical_line_count
        total_code_lines += stats.code_line_count
        output_lines.append(
            f"{language:<8} {stats.file_count:>8} {stats.physical_line_count:>10} {stats.code_line_count:>10}",
        )

    output_lines.append("")
    output_lines.append(f"{'total':<8} {total_files:>8} {total_physical_lines:>10} {total_code_lines:>10}")
    output_lines.append("")
    output_lines.append("code = non-blank, non-comment lines")
    return "\n".join(output_lines)


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Root path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Root path is not a directory: {root}")

    stats_by_language = collect_stats(root)
    print(render_summary(root, stats_by_language))


if __name__ == "__main__":
    main()
