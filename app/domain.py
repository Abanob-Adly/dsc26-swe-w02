from dataclasses import dataclass, replace
from enum import StrEnum

MAX_ATTEMPTS = 3


class ParcelState(StrEnum):
    CREATED = "created"
    OUT_FOR_DELIVERY = "out_for_delivery"
    FAILED_ATTEMPT = "failed_attempt"
    DELIVERED = "delivered"
    RETURNED = "returned"


class EventType(StrEnum):
    DISPATCH = "dispatch"
    DELIVER = "deliver"
    FAIL = "fail"
    RETURN = "return"


class InvalidTransition(Exception): ...


@dataclass(frozen=True)
class Parcel:
    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: ParcelState = ParcelState.CREATED
    attempts: int = 0


def apply_event(parcel: Parcel, event: EventType) -> Parcel:
    """Return a new Parcel. Raise InvalidTransition if the event is not allowed."""
    current_state = parcel.state

    if current_state == ParcelState.CREATED and event == EventType.DISPATCH:
        return replace(
            parcel,
            state=ParcelState.OUT_FOR_DELIVERY,
            attempts=parcel.attempts + 1,
        )

    if current_state == ParcelState.OUT_FOR_DELIVERY and event == EventType.DELIVER:
        return replace(parcel, state=ParcelState.DELIVERED)

    if current_state == ParcelState.OUT_FOR_DELIVERY and event == EventType.FAIL:
        return replace(parcel, state=ParcelState.FAILED_ATTEMPT)

    if current_state == ParcelState.FAILED_ATTEMPT:
        if event == EventType.DISPATCH:
            if parcel.attempts >= MAX_ATTEMPTS:
                raise InvalidTransition(
                    f"Cannot dispatch after {MAX_ATTEMPTS} failed attempts"
                )
            return replace(
                parcel,
                state=ParcelState.OUT_FOR_DELIVERY,
                attempts=parcel.attempts + 1,
            )
        if event == EventType.RETURN:
            return replace(parcel, state=ParcelState.RETURNED)

    # Any other transition is invalid
    raise InvalidTransition(
        f"Invalid transition from state '{current_state}' with event '{event}'"
    )