# Stage 3 Ready For Real ANSYS Checklist

Before calling real ANSYS:

- [ ] `config/ansys.local.toml` exists.
- [ ] `runner.mode = "real"`.
- [ ] `ansys.executable` points to an existing executable.
- [ ] `jobs/<job_id>/input.json` is reviewed.
- [ ] `generated_model.mac`, `generated_solve.mac`, `generated_post.mac` are reviewed.
- [ ] Required SECT files are present in the job package.
- [ ] Spectrum source is confirmed and `ansys_spectrum.mac` is reviewed.
- [ ] `ansys_preflight.json` has no `fail` checks.
- [ ] Formula TODO items are understood and not treated as final passed checks.
- [ ] Output directory has enough disk space and can retain logs, LIS, RST and images.
- [ ] User explicitly starts real run through API or `scripts/run_ansys_real.ps1`.
