from __future__ import annotations

from pathlib import Path

from app.services.tag_ontology import compile_rules, parse_rules_text


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    rules_path = repo_root / "ontology_rules.txt"
    if not rules_path.exists():
        raise RuntimeError(f"Missing rules file: {rules_path}")

    text = rules_path.read_text(encoding="utf-8")
    rules = parse_rules_text(text=text, filename=str(rules_path))
    ontology = compile_rules(rules=rules, filename=str(rules_path))

    edge_count = sum(len(v) for v in ontology.implication_out_edges.values())
    node_count = len(ontology.implication_out_edges)
    print("OK")
    print(f"Rules parsed: {len(rules)}")
    print(f"Implication nodes: {node_count}")
    print(f"Implication edges: {edge_count}")
    print(f"Matcher rules: {len(ontology.matcher_rules)}")


if __name__ == "__main__":
    main()
