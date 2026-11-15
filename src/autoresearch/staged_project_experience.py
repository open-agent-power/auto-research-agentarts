"""Explicit historical cases from completed staged retrieval, never final raw data.

Capture verifies original source and three native actions, without dispatch or
reading the private final packet. Offline final aggregate provenance requires
reopening the original artifact: self-contained hashes are not signatures.
"""
import copy
import hashlib
import math
from pathlib import Path
import re

from . import staged_relevance_adapter as staged, retrieval_holdout as holdout, research_recipe
from . import source_evidence_adapter as source_reader
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_memory import ResearchMemory, observation_id, validate_scope
from .research_project import ResearchProject, code_identity as runtime_code_identity
from . import project_selection

SCHEMA = "staged-retrieval-experience-bundle-v1"
PROTOCOL = "staged-retrieval-saved-binding-v1"
SCHEMA_V2 = "staged-retrieval-experience-bundle-v2"
PROTOCOL_V2 = "staged-retrieval-feedback-binding-v2"
SCHEMA_V3 = "staged-retrieval-experience-bundle-v3"
PROTOCOL_V3 = "staged-retrieval-shadow-binding-v3"
_S067_COMMIT = "5bd9883dd435a1d39b857a51bb6f4d20a53f156b"
_S067_PROTOCOL_SHA = "ca8e7212ed1aa1ce65e197571e0613d3ace738855470ef7c71d7b4f40efaf5c1"
_S067_DRIVER_SHA = "0e40c8d2ab4b38890ac1b28b519bad645d6dcc1f735a1a2c33583b9a999d0892"
_S067_CASE_SHA = "4ff88cb1fb5c365b9cd333f9dd56035d7d2cc366b2df98a2a6ddf8ded4a7712a"
_S067_PROJECT_ID = "project-dc1b1b59889f49c0b744254b1a1afd68"
_S067_RUN_ID = "run-276475c33d7542509c840bc575005271"
_S067_PRIMARY_ID = "action-ad83795edf793a9dc19125edbd2ee442"
_S067_SOURCE_SNAPSHOT = "2ab8f454956a0b0b75df792cfe9ab37cf7942df769963c58fb9c238d021f8dcb"
_S067_DECISION_SHA = "6a4356387fb73b75b1b111a9e619cb57845f1aab63e51b0f54c2920c7c7da383"
_SHADOW_VERIFICATION = ("source_checked_at_capture; offline_shadow_binding_unverifiable_without_origin; "
                        "pre_anchor_snapshot_unverifiable_without_original_snapshot")
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
NOTICE = ("Historical analogy only. Final aggregate was checked against the original at capture; "
          "offline_final_binding_unverifiable_without_origin. Self-contained hashes are not signatures. "
          "No final query IDs, final per-query rows, private final bytes, or source asset bytes are included. "
          "Public data and same-user procedural separation do not establish blindness or scientific validity.")
EVALUATION = "staged-relevance-development-v1"


def _require(value, message, code="INVALID_STAGED_EXPERIENCE"):
    if not value:
        raise ResearchError(code, message)


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None



_SHADOW_A_CONDITION = {"split": "validation", "measure": "candidate_minus_baseline",
                       "metric": "recall@20", "operator": "gt", "threshold": 0}
_SHADOW_B_CONDITION = {
    "all": [_SHADOW_A_CONDITION, {"split": "validation", "measure": "candidate_minus_baseline",
                                   "metric": "mrr@10", "operator": "gte", "threshold": 0}],
    "leave_one_out": {"split": "validation", "measure": "leave_one_out_mean",
                      "metric": "recall@20", "operator": "gt", "threshold": 0},
}


def _shadow_comparison(feedback, condition, value, final):
    """Compare only the fixed S067 rules; missing evidence is not a zero difference.

    This pure helper assumes its arguments will be source-verified by a future
    explicit capture entry point. It does not authenticate them by itself.
    """
    from . import hypothesis_feedback
    from . import retrieval_lexical as lexical
    _require(type(feedback) is dict and canonical(feedback.get("condition")) == canonical(_SHADOW_A_CONDITION)
             and canonical(condition) == canonical(_SHADOW_B_CONDITION),
             "Shadow rules differ from the fixed protocol.", "EVIDENCE_CHANGED")
    outcome = feedback.get("outcome")
    _require(outcome in ("condition_met", "condition_not_met", "unknown"), "Invalid native feedback.", "EVIDENCE_CHANGED")
    if outcome == "unknown" or value is None:
        return {"A_method": None, "B_method": None, "outcome": "unknown", "reason": "policy_unknown", "B_minus_A": None}
    a_value = feedback.get("value")
    _require(type(a_value) in (int, float) and math.isfinite(a_value) and -1 <= a_value <= 1
             and hypothesis_feedback._valid_loo_value(value, condition)
             and canonical(a_value) == canonical(value["means"][0])
             and (outcome == "condition_met") == (a_value > 0),
             "The fixed rules do not match the same saved validation values.", "EVIDENCE_CHANGED")
    a = "tfidf_cosine" if outcome == "condition_met" else "bm25"
    b = "tfidf_cosine" if hypothesis_feedback._loo_matches(condition, value) else "bm25"
    _require(not (a == "bm25" and b == "tfidf_cosine"), "Fixed rules select impossible arms.", "EVIDENCE_CHANGED")
    result = {"A_method": a, "B_method": b, "outcome": "unknown", "reason": "same_arm", "B_minus_A": None}
    if a == b:
        return result
    if final is None:
        result["reason"] = "final_unmeasured"
        return result
    _require(type(final) is dict and final.get("selected_method") == "tfidf_cosine"
             and final.get("baseline_method") == "bm25"
             and final.get("comparison_status") == "distinct_selected_and_baseline"
             and type(final.get("summary")) is dict,
             "The requested counterfactual was not measured in the saved final.", "EVIDENCE_CHANGED")
    try:
        baseline, selected = final["summary"]["baseline"], final["summary"]["selected"]
        _require(type(baseline) is dict and type(selected) is dict
                 and set(baseline) == set(selected) == set(lexical.METRICS),
                 "Invalid saved final aggregate.", "EVIDENCE_CHANGED")
        _require(all(type(number) in (int, float) and math.isfinite(number) and 0 <= number <= 1
                     for table in (baseline, selected) for number in table.values()),
                 "Invalid saved final metric.", "EVIDENCE_CHANGED")
        delta = {metric: baseline[metric] - selected[metric] for metric in lexical.METRICS}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ResearchError("EVIDENCE_CHANGED", "Invalid saved final aggregate.") from None
    result.update(outcome=("condition_met" if delta["mrr@10"] > 0 and delta["recall@20"] >= 0
                           else "condition_not_met"), reason="different_arms_measured", B_minus_A=delta)
    return result


