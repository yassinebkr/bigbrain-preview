"""Runtime-owned inference identity, independent of model-generated payloads."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from uuid import uuid4

current_conversation = ContextVar('llm_conversation', default=None)


@contextmanager
def conversation_scope(session_id, role):
    token = current_conversation.set((session_id, role) if session_id else None)
    try:
        yield
    finally:
        current_conversation.reset(token)


def scoped_conversation(role, *, session_argument=None, message_argument=None, independent=False):
    """Attach scope at an application boundary, never infer it from prompt text."""
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            bound = parameters.bind_partial(*args, **kwargs).arguments
            parent = current_conversation.get()
            session = bound.get(session_argument) if session_argument else None
            if message_argument:
                session = (bound[message_argument].payload or {}).get('session_id')
            if independent:
                session = (parent[0] if parent else None) or ('anonymous-' + uuid4().hex)
                active_role = role + '-' + uuid4().hex
            else:
                active_role = role
            with conversation_scope(session, active_role):
                return await function(*args, **kwargs)
        return wrapped
    return decorate
