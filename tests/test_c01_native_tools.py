"""Native envelope contract tests with synthetic C01 data, never model calls."""
import copy
import unittest

from autoresearch.c01_local_loop import native_schema
from autoresearch.c01_native_tools import ARGUMENT_FIELDS, feedback_for_errors, parse_tool_decision, tools_from_schema
from autoresearch.contracts import ResearchError, canonical
import test_c01_research as fixture


class NativeToolTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.study = self.base.study

    def envelope(self, action='search', parameters=None, **changes):
        state = self.study.observe()
        request = self.base.request(action, parameters if parameters is not None else {'query': 'C01 alloy'})
        arguments = {key: copy.deepcopy(request[key]) for key in ARGUMENT_FIELDS}
        arguments.update(copy.deepcopy(request['parameters']))
        arguments.update(changes)
        body = {'tools': tools_from_schema(native_schema(state))}
        response = {'message': {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'synthetic-tool-call', 'function': {'index': 0, 'name': action, 'arguments': arguments}}]}}
        return response, state, body

    def error(self, code, response, state, body):
        before = self.study.observe()
        snapshots = copy.deepcopy((response, state, body))
        with self.assertRaises(ResearchError) as error:
            parse_tool_decision(response, state, 'runner-owned-request', body)
        self.assertEqual(error.exception.code, code)
        self.assertEqual((response, state, body), snapshots)
        self.assertEqual(self.study.observe(), before)

    def test_converter_preserves_all_argument_constraints_and_does_not_mutate_schema(self):
        self.base.search()
        schema = native_schema(self.study.observe())
        before = copy.deepcopy(schema)
        tools = tools_from_schema(schema)
        self.assertEqual(len(tools), len(schema['oneOf']))
        for branch, tool in zip(schema['oneOf'], tools):
            self.assertEqual(tool['type'], 'function')
            self.assertEqual(tool['function']['name'], branch['properties']['action']['enum'][0])
            converted = tool['function']['parameters']
            action = branch['properties']['parameters']
            self.assertEqual(set(converted['properties']), ARGUMENT_FIELDS | set(action['properties']))
            self.assertEqual(converted['required'], [key for key in branch['required'] if key in ARGUMENT_FIELDS]+action.get('required', []))
            for key in ARGUMENT_FIELDS: self.assertEqual(converted['properties'][key], branch['properties'][key])
            for key, original in action['properties'].items():
                self.assertEqual({k: v for k, v in converted['properties'][key].items() if k != 'description'},
                                 {k: v for k, v in original.items() if k != 'description'})
                if 'description' in original: self.assertIn(original['description'], converted['properties'][key]['description'])
            self.assertNotIn('parameters', converted['properties'])
            self.assertFalse(converted['additionalProperties'])
        tools[0]['function']['parameters']['properties']['reason']['maxLength'] = 3
        self.assertEqual(schema, before)

    def test_latest_diagnostic_is_required_without_repair_and_other_evidence_guards_remain(self):
        self.base.search()
        params={'alpha':2,'features':list(self.study.observe()['data']['features']),
                'hypothesis':'Synthetic alternative','expected_effect':'Synthetic test only'}
        response,state,body=self.envelope('fit',params)
        first=next(t['function'] for t in body['tools'] if t['function']['name']=='fit')
        self.assertNotIn('contains',first['parameters']['properties']['evidence_action_ids'])
        self.assertEqual(parse_tool_decision(response,state,'first-fit-contract',body)['parameters'],params)
        fit=self.base.fit()['action']
        residual=self.study.apply(self.base.request('residuals',{'fit_action_id':fit['id']}))['action']
        response,state,body=self.envelope('fit',params)
        function=next(t['function'] for t in body['tools'] if t['function']['name']=='fit')
        self.assertEqual(function['parameters']['properties']['evidence_action_ids']['contains'],{'enum':[residual['id']]})
        valid=parse_tool_decision(response,state,'next-fit-contract',body)
        self.assertEqual(valid['evidence_action_ids'],[residual['id']])
        stale=copy.deepcopy(response)
        stale['message']['tool_calls'][0]['function']['arguments']['evidence_action_ids']=[fit['id']]
        self.error('LATEST_FEEDBACK_REQUIRED',stale,state,body)
        for ids in ([fit['id'],'unknown-id'],[residual['id'],residual['id']]):
            altered=copy.deepcopy(response)
            altered['message']['tool_calls'][0]['function']['arguments']['evidence_action_ids']=ids
            self.error('INVALID_EVIDENCE',altered,state,body)
        empty=copy.deepcopy(response)
        empty['message']['tool_calls'][0]['function']['arguments']['source_citation_ids']=[]
        self.error('INVALID_EVIDENCE',empty,state,body)
        both=copy.deepcopy(stale)
        arguments=both['message']['tool_calls'][0]['function']['arguments']
        arguments['source_citation_ids']=[]
        self.error('INVALID_EVIDENCE',both,state,body)
        both['message']['tool_calls'][0]['function']['arguments']={'source_citation_ids':[],**arguments}
        self.error('INVALID_EVIDENCE',both,state,body)
        self.assertIn('rejected, not repaired',feedback_for_errors(['LATEST_FEEDBACK_REQUIRED'])[0]['message'])

    def test_malformed_contains_constraints_fail_closed_as_saved_schema_errors(self):
        self.base.search();self.base.fit()
        response,state,body=self.envelope('correlation',{})
        for contains in ({},{'type':'string'},1,{'enum':[]},{'enum':['a','b']},{'enum':[1]}, {'enum':['not-a-known-id']}):
            malformed=copy.deepcopy(body)
            function=next(t['function'] for t in malformed['tools'] if t['function']['name']=='correlation')
            function['parameters']['properties']['evidence_action_ids']['contains']=contains
            self.error('INVALID_TOOL_SCHEMA',response,state,malformed)

    def test_pause_and_stop_details_belong_only_in_reason_not_extra_keys(self):
        for action in ('pause','stop'):
            response,state,body=self.envelope(action,{},reason='Synthetic condition; next check is a domain review.')
            function=next(t['function'] for t in body['tools'] if t['function']['name']==action)
            self.assertEqual(set(function['parameters']['properties']),ARGUMENT_FIELDS)
            self.assertNotIn('contains',function['parameters']['properties']['evidence_action_ids'])
            self.assertIn('inside reason',function['description'])
            self.assertEqual(parse_tool_decision(response,state,'control-contract',body)['parameters'],{})
            for extra in ('field','condition','next_check'):
                invalid=copy.deepcopy(response)
                invalid['message']['tool_calls'][0]['function']['arguments'][extra]='Synthetic'
                self.error('INVALID_TOOL_ARGUMENTS',invalid,state,body)

    def test_inspection_requires_only_common_fields_and_rejects_paths_or_data_edits(self):
        response, state, body = self.envelope('inspect_dataset', {})
        decision = parse_tool_decision(response, state, 'inspect-request', body)
        self.assertEqual(decision['action'], 'inspect_dataset')
        self.assertEqual(decision['parameters'], {})
        for key, value in [('path', '../input.csv'), ('samples', []), ('alpha', 1.0)]:
            altered = copy.deepcopy(response)
            altered['message']['tool_calls'][0]['function']['arguments'][key] = value
            self.error('INVALID_TOOL_ARGUMENTS', altered, state, body)
        terminal = {'tools': tools_from_schema(native_schema(state, terminal_only=True))}
        self.error('ACTION_NOT_AVAILABLE', response, state, terminal)

    def test_converter_is_generic_for_a_new_review_evidence_variant(self):
        branch = copy.deepcopy(native_schema(self.study.observe())['oneOf'][0])
        branch['properties']['action']['enum'] = ['review_evidence']
        branch['description'] = 'Read a known frozen citation and record a bounded interpretation.'
        branch['properties']['parameters'] = {'type': 'object', 'properties': {
            'citation_id': {'type': 'string', 'enum': ['c'*64]}}, 'required': ['citation_id'], 'additionalProperties': False}
        before = copy.deepcopy(branch)
        tool = tools_from_schema({'oneOf': [branch]})[0]
        self.assertEqual(tool['function']['name'], 'review_evidence')
        self.assertEqual(tool['function']['description'], branch['description'])
        self.assertEqual(tool['function']['parameters']['properties']['citation_id']['enum'], ['c'*64])
        self.assertIn('Allowed values:', tool['function']['parameters']['properties']['citation_id']['description'])
        self.assertEqual(branch, before)

    def test_control_proposal_and_review_use_saved_role_permissions_and_exact_evidence(self):
        self.base.search();fit=self.base.fit()['action']
        response,state,old_body=self.envelope('propose_control',{'decision':'pause'})
        self.error('ACTION_NOT_AVAILABLE',response,state,old_body)
        body={'tools':tools_from_schema(native_schema(state,review_controls=True))}
        decision=parse_tool_decision(response,state,'proposal-native',body)
        proposal=self.study.apply(decision)['action']
        self.assertEqual(self.study.observe()['status'],'active')
        request=self.base.control_review_request()
        response,state,old_body=self.envelope('review_evidence',request['parameters'],evidence_action_ids=request['evidence_action_ids'])
        self.error('INVALID_REVIEW',response,state,old_body)
        body={'tools':tools_from_schema(native_schema(state,review_controls=True))}
        valid=parse_tool_decision(response,state,'review-native',body)
        self.assertEqual(set(valid['evidence_action_ids']),{proposal['id'],fit['id']})
        changed=copy.deepcopy(response)
        changed['message']['tool_calls'][0]['function']['arguments']['evidence_action_ids']=[fit['id']]
        self.error('INVALID_CONTROL_REVIEW',changed,state,body)
        self.study.apply(valid)
        schema=native_schema(self.study.observe(),review_controls=True)
        review=next(v for v in schema['oneOf'] if v['properties']['action']['enum']==['review_evidence'])
        self.assertNotIn('control_rationale',review['properties']['parameters']['properties']['field']['enum'])

    def test_array_enum_values_are_visible_without_changing_the_saved_constraints(self):
        self.base.search();tools=tools_from_schema(native_schema(self.study.observe()))
        search=next(t for t in tools if t['function']['name']=='search')['function']['parameters']['properties']
        fit=next(t for t in tools if t['function']['name']=='fit')['function']['parameters']['properties']
        self.assertIn('research_paper',search['kinds']['description'])
        self.assertIn('water_contact_angle_deg',fit['features']['description'])
        self.assertEqual(search['kinds']['items']['enum'],sorted(__import__('autoresearch.knowledge',fromlist=['KINDS']).KINDS))

    def test_invalid_array_enums_rejected_with_actionable_feedback_without_remapping(self):
        response,state,body=self.envelope(parameters={'query':'ALP','kinds':['paper']})
        self.error('INVALID_SEARCH_KIND',response,state,body)
        message=feedback_for_errors(['INVALID_SEARCH_KIND'])[0]['message']
        self.assertIn('research_paper',message);self.assertIn('not paper',message)
        self.base.search()
        params={'alpha':1,'features':['not_a_feature'],'hypothesis':'Synthetic','expected_effect':'Synthetic'}
        response,state,body=self.envelope('fit',params)
        self.error('INVALID_FEATURES',response,state,body)

    def test_converter_rejects_ambiguous_names_or_incomplete_common_contracts(self):
        original = native_schema(self.study.observe())
        for change in ('duplicate', 'name', 'fields', 'required', 'enum'):
            value = copy.deepcopy(original)
            if change == 'duplicate': value['oneOf'].append(copy.deepcopy(value['oneOf'][0]))
            if change == 'name': value['oneOf'][0]['properties']['action']['enum'] = ['../arbitrary-path']
            if change == 'fields': value['oneOf'][0]['properties']['request_id'] = {'type': 'string'}
            if change == 'required': value['oneOf'][0]['required'].remove('reason')
            if change == 'enum': value['oneOf'][0]['properties']['action']['enum'] = ['pause', 'stop']
            before = copy.deepcopy(value)
            with self.subTest(change=change), self.assertRaises(ResearchError) as error:
                tools_from_schema(value)
            self.assertEqual(error.exception.code, 'INVALID_TOOL_SCHEMA')
            self.assertEqual(value, before)

    def test_flat_fields_cannot_collide_with_common_or_runner_owned_names(self):
        for field in sorted(ARGUMENT_FIELDS | {'action', 'request_id', 'parameters'}):
            schema = native_schema(self.study.observe())
            schema['oneOf'][0]['properties']['parameters']['properties'][field] = {'type': 'string'}
            with self.subTest(field=field), self.assertRaises(ResearchError) as error:
                tools_from_schema(schema)
            self.assertEqual(error.exception.code, 'INVALID_TOOL_SCHEMA')

    def test_scalar_enum_and_bounds_are_in_bounded_descriptions_without_repeating_id_arrays(self):
        self.base.search()
        tools = {tool['function']['name']: tool['function']['parameters']['properties']
                 for tool in tools_from_schema(native_schema(self.study.observe()))}
        status = tools['review_evidence']['status']
        self.assertEqual(status['enum'], ['supported', 'unresolved', 'conflicting'])
        self.assertIn('Allowed values: ["supported","unresolved","conflicting"]', status['description'])
        self.assertIn('maximum=10000', tools['fit']['alpha']['description'])
        self.assertIn('maxLength=1000', tools['review_evidence']['finding']['description'])
        self.assertIn('maxItems=4', tools['fit']['features']['description'])
        citation = self.study.observe()['citations'][0]['citation_id']
        self.assertNotIn(citation, tools['fit']['source_citation_ids'].get('description', ''))
        branch = copy.deepcopy(native_schema(self.study.observe())['oneOf'][0])
        branch['properties']['parameters'] = {'type': 'object', 'additionalProperties': False,
            'properties': {'citation_id': {'type': 'string', 'enum': [str(i).zfill(64) for i in range(5000)]}}, 'required': ['citation_id']}
        field = tools_from_schema({'oneOf': [branch]})[0]['function']['parameters']['properties']['citation_id']
        self.assertEqual(len(field['enum']), 5000)
        self.assertLess(len(field.get('description', '')), 1000)
        self.assertNotIn(str(4999).zfill(64), field.get('description', ''))

    def test_one_native_search_binds_current_observation_and_runner_request_without_execution(self):
        response, state, body = self.envelope()
        original = copy.deepcopy((response, state, body))
        result = parse_tool_decision(response, state, 'runner-request-1', body)
        flat = response['message']['tool_calls'][0]['function']['arguments']
        self.assertEqual(result, {'action': 'search', 'request_id': 'runner-request-1',
            **{key: flat[key] for key in ARGUMENT_FIELDS}, 'parameters': {'query': 'C01 alloy'}})
        self.assertEqual((response, state, body), original)
        self.assertEqual(self.study.observe(), state)

    def test_optional_search_fields_roundtrip_without_inserting_defaults_or_dropping_values(self):
        for parameters in ({'query': 'C01 alloy'}, {'query': 'C01 alloy', 'kinds': ['reuse_note'], 'limit': 1}):
            response, state, body = self.envelope(parameters=parameters)
            result = parse_tool_decision(response, state, 'runner-search', body)
            self.assertEqual(result['parameters'], parameters)
            self.assertEqual(set(response['message']['tool_calls'][0]['function']['arguments']), ARGUMENT_FIELDS | set(parameters))
        response, state, body = self.envelope(parameters={'query': 'C01 alloy', 'limit': True})
        self.error('INVALID_TOOL_ARGUMENTS', response, state, body)

    def test_flat_review_roundtrip_and_missing_fields_are_never_guessed(self):
        self.base.search()
        parameters = {'field': 'alp_norm_d21', 'question': 'What is established?',
                      'finding': 'The synthetic source does not resolve this assay question.',
                      'status': 'unresolved', 'next_check': 'Read the primary assay methods.'}
        response, state, body = self.envelope('review_evidence', parameters)
        result = parse_tool_decision(response, state, 'runner-review', body)
        self.assertEqual(result['parameters'], parameters)
        self.assertEqual(set(response['message']['tool_calls'][0]['function']['arguments']), ARGUMENT_FIELDS | set(parameters))
        for field in ('finding', 'status', 'next_check'):
            missing = copy.deepcopy(response)
            del missing['message']['tool_calls'][0]['function']['arguments'][field]
            self.error('INVALID_TOOL_ARGUMENTS', missing, state, body)
        invalid_status = copy.deepcopy(response)
        invalid_status['message']['tool_calls'][0]['function']['arguments']['status'] = 'partial'
        self.error('INVALID_REVIEW_STATUS', invalid_status, state, body)

    def test_old_nested_arguments_and_old_saved_tool_schema_are_explicitly_rejected(self):
        response, state, body = self.envelope()
        nested = copy.deepcopy(response)
        args = nested['message']['tool_calls'][0]['function']['arguments']
        args['parameters'] = {'query': args.pop('query')}
        self.error('INVALID_TOOL_ARGUMENTS', nested, state, body)
        old_body = copy.deepcopy(body)
        tool = next(tool for tool in old_body['tools'] if tool['function']['name'] == 'search')
        schema = tool['function']['parameters']
        del schema['properties']['query']
        schema['required'].remove('query')
        schema['properties']['parameters'] = {'type': 'object', 'properties': {'query': {'type': 'string'}},
            'required': ['query'], 'additionalProperties': False}
        schema['required'].append('parameters')
        self.error('INVALID_TOOL_SCHEMA', nested, state, old_body)

    def test_recovery_uses_saved_required_and_optional_fields_not_a_regenerated_schema(self):
        from unittest.mock import patch
        response, state, body = self.envelope(parameters={'query': 'C01 alloy', 'limit': 2})
        saved = copy.deepcopy(body)
        schema = next(tool for tool in saved['tools'] if tool['function']['name'] == 'search')['function']['parameters']
        schema['required'].append('limit')
        with patch('autoresearch.c01_native_tools.tools_from_schema', side_effect=AssertionError('saved scope must not be regenerated')):
            result = parse_tool_decision(response, state, 'recovered-search', saved)
        self.assertEqual(result['parameters'], {'query': 'C01 alloy', 'limit': 2})
        missing = copy.deepcopy(response)
        del missing['message']['tool_calls'][0]['function']['arguments']['limit']
        self.error('INVALID_TOOL_ARGUMENTS', missing, state, saved)
        del schema['properties']['limit']
        schema['required'].remove('limit')
        self.error('INVALID_TOOL_ARGUMENTS', response, state, saved)

    def test_function_name_supplies_action_and_text_content_cannot_override_it(self):
        response, state, body = self.envelope('pause', parameters={})
        response['message']['content'] = canonical({'action': 'fit', 'request_id': 'model-owned-request', 'parameters': {'alpha': .001}})
        response['message']['thinking'] = 'Untrusted alternative action: fit.'
        result = parse_tool_decision(response, state, 'runner-owned-request', body)
        self.assertEqual(result['action'], 'pause')
        self.assertEqual(result['parameters'], {})
        self.assertEqual(result['request_id'], 'runner-owned-request')
        response['message']['tool_calls'][0]['type'] = 'function'  # Optional official wrapper metadata.
        self.assertEqual(parse_tool_decision(response, state, 'runner-owned-request', body), result)

    def test_text_json_never_falls_back_when_native_call_is_missing(self):
        response, state, body = self.envelope()
        response['message']['content'] = canonical({'action': 'search', **response['message']['tool_calls'][0]['function']['arguments']})
        for absent in ('missing', None, []):
            value = copy.deepcopy(response)
            if absent == 'missing': del value['message']['tool_calls']
            else: value['message']['tool_calls'] = absent
            self.error('MISSING_TOOL_CALL', value, state, body)

    def test_multiple_calls_are_rejected_without_selecting_the_first_valid_call(self):
        response, state, body = self.envelope()
        response['message']['tool_calls'].append({'function': {'name': 'arbitrary_code', 'arguments': {'path': '../private'}}})
        self.error('MULTIPLE_TOOL_CALLS', response, state, body)

    def test_unoffered_name_and_terminal_slot_cannot_be_bypassed(self):
        response, state, body = self.envelope()
        response['message']['tool_calls'][0]['function']['name'] = 'arbitrary_code'
        self.error('ACTION_NOT_AVAILABLE', response, state, body)
        response['message']['tool_calls'][0]['function']['name'] = 'search'
        terminal = {'tools': tools_from_schema(native_schema(state, terminal_only=True))}
        self.error('ACTION_NOT_AVAILABLE', response, state, terminal)

    def test_arguments_must_be_an_object_with_exact_common_fields_and_strict_types(self):
        response, state, body = self.envelope()
        original = response['message']['tool_calls'][0]['function']['arguments']
        invalid = [canonical(original), list(original.items()), None,
                   {key: value for key, value in original.items() if key != 'reason'},
                   {**original, 'action': 'pause'}, {**original, 'request_id': 'model-selected'},
                   {**original, 'reason': 123}, {**original, 'observation_sha256': True},
                   {**original, 'parameters': []}, {**original, 'source_citation_ids': 'not-a-list'},
                   {**original, 'evidence_action_ids': [True]}, {**original, 'parameters': {3: 'no key coercion'}},
                   {**original, 'query': 123}, {**original, 'arbitrary_field': 'not offered'}]
        for arguments in invalid:
            value = copy.deepcopy(response)
            value['message']['tool_calls'][0]['function']['arguments'] = arguments
            with self.subTest(arguments=arguments): self.error('INVALID_TOOL_ARGUMENTS', value, state, body)
        value = copy.deepcopy(response)
        value['message']['tool_calls'] = {'function': {}}
        self.error('INVALID_TOOL_ARGUMENTS', value, state, body)

    def test_stale_observation_and_unknown_source_or_action_ids_use_original_strict_validation(self):
        response, state, body = self.envelope()
        self.base.search()
        self.error('STALE_OBSERVATION', response, self.study.observe(), body)
        for field, values in (('source_citation_ids', ['a'*64]), ('evidence_action_ids', ['unknown-action'])):
            response, current, body = self.envelope(**{field: values})
            self.error('INVALID_EVIDENCE', response, current, body)
        response, current, body = self.envelope(source_citation_ids=[self.study.observe()['citations'][0]['citation_id']]*2)
        self.error('INVALID_EVIDENCE', response, current, body)

    def test_fit_keeps_real_citation_recipe_and_latest_experiment_requirements(self):
        self.base.search()
        recipe = {'alpha': 1, 'features': list(self.study.observe()['data']['features']),
                  'hypothesis': 'Synthetic contract check.', 'expected_effect': 'Compare saved numeric feedback.'}
        response, state, body = self.envelope('fit', recipe)
        result = parse_tool_decision(response, state, 'runner-fit', body)
        self.assertEqual(result['parameters'], recipe)
        self.assertEqual(result['source_citation_ids'], [state['citations'][0]['citation_id']])
        self.base.fit()
        response, state, body = self.envelope('fit', {**recipe, 'alpha': 2}, evidence_action_ids=[])
        self.error('INVALID_EVIDENCE', response, state, body)
        response, state, body = self.envelope('fit', {**recipe, 'alpha': 2})
        result = parse_tool_decision(response, state, 'runner-fit-2', body)
        self.assertEqual(result['evidence_action_ids'], [state['actions'][-1]['id']])

    def test_feedback_is_static_bounded_and_never_echoes_untrusted_error_strings(self):
        errors = ['MISSING_TOOL_CALL', 'MULTIPLE_TOOL_CALLS', 'MISSING_TOOL_CALL',
                  'DUPLICATE_SEARCH', 'PRIVATE_SOURCE_INSTRUCTION <script>', {'secret': 'PRIVATE_SOURCE_INSTRUCTION'}]
        before = copy.deepcopy(errors)
        feedback = feedback_for_errors(errors)
        self.assertEqual([entry['code'] for entry in feedback],
                         ['MISSING_TOOL_CALL', 'MULTIPLE_TOOL_CALLS', 'DUPLICATE_SEARCH', 'UNRECOGNIZED_ERROR'])
        self.assertNotIn('PRIVATE_SOURCE_INSTRUCTION', canonical(feedback))
        self.assertEqual(feedback_for_errors(errors), feedback)
        feedback[0]['message'] = 'changed by caller'
        self.assertNotEqual(feedback_for_errors(errors), feedback)
        self.assertEqual(errors, before)
        self.assertEqual(feedback_for_errors([]), [])
        self.assertLessEqual(len(feedback_for_errors(['UNKNOWN']*100)), 8)

    def test_source_reader_is_available_before_search_and_keeps_exact_selected_pair_and_saved_bounds(self):
        card=self.study.observe()['source_catalogue']['documents'][0]
        params={key:card[key] for key in ('document_id','source_sha256')}
        params.update(start_chunk=0,count=1)
        response,state,body=self.envelope('read_source',params)
        decision=parse_tool_decision(response,state,'runner-owned-read',body)
        self.assertEqual(decision['parameters'],params);self.assertEqual(decision['source_citation_ids'],[])
        for changes in ({'count':3},{'start_chunk':-1},{'start_chunk':4096}):
            response,state,body=self.envelope('read_source',{**params,**changes})
            self.error('INVALID_SOURCE_RANGE',response,state,body)
        for changes in ({'document_id':'../not-offered'},{'source_sha256':'f'*64}):
            response,state,body=self.envelope('read_source',{**params,**changes})
            self.error('INVALID_SOURCE_SELECTION',response,state,body)
        response,state,body=self.envelope(parameters={'query':'alloy','document_id':card['document_id']})
        self.error('INVALID_SOURCE_SELECTION',response,state,body)
        response,state,body=self.envelope('read_source',{**params,'count':2})
        saved=next(x['function'] for x in body['tools'] if x['function']['name']=='read_source')
        saved['parameters']['properties']['count']['maximum']=1
        self.error('INVALID_SOURCE_RANGE',response,state,body)
        terminal={'tools':tools_from_schema(native_schema(state,terminal_only=True))}
        self.error('ACTION_NOT_AVAILABLE',response,state,terminal)

    def test_search_limit_failure_is_specific_without_repairing_actual_returned_value(self):
        response,state,body=self.envelope('search',{'query':'ALP','limit':5})
        before=copy.deepcopy(response)
        self.error('INVALID_SEARCH_LIMIT',response,state,body)
        self.assertEqual(response,before)
        feedback=feedback_for_errors(['INVALID_SEARCH_LIMIT'])
        self.assertIn('1 through 4',feedback[0]['message'])
        self.assertIn('rejected',feedback[0]['message'])
        for limit in (1,4):
            response,state,body=self.envelope('search',{'query':'ALP','limit':limit})
            self.assertEqual(parse_tool_decision(response,state,'runner-valid-limit',body)['parameters']['limit'],limit)
        response,state,body=self.envelope('search',{'query':'ALP'})
        self.assertNotIn('limit',parse_tool_decision(response,state,'runner-omitted-limit',body)['parameters'])

    def test_invalid_review_status_feedback_names_exact_enum_and_partial_knowledge_handling(self):
        feedback = feedback_for_errors(['INVALID_REVIEW_STATUS'])
        self.assertEqual(feedback, [{'code': 'INVALID_REVIEW_STATUS', 'message':
            'status must be exactly supported, unresolved, or conflicting. Partial knowledge still uses unresolved; '
            'describe what is known and unknown in finding and next_check, not as a new status or a sentence in status.'}])
        self.assertEqual(feedback_for_errors(['INVALID_REVIEW_STATUS', 'partial', 'INVALID_REVIEW_STATUS']),
                         feedback + feedback_for_errors(['unknown-status']))


if __name__ == '__main__': unittest.main()
