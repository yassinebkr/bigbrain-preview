"""Node builds use read-only project dependencies and bounded output capture."""

import base64
import json
from pathlib import Path
import shutil
import pytest

from bigbrain.local_projects import ProjectRegistry
from bigbrain.local_project_runner import ProjectRunner


@pytest.mark.asyncio
async def test_node_dependencies_and_build_output_stay_scoped(tmp_path):
    root = tmp_path / 'node-source'
    (root / 'node_modules/demo').mkdir(parents=True)
    (root / 'node_modules/demo/index.js').write_text('module.exports = 42;')
    (root / 'build.js').write_text('const fs = require("fs"); const n = require("demo"); '
        'try { fs.writeFileSync("node_modules/demo/index.js", "corrupted"); process.exit(2); } '
        'catch (e) { if (e.code !== "EROFS") throw e; } '
        'fs.mkdirSync("dist"); fs.writeFileSync("dist/index.html", `<main>${n}</main>`);')
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    result = await ProjectRunner(registry).run(project['id'], 1, ['node', 'build.js'], capture_tree='dist')
    assert result['exitCode'] == 0, result
    assert base64.b64decode(result['treeArtifacts']['index.html']) == b'<main>42</main>'
    assert (root / 'node_modules/demo/index.js').read_text() == 'module.exports = 42;'
    assert not (root / 'dist').exists()


@pytest.mark.asyncio
async def test_real_react_build_and_browser_interaction_use_project_dependencies(tmp_path):
    from bigbrain.local_project_web import run_web_tests
    root = tmp_path / 'react-source'
    (root / 'node_modules').mkdir(parents=True)
    installed = Path(__file__).parents[1] / 'web-ui/node_modules'
    copied = set()
    def dependency(name):
        source = installed / name
        if name in copied or not source.is_dir():
            return
        copied.add(name)
        shutil.copytree(source, root / 'node_modules' / name, symlinks=True)
        metadata = json.loads((source / 'package.json').read_text())
        for child in {**metadata.get('dependencies', {}), **metadata.get('optionalDependencies', {})}:
            dependency(child)
    for name in ('vite', 'react', 'react-dom'):
        dependency(name)
    (root / 'package.json').write_text(json.dumps({'type': 'module'}))
    (root / 'index.html').write_text('<div id="root"></div><script type="module" src="/src/main.jsx"></script>')
    (root / 'src').mkdir()
    (root / 'src/main.jsx').write_text('import React from "react"; import {createRoot} from "react-dom/client"; '
        'function App(){const [n,setN]=React.useState(0);return <main><button onClick={()=>setN(n+1)}>Add</button>'
        '<p id="count">{n}</p></main>}createRoot(document.getElementById("root")).render(<App/>);')
    (root / 'tests').mkdir()
    (root / 'tests/acceptance.json').write_text(json.dumps({'schema_version': 2, 'cases': [
        {'name': 'react increment', 'steps': [{'op': 'click', 'selector': 'button'}],
         'assertions': [{'op': 'text', 'selector': '#count', 'value': '1'}]}]}))
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    result = await run_web_tests(registry, project['id'], 1, 'index.html', web_stack='react_vite')
    assert result['status'] == 'passed', result
    assert result['passed_cases'] == ['react increment']
    assert not (root / 'dist').exists()


@pytest.mark.asyncio
async def test_missing_react_dependencies_produces_environment_diagnostic(tmp_path):
    from bigbrain.local_project_web import run_web_tests
    root = tmp_path / 'react-source'
    (root / 'tests').mkdir(parents=True)
    (root / 'index.html').write_text('<main>Ready</main>')
    (root / 'tests/acceptance.json').write_text(json.dumps({'schema_version': 2, 'cases': [
        {'name': 'visible', 'assertions': [{'op': 'visible', 'selector': 'main'}]}]}))
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    result = await run_web_tests(registry, project['id'], 1, 'index.html', web_stack='react_vite')
    assert result['status'] == 'inconclusive'
    assert result['cause'] == 'environment_blocked'
    assert not (root / 'node_modules').exists()
