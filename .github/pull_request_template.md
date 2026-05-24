## Summary

<!-- What does this PR do and why? -->

## Test Determinism Checklist

For every new or modified test file in this PR, confirm:

- [ ] No `datetime.now()` without timezone — use `datetime.now(UTC)` or the `fixed_utc_now` fixture
- [ ] No `time.sleep()` in test bodies
- [ ] No assertions on dict/set iteration order (use `sorted()` or `set()` comparisons)
- [ ] All filesystem paths use `tmp_path` or `temp_dir` fixture — no hardcoded absolute paths
- [ ] No `random` calls without an explicit seeded RNG (`random.Random(42)`)
- [ ] No network calls (must be mocked or blocked)
- [ ] No dependency on undeclared environment variables
- [ ] Test passes when run in isolation: `uv run pytest path/to/test.py::TestClass::test_name`
- [ ] Test passes when run after a full suite run (no shared state leakage)

## Contract Change Checklist

If this PR touches `public_api.py`, `plugin.py`, `manager.py`, or output formatters:

- [ ] Contract tests in `tests/contracts/` still pass with no changes **OR**
- [ ] A contract test was intentionally updated because this is a documented breaking change + version bump

## Type of change

- [ ] Bug fix (no API change)
- [ ] New feature (backward compatible)
- [ ] Breaking change (contract tests updated, version bumped)
- [ ] Refactor / internal cleanup

## CI lane expected to gate this

- [ ] PR fast lane (always)
- [ ] PR full lane (mark ready for review)
