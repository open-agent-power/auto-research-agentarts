"""Native Ollama tool envelopes for the existing bounded C01 action contract.

No text fallback or argument repair. Envelope/model/token validation belongs to
the controller; tool execution and action-specific validation remain in C01.
Official shape: https://docs.ollama.com/capabilities/tool-calling
"""
import copy
import math
import re

from .c01_model_loop import _decision
from .contracts import ResearchError, canonical

ARGUMENT_FIELDS = {'observation_sha256', 'reason', 'source_citation_ids', 'evidence_action_ids'}
_RESERVED = ARGUMENT_FIELDS | {'action', 'request_id', 'parameters'}
_NAME = re.compile(r'[a-z][a-z0-9_]{0,63}')
_FEEDBACK = {
    'INVALID_CONTROL_REVIEW': 'Use review_evidence field=control_rationale only for the exact current unreviewed control proposal. Include control_review.proposal_action_id and latest_experiment_id when present in evidence_action_ids; cite1..4 original retrieved sources. A review is an unapproved assertion, not scientific authorization.',
    'DUPLICATE_CONTROL_PROPOSAL': 'A current control proposal/review already exists. Use that review to choose a useful numerical action or control decision. Only new experimental feedback can justify a new proposal; do not repeat it.',
    'INVALID_DATASET': 'The frozen dataset could not be inspected consistently within its fixed bounds. Do not invent, repair or replace inputs; use the recorded error and choose a justified pause/stop.',
    'DATASET_INSPECTION_TOO_LARGE': 'The frozen inspection exceeds its fixed response bound. Do not truncate or replace inputs; preserve this limitation and choose a justified pause/stop.',
    'MISSING_TOOL_CALL': 'Call exactly one offered native function; a textual JSON answer does not dispatch a tool.',
    'MULTIPLE_TOOL_CALLS': 'Return exactly one tool call so its real feedback can inform the next decision.',
    'INVALID_TOOL_ARGUMENTS': 'Supply the four common fields observation_sha256, reason, source_citation_ids and evidence_action_ids, plus the offered action fields at TOP LEVEL. Include required fields and only offered optional fields. Never use a parameters bag, action or request_id. pause/stop have no action-specific fields: put domain field, condition and next verification step inside reason, not extra argument keys.',
    'INVALID_SEARCH_KIND': 'kinds items must come from the categories offered in this saved tool schema and, when present, knowledge_inventory. Use research_paper, not paper, only when offered; omit optional kinds to search all indexed categories.',
    'INVALID_SEARCH_LIMIT': 'search limit must be an integer from 1 through 4 inclusive. The returned value was rejected; choose a valid value or omit this optional field to use the existing default of 4.',
    'INVALID_SOURCE_SELECTION': 'Select an exact document_id and its matching source_sha256 from source_catalogue or retrieved references. Scoped search requires both fields together; omitting both searches the library. Never supply paths or substitute a title.',
    'INVALID_SOURCE_RANGE': 'read_source start_chunk must be an existing zero-based chunk offset and count must be1 or2. Use recorded outline chunk_offset or window.next_chunk; start0 reads initial chunks and exposes navigation. Do not guess a page or line number as a chunk offset.',
    'DUPLICATE_READ': 'That exact window was just read. Use its already visible original quotes or choose a useful different range. A later reread can refresh context but does not create new evidence identity or scientific progress.',
    'INVALID_FEATURES': 'features must use the allowed feature IDs in research_context.data.features; follow the offered item count and do not invent display labels.',
    'ACTION_NOT_AVAILABLE': 'Select only a function offered in this saved request; terminal slots permit only the offered control tools.',
    'STALE_OBSERVATION': 'Copy the current observation_sha256 exactly and use the latest feedback.',
    'INVALID_EVIDENCE': 'Cite distinct source and action IDs present in the current observation; experiments require retrieved sources and the latest experiment ID.',
    'LATEST_FEEDBACK_REQUIRED': 'Include the exact feedback_binding.action_id in evidence_action_ids for this numerical action or propose_control. It may identify residuals/correlation rather than fit. Older fit/inspection IDs alone are insufficient; the returned arguments were rejected, not repaired.',
    'DUPLICATE_SEARCH': 'That effective query, source scope, kind set and limit already ran; choose a useful different request, read the fixed source or use a justified control action.',
    'DUPLICATE_RECIPE': 'That recipe already ran; use its real feedback to choose another useful action.',
    'DUPLICATE_ANALYSIS': 'That diagnostic already ran; use its saved result instead of repeating it.',
    'INVALID_REVIEW': 'Review a permitted field or condition using retrieved citations; provide a bounded question, finding, status and next_check without claiming scientific approval.',
    'INVALID_REVIEW_STATUS': 'status must be exactly supported, unresolved, or conflicting. Partial knowledge still uses unresolved; describe what is known and unknown in finding and next_check, not as a new status or a sentence in status.',
    'DUPLICATE_REVIEW': 'That exact interpretation and evidence were already recorded; identify a useful new check or use the existing review.',
    'INVALID_DECISION': 'Use one offered native function with the current observation and correctly typed arguments.',
    'INVALID_REQUEST': 'Follow the offered parameter fields and bounds; paths, code, data and evaluator are fixed.',
    'BUDGET_EXHAUSTED': 'Respect the remaining action and fit budgets; use an offered control action when work is no longer available.',
    'NOT_ACTIVE': 'This study is paused or stopped; no further work is available.',
    'UNRECOGNIZED_ERROR': 'The previous proposal was rejected. Recheck the current observation and offered tool contract without guessing new permissions.',
}


