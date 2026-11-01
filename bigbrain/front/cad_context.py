"""Conversation-owned image inventory and versioned CAD clarification snapshots."""

import hashlib

from ..web.attachments import read_attachment
from ..web.sessions import SessionStore


def design_context(session_id):
    if not session_id:
        return None, []
    session = SessionStore().get(session_id) or {}
    return session.get('cad_context'), session.get('image_sources', [])


def verified_images(inventory):
    """Bind each image shown to inference to its originally uploaded bytes."""
    if len(inventory) > 8:
        raise ValueError('Cette conversation contient plus de huit images. Ouvre une conversation dédiée aux sources utiles.')
    for item in inventory:
        path = read_attachment(item['id'])
        if path is None:
            raise ValueError('Une image de cette conception est indisponible. Joins-la à nouveau.')
        if item.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Une image de cette conception a changé. Joins-la à nouveau pour confirmer sa nouvelle version.')
    return inventory


def save_clarification(session_id, decision, user_text, source_message_id, sources):
    """Retain exact exchanges independently of the rolling inference window."""
    from .decision import Clarify, Delegate, CadRoute
    if not session_id:
        return None
    store = SessionStore()
    session = store.get(session_id)
    if session is None:
        return None
    previous = session.get('cad_context') or {}
    is_cad = isinstance(decision, Delegate) and isinstance(decision.route, CadRoute)
    drawing = (decision.drawing if isinstance(decision, Clarify) else
               decision.route.payload.drawing if is_cad else None)
    # Only a model-authored drawing snapshot or an existing pending clarification
    # starts/continues a design dossier. Ordinary chat remains outside this path.
    if not (drawing or (isinstance(decision, Clarify) and decision.cad)
            or previous.get('status') == 'clarifying' or is_cad):
        return None
    if drawing:
        available = {item['id']: item for item in verified_images(sources)}
        for source in drawing.sources:
            item = available.get(source.attachment_id)
            path = read_attachment(source.attachment_id) if item else None
            if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256:
                raise ValueError('Le dessin référence une source extérieure à cette conversation ou modifiée.')
        statements = {item['id']: item.get('text', '') for item in session.get('messages', [])
                      if item.get('role') == 'user'}
        statements.update({item.get('message_id'): item['user'] for item in previous.get('exchanges', [])})
        for dimension in drawing.dimensions:
            if dimension.origin == 'user' and dimension.user_quote not in statements.get(dimension.user_message_id, ''):
                raise ValueError('Une cote déclarée par l’utilisateur doit citer son message exact dans cette conversation.')
        prior = previous.get('drawing') or {}
        same_sources = {(item['attachment_id'], item['sha256']) for item in prior.get('sources', [])} == {
            (item.attachment_id, item.sha256) for item in drawing.sources}
        if same_sources:
            by_id = {item.id: item for item in drawing.dimensions}
            for old in prior.get('dimensions', []):
                new = by_id.get(old['id'])
                if old.get('critical') and new is None:
                    raise ValueError('Une cote critique de la conception a disparu. Conserve son identité et résous sa portée.')
                if new and old.get('value') is not None and (old['value'], old['unit']) != (new.value, new.unit):
                    old_values = {item['id']: (item.get('value'), item.get('unit')) for item in prior.get('dimensions', [])}
                    changed_dependency = new.origin == 'derived' and any(
                        old_values.get(identity) != (by_id[identity].value, by_id[identity].unit)
                        for identity in new.dependencies)
                    if new.origin not in ('user', 'unresolved') and not changed_dependency:
                        raise ValueError('Une cote acquise a changé sans précision utilisateur ni contradiction explicite.')
    exchanges = list(previous.get('exchanges', []))
    if len(exchanges) >= 64:
        raise ValueError('La conception dépasse 64 échanges. Reprends ses informations dans une conversation dédiée.')
    exchanges.append({'message_id': source_message_id, 'user': user_text,
                      'assistant': decision.reply})
    context = {'status': 'proposed' if is_cad else 'clarifying',
               'sources': sources,
               'drawing': drawing.model_dump(mode='json') if drawing else previous.get('drawing'),
               'exchanges': exchanges,
               'question': decision.reply if isinstance(decision, Clarify) else None}
    return store.set_cad_context(session_id, context)
