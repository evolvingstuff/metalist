"""A seeded synthetic namespace for developing and testing the experiment.

It has the structure the models should exploit: topics whose words predict
their tags (without always naming them), a journal whose entries get journal
tags from their parent, projects whose children share the project tag, and
tags that usually come in pairs.
"""

from __future__ import annotations

import html
import random
from datetime import datetime, timedelta, timezone

from experiments.tag_suggestions.corpus import Corpus, CorpusNote

_TOPICS = {
    "ssm": ["mamba", "selective", "scan", "state", "space", "recurrence"],
    "transformers": ["attention", "heads", "softmax", "context", "tokens", "layers"],
    "cooking": ["onion", "garlic", "simmer", "oven", "salt", "recipe"],
    "running": ["miles", "pace", "tempo", "shoes", "marathon", "stride"],
    "finance": ["budget", "invoice", "taxes", "savings", "account", "rent"],
    "garden": ["tomato", "soil", "seeds", "watering", "compost", "beds"],
}
# Tags that usually come with a topic tag.
_COMPANIONS = {"ssm": "papers", "transformers": "papers", "cooking": "home", "garden": "home"}
_FILLER = ["the", "a", "today", "note", "about", "some", "with", "and", "more", "thing", "later", "idea"]
_PROJECTS = ["apollo", "zephyr", "orchid"]


def build_synthetic_corpus(*, seed: int, note_count: int) -> Corpus:
    assert note_count >= 50
    rng = random.Random(seed)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    notes: dict[str, CorpusNote] = {}
    children: dict[str | None, list[str]] = {None: []}
    counter = [0]

    def add(parent_id: str | None, text: str, tags: list[str]) -> str:
        counter[0] += 1
        note_id = f"n{counter[0]:05d}"
        created_at = start + timedelta(hours=6 * counter[0])
        notes[note_id] = CorpusNote(
            note_id=note_id, parent_id=parent_id, content_html=f"<div>{html.escape(text)}</div>", plain_text=text,
            tags=" ".join(tags), explicit_tags=tuple(tags), meta_tags=(), created_at=created_at,
        )
        children[parent_id].append(note_id)
        children[note_id] = []
        return note_id

    journal = add(None, "Journal", ["journal"])
    projects = {name: add(None, f"Project {name}", [name]) for name in _PROJECTS}
    topic_root = add(None, "Reading and life", [])
    while counter[0] < note_count:
        topic = rng.choice(sorted(_TOPICS))
        words = rng.sample(_TOPICS[topic], 3) + rng.sample(_FILLER, 4)
        rng.shuffle(words)
        tags: list[str] = []
        # Naming the topic in the text is not the rule: most notes only use its words.
        if rng.random() < 0.8:
            tags.append(topic)
        if topic in _COMPANIONS and rng.random() < 0.7:
            tags.append(_COMPANIONS[topic])
        place = rng.random()
        if place < 0.3:
            parent = journal
            tags.append("diary")
        elif place < 0.6:
            project = rng.choice(_PROJECTS)
            parent = projects[project]
            tags.append(f"{project}-task")
        else:
            parent = topic_root
        if not tags:
            tags.append("misc")
        add(parent, " ".join(words), tags)
    return Corpus(
        notes=notes,
        children={parent_id: tuple(child_ids) for parent_id, child_ids in children.items()
                  if child_ids or parent_id is None},
        rules_text="ssm => machine-learning\ntransformers => machine-learning\n",
    )