def _require(condition, code, message):
    if not condition: raise ResearchError(code, message)


def _object_schema(value):
    _require(type(value) is dict and value.get('type') == 'object' and type(value.get('properties')) is dict
             and value.get('additionalProperties') is False
             and len(value['properties']) <= 32 and all(type(k) is str and _NAME.fullmatch(k) is not None for k in value['properties'])
             and all(type(v) is dict for v in value['properties'].values()), 'INVALID_TOOL_SCHEMA', 'bounded object properties required')
    required = value.get('required', [])
    _require(type(required) is list and all(type(k) is str for k in required) and len(required) == len(set(required))
             and set(required) <= set(value['properties']), 'INVALID_TOOL_SCHEMA', 'valid required fields required')
    return value['properties'], required


def _field_description(value):
    """Bounded text hints for renderers that omit scalar schema constraints."""
    result = copy.deepcopy(value)
    description = result.get('description', '')
    _require(type(description) is str and len(description) <= 1000, 'INVALID_TOOL_SCHEMA', 'bounded field description required')
    notes = []
    choices = result.get('enum')
    if type(choices) is list and 1 <= len(choices) <= 12 and all(type(v) in (str, int, float, bool, type(None)) for v in choices):
        encoded = canonical(choices)
        if len(encoded) <= 384: notes.append('Allowed values: '+encoded+'.')
    items = result.get('items')
    item_choices = items.get('enum') if type(items) is dict else None
    if type(item_choices) is list and 1 <= len(item_choices) <= 12:
        encoded = canonical(item_choices)
        if len(encoded) <= 384: notes.append('Allowed array items: '+encoded+'.')
    for key in ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'minLength', 'maxLength', 'minItems', 'maxItems'):
        if key in result:
            value = result[key]
            _require(type(value) in (int, float) and math.isfinite(value), 'INVALID_TOOL_SCHEMA', 'finite field bounds required')
            notes.append(key+'='+canonical(value)+'.')
    if notes: result['description'] = ' '.join([description, *notes]).strip()
    return result


