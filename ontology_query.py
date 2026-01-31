from __future__ import annotations

from pathlib import Path

from app.services.tag_ontology import (
    compile_rules,
    is_valid_tag_token,
    parse_rules_text,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _load_ontology_from_file() -> object:
    rules_path = _repo_root() / "ontology_rules.txt"
    text = rules_path.read_text(encoding="utf-8")
    rules = parse_rules_text(text=text, filename=str(rules_path))
    return compile_rules(rules=rules, filename=str(rules_path))


def _print_focus(ontology, tag: str) -> None:
    left, equals, right = ontology.focus_view(tag=tag)
    print(f"tag: {tag}")
    print(f"  implies-X (left): {len(left)}")
    for item in sorted(left):
        print(f"    {item}")
    print(f"  equal-to-X (SCC): {len(equals)}")
    for item in sorted(equals):
        print(f"    {item}")
    print(f"  X-implies (right): {len(right)}")
    for item in sorted(right):
        print(f"    {item}")


def _parse_query_atoms(text: str) -> tuple[list[str], list[str]]:
    tags: list[str] = []
    phrases: list[str] = []

    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break

        # Allow users to paste rule-style conjunction groups like:
        #   ("some text" contact)
        # Parentheses are just grouping in the DSL; for ad-hoc queries we ignore them.
        if text[index] in ("(", ")"):
            index += 1
            continue

        if text[index] in ("\"", "'"):
            quote = text[index]
            index += 1
            phrase = ""
            while index < len(text):
                ch = text[index]
                if ch == quote:
                    index += 1
                    break
                if ch == "\\":
                    if index + 1 < len(text):
                        nxt = text[index + 1]
                        if nxt == quote or nxt == "\\":
                            phrase += nxt
                            index += 2
                            continue
                    phrase += "\\"
                    index += 1
                    continue
                phrase += ch
                index += 1
            else:
                raise ValueError(f"Unclosed quote {quote!r}")

            if phrase == "":
                raise ValueError("Empty quoted phrase is not allowed")
            phrases.append(phrase)
            continue

        start = index
        while index < len(text) and not text[index].isspace():
            if text[index] in ("(", ")"):
                break
            index += 1
        token = text[start:index]
        if token.endswith(")") and token != ")":
            # Rare case: user typed `tag)` without whitespace.
            token = token.rstrip(")")
        if token.startswith("(") and token != "(":
            token = token.lstrip("(")
        if not is_valid_tag_token(token):
            raise ValueError(f"Invalid tag token: {token!r}")
        tags.append(token)

    return tags, phrases


def main() -> None:
    ontology = _load_ontology_from_file()

    print(
        "Ontology query (Phase-1).\n"
        "- Enter one tag to view left/equal/right.\n"
        "- Enter multiple tags and/or quoted phrases to simulate inference.\n"
        "- Blank line exits."
    )
    while True:
        raw = input("query> ").strip()
        if raw == "":
            return

        if raw.lower() in {"help", "?"}:
            print(
                "Examples:\n"
                "  man\n"
                "  human man\n"
                "  \"Socrates\"\n"
                "  man \"world\"\n"
            )
            continue

        tags, phrases = _parse_query_atoms(raw)

        if not phrases and len(tags) == 1:
            _print_focus(ontology, tags[0])
            continue

        plaintext = " ".join(phrases)
        effective = ontology.infer_effective_tags(base_tags=frozenset(tags), plaintext=plaintext)
        added = sorted(set(effective) - set(tags))
        print("infer:")
        print(f"  base tags: {sorted(tags)}")
        print(f"  plaintext: {plaintext!r}")
        print(f"  effective tags: {sorted(effective)}")
        print(f"  added tags: {added}")


if __name__ == "__main__":
    main()
