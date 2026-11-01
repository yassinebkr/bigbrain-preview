"""Persistent CAD clarifications, source ownership and cross-turn vision."""

import hashlib
import json

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.front.cad_context import design_context, save_clarification, verified_images
from bigbrain.front.decision import Clarify, Delegate
from bigbrain.front.front_brain import FrontBrain
from bigbrain.web.attachments import read_attachment, save_attachment
from bigbrain.web.sessions import SessionStore
from tests.test_cad_drawings import drawing
from tests.test_vision import RecordingProvider, message_for


def fixture():
    store = SessionStore()
    session = store.create()
    record = save_attachment('support.png', 'image/png', b'artificial drawing')
    store.append_message(session['id'], 'user', 'Create this support', [record])
    source = {'attachment_id': record['id'], 'sha256': hashlib.sha256(b'artificial drawing').hexdigest()}
    data = drawing()
    data['sources'] = [source]
    data['dimensions'][0]['sources'] = [source]
    return store, session['id'], record, data


def test_native_schema_exposes_dimension_origin_constraints():
    from bigbrain.cad_drawings import DrawingSpecification
    schema = DrawingSpecification.model_json_schema()
    user = schema['$defs']['UserDimension']
    assert user['properties']['dependencies']['maxItems'] == 0
    assert {'value', 'user_message_id', 'user_quote'} <= set(user['required'])
    derived = schema['$defs']['DerivedDimension']
    assert derived['properties']['dependencies']['minItems'] == 1
    assert schema['$defs']['UnresolvedDimension']['properties']['value']['type'] == 'null'


def test_sources_and_thumbnail_refs_survive_reload():
    store, sid, record, _ = fixture()
    loaded = SessionStore().get(sid)
    assert loaded['messages'][0]['attachments'][0]['id'] == record['id']
    assert loaded['image_sources'][0]['sha256'] == hashlib.sha256(b'artificial drawing').hexdigest()
    assert design_context(store.create()['id']) == (None, [])


@pytest.mark.parametrize('missing', [False, True])
def test_source_mutation_and_disappearance_are_explicit(missing):
    _, sid, record, _ = fixture()
    path = read_attachment(record['id'])
    if missing:
        path.unlink()
    else:
        path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='indisponible|changé'):
        verified_images(design_context(sid)[1])


def test_pending_snapshot_and_exact_answers_survive_history_window():
    store, sid, _, data = fixture()
    data['dimensions'][0].update(value=None, origin='unresolved')
    decision = Clarify(operation='clarify', cad=True, reply='Quelle largeur ?', drawing=data)
    context = save_clarification(sid, decision, 'Create this support', 'first', design_context(sid)[1])
    assert context['revision'] == 1
    for index in range(24):
        decision = Clarify(operation='clarify', cad=True, reply='Précision suivante ?')
        context = save_clarification(sid, decision, str(index), f'm-{index}', design_context(sid)[1])
    assert SessionStore().get(sid)['cad_context']['exchanges'][0]['user'] == 'Create this support'
    assert context['drawing']['dimensions'][0]['origin'] == 'unresolved'
    assert context['revision'] == 25


def test_natural_language_clarification_has_no_image_dependency():
    store = SessionStore()
    sid = store.create()['id']
    result = save_clarification(sid, Clarify(operation='clarify', cad=True, reply='Quelle épaisseur ?'),
                                'Une plaque de 40 par 20 mm', 'm-first', [])
    assert result['sources'] == []
    assert result['question'] == 'Quelle épaisseur ?'
    assert result['exchanges'][0]['user'] == 'Une plaque de 40 par 20 mm'


def test_conversational_reply_preserves_the_pending_question():
    from bigbrain.front.decision import Respond
    store, sid, _, _ = fixture()
    save_clarification(sid, Clarify(operation='clarify', cad=True, reply='Quelle hauteur ?'),
                       'Create this support', 'first', [])
    result = save_clarification(sid, Respond(operation='respond', reply='Bien sûr.'),
                                'Un instant', 'second', [])
    assert result['question'] == 'Quelle hauteur ?'


def test_stale_design_snapshot_cannot_overwrite_newer_answers():
    store, sid, _, _ = fixture()
    first = save_clarification(sid, Clarify(operation='clarify', cad=True, reply='Quelle hauteur ?'),
                              'Create this support', 'first', [], expected_revision=0)
    second = save_clarification(sid, Clarify(operation='clarify', cad=True, reply='Quel diamètre ?'),
                               '25 mm', 'second', [], expected_revision=first['revision'])
    with pytest.raises(ValueError, match='évolué'):
        save_clarification(sid, Clarify(operation='clarify', cad=True, reply='Ancienne question'),
                           'old', 'old', [], expected_revision=first['revision'])
    assert store.get(sid)['cad_context'] == second
    with pytest.raises(ValueError, match='évolué'):
        store.set_cad_context(sid, {**first, 'run_id': 'stale-run'}, expected_revision=first['revision'])
    assert store.get(sid)['cad_context'] == second


def test_cross_conversation_drawing_sources_are_rejected():
    store, _, _, data = fixture()
    sid = store.create()['id']
    with pytest.raises(ValueError, match='extérieure'):
        save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Une cote ?'), 'hello', 'm', [])
    assert 'cad_context' not in store.get(sid)


def test_user_dimension_requires_literal_conversation_statement():
    store, sid, _, data = fixture()
    store.append_message(sid, 'user', 'Largeur de 2 cm')
    mid = store.get(sid)['messages'][-1]['id']
    data['dimensions'][0].update(value=20, origin='user', user_message_id=mid, user_quote='2 cm',
                                 derivation='Unit conversion: 2 cm = 20 mm')
    result = save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Quelle hauteur ?'),
                                'Largeur de 2 cm', mid, design_context(sid)[1])
    assert result['drawing']['dimensions'][0]['value'] == 20
    data['dimensions'][0]['user_quote'] = '3 cm'
    with pytest.raises(ValueError, match='message exact'):
        save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Une cote ?'),
                           'hello', mid, design_context(sid)[1])


