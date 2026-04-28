# SDK Dedup Observability (Fix 2 of issue monkai-agent-hub#2)

**Date:** 2026-04-28
**Status:** Design approved, pending implementation plan
**Sub-project of:** `monkai-agent-hub/docs/superpowers/specs/2026-04-28-dedup-incident-coordination.md` (Fix 2)
**Repo:** `monkai-trace`
**Affected modules:** `monkai_trace/client.py`, `monkai_trace/async_client.py`, `monkai_trace/exceptions.py`

## Problem

The `MonkAIClient` and `AsyncMonkAIClient` upload methods (`_upload_single_record`, `_upload_records_chunk`) return `response.json()` from the Hub without inspecting it. The Hub responds 200 OK with `{inserted_count: 0, duplicate: true}` whenever it deduplicates a batch — historically this happened erroneously (issue monkai-agent-hub#2) and now happens correctly only on genuine retries. Either way, callers (e.g. the Vivo `Azure-Servers/.../tracing.py:152` wrapper) currently log "Record uploaded" on any 200 response without checking the body. Result: silent message-loss on the client side even when the server is behaving correctly.

After the Hub-side Fix 1 ships (PR `monkai-agent-hub#3`, merged to main), `inserted_count: 0` only happens for genuine duplicates — but the SDK still does not surface that fact. Calling code cannot distinguish "all good, retry was a real dup" from "the server lost data" without parsing the response themselves.

## Goals

- Whenever the SDK observes that the Hub reported drops, log a `WARNING` with an accurate count.
- Provide an opt-in `strict_dedup` mode that raises `MonkAIRecordDiscardedError` when any record is dropped — for tests, alerting hooks, and anyone who wants hard failure on data loss.
- Backward-compatible: callers who do nothing keep working (just gain log visibility).

## Non-goals

- Changing what the Hub returns. The response shape is fixed by the server.
- Fixing the deeper observability story (metrics, dashboards). Just the SDK-level signal.
- Inspecting `inserted_at`, namespace alias resolution, or any other response field beyond drop counts.
- Validating that the server's response shape is well-formed. We treat malformed responses as "no drops" (lenient by default; strict mode can still distinguish if needed).

## Approach

A small, file-local helper `_check_dedup_response(response_dict, total_records)` is called from both `_upload_single_record` and `_upload_records_chunk` (sync + async) right before they return. The helper:

1. Reads three optional fields from the response: `inserted_count` (defaulting to `total_records`), `duplicates_skipped` (defaulting to 0), and `duplicate` (boolean flag for the all-dropped early return).
2. Computes `dropped`. Two distinct shapes the Hub uses:
   - **All-dropped**: `inserted_count: 0, duplicate: true` → `dropped = total_records`
   - **Partial drop**: `duplicates_skipped > 0` → `dropped = duplicates_skipped`
   - Anything else → `dropped = 0` (no warning, no raise).
3. If `dropped > 0`: emit `logger.warning("MonkAI dropped N/M records as duplicates within 60s window")`.
4. If `dropped > 0` AND `self._strict_dedup`: raise `MonkAIRecordDiscardedError(message, dropped_count=dropped, inserted_count=inserted_count, total_received=total_records)`.
5. Return `response_dict` unchanged.

The constructor of both clients gains `strict_dedup: bool = False`. The helper accesses `self._strict_dedup`, set in `__init__`.

The exception extends the existing `MonkAIAPIError` so callers handling generic API errors keep working; callers wanting to distinguish dedup-vs-other failures can `except MonkAIRecordDiscardedError`.

## Detection logic — exact

```python
def _check_dedup_response(self, response_dict: dict, total_records: int) -> dict:
    inserted = response_dict.get("inserted_count", total_records)
    skipped = response_dict.get("duplicates_skipped", 0)
    is_all_dup = response_dict.get("duplicate") is True

    if is_all_dup:
        dropped = total_records
    else:
        dropped = skipped

    if dropped > 0:
        logger.warning(
            f"MonkAI dropped {dropped}/{total_records} records as duplicates within 60s window"
        )
        if self._strict_dedup:
            raise MonkAIRecordDiscardedError(
                f"Server discarded {dropped}/{total_records} records as duplicates",
                dropped_count=dropped,
                inserted_count=inserted,
                total_received=total_records,
            )

    return response_dict
```

The helper is identical (with appropriate logger import) on the async client.

## API additions

### Exception (`monkai_trace/exceptions.py`)

```python
class MonkAIRecordDiscardedError(MonkAIAPIError):
    """Raised in strict_dedup mode when the server reports records were deduplicated.

    Attributes:
        dropped_count: number of records the server dropped as duplicates
        inserted_count: number of records the server actually inserted
        total_received: total records sent in the request
    """
    def __init__(self, message: str, dropped_count: int, inserted_count: int, total_received: int):
        super().__init__(message)
        self.dropped_count = dropped_count
        self.inserted_count = inserted_count
        self.total_received = total_received
```

### Constructor flag

Both `MonkAIClient.__init__` and `AsyncMonkAIClient.__init__` add a single new keyword argument:

```python
strict_dedup: bool = False
```

Stored as `self._strict_dedup`. Documented in the docstring.

### Public package surface

`monkai_trace/__init__.py` adds `MonkAIRecordDiscardedError` to the imports and `__all__`.

## Wiring

`_upload_single_record` (sync and async): replace the final `return response.json()` with:

```python
return self._check_dedup_response(response.json(), total_records=1)
```

`_upload_records_chunk`: same, with `total_records=len(records)`.

No other call sites need changing — `upload_record`, `upload_records_batch`, `upload_records_from_json` all flow through these two methods. (Verified by reading `client.py:121, 144, 235` and the equivalent in async_client.py.)

## Testing

Five scenarios in `tests/test_client_dedup_observability.py`. Each mocks `requests.Session.request` (sync) or `aiohttp.ClientSession.request` (async) to return a constructed response, calls `client.upload_record` (or batch), and asserts on (a) what was logged, (b) whether an exception was raised, (c) what was returned.

1. **Clean response (`inserted_count: 1`)**: no warning, no raise even in strict mode, return value passes through.
2. **All-dup (`inserted_count: 0, duplicate: true`)**: warning emitted, format includes `1/1`, no raise (strict_dedup=False).
3. **Partial (`duplicates_skipped: 2, inserted_count: 8`)**: warning emitted, format includes `2/10` (assuming 10-record batch), no raise (strict_dedup=False).
4. **Strict + drop**: same as #2 with `strict_dedup=True` → raises `MonkAIRecordDiscardedError`, attributes `dropped_count=1, inserted_count=0, total_received=1`.
5. **Strict + clean**: same as #1 with `strict_dedup=True` → no raise.

Tests run through `_upload_single_record` for cases #1, #2, #4, #5 and `_upload_records_chunk` for case #3. The async client gets a parallel test file `tests/test_async_client_dedup_observability.py` with the same 5 scenarios mirrored for `aiohttp` mocks.

Decision: keep sync and async test files separate (mirroring the existing pattern of `test_client.py` and the lack of an async equivalent today — adding both establishes the parity that was missing in Phase 1 SDK).

## Backward compatibility

- Default `strict_dedup=False` preserves all existing behaviour.
- Adding a new keyword arg with a default is non-breaking.
- Adding a new exception class is non-breaking; `MonkAIRecordDiscardedError` extends `MonkAIAPIError` so any existing `except MonkAIAPIError` block catches it transparently.
- Warning logs are non-breaking but are visible to anyone who has set `monkai_trace` to `WARNING` level (typically default for libraries). Document in CHANGELOG.

## Versioning

Minor version bump on next PyPI release. The `pyproject.toml` version moves from whatever is current to the next minor. The SDK was just shipped with Phase 1 anonymizer (PR #2 merged to main) — that release should ship this fix together if it lands before the publish.

## Out of scope

- The `upload_log` and `upload_logs_chunk` paths are not deduplicated by the Hub today (they hit a different table). No change needed.
- The `update_session` and other non-record routes are unaffected.
- Issue monkai-trace#3 (structured-content bypass) is independent — it concerns anonymization, not dedup. Tracked separately for Phase 1.5.

## References

- Issue: https://github.com/BeMonkAI/monkai-agent-hub/issues/2 (Fix 2 description)
- Coordination spec: `monkai-agent-hub/docs/superpowers/specs/2026-04-28-dedup-incident-coordination.md`
- Hub PR that fixed Fix 1: https://github.com/BeMonkAI/monkai-agent-hub/pull/3 (merged commit `d37aed7`)
- Affected SDK paths: `monkai_trace/client.py:323` (`_upload_single_record`), `monkai_trace/client.py:330` (`_upload_records_chunk`), and the corresponding async pair
