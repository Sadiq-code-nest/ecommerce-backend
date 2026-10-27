# API Design

Base URL (local): `http://127.0.0.1:8000`
All business endpoints live under `/v1`. `/health` is outside the version prefix so probes do not depend on API versions.

## Product object

```json
{ "id": 1, "name": "Keyboard", "price_cents": 80000, "stock": 15 }
```

Money is stored as integer cents, never as a float.

## Endpoints

| Method | URL | Purpose | Success | Error codes |
|---|---|---|---|---|
| GET | `/health` | Liveness check | 200 | none |
| GET | `/v1/products` | List with search, filter, sort, pagination | 200 | `INVALID_SORT_FIELD` (400), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) |
| GET | `/v1/products/{id}` | Get one product | 200 | `PRODUCT_NOT_FOUND` (404), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) |
| POST | `/v1/products` | Create a product | 201 (200 on idempotent retry) | `PRODUCT_NAME_EXISTS` (409), `IDEMPOTENCY_KEY_REUSED` (422), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) |
| PUT | `/v1/products/{id}` | Replace a product (all fields required) | 200 | `PRODUCT_NOT_FOUND` (404), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) |
| PATCH | `/v1/products/{id}` | Update only the fields sent | 200 | `PRODUCT_NOT_FOUND` (404), `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) |
| DELETE | `/v1/products/{id}` | Delete a product | 204 | `PRODUCT_NOT_FOUND` (404), `RATE_LIMITED` (429) |

## Query parameters for `GET /v1/products`

| Parameter | Type | Default | Rule |
|---|---|---|---|
| `q` | string | none | Case-insensitive match on name |
| `min_price` | int | none | >= 0, in cents |
| `max_price` | int | none | >= 0, in cents |
| `sort` | string | `id` | One of `id`, `name`, `price_cents`, `stock`; prefix `-` for descending |
| `page` | int | 1 | >= 1 |
| `limit` | int | 10 | 1 to 100 |

Response shape: `{ "items": [...], "total": 3, "page": 1, "limit": 10 }`.
`total` is the number of matches before pagination.

## Error format

Every error uses the same shape:

```json
{ "error": { "code": "PRODUCT_NOT_FOUND", "message": "Product not found", "details": [] } }
```

Validation errors fill `details` with one entry per bad field:

```json
{ "field": "body.price_cents", "message": "Input should be greater than or equal to 0" }
```

| Code | Status | Meaning |
|---|---|---|
| `PRODUCT_NOT_FOUND` | 404 | No product with that id |
| `PRODUCT_NAME_EXISTS` | 409 | Another product already has this name (case-insensitive) |
| `IDEMPOTENCY_KEY_REUSED` | 422 | Same key sent with a different body |
| `INVALID_SORT_FIELD` | 400 | `sort` is not in the allowed list |
| `VALIDATION_ERROR` | 422 | Body or parameters failed validation |
| `RATE_LIMITED` | 429 | Too many requests; see the `Retry-After` header |
| `HTTP_404` / `HTTP_405` | 404 / 405 | Unknown path / method not allowed on that path |

## Design decisions

- **Versioning:** `/v1` in the URL, so a breaking change can ship as `/v2` without breaking old clients.
- **Idempotency:** `POST /v1/products` accepts an `Idempotency-Key` header. A retry with the same key and body returns the original product with 200 and creates nothing new. The same key with a different body returns 422.
- **PUT vs PATCH:** PUT replaces the whole product; PATCH changes only the fields sent.
- **Pagination cap:** `limit` is capped at 100 so no client can request unbounded data.
- **Sort whitelist:** only listed fields can be sorted, so clients cannot probe internal fields.
- **Rate limit:** 20 requests per 10 seconds per IP on `/v1` routes, returning 429 with `Retry-After`.

## Known limitations (planned fixes)

- Data, idempotency keys and rate-limit counters live in memory and reset on restart. PostgreSQL (Phase 3) and Redis (Phase 6) fix this.
- With several app instances, each would count rate limits separately. Redis fixes this too.
- No authentication yet. Admin-only product writes arrive in Phase 4.