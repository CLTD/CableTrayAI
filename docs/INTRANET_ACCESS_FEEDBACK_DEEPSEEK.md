# Intranet Access, Feedback, And Local Model Setup

## Access Allowlist

The deployment server is `10.102.15.203`. Initial allowed client IPs are:

- `10.102.15.110`
- `10.102.15.102`
- `10.102.15.105`

The server itself and loopback addresses are allowed for maintenance. The bundled example is:

```text
config/access_control.example.json
```

Manual additions from the dashboard are saved to:

```text
config/access_control.local.json
```

That local file is intentionally excluded from update packages.

## Central Feedback

Client computers submit bug causes and modification suggestions through the dashboard. The server stores them under:

```text
docs/operator_feedback/
```

Generated files:

- `feedback_items.jsonl`
- `feedback_summary.json`
- `feedback_items.csv`

These files stay on the deployment server so later fixes can be made centrally.

## Unit Local Model Connection

CableTrayAI uses an OpenAI-compatible adapter. Ask the digital department for the intranet endpoint, model name, and whether an API key is required. The service must be reachable from the deployment server inside the unit network.

Example:

```toml
[provider]
enabled = true
base_url = "http://<unit-local-model-server>:<port>/v1"
model = "<unit-local-model-name>"
api_key_env = "CABLETRAYAI_LLM_API_KEY"
timeout_seconds = 60
```

The main platform at `http://10.102.15.203:8000/` automatically polls AI quality control. The separate mechanics-room assistant is `http://10.102.15.203:8000/ai-tools`.

The model is for AI quality-control chat, bug explanation, feedback summarization, and internal tool prototyping only. Engineering conclusions still come from standard command flows, ANSYS output, Excel authoritative evaluation, and confirmed formulas.
