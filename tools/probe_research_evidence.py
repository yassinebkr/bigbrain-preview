"""Opt-in bounded public-web research smoke test; no user project or memory."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    root = Path(tempfile.mkdtemp(prefix="bigbrain-research-live-"))
    os.environ['BIGBRAIN_SESSIONS_DIR'] = str(root / 'sessions')
    os.environ['BIGBRAIN_CODEX_EFFORT'] = 'low'
    import bigbrain.config  # load credentials without printing them
    from bigbrain.brains.researcher import BraveSearch
    from bigbrain.llm.codex_provider import CodexProvider
    from bigbrain.research import Limits, ModelPolicy, PageReader, ResearchRuntime
    from bigbrain.research_assessment import ModelReviewer
    if not os.getenv('BRAVE_API_KEY'):
        raise SystemExit('BRAVE_API_KEY is required')
    provider = CodexProvider()
    search = BraveSearch(os.environ['BRAVE_API_KEY'], max_results=3)
    events = []

    async def progress(event):
        events.append(event)
        action = event.get('action') or (event.get('observation') or {}).get('action') or {}
        print(json.dumps({'stage': event['stage'], 'action': action.get('tool')}), flush=True)

    runtime = ResearchRuntime(search, PageReader(), ModelPolicy(provider), progress,
        limits=Limits(actions=7, searches=3, pages=2, reviews=1, seconds=120, tokens=60000),
        reviewer=ModelReviewer(provider))
    print('Evidence directory:', root, flush=True)
    try:
        state = await runtime.run(
            'Does Python 3.13 pathlib.Path.unlink(missing_ok=True) silently ignore '
            'a missing file? Establish the exact scope from official versioned '
            'documentation, distinguish other errors, and give observed citations. '
            'Keep the investigation focused; no current-year search suffix is needed.')
        (root / 'state.json').write_text(state.model_dump_json(indent=2))
        (root / 'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=2))
        print(json.dumps({'status': state.status, 'reason': state.reason,
            'pages_read': sum(s.status == 'read' for s in state.sources),
            'claims': [{'text': c.text, 'status': c.status} for c in state.claims],
            'usage': state.usage}), flush=True)
    finally:
        await search.close()
        await provider.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    if not parser.parse_args().live:
        parser.error('--live required; consumes Brave and Codex usage')
    asyncio.run(main())
