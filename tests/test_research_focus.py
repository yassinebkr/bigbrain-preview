"""Definition focus ranking preserves exact source entries and their conditions."""

from bigbrain.research_extraction import extract_html, window


def block(identity, text, kind, context):
    return {'id': identity, 'text': text, 'kind': kind, 'context': context}


def test_dedicated_option_definition_outranks_compound_signature():
    blocks = [
        block('signature', 'save [--include-extra] [--all]', 'dt', ['Commands', 'save']),
        block('summary', 'Save local changes.', 'p', ['Commands', 'save']),
        block('option', '--include-extra', 'dt', ['Options', '--include-extra']),
        block('condition', 'Includes extra entries while preserving ignored entries.', 'p', ['Options', '--include-extra']),
        block('next', '--all', 'dt', ['Options', '--all']),
    ]
    selected, _ = window(blocks, '--include-extra')
    assert [item['id'] for item in selected] == ['option', 'condition']
    assert selected[1]['text'] == blocks[3]['text']
    assert not any(item['clipped'] for item in selected)


def test_exact_heading_outranks_incidental_definition_signature():
    blocks = [
        block('signature', 'utility(target, missing_ok=True)', 'dt', ['Overview']),
        block('heading', 'missing_ok', 'h3', ['Options']),
        block('condition', 'Only missing targets are ignored.', 'p', ['Options']),
    ]
    selected, _ = window(blocks, 'missing_ok')
    assert any(item['id'] == 'condition' for item in selected)


def test_identical_definition_matches_retain_document_order():
    blocks = [block('first', '--flag', 'dt', ['First']),
              block('first-condition', 'First meaning.', 'p', ['First']),
              block('second', '--flag', 'dt', ['Second'])]
    selected, _ = window(blocks, '--flag')
    assert [item['id'] for item in selected] == ['first', 'first-condition']


def test_definition_aliases_share_their_following_description():
    html = '<html><body><h2>Options</h2><dl><dt>-x</dt><dt>--include-extra</dt>'
    html += '<dt>--no-include-extra</dt><dd><p>Extra entries are saved. Ignored entries remain.</p></dd>'
    html += '<dt>--other</dt><dd><p>Unrelated behavior.</p></dd></dl></body></html>'
    prepared = extract_html(html, 'https://manual.test/command')
    selected, _ = window(prepared['original_blocks'], '--include-extra')
    assert any(b['text'] == 'Extra entries are saved. Ignored entries remain.' for b in selected)
    assert not any(b['text'] == 'Unrelated behavior.' for b in selected)


def test_prose_focus_keeps_enclosing_definition_and_excludes_following_entries():
    html = '<main><dl><dt>apply [options]</dt><dd><p>Apply a saved entry.</p>'
    html += '<p>If conflicts occur, retain the original entry.</p><p>Resolve them manually.</p></dd>'
    html += '<dt>remove</dt><dd><p>Delete an entry.</p></dd></dl></main>'
    prepared = extract_html(html, 'https://manual.test/command')
    selected, _ = window(prepared['original_blocks'], 'conflicts')
    assert [b['text'] for b in selected] == ['apply [options]', 'Apply a saved entry.',
        'If conflicts occur, retain the original entry.', 'Resolve them manually.']
    assert not any(b['clipped'] for b in selected)


def test_heading_focus_preserves_children_and_stops_before_next_sibling():
    html = '<main><h1>Manual</h1><h2>Concurrency</h2><p>Readers and writers coexist.</p>'
    html += '<h3>Limits</h3><p>Only one writer is allowed.</p>'
    html += '<h2>Performance</h2><p>Unrelated benchmark details.</p></main>'
    prepared = extract_html(html, 'https://manual.test/operation')
    for focus in ('Concurrency', 'Readers and writers'):
        selected, _ = window(prepared['original_blocks'], focus)
        assert [b['text'] for b in selected] == ['Concurrency', 'Readers and writers coexist.',
            'Limits', 'Only one writer is allowed.']
        assert not any(b['clipped'] for b in selected)
