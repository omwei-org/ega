# Temporal Semantics

The temporal semantics are frozen for this reference contract.

## What the Observer carries

- `observed_at`: RFC 3339 / ISO 8601 UTC timestamp (`Z` suffix) recording
  when the observation completed. **Captured by the Observer itself** from
  its injectable clock (`Clock.now_utc()` in `src/nextone_interop/clock.py`);
  the default is the system UTC clock. Normal `observe()` has no timestamp
  parameter — callers cannot inject arbitrary observation times. Deterministic fixture/historical construction is a clearly separated
  path: it injects a `FixedUtcClock` and flows through the same `observe()`.
  Naive datetimes are rejected; offset-aware datetimes are normalized to UTC.
- `temporal_basis`: evidence-only meaning of that timestamp, fixed for v1:
  `{"type": "point_in_time", "timestamp_semantics": "observation_completed_at", "clock": "UTC"}`.

## What the Observer never emits

- `FRESH` / `STALE` labels;
- any EGA freshness threshold or max-age policy;
- any authorization validity decision.

Freshness is **evaluated by EGA at evaluation time** (INV-03). The Observer
carries temporal evidence; it does not judge it.

## Older evidence is not labelled stale by the Observer

`fixtures/negative/older_observation_price_2500.json` records the same
observed fact (`2500`) with an older `observed_at`. The envelope contains no
stale verdict. The expected semantic behavior is:

```text
same observed fact + older temporal evidence
→ EGA may determine at evaluation time
  that the applicable freshness condition is not satisfied
```

The test-only evaluator in `tests/ega_evaluation_harness.py` demonstrates
exactly this: `check_freshness` returns `False` for the older envelope under
a one-hour max age, while the golden envelope passes — and neither envelope
knows anything about that decision.
