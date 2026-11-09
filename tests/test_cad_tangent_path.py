"""Driving dimensions and observed curve identities on an editable pipe path."""
import pytest

from bigbrain.solidcraft import SolidCraftSession


@pytest.mark.asyncio
@pytest.mark.parametrize('radius', [30, 260])
async def test_native_dimensioned_tangent_path_and_radius_edit(tmp_path, cad_native_engine, radius):
    async with SolidCraftSession(tmp_path, executable=cad_native_engine) as session:
        await session.batch([
            {'command':'parameters.change','params':{'name':'bend','expression':f'{radius} mm'}},
            {'command':'parameters.change','params':{'name':'lead','expression':'150 mm'}},
            {'command':'sketch.create','params':{'plane':'XZ','name':'Bore_path'}},
            {'command':'sketch.draw.dimensioned','params':{'command':'sketch.line',
                'params':{'points':[[0,2],[0,-150]]},
                'dimensions':{'length':'lead+2'},'as_drawn':True,'locate':True}},
            {'command':'sketch.draw.dimensioned','params':{'command':'sketch.arc.center_point',
                'params':{'center':[radius,-150],'start':'l1.end','sweep':90},
                'dimensions':{'radius':'bend','sweep':'90 deg'}}},
            {'command':'sketch.constraint.tangent','params':{'a':'l1','b':'a1'}},
            {'command':'sketch.draw.dimensioned','params':{'command':'sketch.line',
                'params':{'points':['a1.end',[radius+152,-150-radius]]},
                'dimensions':{'length':'lead+2'},'as_drawn':True}},
            {'command':'sketch.finish','params':{}},
        ])
        for bend, lead in [(radius, 150), (radius+6, 150), (radius+6, 160)]:
            await session.tool('set_parameter', {'name':'bend','value':f'{bend} mm'})
            await session.tool('set_parameter', {'name':'lead','value':f'{lead} mm'})
            design = await session.tool('inspect_design')
            sketch = design['sketches'][0]
            assert sketch['dof'] == 0 and sketch['fully_constrained']
            assert not sketch['failing']
            curves = [curve for curve in sketch['curves'] if not curve.get('construction')]
            assert [curve['type'] for curve in curves] == ['line','arc','line']
            assert not any(curve['fixed'] for curve in curves)
            assert curves[1]['radius'] == pytest.approx(bend)
            for first, second in zip(curves, curves[1:]):
                assert first['end_at'] == pytest.approx(second['start_at'])
            assert curves[-1]['end_at'] == pytest.approx([bend+lead+2,-lead-bend])
            assert sketch['plane']['y_dir'] == [0,0,-1]
            assert not any(item.get('error') or item.get('warning') for item in design['timeline'])
