# Stage 4 Remaining Risks

Known risks before production real-run use:

- The real-run execution path is guarded but has not been exercised against a live ANSYS installation in this development session.
- Real `.LIS` variations outside the current manifest may still need parser extensions.
- Report structure comparison is section-level only; detailed paragraph-by-paragraph wording comparison remains a human review task.
- Formula items still marked `TODO_FORMULA_SOURCE_REQUIRED` must be confirmed before final engineering conclusions.
- Imported output directories are trusted as externally produced; the platform validates filenames and parseability but cannot prove the external calculation setup was correct without the APDL and ANSYS logs.
- `.rst` files are retained as optional evidence but are not parsed in Stage 4.
- ANSYS discovery can report multiple valid executables; selecting the correct version remains a human decision.
- The default real output directory is convenient, but imported files still require human confirmation that they come from the intended calculation.
