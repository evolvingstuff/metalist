"""Bounded navigation and refinement inside one frozen agent scope."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.scope import FrozenScopedNote
from app.services.agent.scope import ScopedSearchSnapshot
from app.services.agent.token_estimation import estimate_input_tokens
from app.services.search_query import SearchClause
from app.services.search_query import parse_search_query
from app.services.tag_term_matching import tag_term_matches_prefix


@dataclass(frozen=True, slots=True)
class TagFacet:
    tag: str
    note_count: int
    result_tree_count: int


@dataclass(frozen=True, slots=True)
class TagFacetPage:
    page: int
    total_pages: int
    total_facets: int
    facets: tuple[TagFacet, ...]


@dataclass(frozen=True, slots=True)
class InvestigationNotePage:
    state_id: str
    page: int
    total_pages: int
    matching_note_count: int
    matching_result_tree_count: int
    evidence_note_ids: tuple[str, ...]
    result_tree_ids: tuple[str, ...]
    result_trees: tuple[dict[str, object], ...]
    returned_character_count: int
    returned_approximate_token_count: int


@dataclass(frozen=True, slots=True)
class _SubsetState:
    state_id: str
    note_ids: tuple[str, ...]
    refinement_label: str


class InvestigationState:
    """Mutable cursor whose every subset is asserted to remain inside ``S0``."""

    def __init__(
        self,
        *,
        snapshot: ScopedSearchSnapshot,
        settings: AgentRetrievalSettings,
    ) -> None:
        self._snapshot = snapshot
        self._settings = settings
        initial = _SubsetState(
            state_id="scope-0",
            note_ids=snapshot.ordered_note_ids,
            refinement_label=snapshot.descriptor.label,
        )
        self._states_by_id = {initial.state_id: initial}
        self._state_history = [initial.state_id]
        self._root_pages_by_state_id: dict[str, tuple[tuple[str, ...], ...]] = {}
        self._current_state = initial
        self._note_page = 1
        self._facet_page = 1
        self._observed_source_ids: set[str] = set()
        self._disclosed_tags: set[str] = set()
        self._next_state_number = 1
        self._assert_subset(initial.note_ids)

    @classmethod
    def start(
        cls,
        *,
        snapshot: ScopedSearchSnapshot,
        settings: AgentRetrievalSettings,
    ) -> InvestigationState:
        if not isinstance(snapshot, ScopedSearchSnapshot):
            raise TypeError("InvestigationState requires ScopedSearchSnapshot")
        if not isinstance(settings, AgentRetrievalSettings):
            raise TypeError("InvestigationState requires AgentRetrievalSettings")
        return cls(snapshot=snapshot, settings=settings)

    @property
    def snapshot(self) -> ScopedSearchSnapshot:
        return self._snapshot

    @property
    def current_state_id(self) -> str:
        return self._current_state.state_id

    @property
    def current_note_ids(self) -> tuple[str, ...]:
        return self._current_state.note_ids

    @property
    def observed_source_ids(self) -> frozenset[str]:
        return frozenset(self._observed_source_ids)

    @property
    def disclosed_tags(self) -> frozenset[str]:
        return frozenset(self._disclosed_tags)

    @property
    def disclosed_state_ids(self) -> tuple[str, ...]:
        return tuple(self._state_history)

    @property
    def total_note_pages(self) -> int:
        return len(self._current_root_pages())

    def current_note_page(self) -> InvestigationNotePage:
        root_ids = self._current_root_ids()
        root_pages = self._current_root_pages()
        total_pages = len(root_pages)
        if self._note_page > total_pages:
            raise RuntimeError("Current note page exceeds total pages")
        page_root_ids = root_pages[self._note_page - 1]
        page_root_id_set = set(page_root_ids)
        page_note_ids = [
            note_id
            for note_id in self._current_state.note_ids
            if self._snapshot.notes_by_id[note_id].root_note_id in page_root_id_set
        ]
        result_trees, returned_character_count = self._serialize_token_bounded_page(
            root_ids=page_root_ids,
            note_ids=page_note_ids,
        )
        self._observed_source_ids.update(page_note_ids)
        for note_id in page_note_ids:
            note = self._snapshot.notes_by_id[note_id]
            self._disclosed_tags.update(
                tag.casefold() for tag in note.explicit_tag_terms
            )
        approximate_tokens = estimate_input_tokens(result_trees)
        return InvestigationNotePage(
            state_id=self._current_state.state_id,
            page=self._note_page,
            total_pages=total_pages,
            matching_note_count=len(self._current_state.note_ids),
            matching_result_tree_count=len(root_ids),
            evidence_note_ids=tuple(page_note_ids),
            result_tree_ids=page_root_ids,
            result_trees=result_trees,
            returned_character_count=returned_character_count,
            returned_approximate_token_count=approximate_tokens,
        )

    def current_facet_page(self) -> TagFacetPage:
        ranked = self._ranked_facets()
        total_pages = self._total_pages(
            item_count=len(ranked),
            page_size=self._settings.max_ranked_tags_per_page,
        )
        if self._facet_page > total_pages:
            raise RuntimeError("Current facet page exceeds total pages")
        start = (
            (self._facet_page - 1) * self._settings.max_ranked_tags_per_page
        )
        end = start + self._settings.max_ranked_tags_per_page
        facets = tuple(ranked[start:end])
        self._disclosed_tags.update(facet.tag.casefold() for facet in facets)
        return TagFacetPage(
            page=self._facet_page,
            total_pages=total_pages,
            total_facets=len(ranked),
            facets=facets,
        )

    def page_next(self) -> InvestigationNotePage:
        total_pages = self.total_note_pages
        if self._note_page >= total_pages:
            raise ValueError("Current subset has no next note page")
        self._note_page += 1
        return self.current_note_page()

    def inspect_tag_facets(self, *, page: int) -> TagFacetPage:
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("Facet page must be a positive integer")
        total_pages = self._total_pages(
            item_count=len(self._ranked_facets()),
            page_size=self._settings.max_ranked_tags_per_page,
        )
        if page > total_pages:
            raise ValueError("Requested facet page is out of range")
        self._facet_page = page
        return self.current_facet_page()

    def refine_tags(self, *, expression: str) -> InvestigationNotePage:
        if not isinstance(expression, str) or expression.strip() == "":
            raise ValueError("Tag refinement expression must not be blank")
        parsed = parse_search_query(expression)
        referenced_tags: set[str] = set()
        for clause in parsed.clauses:
            if clause.required_text or clause.forbidden_text:
                raise ValueError("Tag refinement cannot contain quoted text")
            referenced_tags.update(tag.casefold() for tag in clause.required_tags)
            referenced_tags.update(tag.casefold() for tag in clause.forbidden_tags)
        if not referenced_tags:
            raise ValueError("Tag refinement must contain a tag")
        for tag in referenced_tags:
            if tag not in self._disclosed_tags:
                raise ValueError(f"Tag {tag!r} has not been disclosed")
        refined_ids = tuple(
            note_id
            for note_id in self._current_state.note_ids
            if self._note_matches_tag_expression(
                note=self._snapshot.notes_by_id[note_id],
                clauses=parsed.clauses,
            )
        )
        self._push_subset(note_ids=refined_ids, refinement_label=expression)
        return self.current_note_page()

    def refine_exact_text(self, *, text: str) -> InvestigationNotePage:
        if not isinstance(text, str) or text.strip() == "":
            raise ValueError("Exact-text refinement must not be blank")
        if len(text) > 1_000:
            raise ValueError("Exact-text refinement must not exceed 1000 characters")
        folded = text.casefold()
        refined_ids = tuple(
            note_id
            for note_id in self._current_state.note_ids
            if folded in self._snapshot.notes_by_id[note_id].content_text.casefold()
        )
        self._push_subset(note_ids=refined_ids, refinement_label=f'"{text}"')
        return self.current_note_page()

    def backtrack(self, *, state_id: str) -> InvestigationNotePage:
        if not isinstance(state_id, str) or state_id == "":
            raise ValueError("Backtrack state id must be non-empty")
        if state_id not in self._states_by_id:
            raise ValueError("Backtrack target has not been disclosed")
        self._current_state = self._states_by_id[state_id]
        self._note_page = 1
        self._facet_page = 1
        self._assert_subset(self._current_state.note_ids)
        return self.current_note_page()

    def reopen_sources(self, *, note_ids: list[str]) -> tuple[dict[str, object], ...]:
        return self._rehydrate_observed_sources(
            note_ids=note_ids,
            maximum_note_ids=12,
            operation_label="Source reopen",
        )

    def rehydrate_answer_sources(
        self,
        *,
        note_ids: list[str],
    ) -> tuple[dict[str, object], ...]:
        return self._rehydrate_observed_sources(
            note_ids=note_ids,
            maximum_note_ids=32,
            operation_label="Final answer source rehydration",
        )

    def _rehydrate_observed_sources(
        self,
        *,
        note_ids: list[str],
        maximum_note_ids: int,
        operation_label: str,
    ) -> tuple[dict[str, object], ...]:
        if maximum_note_ids < 1:
            raise ValueError("Source rehydration maximum must be positive")
        if not isinstance(operation_label, str) or operation_label == "":
            raise ValueError("Source rehydration operation label must be non-empty")
        if not isinstance(note_ids, list) or len(note_ids) == 0:
            raise ValueError(f"{operation_label} requires note ids")
        if len(note_ids) > maximum_note_ids:
            raise ValueError(
                f"{operation_label} accepts at most {maximum_note_ids} note ids"
            )
        if any(not isinstance(note_id, str) or note_id == "" for note_id in note_ids):
            raise ValueError(f"{operation_label} ids must be non-empty strings")
        if len(set(note_ids)) != len(note_ids):
            raise ValueError(f"{operation_label} ids must be unique")
        if not set(note_ids).issubset(self._observed_source_ids):
            raise ValueError("Sources must have been previously observed")
        character_limits = self._allocate_content_characters(
            note_ids,
            maximum_total_characters=self._settings.max_page_approximate_tokens * 4,
        )
        return tuple(
            self._serialize_note(
                self._snapshot.notes_by_id[note_id],
                character_limit=character_limits[index],
            )
            for index, note_id in enumerate(note_ids)
        )

    def _push_subset(self, *, note_ids: tuple[str, ...], refinement_label: str) -> None:
        self._assert_subset(note_ids)
        if not set(note_ids).issubset(set(self._current_state.note_ids)):
            raise RuntimeError("Refinement escaped the current subset")
        state_id = f"scope-{self._next_state_number}"
        self._next_state_number += 1
        state = _SubsetState(
            state_id=state_id,
            note_ids=note_ids,
            refinement_label=refinement_label,
        )
        self._states_by_id[state_id] = state
        self._state_history.append(state_id)
        self._current_state = state
        self._note_page = 1
        self._facet_page = 1

    def _assert_subset(self, note_ids: tuple[str, ...]) -> None:
        if len(set(note_ids)) != len(note_ids):
            raise RuntimeError("Investigation subset contains duplicate note ids")
        if not set(note_ids).issubset(set(self._snapshot.ordered_note_ids)):
            raise RuntimeError("Investigation subset escaped frozen scope")
        expected_order = [
            note_id
            for note_id in self._snapshot.ordered_note_ids
            if note_id in set(note_ids)
        ]
        if tuple(expected_order) != note_ids:
            raise RuntimeError("Investigation subset lost frozen ordering")

    def _current_root_ids(self) -> list[str]:
        roots_with_matches = {
            self._snapshot.notes_by_id[note_id].root_note_id
            for note_id in self._current_state.note_ids
        }
        return [
            root_id
            for root_id in self._snapshot.ordered_root_ids
            if root_id in roots_with_matches
        ]

    def _ranked_facets(self) -> list[TagFacet]:
        notes_by_folded_tag: dict[str, set[str]] = {}
        roots_by_folded_tag: dict[str, set[str]] = {}
        spellings_by_folded_tag: dict[str, set[str]] = {}
        for note_id in self._current_state.note_ids:
            note = self._snapshot.notes_by_id[note_id]
            for tag in note.explicit_tag_terms:
                folded = tag.casefold()
                if folded not in notes_by_folded_tag:
                    notes_by_folded_tag[folded] = set()
                    roots_by_folded_tag[folded] = set()
                    spellings_by_folded_tag[folded] = set()
                notes_by_folded_tag[folded].add(note_id)
                roots_by_folded_tag[folded].add(note.root_note_id)
                spellings_by_folded_tag[folded].add(tag)
        facets = [
            TagFacet(
                tag=sorted(spellings_by_folded_tag[folded], key=lambda value: (value.casefold(), value))[0],
                note_count=len(note_ids),
                result_tree_count=len(roots_by_folded_tag[folded]),
            )
            for folded, note_ids in notes_by_folded_tag.items()
        ]
        facets.sort(
            key=lambda facet: (
                -facet.note_count,
                -facet.result_tree_count,
                facet.tag.casefold(),
                facet.tag,
            )
        )
        return facets

    @staticmethod
    def _note_matches_tag_expression(
        *,
        note: FrozenScopedNote,
        clauses: tuple[SearchClause, ...],
    ) -> bool:
        for clause in clauses:
            required_match = all(
                any(
                    tag_term_matches_prefix(term=term, prefix=required)
                    for term in note.explicit_tag_terms
                )
                for required in clause.required_tags
            )
            forbidden_match = any(
                any(
                    tag_term_matches_prefix(term=term, prefix=forbidden)
                    for term in note.explicit_tag_terms
                )
                for forbidden in clause.forbidden_tags
            )
            if required_match and not forbidden_match:
                return True
        return False

    def _allocate_content_characters(
        self,
        note_ids: list[str],
        *,
        maximum_total_characters: int,
    ) -> list[int]:
        if maximum_total_characters < 0:
            raise ValueError("Maximum total characters must not be negative")
        capacities = [
            min(
                len(self._snapshot.notes_by_id[note_id].content_text),
                self._settings.max_note_characters,
            )
            for note_id in note_ids
        ]
        allocated = [0 for _note_id in note_ids]
        remaining = maximum_total_characters
        active = [index for index, capacity in enumerate(capacities) if capacity > 0]
        while remaining > 0 and active:
            increment = max(1, remaining // len(active))
            next_active: list[int] = []
            for index in active:
                granted = min(capacities[index] - allocated[index], increment, remaining)
                allocated[index] += granted
                remaining -= granted
                if allocated[index] < capacities[index]:
                    next_active.append(index)
                if remaining == 0:
                    break
            active = next_active
        assert sum(allocated) <= maximum_total_characters
        return allocated

    def _pack_root_pages(
        self,
        root_ids: list[str],
    ) -> tuple[tuple[str, ...], ...]:
        if not root_ids:
            return ((),)
        pages: list[tuple[str, ...]] = []
        current_page: list[str] = []
        current_cost = 0
        for root_id in root_ids:
            root_note_ids = self._note_ids_for_roots((root_id,))
            root_cost = self._full_root_page_token_cost(
                root_id=root_id,
                note_ids=root_note_ids,
            )
            if (
                current_page
                and (
                    len(current_page) >= self._settings.max_notes_per_page
                    or current_cost + root_cost
                    > self._settings.max_page_approximate_tokens
                )
            ):
                pages.append(tuple(current_page))
                current_page = []
                current_cost = 0
            current_page.append(root_id)
            current_cost += root_cost
        if current_page:
            pages.append(tuple(current_page))
        assert pages
        assert tuple(root_id for page in pages for root_id in page) == tuple(root_ids)
        return tuple(pages)

    def _current_root_pages(self) -> tuple[tuple[str, ...], ...]:
        state_id = self._current_state.state_id
        if state_id not in self._root_pages_by_state_id:
            self._root_pages_by_state_id[state_id] = self._pack_root_pages(
                self._current_root_ids()
            )
        return self._root_pages_by_state_id[state_id]

    def _full_root_page_token_cost(
        self,
        *,
        root_id: str,
        note_ids: list[str],
    ) -> int:
        capacities = [
            min(
                len(self._snapshot.notes_by_id[note_id].content_text),
                self._settings.max_note_characters,
            )
            for note_id in note_ids
        ]
        trees, _returned_characters = self._serialize_page(
            root_ids=(root_id,),
            note_ids=note_ids,
            character_limits=capacities,
        )
        return estimate_input_tokens(trees)

    def _serialize_token_bounded_page(
        self,
        *,
        root_ids: tuple[str, ...],
        note_ids: list[str],
    ) -> tuple[tuple[dict[str, object], ...], int]:
        maximum_content_characters = sum(
            min(
                len(self._snapshot.notes_by_id[note_id].content_text),
                self._settings.max_note_characters,
            )
            for note_id in note_ids
        )
        lower = 0
        upper = maximum_content_characters
        best_trees, best_returned_characters = self._serialize_page(
            root_ids=root_ids,
            note_ids=note_ids,
            character_limits=[0 for _note_id in note_ids],
        )
        minimum_cost = estimate_input_tokens(best_trees)
        if minimum_cost > self._settings.max_page_approximate_tokens:
            return best_trees, best_returned_characters

        while lower <= upper:
            candidate = (lower + upper) // 2
            limits = self._allocate_content_characters(
                note_ids,
                maximum_total_characters=candidate,
            )
            trees, returned_characters = self._serialize_page(
                root_ids=root_ids,
                note_ids=note_ids,
                character_limits=limits,
            )
            token_cost = estimate_input_tokens(trees)
            if token_cost <= self._settings.max_page_approximate_tokens:
                best_trees = trees
                best_returned_characters = returned_characters
                lower = candidate + 1
            else:
                upper = candidate - 1
        return best_trees, best_returned_characters

    def _serialize_page(
        self,
        *,
        root_ids: tuple[str, ...],
        note_ids: list[str],
        character_limits: list[int],
    ) -> tuple[tuple[dict[str, object], ...], int]:
        if len(note_ids) != len(character_limits):
            raise RuntimeError("Note ids and character limits must align")
        serialized_notes = tuple(
            self._serialize_page_note(
                self._snapshot.notes_by_id[note_id],
                character_limit=character_limits[index],
            )
            for index, note_id in enumerate(note_ids)
        )
        returned_character_count = sum(
            min(
                len(self._snapshot.notes_by_id[note_id].content_text),
                character_limits[index],
            )
            for index, note_id in enumerate(note_ids)
        )
        serialized_by_id = {
            self._required_str(note, "note_id"): note
            for note in serialized_notes
        }
        evidence_note_ids = set(note_ids)
        included_structure_ids = self._structure_ids_for_evidence(
            evidence_note_ids=evidence_note_ids,
        )
        result_trees = tuple(
            self._serialize_result_tree(
                note_id=root_id,
                evidence_note_ids=evidence_note_ids,
                included_structure_ids=included_structure_ids,
                serialized_evidence_by_id=serialized_by_id,
            )
            for root_id in root_ids
        )
        return result_trees, returned_character_count

    @staticmethod
    def _serialize_page_note(
        note: FrozenScopedNote,
        *,
        character_limit: int,
    ) -> dict[str, object]:
        if character_limit < 0:
            raise ValueError("Note character limit must not be negative")
        returned_text = note.content_text[:character_limit]
        payload: dict[str, object] = {
            "note_id": note.note_id,
            "content_text": returned_text,
            "created_at": note.created_at,
            "updated_at": note.updated_at,
        }
        if note.explicit_tag_terms:
            payload["tags"] = list(note.explicit_tag_terms)
        if len(returned_text) < len(note.content_text):
            payload["truncated_from_character_count"] = len(note.content_text)
        return payload

    def _note_ids_for_roots(self, root_ids: tuple[str, ...]) -> list[str]:
        root_id_set = set(root_ids)
        return [
            note_id
            for note_id in self._current_state.note_ids
            if self._snapshot.notes_by_id[note_id].root_note_id in root_id_set
        ]

    @staticmethod
    def _serialize_note(
        note: FrozenScopedNote,
        *,
        character_limit: int,
    ) -> dict[str, object]:
        if character_limit < 0:
            raise ValueError("Note character limit must not be negative")
        returned_text = note.content_text[:character_limit]
        payload: dict[str, object] = {
            "note_id": note.note_id,
            "parent_id": note.parent_id,
            "root_note_id": note.root_note_id,
            "content_text": returned_text,
            "content_character_count": len(note.content_text),
            "returned_character_count": len(returned_text),
            "content_is_truncated": len(returned_text) < len(note.content_text),
            "created_at": note.created_at,
            "updated_at": note.updated_at,
        }
        if note.explicit_tag_terms:
            payload["tags"] = list(note.explicit_tag_terms)
        return payload

    def _serialize_result_tree(
        self,
        *,
        note_id: str,
        evidence_note_ids: set[str],
        included_structure_ids: set[str],
        serialized_evidence_by_id: dict[str, dict[str, object]],
    ) -> dict[str, object]:
        node = self._snapshot.tree_nodes_by_id[note_id]
        child_payloads = [
            self._serialize_result_tree(
                note_id=child_id,
                evidence_note_ids=evidence_note_ids,
                included_structure_ids=included_structure_ids,
                serialized_evidence_by_id=serialized_evidence_by_id,
            )
            for child_id in node.child_ids
            if child_id in included_structure_ids
        ]
        if note_id not in evidence_note_ids:
            return {
                "note_id": node.note_id,
                "is_evidence": False,
                "children": child_payloads,
            }
        payload = dict(serialized_evidence_by_id[note_id])
        if child_payloads:
            payload["children"] = child_payloads
        return payload

    def _structure_ids_for_evidence(
        self,
        *,
        evidence_note_ids: set[str],
    ) -> set[str]:
        included_ids = set(evidence_note_ids)
        for evidence_note_id in evidence_note_ids:
            current_id = evidence_note_id
            while self._snapshot.tree_nodes_by_id[current_id].parent_id != "":
                current_id = self._snapshot.tree_nodes_by_id[current_id].parent_id
                included_ids.add(current_id)
        return included_ids

    @staticmethod
    def _required_int(payload: dict[str, object], key: str) -> int:
        value = payload[key]
        assert isinstance(value, int) and not isinstance(value, bool)
        return value

    @staticmethod
    def _required_str(payload: dict[str, object], key: str) -> str:
        value = payload[key]
        assert isinstance(value, str) and value != ""
        return value

    @staticmethod
    def _total_pages(*, item_count: int, page_size: int) -> int:
        if item_count < 0 or page_size < 1:
            raise ValueError("Pagination counts are invalid")
        return max(1, (item_count + page_size - 1) // page_size)
