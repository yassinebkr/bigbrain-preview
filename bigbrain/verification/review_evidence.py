"""Navigation over pinned evidence, not automatic relevance or acceptance."""
import ast


def test_locations(sources, cases, limit=100):
    """Resolve exact executed Python test symbols; never guess unresolved IDs."""
    trees, locations = {}, []
    for case in cases:
        parts = case.split('::')
        path = parts[0]
        if path not in sources or not path.endswith('.py') or len(parts) < 2:
            continue
        if path not in trees:
            try:
                trees[path] = ast.parse(sources[path])
            except (SyntaxError, ValueError):
                trees[path] = None
        node = trees[path]
        for name in parts[1:]:
            name = name.split('[', 1)[0]
            matches = [child for child in getattr(node, 'body', [])
                       if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       and child.name == name]
            node = matches[0] if len(matches) == 1 else None
        if node is not None:
            locations.append({'case': case, 'path': path, 'start': node.lineno,
                              'end': node.end_lineno})
            if len(locations) == limit:
                break
    return {'locations': locations, 'limit': limit,
            'scope': 'Exact executed symbols in pinned sources; locations are not assertion coverage'}


def search_sources(sources, query, path=None, offset=0):
    if not isinstance(query, str) or not query or len(query) > 200:
        raise ValueError('Search query must be a literal string of 1..200 characters')
    if path is not None and (not isinstance(path, str) or path not in sources):
        raise ValueError('Search requires an exact pinned inventory path')
    if type(offset) is not int or offset < 0:
        raise ValueError('Search offset must be a nonnegative integer')
    hits, size, seen = [], 0, 0
    for name in sorted(sources) if path is None else [path]:
        for line_number, line in enumerate(sources[name].splitlines(), 1):
            if query not in line:
                continue
            if seen < offset:
                seen += 1
                continue
            excerpt = line[:400]
            if len(hits) == 20 or size + len(name) + len(excerpt) > 12000:
                return {'hits': hits, 'next_offset': offset + len(hits), 'query': query}
            hits.append({'path': name, 'line': line_number, 'excerpt': excerpt,
                         'line_truncated': len(line) > 400})
            size += len(name) + len(excerpt)
    return {'hits': hits, 'next_offset': None, 'query': query}


def read_pages(sources, selections):
    """Validate entire bounded group before exposing any page as inspected."""
    if not isinstance(selections, list) or not 1 <= len(selections) <= 4:
        raise ValueError('read_many requires 1..4 pages')
    pages = []
    for item in selections:
        if not isinstance(item, dict):
            raise ValueError('Each page must be an object')
        path, start, count = item.get('path'), item.get('start'), item.get('count')
        if (not isinstance(path, str) or path not in sources or type(start) is not int or start < 1
                or type(count) is not int or not 1 <= count <= 200):
            raise ValueError('Use exact pinned paths, start >= 1, count 1..200')
        lines = sources[path].splitlines(keepends=True)
        selected, size = [], 0
        for line in lines[start - 1:start - 1 + count]:
            if size + len(line) > 3500:
                break
            selected.append(line)
            size += len(line)
        if not selected:
            raise ValueError('Page empty or line too long; choose another range')
        pages.append({'path': path, 'start': start, 'content': ''.join(selected),
                      'next_line': start + len(selected) if start + len(selected) <= len(lines) else None})
    return pages
