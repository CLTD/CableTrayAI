# ANSYS Master Macro Policy

Production and dry-run command generation must use `run_all.mac` as the ANSYS batch input.

`run_all.mac` is generated per job and calls:

1. `generated_model.mac`
2. `generated_solve.mac`
3. `generated_post.mac`

The command builder writes:

```text
ansys ... -i jobs/<job_id>/run_all.mac ...
```

Preflight fails when:

- `run_all.mac` is missing.
- the required macros are not called in order.
- `ansys_command.json` still points to `generated_solve.mac`.

This prevents production real runs from bypassing modeling or post-processing.
