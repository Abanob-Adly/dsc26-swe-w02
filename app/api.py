import base64
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain import (
    EventType,
    InvalidTransition,
    Parcel,
    ParcelState,
    apply_event,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_response(
    status_code: int,
    title: str,
    detail: Optional[str] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> JSONResponse:
    content: Dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
    }
    if detail is not None:
        content["detail"] = detail
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type=PROBLEM_MEDIA_TYPE,
    )


# --- Pydantic Schemas ---

class CreateParcelRequest(BaseModel):
    merchant_ref: str = Field(min_length=1, max_length=64)
    cod_amount_piastres: int = Field(ge=0, le=5000000)
    address_text: str = Field(min_length=1, max_length=500)


class EventRequest(BaseModel):
    type: EventType


class ParcelResponse(BaseModel):
    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: ParcelState
    attempts: int


class ParcelListResponse(BaseModel):
    items: List[ParcelResponse]
    next_cursor: Optional[str] = None


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: Optional[str] = None
    errors: Optional[List[Dict[str, Any]]] = None


def create_app() -> FastAPI:
    app = FastAPI(title="Tawseel Parcel API")

    # In-memory store per app instance
    parcels_list: List[Parcel] = []
    parcels_by_id: Dict[str, Parcel] = {}
    merchant_refs: set = set()

    # --- Exception Handlers for RFC 9457 ---

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        formatted_errors = []
        for err in exc.errors():
            formatted_errors.append(
                {
                    "loc": list(err.get("loc", [])),
                    "msg": err.get("msg", ""),
                }
            )
        return problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Unprocessable Entity",
            errors=formatted_errors,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        title_map = {
            400: "Bad Request",
            404: "Not Found",
            409: "Conflict",
            422: "Unprocessable Entity",
        }
        title = title_map.get(exc.status_code, "Error")
        return problem_response(
            status_code=exc.status_code,
            title=title,
            detail=str(exc.detail) if exc.detail else None,
        )

    # --- Endpoints ---

    @app.post(
        "/v1/parcels",
        response_model=ParcelResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createParcel",
        responses={
            201: {"description": "Parcel created successfully"},
            409: {"model": ProblemDetail, "description": "Duplicate merchant_ref"},
            422: {"model": ProblemDetail, "description": "Validation Error"},
        },
    )
    def create_parcel(payload: CreateParcelRequest):
        if payload.merchant_ref in merchant_refs:
            return problem_response(
                status_code=status.HTTP_409_CONFLICT,
                title="Conflict",
                detail=f"Parcel with merchant_ref '{payload.merchant_ref}' already exists",
            )

        parcel_id = f"pcl_{len(parcels_list) + 1}"
        parcel = Parcel(
            id=parcel_id,
            merchant_ref=payload.merchant_ref,
            cod_amount_piastres=payload.cod_amount_piastres,
            address_text=payload.address_text,
            state=ParcelState.CREATED,
            attempts=0,
        )

        parcels_list.append(parcel)
        parcels_by_id[parcel_id] = parcel
        merchant_refs.add(payload.merchant_ref)

        headers = {"Location": f"/v1/parcels/{parcel_id}"}
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "id": parcel.id,
                "merchant_ref": parcel.merchant_ref,
                "cod_amount_piastres": parcel.cod_amount_piastres,
                "address_text": parcel.address_text,
                "state": parcel.state,
                "attempts": parcel.attempts,
            },
            headers=headers,
        )

    @app.get(
        "/v1/parcels/{parcel_id}",
        response_model=ParcelResponse,
        operation_id="getParcel",
        responses={
            200: {"description": "Parcel details"},
            404: {"model": ProblemDetail, "description": "Parcel not found"},
        },
    )
    def get_parcel(parcel_id: str):
        if parcel_id not in parcels_by_id:
            return problem_response(
                status_code=status.HTTP_404_NOT_FOUND,
                title="Not Found",
                detail=f"Parcel '{parcel_id}' not found",
            )
        parcel = parcels_by_id[parcel_id]
        return {
            "id": parcel.id,
            "merchant_ref": parcel.merchant_ref,
            "cod_amount_piastres": parcel.cod_amount_piastres,
            "address_text": parcel.address_text,
            "state": parcel.state,
            "attempts": parcel.attempts,
        }

    @app.get(
        "/v1/parcels",
        response_model=ParcelListResponse,
        operation_id="listParcels",
        responses={
            200: {"description": "List of parcels"},
            400: {"model": ProblemDetail, "description": "Invalid cursor"},
            422: {"model": ProblemDetail, "description": "Invalid query parameters"},
        },
    )
    def list_parcels(
        state: Optional[str] = Query(None),
        limit: int = Query(20),
        cursor: Optional[str] = Query(None),
    ):
        # Validate limit
        if limit < 1 or limit > 100:
            return problem_response(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                title="Unprocessable Entity",
                errors=[
                    {
                        "loc": ["query", "limit"],
                        "msg": "Limit must be between 1 and 100",
                    }
                ],
            )

        # Validate state enum if provided
        if state is not None:
            if state not in [s.value for s in ParcelState]:
                return problem_response(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    title="Unprocessable Entity",
                    errors=[
                        {
                            "loc": ["query", "state"],
                            "msg": f"Input should be a valid ParcelState, got '{state}'",
                        }
                    ],
                )

        # Determine start index using cursor
        start_index = 0
        if cursor is not None:
            try:
                decoded_cursor = base64.b64decode(cursor.encode("utf-8")).decode(
                    "utf-8"
                )
                if not decoded_cursor.startswith("cursor_pcl_"):
                    raise ValueError("Invalid cursor format")
                cursor_id = decoded_cursor.replace("cursor_pcl_", "")

                # Find cursor position in master creation list
                cursor_found = False
                for idx, p in enumerate(parcels_list):
                    if p.id == cursor_id:
                        start_index = idx + 1
                        cursor_found = True
                        break
                if not cursor_found:
                    return problem_response(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        title="Bad Request",
                        detail="Invalid cursor",
                    )
            except Exception:
                return problem_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    title="Bad Request",
                    detail="Invalid cursor",
                )

        # Iterate through master list from start_index to collect matching items
        matching_items: List[Parcel] = []
        last_processed_index = start_index - 1

        for idx in range(start_index, len(parcels_list)):
            p = parcels_list[idx]
            current_p = parcels_by_id[p.id]  # Get latest state
            if state is None or current_p.state == state:
                matching_items.append(current_p)
                last_processed_index = idx
                if len(matching_items) == limit:
                    break

        # Check if there are more matching items in remaining master list
        has_more = False
        for idx in range(last_processed_index + 1, len(parcels_list)):
            p = parcels_list[idx]
            current_p = parcels_by_id[p.id]
            if state is None or current_p.state == state:
                has_more = True
                break

        next_cursor = None
        if has_more and matching_items:
            last_item_id = matching_items[-1].id
            raw_cursor = f"cursor_pcl_{last_item_id}"
            next_cursor = base64.b64encode(raw_cursor.encode("utf-8")).decode("utf-8")

        items_json = [
            {
                "id": item.id,
                "merchant_ref": item.merchant_ref,
                "cod_amount_piastres": item.cod_amount_piastres,
                "address_text": item.address_text,
                "state": item.state,
                "attempts": item.attempts,
            }
            for item in matching_items
        ]

        return {"items": items_json, "next_cursor": next_cursor}

    @app.post(
        "/v1/parcels/{parcel_id}/events",
        response_model=ParcelResponse,
        operation_id="recordParcelEvent",
        responses={
            200: {"description": "Parcel event recorded"},
            404: {"model": ProblemDetail, "description": "Parcel not found"},
            409: {"model": ProblemDetail, "description": "Invalid state transition"},
            422: {"model": ProblemDetail, "description": "Invalid event payload"},
        },
    )
    def record_parcel_event(parcel_id: str, payload: EventRequest):
        if parcel_id not in parcels_by_id:
            return problem_response(
                status_code=status.HTTP_404_NOT_FOUND,
                title="Not Found",
                detail=f"Parcel '{parcel_id}' not found",
            )

        current_parcel = parcels_by_id[parcel_id]
        try:
            updated_parcel = apply_event(current_parcel, payload.type)
        except InvalidTransition as exc:
            return problem_response(
                status_code=status.HTTP_409_CONFLICT,
                title="Conflict",
                detail=str(exc),
            )

        # Update store
        parcels_by_id[parcel_id] = updated_parcel
        for idx, p in enumerate(parcels_list):
            if p.id == parcel_id:
                parcels_list[idx] = updated_parcel
                break

        return {
            "id": updated_parcel.id,
            "merchant_ref": updated_parcel.merchant_ref,
            "cod_amount_piastres": updated_parcel.cod_amount_piastres,
            "address_text": updated_parcel.address_text,
            "state": updated_parcel.state,
            "attempts": updated_parcel.attempts,
        }

    return app


app = create_app()