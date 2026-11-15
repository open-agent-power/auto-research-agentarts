"""Pure synthetic quality-condition checks; no Project, tool, model or data I/O."""
import copy
import itertools
import math
import unittest

from autoresearch.contracts import ResearchError
from autoresearch import tabular_quality_conditions as conditions


def count(field, operator='eq', value=0, *, column=None):
    item = {'field':field, 'operator':operator, 'value':value}
    if column is not None:
        item['column'] = column
    return item


def registration(*items):
    return {'schema_version':'tabular-quality-conditions-v1', 'conditions':list(items)}


def profile():
    return {'rows':8, 'columns':3, 'exact_duplicate_rows':0,
            'key_columns':{'complete_rows':8,'incomplete_rows':0,'duplicate_groups':0,'duplicate_rows':0,'conflict_groups':0},
            'group_columns':{'group_count':2,'singletons':0,'repeated_groups':2,'rows_in_repeated_groups':8,
                             'min_group_size':3,'max_group_size':5,'incomplete_group_rows':0},
            'numeric_columns':[{'name':'reading','counts':{'finite':8,'zero':1,'empty':0,
                'declared_missing':0,'invalid_numeric':0,'nonfinite':0}}], 'flags':[]}


class QualityConditionsTests(unittest.TestCase):
    def evaluate(self, terms, p=None, declared=None):
        return conditions.evaluate_conditions(registration(*terms), profile() if p is None else p,
                                              numeric_columns=['reading'] if declared is None else declared)

    def invalid(self, reg, names=None):
        with self.assertRaises(ResearchError) as error:
            conditions.validate_conditions(reg, numeric_columns=['reading'] if names is None else names)
        self.assertEqual(error.exception.code, 'INVALID_REQUEST')

    def test_valid_complete_gate_and_known_zero(self):
        terms=[count('rows','eq',8),count('columns','eq',3),count('exact_duplicate_rows'),
               count('key.incomplete_rows'),count('key.duplicate_rows'),count('key.conflict_groups'),
               count('group.incomplete_group_rows'),count('group.group_count','eq',2),
               count('group.min_group_size','gte',3),count('numeric.finite','eq',{'ref':'rows'},column='reading'),
               count('numeric.empty',column='reading'),count('numeric.declared_missing',column='reading'),
               count('numeric.invalid_numeric',column='reading'),count('numeric.nonfinite',column='reading'),
               {'field':'flags','operator':'empty'}]
        original, reg = profile(), registration(*terms)
        saved_original, saved_reg = copy.deepcopy(original), copy.deepcopy(reg)
        result=conditions.evaluate_conditions(reg,original,numeric_columns=['reading'])
        self.assertEqual(result['outcome'],'condition_met')
        self.assertIs(result['scientific_validation'],False)
        self.assertEqual(result['items'][2]['actual'],0)
        self.assertTrue(all(item['outcome']=='condition_met' for item in result['items']))
        self.assertEqual(original,saved_original); self.assertEqual(reg,saved_reg)
        clone=conditions.validate_conditions(reg,numeric_columns=['reading'])
        clone['conditions'][0]['value']=99
        self.assertEqual(reg,saved_reg)

    def test_false_known_zero_and_all_comparisons(self):
        for op,target,expected in [('eq',8,'condition_met'),('gt',8,'condition_not_met'),
                                   ('gte',8,'condition_met'),('lt',8,'condition_not_met'),
                                   ('lte',8,'condition_met')]:
            with self.subTest(operator=op):
                self.assertEqual(self.evaluate([count('rows',op,target)])['outcome'],expected)
        self.assertEqual(self.evaluate([count('exact_duplicate_rows','gt',0)])['outcome'],'condition_not_met')
        self.assertEqual(self.evaluate([{'field':'flags','operator':'nonempty'}])['outcome'],'condition_not_met')

    def test_known_missing_group_versus_unavailable_minimum(self):
        p=profile();p['group_columns']={'group_count':0,'singletons':0,'repeated_groups':0,'rows_in_repeated_groups':0,
                                        'min_group_size':None,'max_group_size':None,'incomplete_group_rows':8}
        self.assertEqual(self.evaluate([count('group.group_count','gte',2)],p)['outcome'],'condition_not_met')
        result=self.evaluate([count('group.group_count','gte',2),count('group.min_group_size','gte',3)],p)
        self.assertEqual(result['outcome'],'unknown')
        self.assertEqual([x['outcome'] for x in result['items']],['condition_not_met','unknown'])
        del p['group_columns']['group_count']
        self.assertEqual(self.evaluate([count('group.group_count','gte',2)],p)['outcome'],'unknown')

    def test_false_does_not_hide_unknown_in_either_order(self):
        p=profile();del p['key_columns']['incomplete_rows']
        failed=count('rows','gt',8);unknown=count('key.incomplete_rows')
        for terms in ([failed,unknown],[unknown,failed]):
            with self.subTest(terms=terms):
                r=self.evaluate(terms,p)
                self.assertEqual(r['outcome'],'unknown')
                self.assertIn('condition_not_met',[v['outcome'] for v in r['items']])
                self.assertIn('unknown',[v['outcome'] for v in r['items']])

    def test_invalid_registration_schema_operators_and_paths(self):
        cases=[None,{}, {'schema_version':'bad','conditions':[count('rows')]},
               {'schema_version':conditions.SCHEMA,'conditions':[]},
               registration(*[count('rows','eq',i) for i in range(33)]),
               registration({'field':'rows','operator':'eq','value':0,'extra':1}),
               registration(count('rows','eval',0)), registration(count('rows.__class__','eq',0)),
               registration(count('zero','eq',0)), registration({'field':'flags','operator':'eq','value':0}),
               registration({'field':'flags','operator':'empty','value':0}),
               registration({'field':'flags','operator':'empty','column':'reading'}),
               registration(count('numeric.finite','eq',0)),
               registration(count('numeric.finite','eq',0,column='undeclared')),
               registration(count('rows','eq',0),count('rows','eq',0))]
        for reg in cases:
            with self.subTest(reg=reg):self.invalid(reg)
        for names in ([],['reading','reading'],[' padded'],[True],[''],['x'*257]):
            with self.subTest(names=names):self.invalid(registration(count('rows')),names)

    def test_operand_types_bounds_and_rows_reference_scope(self):
        for v in (True,False,1.0,-1,50001,math.nan,math.inf,'rows',{'ref':'rows','x':1},{'ref':'other'},[]):
            with self.subTest(value=v):self.invalid(registration(count('rows','eq',v)))
        for field in ('rows','columns','group.group_count','group.min_group_size','key.conflict_groups'):
            with self.subTest(field=field):self.invalid(registration(count(field,'eq',{'ref':'rows'})))
        for field in ('exact_duplicate_rows','key.incomplete_rows','key.duplicate_rows','group.incomplete_group_rows'):
            with self.subTest(field=field):
                self.assertEqual(self.evaluate([count(field,'lte',{'ref':'rows'})])['outcome'],'condition_met')
        self.assertEqual(self.evaluate([count('numeric.finite','eq',{'ref':'rows'},column='reading')])['outcome'],'condition_met')

    def test_malformed_profile_counts_become_unknown(self):
        for value in (None,True,False,-1,9,1.0,math.nan,math.inf,'0',[]):
            with self.subTest(value=value):
                p=profile();p['key_columns']['incomplete_rows']=value
                self.assertEqual(self.evaluate([count('key.incomplete_rows')],p)['outcome'],'unknown')
        for value in (True,-1,50001,1.0,math.nan,None):
            with self.subTest(rows=value):
                p=profile();p['rows']=value
                self.assertEqual(self.evaluate([count('numeric.finite','eq',{'ref':'rows'},column='reading')],p)['outcome'],'unknown')
        for value in (0,129,True,1.0,None):
            with self.subTest(columns=value):
                p=profile();p['columns']=value
                self.assertEqual(self.evaluate([count('columns','eq',3)],p)['outcome'],'unknown')
        self.assertEqual(self.evaluate([count('rows')],[])['outcome'],'unknown')

    def test_duplicate_rows_cannot_equal_a_nonempty_dataset(self):
        p={'rows':8,'exact_duplicate_rows':8}
        result=self.evaluate([count('rows','gt',8),count('exact_duplicate_rows','eq',8)],p)
        self.assertEqual(result['outcome'],'unknown')
        self.assertEqual([item['outcome'] for item in result['items']],['condition_not_met','unknown'])
        self.assertEqual(self.evaluate([count('exact_duplicate_rows','eq',0)],
                                       {'rows':0,'exact_duplicate_rows':0})['outcome'],'condition_met')

    def test_numeric_counts_partition_declared_columns_and_zero_subset(self):
        term=[count('numeric.finite','eq',{'ref':'rows'},column='reading')]
        mutations=[lambda p:p['numeric_columns'][0]['counts'].pop('empty'),
                   lambda p:p['numeric_columns'][0]['counts'].__setitem__('nonfinite',1),
                   lambda p:p['numeric_columns'][0]['counts'].__setitem__('zero',9),
                   lambda p:p['numeric_columns'][0]['counts'].__setitem__('zero',True),
                   lambda p:p['numeric_columns'][0]['counts'].__setitem__('finite',math.nan),
                   lambda p:p['numeric_columns'].append(copy.deepcopy(p['numeric_columns'][0])),
                   lambda p:p['numeric_columns'][0].__setitem__('name','other'),
                   lambda p:p.__setitem__('numeric_columns',[])]
        for mutate in mutations:
            p=profile();mutate(p)
            with self.subTest(profile=p):self.assertEqual(self.evaluate(term,p)['outcome'],'unknown')
        p=profile();p['numeric_columns'][0]['counts'].update(finite=7,zero=1,empty=1)
        self.assertEqual(self.evaluate(term,p)['outcome'],'condition_not_met')

    def test_flags_are_bounded_saved_list_not_exception_count(self):
        for value in (None,True,'bad',['dup','dup'],[''],[1],['x'*301],['x']*65,[[]]):
            with self.subTest(value=value):
                p=profile();p['flags']=value
                self.assertEqual(self.evaluate([{'field':'flags','operator':'empty'}],p)['outcome'],'unknown')
        p=profile();p['flags']=['flag-'+str(i) for i in range(64)]
        result=self.evaluate([{'field':'flags','operator':'nonempty'}],p)
        self.assertEqual(result['outcome'],'condition_met')
        self.assertEqual(result['items'][0]['actual'],'nonempty')

    def test_inconsistent_groups_are_unknown_even_with_known_failure(self):
        # Two groups each of minimum size 6 cannot fit in eight complete rows.
        p=profile();p['group_columns']['min_group_size']=6;p['group_columns']['max_group_size']=6
        result=self.evaluate([count('rows','gt',8),count('group.group_count','eq',2),
                              count('group.min_group_size','gte',6)],p)
        self.assertEqual(result['outcome'],'unknown')
        self.assertEqual([item['outcome'] for item in result['items']],
                         ['condition_not_met','unknown','unknown'])
        for key in ('singletons','repeated_groups','rows_in_repeated_groups','incomplete_group_rows',
                    'min_group_size','max_group_size'):
            p=profile();del p['group_columns'][key]
            with self.subTest(missing=key):
                self.assertEqual(self.evaluate([count('group.group_count','eq',2)],p)['outcome'],'unknown')
        for key,value in (('singletons',1),('repeated_groups',1),('rows_in_repeated_groups',7),
                          ('incomplete_group_rows',1),('min_group_size',1),('max_group_size',9)):
            p=profile();p['group_columns'][key]=value
            with self.subTest(key=key):
                self.assertEqual(self.evaluate([count('group.group_count','eq',2)],p)['outcome'],'unknown')

    def test_inconsistent_keys_are_unknown_even_with_known_failure(self):
        p=profile();p['key_columns'].update(complete_rows=2,incomplete_rows=6,duplicate_groups=1,duplicate_rows=3)
        result=self.evaluate([count('rows','gt',8),count('key.incomplete_rows','eq',6)],p)
        self.assertEqual(result['outcome'],'unknown')
        self.assertEqual([item['outcome'] for item in result['items']],['condition_not_met','unknown'])
        for key in ('complete_rows','incomplete_rows','duplicate_groups','duplicate_rows','conflict_groups'):
            p=profile();del p['key_columns'][key]
            with self.subTest(missing=key):
                self.assertEqual(self.evaluate([count('key.incomplete_rows')],p)['outcome'],'unknown')
        p=profile();p['key_columns'].update(duplicate_groups=1,duplicate_rows=1,conflict_groups=2)
        self.assertEqual(self.evaluate([count('key.duplicate_rows','eq',1)],p)['outcome'],'unknown')

    def test_valid_group_size_combinations_remain_known(self):
        for group_count in range(1,5):
            for sizes in itertools.product(range(1,6),repeat=group_count):
                p={'rows':sum(sizes)+1,'group_columns':{
                    'group_count':group_count,'singletons':sum(n==1 for n in sizes),
                    'repeated_groups':sum(n>1 for n in sizes),
                    'rows_in_repeated_groups':sum(n for n in sizes if n>1),
                    'incomplete_group_rows':1,'min_group_size':min(sizes),'max_group_size':max(sizes)}}
                result=self.evaluate([count('group.group_count','eq',group_count),
                                      count('group.min_group_size','eq',min(sizes))],p)
                self.assertEqual(result['outcome'],'condition_met',sizes)

    def test_key_group_checks_do_not_require_unrelated_profile_sections(self):
        p=profile();del p['numeric_columns'];del p['flags']
        self.assertEqual(self.evaluate([count('key.incomplete_rows'),count('group.group_count','eq',2)],p)['outcome'],
                         'condition_met')
        del p['key_columns']
        self.assertEqual(self.evaluate([count('group.group_count','eq',2)],p)['outcome'],'condition_met')
        p=profile();del p['group_columns']
        self.assertEqual(self.evaluate([count('key.incomplete_rows')],p)['outcome'],'condition_met')

    def test_unrelated_missing_fields_do_not_claim_profile_wide_integrity(self):
        p={'rows':8}
        self.assertEqual(self.evaluate([count('rows','eq',8)],p)['outcome'],'condition_met')
        self.assertEqual(self.evaluate([count('numeric.finite','eq',8,column='reading')],p)['outcome'],'unknown')

if __name__=='__main__':unittest.main()
