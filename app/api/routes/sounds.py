from __future__ import annotations

from io import BytesIO
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.request_auth import require_request_auth_token
from app.api.transactions import transactional_route
from app.services.exception_capture import CapturedExceptionContext
from app.services.sound_storage import SoundRecord
from app.services.sound_storage import sound_store


router = APIRouter(prefix="/sounds", tags=["sounds"])


class SoundResponse(BaseModel):
    id: str
    title: str
    original_filename: str
    mime_type: str
    size_bytes: int
    duration_seconds: float
    is_builtin: bool
    created_at: str
    updated_at: str


class SoundLibraryUsageResponse(BaseModel):
    uploaded_bytes: int
    max_uploaded_bytes: int
    max_sound_bytes: int
    max_duration_seconds: float


class SoundListResponse(BaseModel):
    sounds: list[SoundResponse]
    usage: SoundLibraryUsageResponse


class SoundUploadResponse(BaseModel):
    sound: SoundResponse
    usage: SoundLibraryUsageResponse


class SoundUpdateRequest(BaseModel):
    title: str


class SoundUpdateResponse(BaseModel):
    sound: SoundResponse


def _require_bearer_token(request: Request) -> str:
    return require_request_auth_token(request)


def _serialize_sound(record: SoundRecord) -> SoundResponse:
    return SoundResponse(
        id=record.id,
        title=record.title,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        duration_seconds=record.duration_seconds,
        is_builtin=record.is_builtin,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _raise_storage_http(exc: BaseException) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise RuntimeError(f"Unexpected sound storage exception type: {type(exc)}") from exc


def _captured_result(capture: CapturedExceptionContext, result: object) -> object:
    if capture.captured_exception is not None:
        _raise_storage_http(capture.captured_exception)
    return result


def _list_response() -> SoundListResponse:
    snapshot = sound_store.list_sounds()
    return SoundListResponse(
        sounds=[_serialize_sound(record) for record in snapshot.sounds],
        usage=SoundLibraryUsageResponse(
            uploaded_bytes=snapshot.uploaded_bytes,
            max_uploaded_bytes=snapshot.max_uploaded_bytes,
            max_sound_bytes=snapshot.max_sound_bytes,
            max_duration_seconds=snapshot.max_duration_seconds,
        ),
    )


@router.get("", response_model=SoundListResponse)
def list_sounds(request: Request) -> SoundListResponse:
    _require_bearer_token(request)
    return _list_response()


@router.post("/upload", response_model=SoundUploadResponse)
@transactional_route
async def upload_sound(
    request: Request,
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> SoundUploadResponse:
    token = _require_bearer_token(request)
    if not isinstance(file.filename, str) or file.filename == "":
        raise HTTPException(status_code=400, detail="Uploaded sound must include a filename")
    if not isinstance(file.content_type, str) or file.content_type == "":
        raise HTTPException(status_code=400, detail="Uploaded sound must include a non-empty MIME type")

    try:
        content_bytes = await file.read()
    finally:
        await file.close()

    capture = CapturedExceptionContext(KeyError, ValueError)
    record: SoundRecord | None = None
    with capture:
        record = sound_store.create_sound(
            title=title,
            original_filename=file.filename,
            mime_type=file.content_type,
            content_bytes=content_bytes,
            token=token,
        )
    _captured_result(capture, record)
    if record is None:
        raise RuntimeError("Sound upload did not return a record")
    return SoundUploadResponse(sound=_serialize_sound(record), usage=_list_response().usage)


@router.put("/{sound_id}", response_model=SoundUpdateResponse)
@transactional_route
def update_sound_title(
    sound_id: str,
    request: Request,
    payload: SoundUpdateRequest,
) -> SoundUpdateResponse:
    token = _require_bearer_token(request)
    capture = CapturedExceptionContext(KeyError, ValueError)
    record: SoundRecord | None = None
    with capture:
        record = sound_store.update_sound_title(sound_id=sound_id, title=payload.title, token=token)
    _captured_result(capture, record)
    if record is None:
        raise RuntimeError("Sound update did not return a record")
    return SoundUpdateResponse(sound=_serialize_sound(record))


@router.delete("/{sound_id}")
@transactional_route
def delete_sound(sound_id: str, request: Request) -> dict[str, bool]:
    _require_bearer_token(request)
    capture = CapturedExceptionContext(KeyError, ValueError)
    with capture:
        sound_store.delete_sound(sound_id=sound_id)
    _captured_result(capture, None)
    return {"ok": True}


@router.get("/{sound_id}/play")
def play_sound(sound_id: str, request: Request):
    _require_bearer_token(request)
    capture = CapturedExceptionContext(KeyError, ValueError)
    stored = None
    with capture:
        stored = sound_store.get_sound(sound_id=sound_id)
    _captured_result(capture, stored)
    if stored is None:
        raise RuntimeError("Sound playback did not return stored sound")
    quoted_filename = quote(stored.record.original_filename, safe="")
    return StreamingResponse(
        BytesIO(stored.content_bytes),
        media_type=stored.record.mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted_filename}",
            "Cache-Control": "no-store",
        },
    )