def test_silent_dimension_change_and_critical_omission_are_rejected():
    _, sid, _, data = fixture()
    save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Une autre cote ?'),
                       'Create this support', 'first', design_context(sid)[1])
    data['dimensions'][0]['value'] = 65
    with pytest.raises(ValueError, match='changé'):
        save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Continuer ?'),
                           'hello', 'second', design_context(sid)[1])
    data['dimensions'][0]['id'] = 'renamed'
    with pytest.raises(ValueError, match='disparu'):
        save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Continuer ?'),
                           'hello', 'second', design_context(sid)[1])


def test_replacement_image_retains_distinct_source_identity():
    store, sid, record, _ = fixture()
    replacement = save_attachment('support.png', 'image/png', b'replacement drawing')
    store.append_message(sid, 'user', 'Use this corrected drawing', [replacement])
    sources = verified_images(design_context(sid)[1])
    assert [item['id'] for item in sources] == [record['id'], replacement['id']]
    assert len({item['sha256'] for item in sources}) == 2


def test_confirmation_of_changed_dimension_updates_derived_dependents():
    store, sid, _, data = fixture()
    half = dict(data['dimensions'][0], id='half', value=30, origin='derived',
                dependencies=['width'], derivation='width / 2')
    data['dimensions'].append(half)
    save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Une cote ?'),
                       'Create this support', 'first', design_context(sid)[1])
    store.append_message(sid, 'user', 'La largeur est de 80 mm')
    mid = store.get(sid)['messages'][-1]['id']
    data['dimensions'][0].update(value=80, origin='user', user_message_id=mid, user_quote='80 mm')
    data['dimensions'][1]['value'] = 40
    result = save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Une cote ?'),
                                'La largeur est de 80 mm', mid, design_context(sid)[1])
    assert result['drawing']['dimensions'][1]['value'] == 40


def test_clarification_budget_stops_explicitly_without_dropping_earlier_answers():
    store, sid, _, _ = fixture()
    store.set_cad_context(sid, {'status': 'clarifying', 'exchanges': [
        {'message_id': f'm-{index}', 'user': str(index), 'assistant': 'Question'} for index in range(64)]})
    with pytest.raises(ValueError, match='64 échanges'):
        save_clarification(sid, Clarify(operation='clarify', cad=True, reply='Question'),
                           'next', 'next', [])
    assert len(store.get(sid)['cad_context']['exchanges']) == 64


@pytest.mark.asyncio
async def test_missing_image_stops_before_inference_and_new_upload_recovers(monkeypatch):
    store, sid, original, _ = fixture()
    read_attachment(original['id']).unlink()
    provider = RecordingProvider(True)
    bus = MessageBus(auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    replies = []
    async def capture(role, text):
        replies.append(text)
    monkeypatch.setattr(front, '_emit_chat_message', capture)
    message = message_for(original, 'Continue')
    message.payload.update(session_id=sid, attachments=[])
    try:
        await front._handle_ui_message(message)
        assert provider.calls == []
        assert 'indisponible' in replies[-1]
        replacement = save_attachment('support.png', 'image/png', b'new drawing bytes')
        store.append_message(sid, 'user', 'Use this source instead', [replacement])
        message = message_for(replacement, 'Use this source instead')
        message.payload['session_id'] = sid
        await front._handle_ui_message(message)
        assert len(provider.calls) == 1
        blocks = provider.calls[0]['messages'][-1]['content']
        assert sum(block.get('type') == 'image_url' for block in blocks) == 1
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_followup_after_front_restart_receives_image_and_dossier(monkeypatch):
    store, sid, record, data = fixture()
    save_clarification(sid, Clarify(operation='clarify', drawing=data, reply='Quelle hauteur ?'),
                       'Create this support', 'first', design_context(sid)[1])
    store.append_message(sid, 'user', '2 cm')
    provider = RecordingProvider(True)
    bus = MessageBus(auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    emitted = []
    async def capture(*args):
        emitted.append(args)
    monkeypatch.setattr(front, '_emit_chat_message', capture)
    message = message_for(record, '2 cm')
    message.payload.update(session_id=sid, attachments=[], user_message_id=store.get(sid)['messages'][-1]['id'])
    try:
        await front._handle_ui_message(message)
        messages = provider.calls[0]['messages']
        assert any('Quelle hauteur ?' in str(item['content']) for item in messages)
        assert any(store.get(sid)['messages'][0]['id'] in str(item['content']) for item in messages)
        assert any(block.get('type') == 'image_url' for block in messages[-1]['content'])
        assert messages[-1]['content'][0]['text'] == '2 cm'
        assert emitted
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_other_conversation_receives_no_image_or_design(monkeypatch):
    _, _, record, _ = fixture()
    provider = RecordingProvider(True)
    bus = MessageBus(auth=None)
    front = FrontBrain(bus, llm_provider=provider)
    async def capture(*args):
        pass
    monkeypatch.setattr(front, '_emit_chat_message', capture)
    message = message_for(record, 'hello')
    message.payload.update(session_id='other-conversation', attachments=[])
    try:
        await front._handle_ui_message(message)
        assert isinstance(provider.calls[0]['messages'][-1]['content'], str)
        assert all('Conversation CAD dossier' not in str(item['content']) for item in provider.calls[0]['messages'])
    finally:
        await bus.close()
