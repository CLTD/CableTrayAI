---
name: production-real-ansys-orchestrator
description: Production ANSYS orchestration for run_all.mac, guarded real runs, output retention, parsing, and acceptance.
---

# Requirements

- Real ANSYS entrypoint is `run_all.mac`.
- `run_all.mac` calls generated model, solve, and post macros in order.
- Failed real runs must not switch to mock.
- Output retention includes logs, solver files, LIS/OUP, and figures.
- Preflight failures block real execution.
