"""Opt-in subscription probe: four short completions, one native compaction."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    from bigbrain.llm.codex_provider import CodexProvider
    from bigbrain.llm.usage import get_tracker
    root = Path(tempfile.mkdtemp(prefix='bigbrain-codex-conversations-'))
    os.environ['BIGBRAIN_SESSIONS_DIR'] = str(root / 'sessions')
    os.environ['CODEX_CHATGPT_MODEL'] = 'gpt-6.1-sol'
    os.environ['BIGBRAIN_CODEX_EFFORT'] = 'low'
    print('Evidence directory:', root, flush=True)
    tracker = get_tracker()
    tracker.reset()
    provider = CodexProvider()
    events, result = [], {}
    started = time.monotonic()

    async def ask(session, text):
        response = await asyncio.wait_for(provider.chat_complete(
            [{'role': 'user', 'content': text}], conversation_id=session), timeout=90)
        _, path, _ = await provider._binding((session, 'front'))
        state = provider._conversations.load(path)
        events.append({'session': session, 'response': response, 'thread_id': state['thread_id']})
        print('Completed short turn:', session, flush=True)
        return str(response).strip()

    try:
        first = await ask('sess-probe-a', 'Remember the synthetic test marker AMBER-41. Reply only OK. Do not use tools.')
        marker = await ask('sess-probe-a', 'What is my synthetic test marker? Reply with the marker only. Do not use tools.')
        before = events[-1]['thread_id']
        compact = await asyncio.wait_for(provider.compact_conversation('sess-probe-a', timeout=90), 100)
        print('Native compaction completed', flush=True)
        await provider.aclose()
        provider = CodexProvider()  # disk binding + new app-server connection
        resumed = await ask('sess-probe-a', 'What is my synthetic test marker? Reply with the marker only. Do not use tools.')
        other = await ask('sess-probe-b', 'What synthetic test marker did I previously give you in THIS conversation? If none, reply only UNKNOWN. Do not use tools.')
        checks = {'marker_recalled': marker == 'AMBER-41', 'marker_after_compaction_restart': resumed == 'AMBER-41',
                  'other_chat_isolated': other == 'UNKNOWN',
                  'other_thread_distinct': events[-1]['thread_id'] != before,
                  'same_thread': all(e['thread_id'] == before for e in events if e['session'] == 'sess-probe-a'),
                  'compacted': compact['status'] == 'compacted'}
        result = {'success': all(checks.values()), 'checks': checks, 'events': events,
                  'compaction': compact}
    except Exception as exc:
        # These adapter errors contain protocol diagnostics, never auth headers.
        result = {'success': False, 'error_type': type(exc).__name__, 'error': str(exc)[:1600], 'events': events}
    finally:
        await provider.aclose()
        result.update(elapsed_seconds=round(time.monotonic() - started, 2), usage=tracker.totals(),
                      model='gpt-6.1-sol', effort='low', provider='codex-chatgpt')
        (root / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    if not parser.parse_args().live:
        parser.error('--live required; this consumes subscription usage')
    asyncio.run(main())
