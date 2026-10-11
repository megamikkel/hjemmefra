# ADR-0004: Confidence, provenance and no invented data

Every offer carries `price_confidence` (VERIFIED/HIGH/MEDIUM/LOW/UNKNOWN),
`validation_status` (NORMAL/SUSPICIOUS/INVALID/REQUIRES_REVIEW), the raw record
it came from (`raw_id`, `source_reference`, `captured_at`) and a fingerprint
used for idempotent imports. OCR values keep raw value, normalized value,
confidence and source location; ambiguous digit strings ("2995") are resolved
only by plausibility and downgraded, otherwise UNKNOWN. Only NORMAL offers with
confidence ≥ the request's minimum (CHEAPEST forces HIGH) may feed exact-price
plans. A missing price is `PRICE_UNKNOWN`; the recipe needing it is excluded
and the exclusion is reported as a warning. Savings are only reported with a
reference price and carry `saving_confidence`; availability is always OFFERED,
never IN_STOCK, without real-time inventory data.

LLMs may suggest product mappings or phrase explanations; every structured value
passes Pydantic schemas and the validation pipeline, and all numbers in
explanations come from the engine's structured result.
