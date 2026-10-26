## Status
Accepted

## Context
The `GET /v1/parcels` endpoint requires listing parcels with support for filtering by state and limit parameters. During active courier operations, parcels frequently change states (e.g., from `created` to `out_for_delivery`) between consecutive pagination requests.

## Decision
We adopted cursor-based pagination using a base64-encoded cursor anchor instead of traditional offset pagination.

## Consequences
- Pagination remains deterministic and stable even when parcels update their state between page requests.
- Prevents skipping or duplicating items when iterating through paginated lists mid-dispatch.
- Provides a consistent O(1) pointer-based continuation for client integrations.