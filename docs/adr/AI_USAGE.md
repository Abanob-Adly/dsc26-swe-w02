## Tools
- GitHub Copilot / ChatGPT / Gemini

## What AI got wrong
- Initially attempted to import Pydantic models directly into `app/domain.py`, violating the requirement for a pure Python domain layer.
- Generated standard offset-based pagination that failed when items changed state mid-walk during filter tests.

## In my own words
Why does listParcels need a cursor rather than an offset?
Offset pagination causes items to be skipped or duplicated if earlier parcels change state or new parcels are created between paginated requests. A cursor anchors the pagination position to a specific parcel, ensuring a stable and idempotent traversal regardless of concurrent state changes.

Which of your four operations would break the courier app if you renamed one field, and who would have to approve that change?
Renaming a field in `GET /v1/parcels` (or any endpoint returning parcel objects) would immediately break the courier app's parser and interface. Such a breaking change in the API contract must be approved by both the courier app team and the merchant integration team before deployment.