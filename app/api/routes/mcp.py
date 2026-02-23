from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response

from app.mcp.read_service import ReadService
from app.mcp.server import handle_message


router = APIRouter(prefix="/mcp", tags=["mcp"])
_read_service = ReadService()


@router.post("")
def mcp_endpoint(payload: dict):
    response = handle_message(payload=payload, read_service=_read_service)
    if response is None:
        return Response(status_code=204)

    if "error" in response:
        return response

    if "result" in response:
        result = response["result"]
        if isinstance(result, dict) and "isError" in result:
            return response

    return response
