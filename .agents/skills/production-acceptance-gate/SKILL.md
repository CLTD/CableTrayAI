---
name: production-acceptance-gate
description: Production acceptance gate for tests, hardcode scan, real-run status, report audit, and baseline validation.
---

# Requirements

- Tests pass and meet production count threshold.
- Hardcoded sample scan has no matches.
- `source_materials` remains unchanged.
- Formal acceptance is blocked unless real or imported-real data supports it.
