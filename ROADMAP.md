# Roadmap

This document outlines the development direction for
**robot-framework-optimizer-core** and the planned
**robot-framework-optimizer-pro** commercial extension.

> **Legend** — ✅ Shipped · 🔄 In progress · 🗓 Planned · ⭐ Pro only

---

## Always-Free Core Features

These features are part of the open-source Core package and will remain
free forever under the MIT licence.

| Feature | Status |
|---|---|
| Dead code / unused keyword detection | ✅ 1.0 |
| Sleep pattern analysis | ✅ 1.0 |
| Flakiness detector (from run history) | ✅ 1.0 |
| Hardcoded value detection | ✅ 1.0 |
| Naming convention checks | ✅ 1.0 |
| Setup / teardown analysis | ✅ 1.0 |
| Tag consistency validation | ✅ 1.0 |
| Test documentation coverage | ✅ 1.0 |
| Extensible plugin / analyzer system | ✅ 1.0 |
| SARIF 2.1 output (GitHub GHAS integration) | ✅ 1.0 |
| CLI (`robot-optimizer analyze`, `list-analyzers`) | ✅ 1.0 |
| TOML configuration (`robot.toml` / `pyproject.toml`) | ✅ 1.0 |
| Structured JSON output | ✅ 1.0 |
| Parallel directory analysis | ✅ 1.0 |
| Python 3.11 / 3.12 / 3.13 support | ✅ 1.0 |
| Suite-level cross-file dead code analysis | ✅ 1.0 |
| Thread-safe DI container | ✅ 1.0 |
| Pydantic v2 domain models | ✅ 1.0 |
| Per-analyzer configuration | ✅ 1.0 |
| Deprecation utilities for API stability | ✅ 1.0 |

---

## Upcoming Community Features (Core, Free)

These are planned improvements driven by community feedback.  Contributions
are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

| Feature | Target | Notes |
|---|---|---|
| `--watch` mode (re-analyse on file save) | 1.1 | inotify / watchdog |
| JUnit XML output format | 1.1 | CI report integration |
| Incremental analysis cache | 1.2 | Skip unchanged files |
| `robot-optimizer init` config wizard | 1.2 | Interactive setup |
| GitHub Actions composite action | 1.2 | Zero-config GHAS |
| Severity override via inline comments | 1.3 | `# noqa: sleep_detector` style |
| Python 3.14 support | 1.3 | Track CPython beta |
| VS Code extension (open-source) | 2.0 | Squiggly-line diagnostics |

---

## Pro Features — robot-framework-optimizer-pro

The Pro package extends Core with advanced capabilities for teams and
enterprises.  It is a paid product that funds ongoing development of the
free Core package.

> Hooks for all Pro features are already present in Core 1.0 — upgrading
> requires only installing the Pro package.

| Feature | Notes |
|---|---|
| ⭐ **Auto-fix** — apply safe, mechanical fixes automatically | `analyze_file(auto_fix=True)` |
| ⭐ **HTML / PDF reports** — rich, shareable analysis reports | `analyze_file(report_format="html")` |
| ⭐ **Baseline diffing** — suppress already-known findings | `analyze_file(baseline=Path("baseline.json"))` |
| ⭐ **CI/CD dashboard** — trend tracking across builds | Webhook + hosted dashboard |
| ⭐ **Team rule management** — shared rule sets via URL | Central policy server |
| ⭐ **AI-powered fix suggestions** — LLM-assisted remediation | Opt-in, privacy-preserving |
| ⭐ **Priority support** — SLA-backed response | Slack / email |
| ⭐ **Custom rule IDE** — GUI rule builder | No coding required |
| ⭐ **Import graph analysis** — cross-suite dependency map | Pro-tier dead code |
| ⭐ **License compliance audit** — check library licences | Enterprise feature |

**Interested in Pro?**
→ <https://github.com/kobolcs/robot_optimizer_core_pro>

---

## How to Influence the Roadmap

- 👍 React to existing issues to signal demand.
- 💬 Open a [GitHub Discussion](https://github.com/kobolcs/robot_optimizer_core/discussions)
  to propose a new feature.
- 🐛 File a [bug report](https://github.com/kobolcs/robot_optimizer_core/issues/new)
  if something doesn't work as expected.
- 🤝 Submit a pull request — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

*Last updated: 2026-04-29*
