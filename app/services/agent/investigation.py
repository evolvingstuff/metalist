"""Bounded navigation and refinement inside one frozen agent scope."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.evidence_serialization import EvidenceNoteTokenSource
from app.services.agent.evidence_serialization import EvidenceTreeTokenSource
from app.services.agent.evidence_serialization import estimate_cached_root_tree_tokens
from app.services.agent.evidence_serialization import serialize_evidence_note_payload
from app.services.agent.evidence_serialization import serialize_evidence_result_trees
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.scope import FrozenScopedNote
from app.services.agent.scope import ScopedSearchSnapshot
from app.services.agent.token_estimation import estimate_input_tokens
from app.services.search_query import SearchClause
from app.services.search_query import parse_search_query
from app.services.tag_term_matching import tag_term_matches_prefix
from app.services.tag_ontology import TagOntology


@dataclass(frozen=True, slots=True)
class TagFacet:
    tag: str
    note_count: int
    result_tree_count: int
    synonyms: tuple[str, ...]


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
class InvestigationScopeSize:
    note_count: int
    result_tree_count: int
    approximate_token_count: int


@dataclass(frozen=True, slots=True)
class RootPrefixRetention:
    original_note_count: int
    original_result_tree_count: int
    retained_note_count: int
    retained_result_tree_count: int
    retained_approximate_token_count: int
    retained_root_ids: tuple[str, ...]
    dropped_root_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NarrowingAttempt:
    tags: tuple[str, ...]
    expression: str
    note_count: int
    result_tree_count: int
    approximate_token_count: int
    rejected_zero_results: bool


@dataclass(frozen=True, slots=True)
class NarrowingResult:
    target_approximate_token_count: int
    original: InvestigationScopeSize
    attempts: tuple[NarrowingAttempt, ...]
    selected_tags: tuple[str, ...]
    selected_expression: str
    selected: InvestigationScopeSize
    did_narrow: bool


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
        ontology: TagOntology,
    ) -> None:
        if not isinstance(ontology, TagOntology):
            raise TypeError("ontology must be TagOntology")
        self._snapshot = snapshot
        self._settings = settings
        self._ontology = ontology
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
        self._equivalent_tags_by_folded_tag: dict[str, frozenset[str]] = {}
        self._inherited_explicit_tag_terms_by_note_id: dict[str, tuple[str, ...]] = {}
        self._matching_note_ids_by_state_and_folded_tag: dict[
            tuple[str, str], frozenset[str]
        ] = {}
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
        return cls(
            snapshot=snapshot,
            settings=settings,
            ontology=TagOntology.empty(),
        )

    @classmethod
    def start_with_ontology(
        cls,
        *,
        snapshot: ScopedSearchSnapshot,
        settings: AgentRetrievalSettings,
        ontology: TagOntology,
    ) -> InvestigationState:
        if not isinstance(snapshot, ScopedSearchSnapshot):
            raise TypeError("InvestigationState requires ScopedSearchSnapshot")
        if not isinstance(settings, AgentRetrievalSettings):
            raise TypeError("InvestigationState requires AgentRetrievalSettings")
        if not isinstance(ontology, TagOntology):
            raise TypeError("InvestigationState requires TagOntology")
        return cls(snapshot=snapshot, settings=settings, ontology=ontology)

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
    def required_scope_tags(self) -> frozenset[str]:
        if self._snapshot.descriptor.scope_kind not in {"search", "reference"}:
            return frozenset()
        parsed = parse_search_query(self._snapshot.descriptor.search_query)
        required_by_clause = [
            {tag.casefold() for tag in clause.required_tags}
            for clause in parsed.clauses
        ]
        if not required_by_clause:
            raise RuntimeError("Parsed scope query contains no clauses")
        required_in_every_clause = set(required_by_clause[0])
        for clause_tags in required_by_clause[1:]:
            required_in_every_clause.intersection_update(clause_tags)
        equivalents: set[str] = set()
        for tag in required_in_every_clause:
            equivalents.update(self._folded_equivalent_tags(tag))
        return frozenset(equivalents)

    @property
    def total_note_pages(self) -> int:
        return len(self._current_root_pages())

    def current_scope_size(self) -> InvestigationScopeSize:
        root_ids = self._current_root_ids()
        return self._scope_size(
            note_ids=self._current_state.note_ids,
            root_ids=root_ids,
        )

    def retain_root_prefix_within_token_budget(self) -> RootPrefixRetention:
        original_root_ids = tuple(self._current_root_ids())
        original_note_count = len(self._current_state.note_ids)
        note_ids_by_root_id: dict[str, list[str]] = {
            root_id: [] for root_id in original_root_ids
        }
        for note_id in self._current_state.note_ids:
            root_id = self._snapshot.notes_by_id[note_id].root_note_id
            note_ids_by_root_id[root_id].append(note_id)
        retained_root_id_list: list[str] = []
        retained_token_count = 0
        for root_id in original_root_ids:
            root_token_count = self._full_root_page_token_cost(
                root_id=root_id,
                note_ids=note_ids_by_root_id[root_id],
            )
            if (
                retained_token_count + root_token_count
                > self._settings.max_page_approximate_tokens
            ):
                break
            retained_root_id_list.append(root_id)
            retained_token_count += root_token_count
        retained_root_ids = tuple(retained_root_id_list)
        retained_root_id_set = set(retained_root_ids)
        retained_note_ids = tuple(
            note_id
            for note_id in self._current_state.note_ids
            if self._snapshot.notes_by_id[note_id].root_note_id
            in retained_root_id_set
        )
        dropped_root_ids = original_root_ids[len(retained_root_ids) :]
        if dropped_root_ids:
            self._push_subset(
                note_ids=retained_note_ids,
                refinement_label="token-bounded leading root prefix",
            )
        return RootPrefixRetention(
            original_note_count=original_note_count,
            original_result_tree_count=len(original_root_ids),
            retained_note_count=len(retained_note_ids),
            retained_result_tree_count=len(retained_root_ids),
            retained_approximate_token_count=retained_token_count,
            retained_root_ids=retained_root_ids,
            dropped_root_ids=dropped_root_ids,
        )

    def narrow_by_ordered_tags(
        self,
        *,
        ordered_tags: list[str],
        target_approximate_tokens: int,
    ) -> NarrowingResult:
        if not isinstance(ordered_tags, list):
            raise TypeError("ordered_tags must be a list")
        if any(not isinstance(tag, str) or tag.strip() == "" for tag in ordered_tags):
            raise ValueError("Narrowing tags must be non-empty strings")
        normalized_tags = [tag.strip() for tag in ordered_tags]
        folded_tags = [tag.casefold() for tag in normalized_tags]
        if len(set(folded_tags)) != len(folded_tags):
            raise ValueError("Narrowing tags must be unique")
        if not set(folded_tags).issubset(self._disclosed_tags):
            raise ValueError("Narrowing tags must have been disclosed")
        redundant_scope_tags = set(folded_tags).intersection(
            self.required_scope_tags
        )
        if redundant_scope_tags:
            raise ValueError(
                "Narrowing tags already required by the frozen user search: "
                + ", ".join(sorted(redundant_scope_tags))
            )
        if target_approximate_tokens < 1:
            raise ValueError("Narrowing target must be positive")
        original = self.current_scope_size()
        attempts: list[NarrowingAttempt] = []
        best_tags: tuple[str, ...] = ()
        best_ids = self._current_state.note_ids
        best_size = original
        found_candidate_at_or_below_target = False
        for tag_index in range(len(normalized_tags)):
            prefix = tuple(normalized_tags[: tag_index + 1])
            prefix_folded = tuple(tag.casefold() for tag in prefix)
            refined_ids = tuple(
                note_id
                for note_id in self._current_state.note_ids
                if all(
                    self._note_matches_effective_tag(
                        note_id=note_id,
                        required_tag=required,
                    )
                    for required in prefix_folded
                )
            )
            expression = " ".join(prefix)
            if not refined_ids:
                attempts.append(
                    NarrowingAttempt(
                        tags=prefix,
                        expression=expression,
                        note_count=0,
                        result_tree_count=0,
                        approximate_token_count=0,
                        rejected_zero_results=True,
                    )
                )
                break
            root_ids = self._root_ids_for_note_ids(refined_ids)
            size = self._scope_size(note_ids=refined_ids, root_ids=root_ids)
            attempts.append(
                NarrowingAttempt(
                    tags=prefix,
                    expression=expression,
                    note_count=size.note_count,
                    result_tree_count=size.result_tree_count,
                    approximate_token_count=size.approximate_token_count,
                    rejected_zero_results=False,
                )
            )
            if not found_candidate_at_or_below_target:
                best_tags = prefix
                best_ids = refined_ids
                best_size = size
                if size.approximate_token_count <= target_approximate_tokens:
                    found_candidate_at_or_below_target = True
        did_narrow = best_tags != () and best_ids != self._current_state.note_ids
        selected_expression = " ".join(best_tags)
        if did_narrow:
            self._push_subset(
                note_ids=best_ids,
                refinement_label=selected_expression,
            )
        return NarrowingResult(
            target_approximate_token_count=target_approximate_tokens,
            original=original,
            attempts=tuple(attempts),
            selected_tags=best_tags,
            selected_expression=selected_expression,
            selected=best_size,
            did_narrow=did_narrow,
        )

    def current_note_page(self) -> InvestigationNotePage:
        root_ids = self._current_root_ids()
        root_pages = self._current_root_pages()
        total_pages = len(root_pages)
        if self._note_page > total_pages:
            raise RuntimeError("Current note page exceeds total pages")
        page_root_ids = root_pages[self._note_page - 1]
        return self._build_note_page(
            page=self._note_page,
            total_pages=total_pages,
            matching_root_ids=root_ids,
            page_root_ids=page_root_ids,
        )

    def current_scope_as_single_page(self) -> InvestigationNotePage:
        if self._note_page != 1:
            raise RuntimeError("Single-page scope serialization requires page 1")
        root_ids = self._current_root_ids()
        return self._build_note_page(
            page=1,
            total_pages=1,
            matching_root_ids=root_ids,
            page_root_ids=tuple(root_ids),
        )

    def _build_note_page(
        self,
        *,
        page: int,
        total_pages: int,
        matching_root_ids: list[str],
        page_root_ids: tuple[str, ...],
    ) -> InvestigationNotePage:
        page_root_id_set = set(page_root_ids)
        page_note_ids = [
            note_id
            for note_id in self._current_state.note_ids
            if self._snapshot.notes_by_id[note_id].root_note_id in page_root_id_set
        ]
        (
            result_trees,
            returned_character_count,
            approximate_tokens,
        ) = self._serialize_token_bounded_page(
            root_ids=page_root_ids,
            note_ids=page_note_ids,
        )
        self._observed_source_ids.update(page_note_ids)
        for note_id in page_note_ids:
            note = self._snapshot.notes_by_id[note_id]
            self._disclosed_tags.update(
                tag.casefold() for tag in note.explicit_tag_terms
            )
        return InvestigationNotePage(
            state_id=self._current_state.state_id,
            page=page,
            total_pages=total_pages,
            matching_note_count=len(self._current_state.note_ids),
            matching_result_tree_count=len(matching_root_ids),
            evidence_note_ids=tuple(page_note_ids),
            result_tree_ids=page_root_ids,
            result_trees=result_trees,
            returned_character_count=returned_character_count,
            returned_approximate_token_count=approximate_tokens,
        )

    def current_facet_page(self) -> TagFacetPage:
        ranked = self._ranked_facets()
        return self._facet_page_from_ranked(ranked=ranked)

    def current_narrowing_facet_page(self) -> TagFacetPage:
        if self._facet_page != 1:
            raise RuntimeError("Automatic narrowing requires the first facet page")
        ranked = [
            facet
            for facet in self._ranked_narrowing_facets()
            if not facet.tag.startswith("@")
            and facet.tag.casefold() not in self.required_scope_tags
        ]
        return self._facet_page_from_ranked(ranked=ranked)

    def _facet_page_from_ranked(self, *, ranked: list[TagFacet]) -> TagFacetPage:
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

    def _root_ids_for_note_ids(self, note_ids: tuple[str, ...]) -> list[str]:
        roots_with_matches = {
            self._snapshot.notes_by_id[note_id].root_note_id
            for note_id in note_ids
        }
        return [
            root_id
            for root_id in self._snapshot.ordered_root_ids
            if root_id in roots_with_matches
        ]

    def _scope_size(
        self,
        *,
        note_ids: tuple[str, ...],
        root_ids: list[str],
    ) -> InvestigationScopeSize:
        token_count = sum(
            self._full_root_page_token_cost(
                root_id=root_id,
                note_ids=[
                    note_id
                    for note_id in note_ids
                    if self._snapshot.notes_by_id[note_id].root_note_id == root_id
                ],
            )
            for root_id in root_ids
        )
        return InvestigationScopeSize(
            note_count=len(note_ids),
            result_tree_count=len(root_ids),
            approximate_token_count=token_count,
        )

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
                synonyms=self._synonyms_for_tag(folded),
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

    def _ranked_narrowing_facets(self) -> list[TagFacet]:
        spellings_by_folded_tag: dict[str, set[str]] = {}
        for note_id in self._current_state.note_ids:
            note = self._snapshot.notes_by_id[note_id]
            for tag in note.explicit_tag_terms:
                folded = tag.casefold()
                if folded not in spellings_by_folded_tag:
                    spellings_by_folded_tag[folded] = set()
                spellings_by_folded_tag[folded].add(tag)
        equivalents_by_folded_tag = {
            folded: self._folded_equivalent_tags(folded)
            for folded in spellings_by_folded_tag
        }
        matching_candidates_by_explicit_term: dict[str, frozenset[str]] = {}
        matching_note_ids_by_folded_tag = {
            folded: set() for folded in spellings_by_folded_tag
        }
        matching_root_ids_by_folded_tag = {
            folded: set() for folded in spellings_by_folded_tag
        }
        for note_id in self._current_state.note_ids:
            matched_folded_tags: set[str] = set()
            for explicit_term in self._inherited_explicit_tag_terms(note_id=note_id):
                normalized_term = explicit_term.casefold()
                if normalized_term not in matching_candidates_by_explicit_term:
                    matching_candidates_by_explicit_term[normalized_term] = frozenset(
                        folded
                        for folded, equivalents in equivalents_by_folded_tag.items()
                        if any(
                            tag_term_matches_prefix(
                                term=explicit_term,
                                prefix=equivalent,
                            )
                            for equivalent in equivalents
                        )
                    )
                matched_folded_tags.update(
                    matching_candidates_by_explicit_term[normalized_term]
                )
            root_note_id = self._snapshot.notes_by_id[note_id].root_note_id
            for matched_folded_tag in matched_folded_tags:
                matching_note_ids_by_folded_tag[matched_folded_tag].add(note_id)
                matching_root_ids_by_folded_tag[matched_folded_tag].add(root_note_id)
        facets: list[TagFacet] = []
        for folded, spellings in spellings_by_folded_tag.items():
            matching_note_ids = matching_note_ids_by_folded_tag[folded]
            matching_root_ids = matching_root_ids_by_folded_tag[folded]
            self._matching_note_ids_by_state_and_folded_tag[
                (self._current_state.state_id, folded)
            ] = frozenset(matching_note_ids)
            facets.append(
                TagFacet(
                    tag=sorted(
                        spellings,
                        key=lambda value: (value.casefold(), value),
                    )[0],
                    note_count=len(matching_note_ids),
                    result_tree_count=len(matching_root_ids),
                    synonyms=self._synonyms_for_tag(folded),
                )
            )
        facets.sort(
            key=lambda facet: (
                -facet.note_count,
                -facet.result_tree_count,
                facet.tag.casefold(),
                facet.tag,
            )
        )
        return facets

    def _note_matches_effective_tag(
        self,
        *,
        note_id: str,
        required_tag: str,
    ) -> bool:
        folded_required_tag = required_tag.casefold()
        cache_key = (self._current_state.state_id, folded_required_tag)
        if cache_key in self._matching_note_ids_by_state_and_folded_tag:
            return note_id in self._matching_note_ids_by_state_and_folded_tag[cache_key]
        equivalents = self._folded_equivalent_tags(folded_required_tag)
        return any(
            tag_term_matches_prefix(term=term, prefix=equivalent)
            for term in self._inherited_explicit_tag_terms(note_id=note_id)
            for equivalent in equivalents
        )

    def _inherited_explicit_tag_terms(self, *, note_id: str) -> tuple[str, ...]:
        if note_id in self._inherited_explicit_tag_terms_by_note_id:
            return self._inherited_explicit_tag_terms_by_note_id[note_id]
        inherited_terms: list[str] = []
        seen_folded_terms: set[str] = set()
        current_id = note_id
        visited: set[str] = set()
        while current_id != "":
            if current_id in visited:
                raise RuntimeError(f"Hierarchy cycle detected at {current_id}")
            visited.add(current_id)
            if current_id in self._snapshot.notes_by_id:
                note = self._snapshot.notes_by_id[current_id]
                for term in note.explicit_tag_terms:
                    folded_term = term.casefold()
                    if folded_term in seen_folded_terms:
                        continue
                    seen_folded_terms.add(folded_term)
                    inherited_terms.append(term)
            node = self._snapshot.tree_nodes_by_id[current_id]
            current_id = node.parent_id
        frozen_terms = tuple(inherited_terms)
        self._inherited_explicit_tag_terms_by_note_id[note_id] = frozen_terms
        return frozen_terms

    def _synonyms_for_tag(self, folded_tag: str) -> tuple[str, ...]:
        equivalents = self._equivalent_tags(folded_tag)
        return tuple(
            sorted(
                (tag for tag in equivalents if tag.casefold() != folded_tag),
                key=lambda value: (value.casefold(), value),
            )
        )

    def _folded_equivalent_tags(self, folded_tag: str) -> frozenset[str]:
        return frozenset(tag.casefold() for tag in self._equivalent_tags(folded_tag))

    def _equivalent_tags(self, folded_tag: str) -> frozenset[str]:
        if folded_tag in self._equivalent_tags_by_folded_tag:
            return self._equivalent_tags_by_folded_tag[folded_tag]
        matching_keys = [
            tag
            for tag in self._ontology.scc_members_by_tag
            if tag.casefold() == folded_tag
        ]
        if not matching_keys:
            equivalents = frozenset({folded_tag})
            self._equivalent_tags_by_folded_tag[folded_tag] = equivalents
            return equivalents
        equivalents: set[str] = set()
        for matching_key in matching_keys:
            _left, equals, _right = self._ontology.focus_view(tag=matching_key)
            equivalents.update(equals)
        if not equivalents:
            raise RuntimeError("Ontology equivalence lookup returned no tags")
        frozen_equivalents = frozenset(equivalents)
        self._equivalent_tags_by_folded_tag[folded_tag] = frozen_equivalents
        return frozen_equivalents

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
        evidence_notes = tuple(
            EvidenceNoteTokenSource(
                note_id=note_id,
                content_text=self._snapshot.notes_by_id[note_id].content_text,
                explicit_tag_terms=(
                    self._snapshot.notes_by_id[note_id].explicit_tag_terms
                ),
                created_at=self._snapshot.notes_by_id[note_id].created_at,
                updated_at=self._snapshot.notes_by_id[note_id].updated_at,
                character_limit=min(
                    len(self._snapshot.notes_by_id[note_id].content_text),
                    self._settings.max_note_characters,
                ),
            )
            for note_id in note_ids
        )
        structure_nodes = tuple(
            EvidenceTreeTokenSource(
                note_id=note_id,
                parent_id=node.parent_id,
                child_ids=node.child_ids,
            )
            for note_id, node in self._snapshot.tree_nodes_by_id.items()
            if node.root_note_id == root_id
        )
        return estimate_cached_root_tree_tokens(
            root_id=root_id,
            evidence_notes=evidence_notes,
            structure_nodes=structure_nodes,
        )

    def _serialize_token_bounded_page(
        self,
        *,
        root_ids: tuple[str, ...],
        note_ids: list[str],
    ) -> tuple[tuple[dict[str, object], ...], int, int]:
        full_character_limits = [
            min(
                len(self._snapshot.notes_by_id[note_id].content_text),
                self._settings.max_note_characters,
            )
            for note_id in note_ids
        ]
        maximum_content_characters = sum(full_character_limits)
        full_trees, full_returned_characters = self._serialize_page(
            root_ids=root_ids,
            note_ids=note_ids,
            character_limits=full_character_limits,
        )
        full_token_cost = estimate_input_tokens(full_trees)
        if full_token_cost <= self._settings.max_page_approximate_tokens:
            return full_trees, full_returned_characters, full_token_cost

        lower = 0
        upper = maximum_content_characters - 1
        best_trees, best_returned_characters = self._serialize_page(
            root_ids=root_ids,
            note_ids=note_ids,
            character_limits=[0 for _note_id in note_ids],
        )
        minimum_cost = estimate_input_tokens(best_trees)
        if minimum_cost > self._settings.max_page_approximate_tokens:
            return best_trees, best_returned_characters, minimum_cost
        best_token_cost = minimum_cost

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
                best_token_cost = token_cost
                lower = candidate + 1
            else:
                upper = candidate - 1
        return best_trees, best_returned_characters, best_token_cost

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
            serialize_evidence_note_payload(
                note_id=self._snapshot.notes_by_id[note_id].note_id,
                content_text=self._snapshot.notes_by_id[note_id].content_text,
                explicit_tag_terms=(
                    self._snapshot.notes_by_id[note_id].explicit_tag_terms
                ),
                created_at=self._snapshot.notes_by_id[note_id].created_at,
                updated_at=self._snapshot.notes_by_id[note_id].updated_at,
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
        result_trees = serialize_evidence_result_trees(
            root_ids=root_ids,
            evidence_payloads_by_id=serialized_by_id,
            parent_id_by_id={
                note_id: node.parent_id
                for note_id, node in self._snapshot.tree_nodes_by_id.items()
            },
            child_ids_by_id={
                note_id: node.child_ids
                for note_id, node in self._snapshot.tree_nodes_by_id.items()
            },
        )
        return result_trees, returned_character_count

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
