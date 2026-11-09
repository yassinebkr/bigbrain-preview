"""Native finishing commands accept names without predicted timeline identities."""
import pytest

from bigbrain.solidcraft import SolidCraftSession


@pytest.mark.asyncio
async def test_native_named_fillet_and_chamfer(cad_native_engine,tmp_path):
    async with SolidCraftSession(tmp_path,executable=cad_native_engine) as session:
        await session.batch([{'command':'solid.box','params':{
            'length':40,'width':30,'height':10,'body_name':'Block','name':'Envelope'}}])
        for command,params,name in [
            ('solid.fillet',{'radius':2,'edges':[[40,15,10]],'fit':'exact'},'Top_round'),
            ('solid.chamfer',{'distance':1,'edges':[[20,0,0]]},'Bottom_bevel')]:
            await session.tool('body_topology',{'body':'Block'})
            await session.batch([{'command':command,'params':{**params,'body':'Block','name':name}}])
            observed=await session.tool('inspect_design')
            assert observed['timeline'][-1]['name']==name
            assert not any(item.get('error') or item.get('warning') for item in observed['timeline'])
        await session.tool('save',{'path':str(tmp_path/'named.sc')})
        await session.tool('open',{'path':str(tmp_path/'named.sc')})
        observed=await session.tool('inspect_design')
        assert [item['name'] for item in observed['timeline']][-2:]==['Top_round','Bottom_bevel']