def _read_s067_shadow_checked(project, state, base_record, study_workspace):
    """WIP source-side check for the fixed S067 operator shadow receipt.

    No research is dispatched. This returns a compact projection only. A valid
    hash chain is a local consistency check, not a signature or a trusted clock.
    """
    from . import project_experience_binding, staged_feedback_reader as reader
    from .local_workbench import LocalWorkbench
    from .research_project import safe_path

    def raw(path, maximum):
        return source_reader._read_file(safe_path(path), maximum)

    def document(path, maximum):
        data = raw(path, maximum)
        value = staged._parse(data)
        _require(canonical(value).encode('utf-8') == data, 'Shadow source JSON changed.', 'EVIDENCE_CHANGED')
        return value, hashlib.sha256(data).hexdigest()

    root = safe_path(Path(study_workspace).absolute())
    _require(root.name == 's067-boolq-paired-passage-v1' and root.parent.name == 'runs',
             'Only the fixed S067 receipt is supported.', 'INVALID_REQUEST')
    start, start_sha = document(root / 'start.json', 65536)
    decision, decision_sha = document(root / 'private/shadow-decision.json', 65536)
    inputs, inputs_sha = document(root / 'private/shadow-inputs.json', 2 * 1024 * 1024)
    claim_path = root.parent.parent.parent / '.study-claims/s067-boolq-paired-passage-v1.json'
    claim, claim_sha = document(claim_path, 65536)
    _require(start.get('schema_version') == 's067-start-v1' and start.get('study_id') == root.name
             and start.get('workspace') == str(root) and start.get('claim_sha256') == claim_sha
             and start.get('source_commit') == _S067_COMMIT and start.get('protocol_sha256') == _S067_PROTOCOL_SHA
             and start.get('driver_sha256') == _S067_DRIVER_SHA and decision.get('case_sha256') == _S067_CASE_SHA
             and claim.get('schema_version') == 's067-study-claim-v1' and claim.get('study_id') == root.name
             and claim.get('workspace') == str(root) and claim.get('source_commit') == start.get('source_commit')
             and claim.get('protocol_sha256') == start.get('protocol_sha256')
             and claim.get('case_sha256') == decision.get('case_sha256')
             and claim.get('original_source_sha256') == 'ebc29ea3808c5c611672384b3de56e83349fe38fc1fe876fd29b674d81d0a80a',
             'Original source claim or startup identity differs.', 'EVIDENCE_CHANGED')
    pin = root.parent.parent
    for relative, key in (('scripts/run_boolq_case_comparison_study.py', 'driver_sha256'),
                          ('docs/execution/g5-local/boolq-case-comparison-protocol-v1.json', 'protocol_sha256'),
                          ('tests/test_boolq_case_comparison_study.py', 'test_sha256'),
                          ('scripts/run_squad_paragraph_study.py', 'helper_sha256')):
        _require(_hash(start.get(key)) and hashlib.sha256(raw(pin / relative, 5 * 1024 * 1024)).hexdigest() == start[key],
                 'Original producer source file differs.', 'EVIDENCE_CHANGED')
    _require(start.get('source_commit') == decision.get('source_commit')
             and start.get('driver_sha256') == decision.get('driver_sha256')
             and start.get('protocol_sha256') == decision.get('protocol_sha256')
             and start.get('project_code_identity') == state.get('code_identity'),
             'Original producer identity differs.', 'EVIDENCE_CHANGED')
    manager = LocalWorkbench.open_readonly(root / 'manager')
    with manager._connect(readonly=True) as con:
        _, managed = manager._project(con, state['id'])
    _require(managed.root == project.root, 'Study manager does not bind this Project.', 'EVIDENCE_CHANGED')
    expected_fields = {'case_sha256','driver_sha256','native_A_condition','native_A_method','native_A_outcome',
                       'native_A_value','plan_sha256','plan_version','primary_action_id','primary_parent_request_sha256',
                       'primary_result_sha256','project_id','protocol_sha256','registration_sha256','run_id',
                       'schema_version','shadow_B_condition','shadow_B_method','shadow_B_value','snapshot_ref',
                       'source_commit','source_snapshot_sha256','state_version','study_id','validation_inputs_sha256'}
    _require(type(decision) is dict and set(decision) == expected_fields
             and decision['schema_version'] == 's067-shadow-decision-v1' and decision['study_id'] == root.name
             and type(decision['state_version']) is int and _hash(decision['snapshot_ref'])
             and state['id'] == decision['project_id'] == _S067_PROJECT_ID
             and state['run_id'] == decision['run_id'] == _S067_RUN_ID
             and decision_sha == _S067_DECISION_SHA
             and decision['source_snapshot_sha256'] == state['source_snapshot_sha256'] == _S067_SOURCE_SNAPSHOT
             and decision['validation_inputs_sha256'] == inputs_sha,
             'Original shadow decision shape or Project binding differs.', 'EVIDENCE_CHANGED')
    p = base_record['provenance']; primary = p['actions']['primary']; history = p['feedback_history']
    primary_parent = next(x for x in state['controller_requests'] if x['request_id'] == p['parent_bindings']['primary']['request_id'])
    audit_parent = next(x for x in state['controller_requests'] if x['request_id'] == p['parent_bindings']['audit']['request_id'])
    final_parent = p['parent_bindings']['final']
    case_revisions = state.get('experience_revisions', [])
    _require(len(case_revisions) == 1 and case_revisions[0]['inclusion_status'] == 'active'
             and case_revisions[0]['bundle_sha256'] == decision['case_sha256']
             and case_revisions[0]['based_on_state_version'] < primary_parent['state_version_before'],
             'Original historical case inclusion differs.', 'EVIDENCE_CHANGED')
    case, case_raw = project_experience_binding._load(project.root, case_revisions[0])
    _require(hashlib.sha256(case_raw).hexdigest() == decision['case_sha256']
             and primary_parent['request']['proposal'].get('experience_case_refs') == [{
                 'case_id': case['id'], 'case_version': case['version'], 'bundle_sha256': decision['case_sha256']}]
             and canonical(case['record']['provenance']['feedback_history']['registration']['condition'])
                 == canonical(_SHADOW_B_CONDITION),
             'Original case or primary proposal reference differs.', 'EVIDENCE_CHANGED')
    anchors = [item for item in state.get('researcher_feedback', []) if item.get('request_id') == 's067-shadow-anchor']
    _require(len(anchors) == 1, 'Original shadow anchor is missing or ambiguous.', 'EVIDENCE_CHANGED')
    anchor = anchors[0]
    _require(anchor.get('id') == 'feedback-s067-shadow-anchor' and anchor.get('action_id') == primary['id']
             and anchor.get('comment') == 'sha256:' + decision_sha
             and anchor.get('content_trust') == 'unverified_researcher_statement'
             and type(anchor.get('based_on_state_version')) is int
             and anchor['based_on_state_version'] == decision['state_version']
             and primary_parent['state_version_after'] == anchor['based_on_state_version']
             and audit_parent['state_version_before'] == anchor['based_on_state_version'] + 1
             and audit_parent['state_version_after'] <= p['freeze']['request']['expected_state_version']
             and p['freeze']['request']['expected_state_version'] < final_parent['state_version_before']
             and [x for x in audit_parent['selection_context'].get('researcher_feedback', []) if x.get('request_id') == anchor['request_id']] == [anchor],
             'Original operator anchor or its pre-audit sequence differs.', 'EVIDENCE_CHANGED')
    fb = history['feedback']; reg = history['registration']
    _require(decision['primary_action_id'] == primary['id'] == _S067_PRIMARY_ID
             and start.get('controller_code_identity') == primary_parent['controller_code_identity']
             and decision['primary_result_sha256'] == primary['result_sha256']
             and decision['primary_parent_request_sha256'] == primary_parent['request_sha256']
             and decision['registration_sha256'] == reg['registration_sha256']
             and decision['plan_sha256'] == reg['plan_sha256'] and decision['plan_version'] == reg['plan_version']
             and canonical(decision['native_A_condition']) == canonical(fb['condition'])
             and canonical(decision['native_A_value']) == canonical(fb['value'])
             and decision['native_A_outcome'] == fb['outcome'],
             'Original shadow and preregistered primary feedback differ.', 'EVIDENCE_CHANGED')
    original = next(x for x in state['actions'] if x['id'] == primary['id'])
    checked = reader._checked_primary(project, state, original)
    qids = sorted(checked['source']['spec']['query_splits']['validation'])
    _require(len(qids) == 200 and len(set(qids)) == 200, 'Original validation coverage differs.', 'EVIDENCE_CHANGED')
    rows = []
    for qid in qids:
        row = {'query_id': qid}
        for method in ('bm25', 'tfidf_cosine'):
            metrics = checked['metrics'][('validation', qid, method)]['metrics']
            row[method] = {key: metrics[key] for key in ('recall@20', 'mrr@10')}
        rows.append(row)
    expected_inputs = {'schema_version':'s067-shadow-validation-inputs-v1','rows':rows,
                       'case_sha256':decision['case_sha256'],'primary_action_id':primary['id'],
                       'primary_result_sha256':primary['result_sha256']}
    _require(canonical(inputs) == canonical(expected_inputs), 'Original validation inputs differ.', 'EVIDENCE_CHANGED')
    paired = checked['summary']['splits']['validation']['paired_candidate_minus_baseline']
    deltas = [r['tfidf_cosine']['recall@20'] - r['bm25']['recall@20'] for r in rows]
    aggregate = reader._stability_aggregate(deltas, paired['recall@20'])
    value = {'means':[paired[k]['mean'] for k in ('recall@20','mrr@10')],
             'leave_one_out':{'minimum':aggregate['leave_one_out']['minimum'],
                              'maximum':aggregate['leave_one_out']['maximum'],'queries':len(qids)}}
    _require(canonical(value) == canonical(decision['shadow_B_value']), 'Original shadow arithmetic differs.', 'EVIDENCE_CHANGED')
    result = _shadow_comparison(fb, decision['shadow_B_condition'], value, base_record['payload']['final'])
    _require(result['A_method'] == decision['native_A_method'] and result['B_method'] == decision['shadow_B_method'],
             'Original shadow decision selects different methods.', 'EVIDENCE_CHANGED')
    _require(document(root / 'private/shadow-decision.json', 65536)[1] == decision_sha
             and document(root / 'private/shadow-inputs.json', 2 * 1024 * 1024)[1] == inputs_sha
             and document(root / 'start.json', 65536)[1] == start_sha
             and document(claim_path, 65536)[1] == claim_sha and project.status() == state,
             'Original shadow evidence changed during capture.', 'STALE_STATE')
    return {'schema_version':'staged-shadow-comparison-v1','case_sha256':decision['case_sha256'],
            'source_commit':decision['source_commit'],'protocol_sha256':decision['protocol_sha256'],
            'driver_sha256':decision['driver_sha256'],'decision_sha256':decision_sha,
            'validation_inputs_sha256':inputs_sha,'start_sha256':start_sha,'claim_sha256':claim_sha,
            'anchor_request_id':anchor['request_id'],
            'anchor_based_on_state_version':anchor['based_on_state_version'],
            'anchor_content_trust':'unverified_researcher_statement',
            'audit_parent_request_id':audit_parent['request_id'],'audit_context_sha256':audit_parent['selection_context']['context_sha256'],
            'condition':copy.deepcopy(decision['shadow_B_condition']),'value':value,'comparison':result,
            'verification':_SHADOW_VERIFICATION}


def _read_s067_shadow(project, state, base_record, study_workspace):
    try:
        return _read_s067_shadow_checked(project, state, base_record, study_workspace)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, StopIteration, UnicodeError, OverflowError, OSError):
        raise ResearchError('EVIDENCE_CHANGED', 'Original shadow source is unavailable or malformed.') from None

def _read(project, action):
    from .research_project import safe_path
    path = safe_path(project.root / "artifacts" / (action["id"] + ".json"))
    raw = source_reader._read_file(path, 5 * 1024 * 1024)
    env = staged._parse(raw)
    _require(type(env) is dict and set(env) == {"action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"}
             and env["sha256"] == fingerprint({k: v for k, v in env.items() if k != "sha256"}) == action["result_sha256"]
             and env["action_id"] == action["id"] and env["request_sha256"] == action["request_sha256"]
             and env["code_identity"] == action["code_identity"]
             and env["source_snapshot_sha256"] == action["source_snapshot_sha256"], "Original action envelope changed.", "EVIDENCE_CHANGED")
    return env, hashlib.sha256(raw).hexdigest()


