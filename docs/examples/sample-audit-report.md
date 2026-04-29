# Robot Framework Suite Health Audit — Sample

## Executive summary

The reviewed suite (`examples/bad_robot_suite`) is functionally understandable but shows clear quality debt typical of inherited enterprise automation. Current patterns increase flaky outcomes, slow execution, and maintenance overhead. The suite is a good candidate for staged hardening without major framework migration.

## Key findings

### Stability risks
- Multiple fixed `Sleep` calls are used in login and checkout flows instead of state-based synchronization.
- Setup/teardown usage is inconsistent between suites, creating higher risk of leaked browser/session state.

### Maintainability risks
- Unused legacy keyword definitions remain in shared resources.
- Duplicate keyword names (for example, `Submit Login`) are defined across files, which can cause ambiguity and drift.
- Naming quality is inconsistent (`legacy helper` vs. title-cased business keywords).

### Environment/configuration risks
- Hardcoded environment targets are present (`localhost` and internal staging URLs) instead of centrally managed configuration.
- Credentials and test data are embedded in tests/keywords rather than injected by environment.

### Governance/consistency risks
- Some tests have missing test-level documentation.
- Tagging strategy is inconsistent (`smoke`, `regression`, `e2e`, `high-priority`, sprint tag), making selective execution and reporting less reliable.

## Example findings

- `Sleep    2s` in login verification and `Sleep    5` in checkout confirmation flows.
- `Unused Legacy Tax Validation` keyword is defined but never called.
- `Submit Login` is defined in both a suite file and a shared resource.
- `http://localhost:8080/shop` and `https://staging-retail.example.internal/...` are hardcoded.
- `Locked User Sees Account Disabled Message` and `Saved Customer Checkout` omit `[Documentation]` entries.

## Recommended remediation plan

### Phase 1: quick fixes (1–2 sprints)
- Replace fixed sleeps with explicit wait keywords tied to page/application readiness.
- Remove or quarantine unused keywords.
- Normalize naming for non-compliant keywords.
- Externalize base URLs and sensitive data into variables/config.

### Phase 2: suite cleanup (2–4 sprints)
- Consolidate duplicate keywords into one authoritative resource.
- Standardize test metadata: required documentation and controlled tag taxonomy.
- Align suite setup/teardown patterns and error-handling behavior.

### Phase 3: CI governance (ongoing)
- Enforce analyzer checks as non-blocking first, then gradually elevate selected rules to gates.
- Track trend metrics: sleep count, duplicate/unused keyword count, metadata compliance.
- Add ownership/reporting for remediation SLAs by feature team.

## Business value

Executing this plan typically yields measurable outcomes:
- Lower flaky failure rates and fewer false alarms in CI.
- Faster feedback cycles by reducing unnecessary waits and reruns.
- Easier onboarding through consistent keyword and metadata conventions.
- Lower long-term maintenance cost by reducing duplicated and dead automation code.
