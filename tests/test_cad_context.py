"""Geometry transport preserves complete native records and evidence ownership."""
from copy import deepcopy
import json

from bigbrain.cad_context import decision_observations, geometry_records


def unpack(value):
    if isinstance(value,list):
        return value
    records = [None]*value['count']
    for group in value['groups']:
        for position,row in zip(group['positions'],group['rows']):
            records[position] = dict(zip(group['columns'],row))
    return records


def test_geometry_records_roundtrip_mixed_shapes_and_exact_values():
    records = [{'index':i,'name':f'F{i}:side','point':[i,1.000000000000003,-1e-12],
                'cylinder':{'radius':105.0,'axis':[0,0,1]}} for i in range(50)]
    records.insert(7,{'index':90,'name':'plane','plane_normal':[1,0,0],'warning':None})
    records.insert(9,{'index':91,'name':'plane','plane_normal':[1,0,0]})
    before = deepcopy(records)
    packed = geometry_records(records)
    assert unpack(packed) == before
    assert records == before
    assert len(json.dumps(packed)) < len(json.dumps(records))


def test_small_records_keep_their_simple_representation():
    assert geometry_records([]) == []
    assert geometry_records([{'a':1}]) == [{'a':1}]


def test_observation_encoding_is_detached_and_keeps_revision_identity():
    edges = [{'index':i,'name':f'E{i}','start':[0,0,i],'end':[0,1,i]} for i in range(30)]
    observed = {'body_topology:B':{'checkpoint':'checkpoint','result':{'body':'B','edges':edges}},
        'precise_geometry:':{'checkpoint':'checkpoint','result':{'geometry':{'source_sha256':'hash'},
            'bodies':{'B':{'body':'B','edges':edges,'volume_mm3':42.000000000001}}}}}
    before = deepcopy(observed)
    packed = decision_observations(observed)
    assert observed == before
    assert unpack(packed['body_topology:B']['result']['edges']) == edges
    precise = packed['precise_geometry:']['result']
    assert unpack(precise['bodies']['B']['edges']) == edges
    assert precise['geometry']['source_sha256'] == 'hash'
    assert precise['bodies']['B']['volume_mm3'] == 42.000000000001


def test_design_parameter_reference_requires_exact_equality():
    params = [{'name':'radius','value':260.00000000000006}]
    observed = {'inspect_design:':{'checkpoint':'a','result':{'params':params}}}
    packed = decision_observations(observed,{'params':deepcopy(params)})
    assert packed['inspect_design:']['result']['params'] == {'$ref':'#/current_design/params'}
    assert observed['inspect_design:']['result']['params'] == params
    different = decision_observations(observed,{'params':[{'name':'radius','value':260}]})
    assert different['inspect_design:']['result']['params'] == params


def test_nested_sketch_observations_roundtrip_without_omitting_constraints():
    observed = {'inspect_design:':{'checkpoint':'a','result':{'sketches':[
        {'name':f'S{i}','plane':{'origin':[0,0,i]},'dof':0,
         'curves':[{'id':f'c{j}','radius':30.000000000000007,'fixed':False} for j in range(20)],
         'constraints':[{'id':f'k{j}','type':'diameter','expression':'diameter','value':60.000000000000014}
                        for j in range(20)]} for i in range(3)]}}}
    def decode(value):
        if isinstance(value,dict):
            if value.get('encoding') == 'columnar-records-v1':
                return decode(unpack(value))
            return {key:decode(item) for key,item in value.items()}
        if isinstance(value,list):
            return [decode(item) for item in value]
        return value
    assert decode(decision_observations(observed)) == observed
