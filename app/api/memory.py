"""Memory mode API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mako.lookup import TemplateLookup

from .dependencies import get_db
from ..models.database import SafeSession
from ..core.config import VERSION
from ..services.memory_service import MemoryService, apply_memory_flags

router = APIRouter(prefix="/memory", tags=["memory"])

_template_lookup = TemplateLookup(
    directories=[str(Path(__file__).parent.parent / "templates")]
)


class MemoryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    search_query: str = Field(..., alias="searchQuery")
    previous_note_id: Optional[str] = Field(None, alias="previousNoteId")
    feedback: Optional[int] = Field(None)

    @field_validator("search_query")
    @classmethod
    def ensure_search_not_none(cls, value: str) -> str:
        if value is None:
            raise ValueError("searchQuery is required")
        return value

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value not in (-1, 0, 1):
            raise ValueError("feedback must be -1, 0, or 1")
        return value


class MemoryStatsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    positive: float
    negative: float
    ratio: float
    total: float


class MemoryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    note_id: str = Field(..., alias="noteId")
    root_note_id: str = Field(..., alias="rootNoteId")
    html: str
    probability: float
    stats: MemoryStatsResponse


@router.post("", response_model=MemoryResponse)
def fetch_memory_note(payload: MemoryRequest, db: SafeSession = Depends(get_db)) -> MemoryResponse:
    if payload.search_query is None:
        raise HTTPException(status_code=422, detail="searchQuery is required for memory mode")

    service = MemoryService(db)

    if payload.previous_note_id and payload.feedback is not None:
        service.record_feedback(payload.previous_note_id, payload.feedback)

    notes = service.build_candidate_tree(payload.search_query or None)
    if not notes:
        raise HTTPException(status_code=404, detail="No notes available for the current search context")

    selected_note, root_note, stats, probability = service.choose_note(
        notes,
        payload.previous_note_id,
    )
    apply_memory_flags(root_note, selected_note['id'])

    template = _template_lookup.get_template('notes_list.html')
    html = template.render(
        notes=[root_note],
        version=VERSION,
        note_locks={},
        current_client_id=None,
        search_query=payload.search_query,
    )

    stats_response = MemoryStatsResponse(
        positive=stats.pos,
        negative=stats.neg,
        ratio=stats.ratio,
        total=stats.total,
    )

    return MemoryResponse(
        note_id=selected_note['id'],
        root_note_id=root_note['id'],
        html=html,
        probability=probability,
        stats=stats_response,
    )