def tools_from_schema(schema):
    """Flatten action parameters into top-level native function arguments."""
    _require(type(schema) is dict and type(schema.get('oneOf')) is list and 1 <= len(schema['oneOf']) <= 16,
             'INVALID_TOOL_SCHEMA', 'bounded action variants required')
    tools, names = [], set()
    for variant in schema['oneOf']:
        _require(type(variant) is dict and variant.get('type') == 'object'
                 and type(variant.get('properties')) is dict and set(variant['properties']) == ARGUMENT_FIELDS | {'action', 'parameters'}
                 and type(variant.get('required')) is list and len(variant['required']) == 6
                 and all(type(key) is str for key in variant['required']) and set(variant['required']) == ARGUMENT_FIELDS | {'action', 'parameters'},
                 'INVALID_TOOL_SCHEMA', 'each action requires the exact common envelope')
        action = variant['properties']['action']
        _require(type(action) is dict and action.get('type') == 'string' and type(action.get('enum')) is list
                 and len(action['enum']) == 1 and type(action['enum'][0]) is str and _NAME.fullmatch(action['enum'][0]) is not None,
                 'INVALID_TOOL_SCHEMA', 'one named action per variant required')
        name = action['enum'][0]
        _require(name not in names, 'INVALID_TOOL_SCHEMA', 'duplicate tool names are ambiguous')
        names.add(name)
        action_properties, action_required = _object_schema(variant['properties']['parameters'])
        _require(not set(action_properties) & _RESERVED, 'INVALID_TOOL_SCHEMA', 'action fields collide with the common or reserved envelope')
        parameters = {'type': 'object', 'properties': {
            key: copy.deepcopy(value) for key, value in variant['properties'].items() if key in ARGUMENT_FIELDS},
            'required': [key for key in variant['required'] if key in ARGUMENT_FIELDS]+list(action_required), 'additionalProperties': False}
        try: parameters['properties'].update({key: _field_description(value) for key, value in action_properties.items()})
        except (ValueError, TypeError, RecursionError, OverflowError):
            raise ResearchError('INVALID_TOOL_SCHEMA', 'action fields must be finite JSON') from None
        description = variant.get('description', f'Propose one bounded {name} research action. Supply common and action fields at top level, never a parameters bag. Paths, code and evaluator remain fixed.')
        _require(type(description) is str and 1 <= len(description) <= 2000, 'INVALID_TOOL_SCHEMA', 'bounded tool description required')
        try: canonical(parameters)
        except (ValueError, TypeError, RecursionError):
            raise ResearchError('INVALID_TOOL_SCHEMA', 'tool schema must be finite JSON') from None
        tools.append({'type': 'function', 'function': {'name': name, 'description': description, 'parameters': parameters}})
    return tools


def _plain_json(value, depth=0):
    if depth > 32: return False
    if type(value) is dict: return all(type(key) is str and _plain_json(item, depth+1) for key, item in value.items())
    if type(value) is list: return all(_plain_json(item, depth+1) for item in value)
    if type(value) is float: return math.isfinite(value)
    return value is None or type(value) in (str, int, bool)


def _typed(value, schema):
    types = schema.get('type')
    if types is None: return True
    types = types if type(types) is list else [types]
    matches = {'string': type(value) is str, 'integer': type(value) is int,
               'number': type(value) in (int, float), 'boolean': type(value) is bool,
               'array': type(value) is list, 'object': type(value) is dict, 'null': value is None}
    return all(type(t) is str and t in matches for t in types) and any(matches[t] for t in types)


def _contains_id(schema):
    """Only the one-ID membership shape emitted by our tools is supported."""
    if 'contains' not in schema: return None
    contains = schema['contains']
    _require(type(contains) is dict and set(contains) == {'enum'} and type(contains['enum']) is list
             and len(contains['enum']) == 1 and type(contains['enum'][0]) is str and 1 <= len(contains['enum'][0]) <= 160,
             'INVALID_TOOL_SCHEMA', 'contains must identify one exact required action ID')
    return contains['enum'][0]


def _constrained(value, schema, depth=0):
    """Validate the bounded keywords emitted by native_schema, without repair."""
    if depth > 8 or not _typed(value, schema): return False
    if 'enum' in schema and value not in schema['enum']: return False
    if type(value) is str:
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', float('inf')): return False
    elif type(value) is list:
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')): return False
        if 'items' in schema and not all(_constrained(item, schema['items'], depth+1) for item in value): return False
        if 'contains' in schema and _contains_id(schema) not in value: return False
    elif type(value) in (int, float):
        if value < schema.get('minimum', -float('inf')) or value > schema.get('maximum', float('inf')): return False
    return True