def _action(action, state, method, primary=None):
    identifier(action["id"], "action_id")
    identifier(action["request_id"], "request_id")
    _require(action["status"] == "completed" and action["failure"] is None and action["command"] == method
             and action["project_id"] == state["id"] and action["run_id"] == state["run_id"]
             and action["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and action["code_identity"] == state["code_identity"] and action["dimension"] is None
             and action["artifact"] == "artifacts/" + action["id"] + ".json"
             and all(_hash(action[k]) for k in ("request_sha256", "result_sha256", "code_identity")),
             "Original action identity differs.", "EVIDENCE_CHANGED")
    request = {"project_id": state["id"], "command": method, "dimension": None,
               "source_snapshot_sha256": state["source_snapshot_sha256"]}
    from . import method_registry as registry
    evaluation = registry.evaluation_ref(method)
    params = {} if primary is None else {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
    if primary is not None:
        request.update(parameters=params, evaluation_ref=evaluation)
        _require(action["parameters"] == params and action["evaluation_ref"] == evaluation,
                 "Followup does not bind the original primary.", "EVIDENCE_CHANGED")
    instance = {"definition_ref": {"id": method, "version": "1"},
                "input_bindings": {"source_snapshot_sha256": state["source_snapshot_sha256"], **params},
                "parameters": params, "evaluation_ref": evaluation, "scope": state["source_scope"]}
    _require(action["request_sha256"] == fingerprint(request)
             and action["id"] == "action-" + fingerprint({"request_id": action["request_id"], **request})[:32]
             and action["method_instance"] == instance, "Action request or producer instance differs.", "EVIDENCE_CHANGED")


def _verify_action_rows(project, actions):
    """Bind status projections to original action-table record and fingerprint columns."""
    with project._connect(readonly=True) as con:
        con.execute("BEGIN")
        for action in actions:
            rows = con.execute("SELECT request_id, fingerprint, record FROM actions WHERE request_id=?",
                               (action["request_id"],)).fetchall()
            _require(len(rows) == 1 and rows[0]["request_id"] == action["request_id"]
                     and rows[0]["fingerprint"] == action["request_sha256"]
                     and staged._parse(rows[0]["record"].encode("utf-8")) == action,
                     "Original action database row or fingerprint differs from the project snapshot.", "EVIDENCE_CHANGED")


def _project_action(action):
    """Keep only typed action identity fields, never arbitrary action observations."""
    fields = {"artifact", "code_identity", "command", "dimension", "failure", "id", "method_instance", "project_id", "request_id", "request_sha256", "result_sha256", "run_id", "source_snapshot_sha256", "status"}
    if action["command"] != staged.TOOL_ID:
        fields |= {"parameters", "evaluation_ref"}
    return {key: copy.deepcopy(action[key]) for key in fields}


def _parent(state, action, registration, freeze):
    matches = [p for p in state.get("controller_requests", []) if p.get("child_request_id") == action["request_id"]]
    _require(len(matches) == 1, "Exactly one original controller parent is required.", "EVIDENCE_CHANGED")
    parent = matches[0]
    expected_id = "controller-child-" + fingerprint({"project_id": state["id"], "request_id": parent["request_id"]})[:32]
    child = {k: copy.deepcopy(action[k]) for k in ("id", "request_id", "command", "status", "artifact", "result_sha256", "failure") if k in action}
    _require(parent["status"] == "completed" and parent["project_id"] == state["id"]
             and parent["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and parent["code_identity"] == state["code_identity"] and parent["child_request_id"] == expected_id
             and parent["request_sha256"] == fingerprint(parent["request"])
             and parent["decision_sha256"] == fingerprint(parent["decision"])
             and parent["request"].get("command") == "controller.advance_selection"
             and parent["request"].get("project_id") == state["id"]
             and parent["request"].get("expected_state_version") == parent["state_version_before"]
             and type(parent.get("result")) is dict and parent["result"].get("child") == child
             and parent["result"].get("reused") is False,
             "Original controller parent/child binding changed.", "EVIDENCE_CHANGED")
    ctx = parent["selection_context"]
    selected = project_selection.validate_proposal(ctx, parent["request"]["proposal"])["candidate"]
    _require(selected is not None and selected["method_id"] == action["command"]
             and selected["parameters"] == action["method_instance"]["parameters"]
             and selected["evaluation_ref"] == action["method_instance"]["evaluation_ref"]
             and ctx["project_id"] == state["id"] and ctx["run_id"] == state["run_id"]
             and ctx["state_version"] == parent["state_version_before"]
             and ctx["snapshot_ref"] == parent["snapshot_ref_before"]
             and ctx["domain_scope"] == state["source_scope"]
             and fingerprint(ctx["research_plan"]) == registration["plan_sha256"]
             and ctx["source_snapshot_sha256"] == state["source_snapshot_sha256"]
             and ctx["project_code_identity"] == state["code_identity"]
             and ctx["controller_code_identity"] == parent["controller_code_identity"]
             and parent["decision"]["next_action"].get("method_id") == action["command"]
             and parent["decision"]["next_action"].get("parameters", {}) == selected["parameters"]
             and parent["decision"].get("selection_ref", {}).get("candidate_id") == selected["id"]
             and parent["decision"].get("selection_ref", {}).get("context_sha256") == ctx["context_sha256"],
             "Original selection and action differ.", "EVIDENCE_CHANGED")
    expected_freeze = None
    if action["command"] == holdout.FINAL_TOOL_ID:
        expected_freeze = {key: copy.deepcopy(freeze[key]) for key in
                           ("selected_method", "validation_delta_recall20", "primary_action_id", "primary_result_sha256")}
        expected_freeze["freeze_sha256"] = freeze["record_sha256"]
        if registration["schema_version"] == "retrieval-holdout-registration-v2":
            expected_freeze["feedback_binding"] = copy.deepcopy(freeze["feedback_binding"])
    expected_evaluation = {"schema_version": ("staged-evaluation-context-v2" if registration["schema_version"] == "retrieval-holdout-registration-v2" else "staged-evaluation-context-v1"), "holdout_sha256": registration["sha256"],
                           "query_count": registration["query_count"], "policy": registration["policy"],
                           "freeze": expected_freeze, "final": None, "scientific_validation": False,
                           "limitations": holdout.PUBLIC_LIMITATIONS}
    _require(canonical(ctx.get("staged_evaluation")) == canonical(expected_evaluation),
             "Saved controller context differs from preregistered holdout or frozen strategy.", "EVIDENCE_CHANGED")
    return {"request_id": parent["request_id"], "request_sha256": parent["request_sha256"],
            "decision_sha256": parent["decision_sha256"], "context_sha256": ctx["context_sha256"],
            "controller_code_identity": parent["controller_code_identity"], "child_request_id": action["request_id"],
            "state_version_before": parent["state_version_before"], "state_version_after": parent["state_version_after"]}


def _dev_source(project, before):
    raw = source_reader._read_file(project.root / "source.json", staged.LIMITS["packet_bytes"])
    source_sha = hashlib.sha256(raw).hexdigest()
    _require(source_sha == before["registration"]["source_sha256"] and before["registration"]["method_id"] == staged.TOOL_ID,
             "Original staged source identity changed.", "EVIDENCE_CHANGED")
    packet = staged._parse(raw)
    spec, docs, queries, qrels, doc_lines, query_lines = staged._checked(packet)
    _require(packet["snapshot_sha256"] == before["source_snapshot_sha256"] and packet["scope"] == before["source_scope"],
             "Original source snapshot or scope changed.", "EVIDENCE_CHANGED")
    refs = {"task_kind": packet["task_kind"], "stage": packet["stage"], "spec": spec,
            "spec_source": packet["spec_source"],
            "assets": {k: {f: v[f] for f in ("sha256", "bytes")} for k, v in packet["assets"].items()},
            "source_inclusion": "asset_bytes_excluded_hash_references_only"}
    return source_sha, refs, (docs, queries, qrels, doc_lines, query_lines)


def _check_audit(tool, primary, params):
    staged.AUDIT.next_decision(tool)
    saved = staged._saved(primary)
    summary, deltas, adverse = staged._paired(saved["per_query_metrics"])
    audit = tool["result"]
    _require(audit["stage"] == "development" and audit["predecessor"] == params
             and audit["source_snapshot_sha256"] == saved["source_snapshot_sha256"] and audit["scope"] == saved["scope"]
             and audit["rankings_sha256"] == saved["rankings_before_scoring_sha256"]
             and audit["summary"] == summary and audit["per_query_deltas"] == deltas and audit["adverse_queries"] == adverse
             and audit["usage"] == {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0, "scoring_calls": 0,
                                     "native_fits": 0, "model_calls": 0},
             "Saved audit differs from the original primary.", "EVIDENCE_CHANGED")
    expected_result = {"stage": "development", "scope": copy.deepcopy(saved["scope"]),
        "source_snapshot_sha256": saved["source_snapshot_sha256"], "predecessor": copy.deepcopy(params),
        "rankings_sha256": saved["rankings_before_scoring_sha256"], "summary": summary,
        "adverse_queries": adverse, "per_query_deltas": deltas,
        "usage": {"query_pairs": len(deltas), "index_builds": 0, "ranking_calls": 0, "scoring_calls": 0, "native_fits": 0, "model_calls": 0},
        "limitations": copy.deepcopy(staged.NOTES) + ["Saved metrics are inspected without reranking or rescoring labels."]}
    refs = copy.deepcopy(primary["evidence_refs"])
    refs.append({"source_snapshot_sha256": saved["source_snapshot_sha256"], "producer": copy.deepcopy(params),
                 "locator": {"kind": "saved_development_action", **params}})
    expected_tool = staged._tool(staged.AUDIT_TOOL_ID, expected_result, "saved_staged_relevance_audit",
                                 {"query_pairs": len(deltas), "adverse_queries": len(adverse)}, refs)
    _require(tool == expected_tool, "Saved audit envelope has unexpected fields or observations.", "EVIDENCE_CHANGED")
    return summary, deltas, adverse


def _final_projection(tool, metadata, frozen, params, source_snapshot):
    result = holdout.validate_final_result(tool)
    _require(result["predecessor"] == params and result["source_snapshot_sha256"] == source_snapshot
             and result["holdout_sha256"] == metadata["sha256"] and result["freeze_sha256"] == frozen["record_sha256"]
             and result["scope"]["corpus_sha256"] == metadata["corpus_sha256"]
             and result["scope"]["query_count"] == metadata["query_count"]
             and result["selected_method"] == frozen["selected_method"],
             "Final result does not match its source, freeze or predecessor.", "EVIDENCE_CHANGED")
    return {"selected_method": result["selected_method"], "baseline_method": result["baseline_method"],
            "comparison_status": ("selected_equals_baseline_single_computation" if result["selected_method"] == "bm25" else "distinct_selected_and_baseline"),
            "query_count": result["scope"]["query_count"], "summary": copy.deepcopy(result["summary"]),
            "usage": copy.deepcopy(result["usage"]), "limitations": copy.deepcopy(result["limitations"]),
            "verification": "source_verified_at_capture; offline_final_binding_unverifiable_without_origin"}


def _feedback_history(project, state, reg, freeze, primary, audit, parents):
    """Verify original producer-bound feedback without imposing today's controller pin."""
    from . import feedback_policy, hypothesis_feedback
    policy = reg["policy"]
    records = [r for r in state.get("hypothesis_registrations", []) if r.get("request_id") == policy["registration_request_id"]]
    _require(len(records) == 1, "Original preregistered feedback is missing or ambiguous.", "EVIDENCE_CHANGED")
    registered = records[0]
    hypothesis_feedback._check_record(registered)
    primary_parent = next(p for p in state["controller_requests"] if p["request_id"] == parents[0]["request_id"])
    audit_parent = next(p for p in state["controller_requests"] if p["request_id"] == parents[1]["request_id"])
    _require(registered["project_id"] == state["id"] and registered["run_id"] == state["run_id"]
             and registered["source_sha256"] == reg["source_sha256"]
             and registered["source_snapshot_sha256"] == reg["source_snapshot_sha256"]
             and registered["project_code_identity"] == reg["project_code_identity"]
             and registered["plan_sha256"] == reg["plan_sha256"] and registered["plan_version"] == reg["plan_version"]
             and registered["scope_sha256"] == fingerprint(state["source_scope"])
             and registered["candidate"]["method_id"] == staged.TOOL_ID
             and reg["state_version_before"] < registered["state_version_before"] < parents[0]["state_version_before"]
             and registered["controller_request_id"] == parents[0]["request_id"]
             and all(p["controller_code_identity"] == registered["controller_code_identity"] for p in parents)
             and state.get("plan_revisions") and fingerprint(state["plan_revisions"][-1]) == reg["plan_sha256"],
             "Original preregistration source, producer, plan or order differs.", "EVIDENCE_CHANGED")
    initial = [item for item in primary_parent["selection_context"].get("hypothesis_feedback", {}).get("items", [])
               if item.get("request_id") == registered["request_id"]]
    _require(len(initial) == 1 and initial[0].get("outcome") == "unknown"
             and initial[0].get("unknown_reason") == "controller_not_started"
             and initial[0].get("controller_request_id") == registered["controller_request_id"]
             and initial[0].get("registration_sha256") == registered["registration_sha256"]
             and canonical(initial[0].get("candidate")) == canonical(registered["candidate"])
             and canonical(initial[0].get("condition")) == canonical(registered["condition"])
             and canonical(initial[0].get("branches")) == canonical(registered.get("branches")),
             "Primary context did not contain the original predeclared feedback.", "EVIDENCE_CHANGED")
    view = hypothesis_feedback.feedback_context(project, state)
    items = [item for item in view["items"] if item["request_id"] == registered["request_id"]]
    _require(len(items) == 1 and items[0]["outcome"] in ("condition_met", "condition_not_met")
             and items[0]["action_id"] == primary["id"] and items[0]["result_sha256"] == primary["result_sha256"]
             and registered["branches"][items[0]["outcome"]] == {"kind": "method", "method_id": staged.AUDIT_TOOL_ID},
             "The original known feedback did not authorize this audit.", "EVIDENCE_CHANGED")
    proposal = feedback_policy.select_from_feedback(audit_parent["selection_context"], registration=registered,
                  provider={"kind": "operator_assistant", "label": "preregistered-feedback-policy-v1"})
    proposal["rationale"] = ("Preregistration " + registered["request_id"] + " sha256:"
                             + registered["registration_sha256"] + ". " + proposal["rationale"])
    audit_items = [item for item in audit_parent["selection_context"].get("hypothesis_feedback", {}).get("items", [])
                   if item.get("request_id") == registered["request_id"]]
    binding = {"registration_request_id": registered["request_id"], "registration_sha256": registered["registration_sha256"],
               "outcome": items[0]["outcome"], "audit_action_id": audit["id"],
               "audit_result_sha256": audit["result_sha256"], "audit_parent_request_id": parents[1]["request_id"]}
    _require(len(audit_items) == 1 and canonical(audit_items[0]) == canonical(items[0])
             and canonical(proposal) == canonical(audit_parent["request"]["proposal"])
             and proposal["choice"]["kind"] == "execute"
             and canonical(binding) == canonical(freeze["feedback_binding"])
             and freeze["selected_method"] == policy[items[0]["outcome"]],
             "The original audit is not the preregistered feedback decision.", "EVIDENCE_CHANGED")
    return {"registration": copy.deepcopy(registered), "feedback": copy.deepcopy(items[0]),
            "audit_proposal": copy.deepcopy(proposal),
            "verification": "source_context_verified_at_capture; offline_policy_binding_unverifiable_without_origin"}


def derive_staged_observation(workspace, primary_action_id):
    """Capture only completed original native actions; perform no research dispatch."""
    try:
        identifier(primary_action_id, "primary_action_id")
        project = ResearchProject(workspace)
        before = project.status()
        initial_code = runtime_code_identity()
        implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        _require(not any(a["status"] in ("pending", "running", "unknown") for a in before["actions"] + before["evidence_actions"])
                 and not any(p["status"] in ("prepared", "running", "unknown") for p in before.get("controller_requests", [])),
                 "Resolve all pending source requests first.", "EXECUTION_UNKNOWN")
        metadata = holdout.validate_metadata(before)
        _require(metadata is not None and metadata["frozen_evaluation_strategy"] is not None,
                 "A preregistered holdout and frozen strategy are required.", "ARTIFACT_NOT_AVAILABLE")
        reg, freeze = metadata["private_evaluation"], metadata["frozen_evaluation_strategy"]
        v2 = reg["schema_version"] == "retrieval-holdout-registration-v2"
        source_sha, source, parsed = _dev_source(project, before)
        actions = []
        for method in (staged.TOOL_ID, staged.AUDIT_TOOL_ID, holdout.FINAL_TOOL_ID):
            matching = [x for x in before["actions"] if x["command"] == method]
            _require(len(matching) == 1 and matching[0]["status"] == "completed", "One completed action per stage is required.", "ARTIFACT_NOT_AVAILABLE")
            actions.append(matching[0])
        primary, audit, final = actions
        _verify_action_rows(project, actions)
        _require(primary["id"] == primary_action_id and freeze["primary_action_id"] == primary_action_id
                 and freeze["primary_result_sha256"] == primary["result_sha256"], "Frozen primary identity differs.", "EVIDENCE_CHANGED")
        for item, method in zip(actions, (staged.TOOL_ID, staged.AUDIT_TOOL_ID, holdout.FINAL_TOOL_ID)):
            _action(item, before, method, None if item is primary else primary)
        parents = [_parent(before, item, reg, freeze) for item in actions]
        _require(reg["state_version_before"] < parents[0]["state_version_before"]
                 and parents[0]["state_version_after"] <= parents[1]["state_version_before"]
                 and parents[1]["state_version_after"] <= freeze["request"]["expected_state_version"]
                 and freeze["request"]["expected_state_version"] < parents[2]["state_version_before"],
                 "Original staged registration and action order differs.", "EVIDENCE_CHANGED")
        envelopes, raw_hashes = zip(*[_read(project, item) for item in actions])
        first, second, third = [env["tool_result"] for env in envelopes]
        for action, tool in zip(actions, (first, second, third)):
            observations = [dict(item, id=action["id"] + ":observation:" + str(i), action_id=action["id"])
                            for i, item in enumerate(tool["observations"])]
            _require(action["observations"] == observations, "Action observations differ from the original result.", "EVIDENCE_CHANGED")
        saved = staged._saved(first)
        _require(saved["scope"] == before["source_scope"] and saved["source_snapshot_sha256"] == before["source_snapshot_sha256"]
                 and saved["comparison"] == source["spec"]["comparison"], "Saved primary differs from the source.", "EVIDENCE_CHANGED")
        docs, queries, qrels, doc_lines, query_lines = parsed
        for row in saved["rankings"]:
            _require(row["query_id"] in queries and row["query_line"] == query_lines[row["query_id"]]
                     and all(doc in docs and doc_lines[doc] == line for doc, line in zip(row["ranking"], row["ranked_doc_lines"])),
                     "Saved development ranking coordinates differ.", "EVIDENCE_CHANGED")
        for row in saved["per_query_metrics"]:
            _require(row["qrel_locator"]["document_grades"] == qrels[row["query_id"]],
                     "Saved development labels differ from the source.", "EVIDENCE_CHANGED")
        params = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
        paired, _, adverse = _check_audit(second, first, params)
        if v2:
            feedback_history = _feedback_history(project, before, reg, freeze, primary, audit, parents)
            delta = paired["splits"]["validation"]["paired_candidate_minus_baseline"]["recall@20"]["mean"]
            _require(type(delta) in (int, float) and math.isfinite(delta) and delta == freeze["validation_delta_recall20"],
                     "Frozen observed recall differs from original primary.", "EVIDENCE_CHANGED")
        else:
            _, expected = holdout._check_frozen(project, before, freeze)
            _require(canonical(expected) == canonical(first), "Frozen result differs from original primary.", "EVIDENCE_CHANGED")
        final_projection = _final_projection(third, reg, freeze, params, before["source_snapshot_sha256"])
        origin = {"project_id": before["id"], "run_id": before["run_id"], "state_version": before["state_version"],
                  "snapshot_ref": before["snapshot_ref"], "source_snapshot_sha256": before["source_snapshot_sha256"],
                  "source_file_sha256": source_sha, "registered_project_code_identity": before["code_identity"],
                  "producer_code_identity": primary["code_identity"], "capture_runtime_code_identity": initial_code,
                  "capture_implementation_sha256": implementation}
        provenance = {"action_id": primary["id"], "source_record_sha256": fingerprint(before), "origin": origin,
                      "source": source, "actions": {"primary": _project_action(primary), "audit": _project_action(audit), "final": _project_action(final)},
                      "artifacts": {"primary": envelopes[0], "audit": envelopes[1]},
                      "artifact_file_sha256": {"primary": raw_hashes[0], "audit": raw_hashes[1], "final": raw_hashes[2]},
                      "parent_bindings": {k: p for k, p in zip(("primary", "audit", "final"), parents)},
                      "holdout_registration": reg, "freeze": freeze,
                      "final_ref": {"action_id": final["id"], "request_id": final["request_id"], "result_sha256": final["result_sha256"]}}
        if v2:
            provenance["feedback_history"] = feedback_history
        scope = {"source_manifest_sha256": before["source_snapshot_sha256"],
                 "inputs_sha256": fingerprint({"primary": primary["result_sha256"], "audit": audit["result_sha256"],
                                                "final": final["result_sha256"], "source": fingerprint(source),
                                                "freeze": freeze["record_sha256"]}),
                 "analysis_code_sha256": fingerprint({"implementation_sha256": implementation, "runtime_code_identity": initial_code}),
                 "protocol": PROTOCOL_V2 if v2 else PROTOCOL}
        payload = {"method_id": staged.TOOL_ID, "evaluation_ref": EVALUATION,
                   "source_scope": before["source_scope"], "comparison": saved["comparison"],
                   "paired_summary": paired, "adverse_queries": len(adverse),
                   "final": final_projection, "origin_limitations": saved["limitations"],
                   "verification": "saved_only_binding_structure_and_arithmetic"}
        entry = {"schema_version": "conditional-research-memory-v1", "kind": "diagnostic_observation", "scope": scope,
                 "review_status": "derived_not_scientifically_reviewed", "numerical_recomputation": False,
                 "payload": payload, "provenance": provenance}
        entry["id"] = observation_id(entry)
        _validate_record(entry)
        _require(hashlib.sha256(source_reader._read_file(project.root / "source.json", staged.LIMITS["packet_bytes"])).hexdigest() == source_sha
                 and all(_read(project, item)[1] == raw_hash for item, raw_hash in zip(actions, raw_hashes)),
                 "Source or action artifact changed while capturing.", "STALE_STATE")
        _verify_action_rows(project, actions)
        _require(project.status() == before and runtime_code_identity() == initial_code
                 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == implementation,
                 "Project or capture implementation changed.", "STALE_STATE")
        return {"scope": scope, "entries": [entry], "validation": {"protocol": PROTOCOL_V2 if v2 else PROTOCOL,
                "source_packet_checked_at_capture": True, "final_aggregate_verified_at_capture": True,
                "offline_final_binding_unverifiable_without_origin": True, "scientific_validation": False,
                **({"offline_policy_binding_unverifiable_without_origin": True} if v2 else {})}}
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError, OSError):
        raise ResearchError("EVIDENCE_CHANGED", "Staged project or saved evidence is malformed.") from None


def _check_final_projection(value, frozen, reg):
    _require(type(value) is dict and set(value) == {"selected_method", "baseline_method", "comparison_status", "query_count", "summary", "usage", "limitations", "verification"}
             and value["selected_method"] == frozen["selected_method"] and value["baseline_method"] == "bm25"
             and value["comparison_status"] == ("selected_equals_baseline_single_computation" if value["selected_method"] == "bm25" else "distinct_selected_and_baseline")
             and type(value["query_count"]) is int and value["query_count"] == reg["query_count"]
             and 1 <= value["query_count"] <= staged.LIMITS["max_queries"]
             and value["verification"] == "source_verified_at_capture; offline_final_binding_unverifiable_without_origin",
             "Invalid final aggregate projection.")
    n = value["query_count"]
    calls = n * (1 if value["selected_method"] == "bm25" else 2)
    _require(value["usage"] == {"index_builds": 1, "ranking_calls": calls, "scoring_calls": calls, "native_fits": 0, "model_calls": 0}
             and all(type(x) is int for x in value["usage"].values())
             and value["limitations"] == ["Procedural same-user separation only; not OS-isolated or independently blind.",
                                           "Final binary relevance metrics do not establish scientific validity."],
             "Final count or limitation projection differs.")
    sums = value["summary"]
    from . import retrieval_lexical
    _require(type(sums) is dict and set(sums) == {"baseline", "selected", "delta"}, "Invalid final summary.")
    for kind in ("baseline", "selected", "delta"):
        _require(type(sums[kind]) is dict and set(sums[kind]) == set(retrieval_lexical.METRICS)
                 and all(type(x) in (int, float) and math.isfinite(x) and (-1 if kind == "delta" else 0) <= x <= 1
                         for x in sums[kind].values()), "Invalid final metric values.")
    _require(all(abs(sums["delta"][k] - (sums["selected"][k] - sums["baseline"][k])) <= 1e-12
                 for k in retrieval_lexical.METRICS), "Final aggregate deltas differ.")
    if value["selected_method"] == "bm25":
        _require(sums["selected"] == sums["baseline"] and all(v == 0 for v in sums["delta"].values()),
                 "Single-arm baseline cannot imply a separate final comparison.")


def _validate_feedback_history(history, reg, freeze, primary, audit, parents, saved, paired, origin):
    from . import hypothesis_feedback, staged_feedback_reader
    _require(type(history) is dict and set(history) == {"registration", "feedback", "audit_proposal", "verification"}
             and history["verification"] == "source_context_verified_at_capture; offline_policy_binding_unverifiable_without_origin",
             "Invalid feedback history or offline limitation.")
    registration, item, proposal = history["registration"], history["feedback"], history["audit_proposal"]
    hypothesis_feedback._check_record(registration)
    condition = registration["condition"]
    primary_candidate = {"method_id": primary["command"], "parameters": primary["method_instance"]["parameters"],
                         "evaluation_ref": primary["method_instance"]["evaluation_ref"]}
    version = ("hypothesis-feedback-context-v3" if "leave_one_out" in condition else
               "hypothesis-feedback-context-v2" if "all" in condition else "hypothesis-feedback-context-v1")
    hypothesis_feedback.validate_context({"schema_version": version, "items": [item], "scientific_validation": False,
                                          "test_notice": hypothesis_feedback.STAGED_NOTICE})
    _require(registration["request_id"] == reg["policy"]["registration_request_id"]
             and registration["request_id"] != reg["request_id"]
             and registration["project_id"] == origin["project_id"] and registration["run_id"] == origin["run_id"]
             and registration["source_sha256"] == reg["source_sha256"]
             and registration["source_snapshot_sha256"] == reg["source_snapshot_sha256"]
             and registration["project_code_identity"] == reg["project_code_identity"]
             and registration["plan_sha256"] == reg["plan_sha256"] and registration["plan_version"] == reg["plan_version"]
             and registration["scope_sha256"] == fingerprint(saved["scope"])
             and registration["protocol_sha256"] == fingerprint(staged.COMPARISON)
             and registration["candidate"]["method_id"] == staged.TOOL_ID
             and canonical(registration["candidate"]) == canonical({"id": "choice-" + fingerprint(primary_candidate)[:32], **primary_candidate})
             and registration["controller_request_id"] == parents["primary"]["request_id"]
             and reg["state_version_before"] < registration["state_version_before"] < parents["primary"]["state_version_before"]
             and all(p["controller_code_identity"] == registration["controller_code_identity"] for p in parents.values())
             and item["request_id"] == registration["request_id"]
             and item["controller_request_id"] == registration["controller_request_id"]
             and item["registration_sha256"] == registration["registration_sha256"]
             and canonical(item["candidate"]) == canonical(registration["candidate"])
             and canonical(item["condition"]) == canonical(condition)
             and canonical(item.get("branches")) == canonical(registration.get("branches"))
             and item["outcome"] in ("condition_met", "condition_not_met")
             and item["action_id"] == primary["id"] and item["result_sha256"] == primary["result_sha256"]
             and registration["branches"][item["outcome"]] == {"kind": "method", "method_id": staged.AUDIT_TOOL_ID},
             "Saved feedback registration, source or outcome differs.")
    metrics = paired["splits"]["validation"]["paired_candidate_minus_baseline"]
    if "all" in condition:
        means = [metrics[c["metric"]]["mean"] for c in condition["all"]]
        value = means
        if "leave_one_out" in condition:
            metric = condition["leave_one_out"]["metric"]
            rows = {(r["query_id"], r["method"]): r for r in saved["per_query_metrics"] if r["split"] == "validation"}
            qids = sorted({key[0] for key in rows})
            _require(len(qids) >= 2, "Insufficient original validation queries for leave-one-out.")
            deltas = [rows[qid, "tfidf_cosine"]["metrics"][metric] - rows[qid, "bm25"]["metrics"][metric] for qid in qids]
            loo = staged_feedback_reader._stability_aggregate(deltas, metrics[metric])["leave_one_out"]
            value = {"means": means, "leave_one_out": {"minimum": loo["minimum"], "maximum": loo["maximum"], "queries": len(qids)}}
    else:
        value = metrics[condition["metric"]]["mean"]
    _require(canonical(value) == canonical(item["value"]), "Feedback values differ from saved validation arithmetic.")
    binding = {"registration_request_id": registration["request_id"], "registration_sha256": registration["registration_sha256"],
               "outcome": item["outcome"], "audit_action_id": audit["id"], "audit_result_sha256": audit["result_sha256"],
               "audit_parent_request_id": parents["audit"]["request_id"]}
    rationale = ("Preregistration " + registration["request_id"] + " sha256:" + registration["registration_sha256"]
                 + ". Frozen " + item["outcome"] + " branch selects the eligible audit of the registered saved result.")
    audit_candidate = {"method_id": staged.AUDIT_TOOL_ID, "parameters": {"based_on_action_id": primary["id"],
                       "based_on_result_sha256": primary["result_sha256"]}, "evaluation_ref": audit["evaluation_ref"]}
    _require(canonical(freeze["feedback_binding"]) == canonical(binding)
             and freeze["selected_method"] == reg["policy"][item["outcome"]]
             and type(proposal) is dict and set(proposal) == {"schema_version", "context_sha256", "provider", "choice", "rationale", "evidence_citation_ids"}
             and proposal["schema_version"] == "project-selection-proposal-v1"
             and proposal["context_sha256"] == parents["audit"]["context_sha256"]
             and proposal["provider"] == {"kind": "operator_assistant", "label": "preregistered-feedback-policy-v1"}
             and type(proposal["choice"]) is dict and set(proposal["choice"]) == {"kind", "candidate_id"}
             and proposal["choice"]["kind"] == "execute"
             and proposal["choice"]["candidate_id"] == "choice-" + fingerprint(audit_candidate)[:32]
             and proposal["rationale"] == rationale and proposal["evidence_citation_ids"] == []
             and parents["audit"]["request_sha256"] == fingerprint({"project_id": origin["project_id"], "command": "controller.advance_selection",
                 "need": "next_check", "expected_state_version": parents["audit"]["state_version_before"], "proposal": proposal}),
             "Saved feedback audit or selected method differs.")


def _validate_record(record):
    import base64
    _require(type(record) is dict and set(record) == {"schema_version", "id", "kind", "scope", "review_status", "numerical_recomputation", "payload", "provenance"}
             and record["schema_version"] == "conditional-research-memory-v1" and record["kind"] == "diagnostic_observation"
             and record["review_status"] == "derived_not_scientifically_reviewed" and record["numerical_recomputation"] is False,
             "Invalid staged memory record.")
    scope = validate_scope(record["scope"])
    _require(scope["protocol"] in (PROTOCOL, PROTOCOL_V2) and observation_id(record) == record["id"], "Staged record identity differs.")
    v2 = scope["protocol"] == PROTOCOL_V2
    p = record["provenance"]
    provenance_fields = {"action_id", "source_record_sha256", "origin", "source", "actions", "artifacts", "artifact_file_sha256", "parent_bindings", "holdout_registration", "freeze", "final_ref"}
    if v2:
        provenance_fields.add("feedback_history")
    _require(type(p) is dict and set(p) == provenance_fields
             and _hash(p["source_record_sha256"]), "Invalid staged provenance.")
    origin, source, payload = p["origin"], p["source"], record["payload"]
    _require(type(origin) is dict and set(origin) == {"project_id", "run_id", "state_version", "snapshot_ref", "source_snapshot_sha256", "source_file_sha256", "registered_project_code_identity", "producer_code_identity", "capture_runtime_code_identity", "capture_implementation_sha256"}
             and type(origin["state_version"]) is int and origin["state_version"] > 0
             and all(_hash(origin[k]) for k in ("snapshot_ref", "source_snapshot_sha256", "source_file_sha256", "registered_project_code_identity", "producer_code_identity", "capture_runtime_code_identity", "capture_implementation_sha256")),
             "Invalid staged origin.")
    identifier(origin["project_id"], "project_id")
    identifier(origin["run_id"], "run_id")
    _require(type(source) is dict and set(source) == {"task_kind", "stage", "spec", "spec_source", "assets", "source_inclusion"}
             and source["task_kind"] == "staged_relevance_development" and source["stage"] == "development"
             and source["source_inclusion"] == "asset_bytes_excluded_hash_references_only"
             and type(source["assets"]) is dict and set(source["assets"]) == set(staged.FILES), "Invalid source references.")
    spec_asset = source["spec_source"]
    _require(type(spec_asset) is dict and set(spec_asset) == {"file_name", "sha256", "bytes", "bytes_base64"}
             and spec_asset["file_name"] == "spec.json" and _hash(spec_asset["sha256"]) and type(spec_asset["bytes"]) is int,
             "Original development specification bytes required.")
    try:
        raw_spec = base64.b64decode(spec_asset["bytes_base64"], validate=True)
    except (ValueError, TypeError):
        raise ResearchError("INVALID_STAGED_EXPERIENCE", "Malformed development specification encoding.") from None
    spec = staged._parse(raw_spec)
    staged._spec(spec)
    _require(0 < len(raw_spec) <= staged.LIMITS["spec_bytes"] and len(raw_spec) == spec_asset["bytes"]
             and hashlib.sha256(raw_spec).hexdigest() == spec_asset["sha256"]
             and base64.b64encode(raw_spec).decode("ascii") == spec_asset["bytes_base64"] and spec == source["spec"]
             and all(type(asset) is dict and set(asset) == {"sha256", "bytes"} and _hash(asset["sha256"])
                     and type(asset["bytes"]) is int and 0 < asset["bytes"] <= staged._limit(role)
                     for role, asset in source["assets"].items()), "Development source references differ.")
    _require(type(payload) is dict and set(payload) == {"method_id", "evaluation_ref", "source_scope", "comparison", "paired_summary", "adverse_queries", "final", "origin_limitations", "verification"}
             and payload["method_id"] == staged.TOOL_ID and payload["evaluation_ref"] == EVALUATION
             and type(payload["source_scope"]) is dict and payload["source_scope"].get("domain") == "retrieval"
             and payload["source_scope"].get("contract") == staged.CONTRACT
             and payload["source_scope"].get("input_identities") == source["assets"]
             and payload["comparison"] == spec["comparison"] and payload["verification"] == "saved_only_binding_structure_and_arithmetic",
             "Invalid staged observation payload.")
    fake_state = {"id": origin["project_id"], "run_id": origin["run_id"], "source_snapshot_sha256": origin["source_snapshot_sha256"],
                  "source_scope": payload["source_scope"], "code_identity": origin["registered_project_code_identity"]}
    actions, artifacts = p["actions"], p["artifacts"]
    _require(type(actions) is dict and set(actions) == {"primary", "audit", "final"}
             and type(artifacts) is dict and set(artifacts) == {"primary", "audit"}, "Invalid captured stage evidence.")
    primary, audit, final = actions["primary"], actions["audit"], actions["final"]
    for item, method in ((primary, staged.TOOL_ID), (audit, staged.AUDIT_TOOL_ID), (final, holdout.FINAL_TOOL_ID)):
        _require(type(item) is dict and item == _project_action(item), "Unexpected action projection fields.")
        _action(item, fake_state, method, None if item is primary else primary)
    _require(p["action_id"] == primary["id"] and origin["producer_code_identity"] == primary["code_identity"], "Staged primary identity differs.")
    for label in ("primary", "audit"):
        env, action = artifacts[label], actions[label]
        _require(type(env) is dict and set(env) == {"action_id", "code_identity", "request_sha256", "sha256", "source_snapshot_sha256", "tool_result"}
                 and env["sha256"] == fingerprint({k: v for k, v in env.items() if k != "sha256"}) == action["result_sha256"]
                 and env["action_id"] == action["id"] and env["request_sha256"] == action["request_sha256"]
                 and env["code_identity"] == action["code_identity"] and env["source_snapshot_sha256"] == origin["source_snapshot_sha256"],
                 "Saved stage envelope differs.")
    saved = staged._saved(artifacts["primary"]["tool_result"])
    _require(saved["scope"] == payload["source_scope"] and saved["comparison"] == payload["comparison"]
             and saved["source_snapshot_sha256"] == origin["source_snapshot_sha256"]
             and {(row["split"], row["query_id"]) for row in saved["per_query_metrics"]}
                 == {(split, qid) for split, ids in spec["query_splits"].items() for qid in ids}
             and all(ref["url"] == spec["source_url"] and ref["license_note"] == spec["license_notes"]["corpus" if ref["locator"]["role"] == "corpus" else "queries_and_qrels"]
                     for ref in artifacts["primary"]["tool_result"]["evidence_refs"]), "Saved primary source differs.")
    params = {"based_on_action_id": primary["id"], "based_on_result_sha256": primary["result_sha256"]}
    paired, _, adverse = _check_audit(artifacts["audit"]["tool_result"], artifacts["primary"]["tool_result"], params)
    _require(paired == payload["paired_summary"] and type(payload["adverse_queries"]) is int
             and payload["adverse_queries"] == len(adverse) and payload["origin_limitations"] == saved["limitations"],
             "Saved stage summaries differ.")
    reg, freeze = p["holdout_registration"], p["freeze"]
    reg_fields = {"schema_version", "request_id", "request_sha256", "request", "project_id", "run_id", "state_version_before", "sha256", "bytes", "query_count", "corpus_sha256", "source_sha256", "source_snapshot_sha256", "plan_sha256", "plan_version", "project_code_identity", "policy", "scientific_validation", "record_sha256"}
    freeze_fields = {"schema_version", "request_id", "request", "request_sha256", "project_id", "run_id", "holdout_record_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity", "primary_action_id", "primary_result_sha256", "validation_delta_recall20", "policy", "selected_method", "scientific_validation", "record_sha256"}
    if v2:
        freeze_fields.add("feedback_binding")
    _require(type(reg) is dict and set(reg) == reg_fields and reg["schema_version"] == ("retrieval-holdout-registration-v2" if v2 else "retrieval-holdout-registration-v1")
             and type(freeze) is dict and set(freeze) == freeze_fields and freeze["schema_version"] == ("retrieval-holdout-freeze-v2" if v2 else "retrieval-holdout-freeze-v1")
             and all(_hash(reg[k]) for k in ("request_sha256", "sha256", "corpus_sha256", "source_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity", "record_sha256"))
             and all(_hash(freeze[k]) for k in ("request_sha256", "holdout_record_sha256", "source_snapshot_sha256", "plan_sha256", "project_code_identity", "primary_result_sha256", "record_sha256"))
             and type(reg["state_version_before"]) is int and 0 <= reg["state_version_before"] < origin["state_version"]
             and type(reg["bytes"]) is int and 0 < reg["bytes"] <= holdout.MAX_HOLDOUT_BYTES
             and type(reg["query_count"]) is int and 1 <= reg["query_count"] <= staged.LIMITS["max_queries"]
             and type(reg["plan_version"]) is int and 1 <= reg["plan_version"] <= origin["state_version"]
             and canonical(reg["policy"]) == canonical(freeze["policy"])
             and (canonical(holdout._feedback_policy(reg["policy"])) == canonical(reg["policy"]) if v2 else reg["policy"] == holdout.POLICY)
             and reg["scientific_validation"] is False and freeze["scientific_validation"] is False,
             "Invalid holdout or frozen metadata schema.")
    for item in (reg, freeze):
        identifier(item["request_id"])
    identifier(freeze["primary_action_id"], "primary_action_id")
    expected_registration_request = {"request_id": reg["request_id"], "expected_state_version": reg["state_version_before"], "holdout_sha256": reg["sha256"], "holdout_bytes": reg["bytes"]}
    if v2:
        expected_registration_request["selection_policy"] = reg["policy"]
    _require(type(reg["request"]) is dict and canonical(reg["request"]) == canonical(expected_registration_request)
             and type(reg["request"]["expected_state_version"]) is int and type(reg["request"]["holdout_bytes"]) is int
             and reg["request_sha256"] == fingerprint(reg["request"])
             and type(freeze["request"]) is dict and set(freeze["request"]) == {"request_id", "expected_state_version", "primary_action_id"}
             and freeze["request"]["request_id"] == freeze["request_id"] and freeze["request"]["primary_action_id"] == freeze["primary_action_id"]
             and type(freeze["request"]["expected_state_version"]) is int and reg["state_version_before"] < freeze["request"]["expected_state_version"] < origin["state_version"]
             and freeze["request_sha256"] == fingerprint(freeze["request"]) and reg["request_id"] != freeze["request_id"],
             "Holdout/freeze request identity differs.")
    _require(type(reg) is dict and type(freeze) is dict
             and reg.get("record_sha256") == fingerprint({k: v for k, v in reg.items() if k != "record_sha256"})
             and freeze.get("record_sha256") == fingerprint({k: v for k, v in freeze.items() if k != "record_sha256"})
             and reg.get("project_id") == origin["project_id"] and reg.get("run_id") == origin["run_id"]
             and reg.get("source_snapshot_sha256") == origin["source_snapshot_sha256"]
             and reg.get("source_sha256") == origin["source_file_sha256"]
             and reg.get("project_code_identity") == origin["registered_project_code_identity"]
             and reg.get("corpus_sha256") == source["assets"]["corpus"]["sha256"]
             and freeze.get("holdout_record_sha256") == reg["record_sha256"] and freeze.get("project_id") == origin["project_id"]
             and freeze.get("run_id") == origin["run_id"] and freeze.get("source_snapshot_sha256") == origin["source_snapshot_sha256"]
             and freeze.get("project_code_identity") == origin["registered_project_code_identity"]
             and freeze.get("plan_sha256") == reg.get("plan_sha256") and canonical(freeze.get("policy")) == canonical(reg["policy"])
             and freeze.get("primary_action_id") == primary["id"] and freeze.get("primary_result_sha256") == primary["result_sha256"],
             "Holdout or frozen registration binding differs.")
    delta = paired["splits"]["validation"]["paired_candidate_minus_baseline"]["recall@20"]["mean"]
    _require(type(delta) in (int, float) and math.isfinite(delta)
             and (not v2 or (type(freeze["validation_delta_recall20"]) in (int, float) and math.isfinite(freeze["validation_delta_recall20"])))
             and freeze["validation_delta_recall20"] == delta
             and (v2 or freeze["selected_method"] == ("tfidf_cosine" if delta > 0 else "bm25")), "Frozen validation selection differs.")
    _check_final_projection(payload["final"], freeze, reg)
    final_ref = p["final_ref"]
    _require(final_ref == {"action_id": final["id"], "request_id": final["request_id"], "result_sha256": final["result_sha256"]}, "Final action reference differs.")
    file_hashes = p["artifact_file_sha256"]
    _require(type(file_hashes) is dict and set(file_hashes) == {"primary", "audit", "final"} and all(_hash(v) for v in file_hashes.values())
             and all(file_hashes[name] == hashlib.sha256(canonical(artifacts[name]).encode("utf-8")).hexdigest() for name in ("primary", "audit")),
             "Invalid artifact-byte references.")
    parents = p["parent_bindings"]
    _require(type(parents) is dict and set(parents) == {"primary", "audit", "final"}, "Three original parent references required.")
    parent_fields = {"request_id", "request_sha256", "decision_sha256", "context_sha256", "controller_code_identity", "child_request_id", "state_version_before", "state_version_after"}
    for name in ("primary", "audit", "final"):
        parent = parents[name]
        _require(type(parent) is dict and set(parent) == parent_fields and all(_hash(parent[k]) for k in ("request_sha256", "decision_sha256", "context_sha256", "controller_code_identity"))
                 and type(parent["state_version_before"]) is int and type(parent["state_version_after"]) is int
                 and 0 <= parent["state_version_before"] < parent["state_version_after"] <= origin["state_version"]
                 and parent["child_request_id"] == actions[name]["request_id"]
                 and parent["child_request_id"] == "controller-child-" + fingerprint({"project_id": origin["project_id"], "request_id": parent["request_id"]})[:32],
                 "Parent identity or ordering differs.")
        identifier(parent["request_id"])
    _require(reg["state_version_before"] < parents["primary"]["state_version_before"]
             and parents["primary"]["state_version_after"] <= parents["audit"]["state_version_before"]
             and parents["audit"]["state_version_after"] <= freeze["request"]["expected_state_version"]
             and freeze["request"]["expected_state_version"] < parents["final"]["state_version_before"], "Stage order differs.")
    if v2:
        _validate_feedback_history(p["feedback_history"], reg, freeze, primary, audit, parents, saved, paired, origin)
    _require(scope["source_manifest_sha256"] == origin["source_snapshot_sha256"]
             and scope["inputs_sha256"] == fingerprint({"primary": primary["result_sha256"], "audit": audit["result_sha256"],
                 "final": final["result_sha256"], "source": fingerprint(source), "freeze": freeze["record_sha256"]})
             and scope["analysis_code_sha256"] == fingerprint({"implementation_sha256": origin["capture_implementation_sha256"],
                                                                 "runtime_code_identity": origin["capture_runtime_code_identity"]}),
             "Staged record scope differs.")
    return record



def _base_from_shadow_record(record):
    """Reconstruct the exact v2 evidence subset before validating a v3 extension."""
    _require(type(record) is dict and type(record.get('scope')) is dict
             and record['scope'].get('protocol') == PROTOCOL_V3 and type(record.get('provenance')) is dict,
             'Invalid shadow record scope.')
    extension = record['provenance'].get('shadow_comparison')
    _require(type(extension) is dict and set(extension) == {'base_scope', 'projection'},
             'Invalid shadow extension.')
    base = copy.deepcopy(record); base['provenance'].pop('shadow_comparison')
    base['scope'] = copy.deepcopy(extension['base_scope']); base['id'] = observation_id(base)
    _validate_record(base)
    return base, extension['projection']


def _validate_shadow_record(record):
    from . import staged_feedback_reader as reader
    base, shadow = _base_from_shadow_record(record)
    fields = {'schema_version','case_sha256','source_commit','protocol_sha256','driver_sha256',
              'decision_sha256','validation_inputs_sha256','start_sha256','claim_sha256','anchor_request_id','anchor_based_on_state_version',
              'anchor_content_trust','audit_parent_request_id','audit_context_sha256','condition','value',
              'comparison','verification'}
    _require(type(shadow) is dict and set(shadow) == fields and shadow['schema_version'] == 'staged-shadow-comparison-v1'
             and shadow['case_sha256'] == _S067_CASE_SHA
             and all(_hash(shadow[k]) for k in ('case_sha256','protocol_sha256','driver_sha256','decision_sha256',
                                                 'validation_inputs_sha256','start_sha256','claim_sha256','audit_context_sha256'))
             and shadow['decision_sha256'] == _S067_DECISION_SHA
             and shadow['source_commit'] == _S067_COMMIT and shadow['protocol_sha256'] == _S067_PROTOCOL_SHA
             and shadow['driver_sha256'] == _S067_DRIVER_SHA
             and shadow['anchor_request_id'] == 's067-shadow-anchor'
             and shadow['anchor_content_trust'] == 'unverified_researcher_statement'
             and shadow['verification'] == _SHADOW_VERIFICATION,
             'Invalid compact shadow binding.')
    parent = base['provenance']['parent_bindings']; primary = base['provenance']['actions']['primary']
    origin = base['provenance']['origin']
    _require(origin['project_id'] == _S067_PROJECT_ID and origin['run_id'] == _S067_RUN_ID
             and origin['source_snapshot_sha256'] == _S067_SOURCE_SNAPSHOT and primary['id'] == _S067_PRIMARY_ID,
             'Shadow case is not the fixed S067 source.')
    _require(type(shadow['anchor_based_on_state_version']) is int
             and parent['primary']['state_version_after'] == shadow['anchor_based_on_state_version']
             and shadow['anchor_based_on_state_version'] + 1 == parent['audit']['state_version_before']
             and shadow['audit_parent_request_id'] == parent['audit']['request_id']
             and shadow['audit_context_sha256'] == parent['audit']['context_sha256'],
             'Compact shadow sequence differs.')
    expected_scope = copy.deepcopy(base['scope']); expected_scope['protocol'] = PROTOCOL_V3
    expected_scope['inputs_sha256'] = fingerprint({'base_inputs_sha256':base['scope']['inputs_sha256'],
                                                   'shadow_decision_sha256':shadow['decision_sha256']})
    _require(record['scope'] == expected_scope and observation_id(record) == record['id'],
             'Shadow scoped identity differs.')
    saved = staged._saved(base['provenance']['artifacts']['primary']['tool_result'])
    qids = sorted(base['provenance']['source']['spec']['query_splits']['validation'])
    metrics = {(r['split'],r['query_id'],r['method']):r['metrics'] for r in saved['per_query_metrics']}
    _require(len(qids) == 200 and len(set(qids)) == 200, 'Shadow validation coverage differs.')
    try:
        rows = [{'query_id':qid, **{method:{k:metrics[('validation',qid,method)][k] for k in ('recall@20','mrr@10')}
                                    for method in ('bm25','tfidf_cosine')}} for qid in qids]
        paired = base['payload']['paired_summary']['splits']['validation']['paired_candidate_minus_baseline']
        deltas = [r['tfidf_cosine']['recall@20']-r['bm25']['recall@20'] for r in rows]
        aggregate = reader._stability_aggregate(deltas,paired['recall@20'])
        value = {'means':[paired[k]['mean'] for k in ('recall@20','mrr@10')],
                 'leave_one_out':{'minimum':aggregate['leave_one_out']['minimum'],
                                  'maximum':aggregate['leave_one_out']['maximum'],'queries':len(qids)}}
        inputs = {'schema_version':'s067-shadow-validation-inputs-v1','rows':rows,'case_sha256':shadow['case_sha256'],
                  'primary_action_id':primary['id'],'primary_result_sha256':primary['result_sha256']}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ResearchError('INVALID_STAGED_EXPERIENCE', 'Shadow saved validation values differ.') from None
    _require(fingerprint(inputs) == shadow['validation_inputs_sha256']
             and canonical(value) == canonical(shadow['value'])
             and canonical(shadow['comparison']) == canonical(_shadow_comparison(
                 base['provenance']['feedback_history']['feedback'], shadow['condition'], value, base['payload']['final'])),
             'Shadow validation arithmetic or comparison differs.')
    return record


def derive_staged_shadow_observation(workspace, primary_action_id, *, study_workspace):
    """Explicit S067 source-side shadow capture, without dispatch or private holdout access."""
    project = ResearchProject(workspace); before = project.status()
    initial_code = runtime_code_identity(); initial_implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    derived = derive_staged_observation(workspace, primary_action_id)
    base = derived['entries'][0]
    _require(base['scope']['protocol'] == PROTOCOL_V2, 'The fixed shadow needs a native v2 feedback record.', 'INVALID_REQUEST')
    shadow = _read_s067_shadow(project, before, base, study_workspace)
    result = copy.deepcopy(base); result['provenance']['shadow_comparison'] = {'base_scope':copy.deepcopy(base['scope']),
                                                                             'projection':shadow}
    result['scope']['protocol'] = PROTOCOL_V3
    result['scope']['inputs_sha256'] = fingerprint({'base_inputs_sha256':base['scope']['inputs_sha256'],
                                                    'shadow_decision_sha256':shadow['decision_sha256']})
    result['id'] = observation_id(result)
    _validate_shadow_record(result)
    original_actions = [next(x for x in before['actions'] if x['id'] == base['provenance']['actions'][name]['id'])
                        for name in ('primary','audit','final')]
    _verify_action_rows(project, original_actions)
    _require(all(_read(project, action)[1] == base['provenance']['artifact_file_sha256'][name]
                 for name, action in zip(('primary','audit','final'), original_actions)),
             'Original action artifacts changed during shadow capture.', 'STALE_STATE')
    source_sha, _, _ = _dev_source(project, before)
    _require(source_sha == base['provenance']['origin']['source_file_sha256'],
             'Original source changed during shadow capture.', 'STALE_STATE')
    from . import project_experience_binding
    _, original_case = project_experience_binding._load(project.root, before['experience_revisions'][0])
    from .research_project import safe_path
    study = safe_path(Path(study_workspace).absolute())
    for relative, expected in (('private/shadow-decision.json',shadow['decision_sha256']),
                               ('private/shadow-inputs.json',shadow['validation_inputs_sha256']),
                               ('start.json',shadow['start_sha256'])):
        _require(hashlib.sha256(source_reader._read_file(safe_path(study / relative), 2 * 1024 * 1024)).hexdigest() == expected,
                 'Original shadow source changed during capture.', 'STALE_STATE')
    start = staged._parse(source_reader._read_file(safe_path(study / 'start.json'),65536))
    for relative, key in (('scripts/run_boolq_case_comparison_study.py','driver_sha256'),
                          ('docs/execution/g5-local/boolq-case-comparison-protocol-v1.json','protocol_sha256'),
                          ('tests/test_boolq_case_comparison_study.py','test_sha256'),
                          ('scripts/run_squad_paragraph_study.py','helper_sha256')):
        _require(hashlib.sha256(source_reader._read_file(safe_path(study.parent.parent / relative),5 * 1024 * 1024)).hexdigest() == start[key],
                 'Original producer source changed during capture.', 'STALE_STATE')
    claim = study.parent.parent.parent / '.study-claims/s067-boolq-paired-passage-v1.json'
    _require(hashlib.sha256(source_reader._read_file(safe_path(claim),65536)).hexdigest() == shadow['claim_sha256']
             and hashlib.sha256(original_case).hexdigest() == shadow['case_sha256'] and project.status() == before
             and runtime_code_identity() == initial_code
             and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == initial_implementation,
             'Project, claim or historical case changed during shadow capture.', 'STALE_STATE')
    return {'scope':result['scope'],'entries':[result],
            'validation':{**derived['validation'],'protocol':PROTOCOL_V3,'shadow_source_checked_at_capture':True,
                          'offline_shadow_binding_unverifiable_without_origin':True}}

def validate_bundle(bundle):
    try:
        _require(type(bundle) is dict and set(bundle) == {"schema_version", "id", "version", "record", "method_card", "limitations", "source_inclusion_status", "scientific_validation"}
                 and bundle["schema_version"] in (SCHEMA, SCHEMA_V2, SCHEMA_V3) and bundle["source_inclusion_status"] == "active_at_export"
                 and bundle["scientific_validation"] is False and type(bundle["version"]) is int and 1 <= bundle["version"] <= 2**31 - 1,
                 "Invalid staged case bundle.")
        identifier(bundle["id"], "case_id")
        _require(len(canonical(bundle).encode("utf-8")) <= MAX_BUNDLE_BYTES, "Staged case bundle exceeds 4 MiB.", "BUNDLE_TOO_LARGE")
        record = (_validate_shadow_record(bundle["record"]) if bundle["schema_version"] == SCHEMA_V3
                  else _validate_record(bundle["record"]))
        _require({SCHEMA:PROTOCOL, SCHEMA_V2:PROTOCOL_V2, SCHEMA_V3:PROTOCOL_V3}[bundle["schema_version"]]
                 == record["scope"]["protocol"], "Bundle version differs from its saved feedback protocol.")
        card = research_recipe.validate_method_card(bundle["method_card"])
        _require(card["scope_match"] == {"domain": "retrieval", "contract": staged.CONTRACT}
                 and card["method_refs"] == [{"method_id": staged.TOOL_ID, "evaluation_ref": EVALUATION}], "Method card must match the staged source.")
        _require(type(bundle["limitations"]) is list and 1 <= len(bundle["limitations"]) <= 8
                 and all(type(v) is str and 0 < len(v.strip()) <= 4000 and "\x00" not in v for v in bundle["limitations"]), "Bounded limitations required.")
        return copy.deepcopy(bundle)
    except ResearchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, UnicodeError, OverflowError, RecursionError):
        raise ResearchError("INVALID_STAGED_EXPERIENCE", "Malformed staged case bundle.") from None


def parse_bundle(raw):
    return validate_bundle(research_recipe.parse_json(raw, maximum=MAX_BUNDLE_BYTES, code="INVALID_STAGED_EXPERIENCE"))


def summary(bundle):
    bundle = validate_bundle(bundle)
    record = bundle["record"]
    if bundle["schema_version"] == SCHEMA_V3:
        base, shadow = _base_from_shadow_record(record)
        historical = copy.deepcopy(bundle); historical["schema_version"] = SCHEMA_V2; historical["record"] = base
        value = summary(historical)
        value["origin_evidence"]["binding_scope"] = copy.deepcopy(record["scope"])
        value["observation"]["shadow_comparison"] = copy.deepcopy(shadow)
        value["limitations"].append("External operator shadow is not a second native registration; " + _SHADOW_VERIFICATION)
        _require(len(canonical(value).encode("utf-8")) <= 64 * 1024, "Staged case summary exceeds 64 KiB.", "SUMMARY_TOO_LARGE")
        return value
    p, payload = record["provenance"], record["payload"]
    compact_scope = {k: copy.deepcopy(v) for k, v in payload["source_scope"].items()
                     if v is None or type(v) in (str, int, float, bool) or k == "input_identities"}
    value = {"case_id": bundle["id"], "case_version": bundle["version"], "entry_id": record["id"],
             "method_card": bundle["method_card"], "origin_evidence": {**p["origin"], "action_id": p["action_id"],
                 "result_sha256": p["actions"]["primary"]["result_sha256"], "binding_scope": record["scope"],
                 "audit_action_id": p["actions"]["audit"]["id"], "audit_result_sha256": p["actions"]["audit"]["result_sha256"],
                 "final_action_id": p["final_ref"]["action_id"], "final_result_sha256": p["final_ref"]["result_sha256"]},
             "source_scope": compact_scope, "observation": {"kind": "saved_staged_retrieval",
                 "method_id": payload["method_id"], "evaluation_ref": payload["evaluation_ref"], "comparison": payload["comparison"],
                 "paired_summary": payload["paired_summary"], "adverse_queries": payload["adverse_queries"],
                 "final": payload["final"], "verification": payload["verification"]},
             "limitations": [*payload["origin_limitations"], *bundle["limitations"], NOTICE],
             "transfer_scope": "analogy_not_current_evidence", "scientific_validation": False}
    if bundle["schema_version"] == SCHEMA_V2:
        history = p["feedback_history"]
        value["observation"]["preregistered_feedback"] = {
            "registration_schema_version": history["registration"]["schema_version"],
            "registration_request_id": history["registration"]["request_id"],
            "registration_sha256": history["registration"]["registration_sha256"],
            "condition": copy.deepcopy(history["registration"]["condition"]),
            "value": copy.deepcopy(history["feedback"]["value"]), "outcome": history["feedback"]["outcome"],
            "audit_parent_request_id": p["parent_bindings"]["audit"]["request_id"],
            "audit_parent_request_sha256": p["parent_bindings"]["audit"]["request_sha256"],
            "policy": copy.deepcopy(p["holdout_registration"]["policy"]),
            "verification": history["verification"]}
        value["limitations"].append("offline_policy_binding_unverifiable_without_origin; the original audit context is not included.")
    _require(len(canonical(value).encode("utf-8")) <= 64 * 1024, "Staged case summary exceeds 64 KiB.", "SUMMARY_TOO_LARGE")
    return value


class StagedExperienceMemory(ResearchMemory):
    def import_project(self, workspace, primary_action_id):
        return self._import_derived(derive_staged_observation(workspace, primary_action_id), verification="binding")

    def import_project_with_shadow(self, workspace, primary_action_id, *, study_workspace):
        return self._import_derived(derive_staged_shadow_observation(workspace, primary_action_id,
                                    study_workspace=study_workspace), verification="binding")

    def export_case(self, scope, entry_id, *, case_id, version, method_card, limitations):
        validate_scope(scope)
        with self._connect() as con:
            row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone() if con is not None else None
            _require(row is not None, "No staged source entry matches this identity.", "NOT_FOUND")
            record = self._verify(con, row)
            _require(record["scope"] == scope, "Export requires exact source scope.", "INVALID_SCOPE")
            _require(row["status"] == "active", "Retired evidence cannot be exported.", "EXPERIENCE_RETIRED")
            schema = {PROTOCOL:SCHEMA, PROTOCOL_V2:SCHEMA_V2, PROTOCOL_V3:SCHEMA_V3}.get(record["scope"]["protocol"])
            _require(schema is not None, "Unsupported staged experience protocol.")
            return validate_bundle({"schema_version": schema, "id": case_id, "version": version, "record": record,
                    "method_card": method_card, "limitations": limitations, "source_inclusion_status": "active_at_export", "scientific_validation": False})
