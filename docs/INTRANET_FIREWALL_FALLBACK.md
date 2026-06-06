# Intranet Firewall Fallback

## Purpose

This note documents the deployment fallback when the CableTrayAI server starts locally but other unit computers cannot open `http://<server-ip>:8000/`.

## Diagnosis Rule

Run on the deployment computer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check_intranet_access.ps1
```

Or double-click:

- `CHECK_NETWORK_ACCESS.cmd`
- `网络访问自检.cmd`

The script writes:

- `docs/intranet_access_diagnosis.json`

## Interpretation

- `http://127.0.0.1:8000/` passes, but other computers cannot open `http://10.x.x.x:8000/`:
  - CableTrayAI is running.
  - The likely blocker is Windows firewall, security software, VLAN routing, or unit network policy.
  - Ask the administrator or digitalization team to allow inbound TCP `8000` on the deployment computer.

- Browser shows `forbidden` JSON:
  - The web service is reachable.
  - The client IP is not in the CableTrayAI allowlist.
  - Add that IP in the web permission panel or `config/access_control.local.json`.

- Neither local nor public URL opens:
  - The service did not start.
  - Restart with `START_NO_POWERSHELL.cmd` or `INSTALL_AND_START.ps1`.
  - Check `logs/internal_server.err.log`.

## Boundary

The software can add Windows firewall rules when it has administrator rights. It cannot bypass unit security policy or VLAN routing restrictions. In that case the correct fix is network policy approval, not code changes.