def parse_tool_decision(response, observation, request_id, body, *, decision_parser=None):
    """Use only one offered function name and its exact object arguments.

    Content/thinking never provide dispatch data. The original request/response,
    observation and nested argument dictionaries are left unchanged.
    """
    message = response.get('message') if type(response) is dict else None
    calls = message.get('tool_calls') if type(message) is dict else None
    _require(calls is not None and calls != [], 'MISSING_TOOL_CALL', 'one native tool call is required')
    _require(type(calls) is list, 'INVALID_TOOL_ARGUMENTS', 'tool_calls must be an array')
    _require(len(calls) == 1, 'MULTIPLE_TOOL_CALLS', 'only one native tool call may dispatch')
    call = calls[0]
    function = call.get('function') if type(call) is dict else None
    _require(type(function) is dict and type(function.get('name')) is str and call.get('type', 'function') == 'function',
             'INVALID_TOOL_ARGUMENTS', 'a native function call is required')
    tools = body.get('tools') if type(body) is dict else None
    _require(type(tools) is list and 1 <= len(tools) <= 16, 'INVALID_TOOL_SCHEMA', 'saved request tools are required')
    offered = {}
    for tool in tools:
        item = tool.get('function') if type(tool) is dict else None
        _require(type(item) is dict and tool.get('type') == 'function' and type(item.get('name')) is str
                 and _NAME.fullmatch(item['name']) is not None and item['name'] not in offered,
                 'INVALID_TOOL_SCHEMA', 'saved function names must be valid and unique')
        offered[item['name']] = item
    name, arguments = function['name'], function.get('arguments')
    _require(name in offered, 'ACTION_NOT_AVAILABLE', 'returned function was not offered in this saved request')
    schema = offered[name].get('parameters')
    properties, required = _object_schema(schema)
    required_feedback = None
    for key, field in properties.items():
        if 'contains' in field:
            required_feedback = _contains_id(field)
            _require(key == 'evidence_action_ids' and field.get('type') == 'array'
                     and required_feedback in field.get('items', {}).get('enum', []),
                     'INVALID_TOOL_SCHEMA', 'required feedback must be one permitted action ID')
    action_fields = set(properties)-ARGUMENT_FIELDS
    _require(ARGUMENT_FIELDS <= set(required) and not action_fields & _RESERVED and schema.get('additionalProperties') is False,
             'INVALID_TOOL_SCHEMA', 'saved tool must use the flat common/action contract')
    _require(type(arguments) is dict and set(required) <= set(arguments) <= set(properties)
             and type(arguments['observation_sha256']) is str and type(arguments['reason']) is str
             and all(type(arguments[key]) is list and all(type(item) is str for item in arguments[key])
                     for key in ('source_citation_ids', 'evidence_action_ids'))
             and _plain_json(arguments) and all(_typed(value, properties[key]) for key, value in arguments.items()),
             'INVALID_TOOL_ARGUMENTS', 'required and optional flat arguments must exactly follow the saved tool')
    for key, value in arguments.items():
        # Validate all other constraints first, independent of JSON key order.
        if not _constrained(value, {k: v for k, v in properties[key].items() if k != 'contains'}):
            code = ('STALE_OBSERVATION' if key == 'observation_sha256' else
                    'INVALID_EVIDENCE' if key in {'source_citation_ids','evidence_action_ids'} else
                    'INVALID_SOURCE_SELECTION' if key in {'document_id','source_sha256'} else
                    'INVALID_SOURCE_RANGE' if name == 'read_source' and key in {'start_chunk','count'} else
                    'INVALID_REVIEW_STATUS' if name == 'review_evidence' and key == 'status' else
                    'INVALID_REVIEW' if name == 'review_evidence' and key == 'field' else
                    'INVALID_SEARCH_KIND' if name == 'search' and key == 'kinds' else
                    'INVALID_SEARCH_LIMIT' if name == 'search' and key == 'limit' else
                    'INVALID_FEATURES' if name == 'fit' and key == 'features' else 'INVALID_TOOL_ARGUMENTS')
            raise ResearchError(code, 'native argument violates its saved constraints')
    _require(all(len(arguments[key]) == len(set(arguments[key])) for key in ('source_citation_ids', 'evidence_action_ids')),
             'INVALID_EVIDENCE', 'cite distinct source and action identifiers')
    _require(required_feedback is None or required_feedback in arguments['evidence_action_ids'],
             'LATEST_FEEDBACK_REQUIRED', 'native arguments omit the saved required numerical feedback ID')
    common = {key: arguments[key] for key in ARGUMENT_FIELDS}
    params = {key: value for key, value in arguments.items() if key in action_fields}
    parser = _decision if decision_parser is None else decision_parser
    _require(callable(parser), 'INVALID_TOOL_SCHEMA', 'trusted domain decision parser required')
    return parser(canonical({'action': name, **common, 'parameters': params}), observation, request_id)


def feedback_for_errors(errorcodes):
    """At most eight deduplicated static messages; never echo unknown strings."""
    _require(type(errorcodes) in (list, tuple), 'INVALID_REQUEST', 'error codes must be a sequence')
    feedback, seen = [], set()
    for value in errorcodes[-8:]:
        code = value if type(value) is str and value in _FEEDBACK else 'UNRECOGNIZED_ERROR'
        if code not in seen:
            seen.add(code)
            feedback.append({'code': code, 'message': _FEEDBACK[code]})
    return feedback
