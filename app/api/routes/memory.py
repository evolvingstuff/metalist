from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from pathlib import Path

from app.api.deps import get_db
from app.models.database import SafeSession
from app.core.config import VERSION
from app.services.memory_service import MemoryService, apply_memory_flags
from app.presentation.templates import get_templates


router = APIRouter(tags=["memory2"])


class MemoryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    search_query: str = Field(..., alias="searchQuery")
    previous_note_id: Optional[str] = Field(None, alias="previousNoteId")
    feedback: Optional[int] = Field(None)

    @field_validator("search_query")
    @classmethod
    def ensure_query(cls, value: str) -> str:
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


class MemoryStats(BaseModel):
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
    stats: MemoryStats


@router.post("/memory", response_model=MemoryResponse)
def memory_endpoint(payload: MemoryRequest, db: SafeSession = Depends(get_db)) -> MemoryResponse:
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

    template = get_templates().get_template('notes_list.html')
    html = template.render(
        notes=[root_note],
        version=VERSION,
        note_locks={},
        current_client_id=None,
        search_query=payload.search_query,
    )

    stats_response = MemoryStats(
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
