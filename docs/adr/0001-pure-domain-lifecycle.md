## Status
Accepted

## Context
The parcel state lifecycle (dispatch, deliver, fail, return) contains the core business logic of Tawseel. The state machine rules and transition limits are expected to change frequently as operations evolve. We needed to decide whether to couple state logic with HTTP framework models (FastAPI/Pydantic) or isolate it.

## Decision
We isolated the lifecycle into a pure Python module (`app/domain.py`) with zero dependencies on external frameworks or HTTP libraries. State transitions are managed using pure dataclass transformations via `apply_event`.

## Consequences
- The core business rules can be thoroughly tested in isolation without spawning HTTP servers or API clients.
- Future changes to API frameworks or database ORMs will not impact the domain state rules.
- Pure immutable transitions prevent accidental state mutation across request contexts.