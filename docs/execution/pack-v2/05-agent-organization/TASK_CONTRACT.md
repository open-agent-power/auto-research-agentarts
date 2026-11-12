# Task Contract

Required:
- task_id / title / objective / user value；
- workstream / owner；
- dependencies；
- input snapshot / source refs；
- allowed/prohibited files；
- interface contract；
- acceptance criteria；
- tests and benchmark IDs；
- budget/runtime;
- risk class；
- expected artifacts；
- docs to update。

States:
`proposed → ready → claimed → in_progress → review → integrated → verified`
Other: `blocked / needs_decision / rejected / cancelled`

Completion receipt:
```json
{
  "task_id":"M1-RESEARCH-001",
  "status":"verified",
  "branch":"feat/plan-feedback",
  "commit":"sha",
  "changed_files":[],
  "tests":[{"command":"...","exit_code":0,"evidence_ref":"..."}],
  "real_runs":[],
  "artifacts":[],
  "cost":{"tokens":null,"currency":null,"amount":null},
  "limitations":[],
  "docs_updated":[],
  "next_recommendation":"..."
}
```

Done means acceptance evidence exists, not merely code written.
