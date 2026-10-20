"""Chromium acceptance for P1 with isolated TEST bus fixtures, no LLM calls."""
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from playwright.async_api import async_playwright

from bigbrain.bus.bus import MessageBus
from bigbrain.web.server import WebServer


async def check(root):
    for setting, name in {
        'BIGBRAIN_SESSIONS_DIR': 'sessions', 'BIGBRAIN_WORKSPACE_DIR': 'workspace',
        'BIGBRAIN_EVIDENCE_ROOT': 'evidence', 'BIGBRAIN_MEMORY_DIR': 'memory',
        'BIGBRAIN_SOUL_FILE': 'soul.json', 'BIGBRAIN_ATTACHMENTS_DIR': 'attachments',
        'BIGBRAIN_TASKS_FILE': 'tasks.json',
    }.items():
        os.environ[setting] = str(root / name)
    os.environ.pop('BIGBRAIN_WEB_PASSWORD', None)
    project = root / 'workspace' / 'sandbox' / 'p1-demo'
    project.mkdir(parents=True)
    (project / 'example.py').write_text('import time\nprint("P1 isolated file fixture", flush=True)\ntime.sleep(1)\nprint("Python execution complete")\n')
    (project / 'index.html').write_text('<h1>Isolated P1 application</h1><label>Notes <input id="notes" oninput="localStorage.setItem(\'notes\',this.value)"></label><script>document.querySelector("#notes").value=localStorage.getItem("notes")||""</script>')
    (project / '.project.json').write_text(json.dumps({'deliverable_type': 'web_app', 'entry_point': 'index.html', 'verified': True}))
    bus = MessageBus(root / 'logs', auth=None)
    server = WebServer(bus, host='127.0.0.1', port=0)
    original = server._sessions.create('P1 original conversation')['id']
    other = server._sessions.create('P1 separate conversation')['id']
    server._sessions.append_message(original, 'user', 'Isolated original request')
    server._sessions.append_message(other, 'user', 'Isolated separate request')
    async def emit(event, task_id, session=original, **data):
        await bus.broadcast_event(source='orchestrator_default' if event == 'workspace.proposal' else 'p1_acceptance_test', workspace='default', event_type=event,
            payload={'session_id': session, 'task_id': task_id, **data})
    await server.start()
    try:
        port = server._site._server.sockets[0].getsockname()[1]
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(viewport={'width': 1600, 'height': 950})
            state = json.dumps({'state': {'activeSessionKey': original, 'view': 'chat'}, 'version': 0})
            await context.add_init_script("localStorage.setItem('aplot_auth_token','isolated-p1-test');"
                f"if (!localStorage.getItem('aplot-ai-storage')) localStorage.setItem('aplot-ai-storage', {json.dumps(state)});")
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                await page.goto(f'http://127.0.0.1:{port}')
                await page.get_by_text('Isolated original request', exact=True).wait_for()
                navigation = await page.get_by_label('Navigation principale').bounding_box()
                assert navigation['height'] > navigation['width'] * 4, navigation
                assert abs(navigation['y'] + navigation['height'] / 2 - 475) < 2, navigation
                assert await page.get_by_role('group', name='Mode de présentation').count() == 0
                draft = page.get_by_placeholder('Initiate a query or send a command to the AI...')
                await draft.fill('Keep my draft and focus')
                # Let the initial ChatInput entrance animation finish before
                # comparing geometry; it is unrelated to the first run event.
                await page.wait_for_timeout(600)
                chat_box_before = await draft.bounding_box()
                message_before = await page.get_by_text('Isolated original request', exact=True).bounding_box()
                await emit('task.routing', 'web', description='P1 web project')
                await emit('task.received', 'web')
                await emit('workspace.proposal', 'web', producer='architect', proposal={'version': 1, 'revision': 1, 'widgets': ['files', 'preview']})
                await emit('subtask.started', 'web', subtask_id='build', brain='web_app_brain_0', description='Build application')
                pane = page.get_by_role('complementary', name='Surface contextuelle')
                await pane.get_by_label('Objet du travail').get_by_text('web_app_brain_0', exact=True).wait_for()
                assert await draft.input_value() == 'Keep my draft and focus'
                assert await draft.evaluate('(node) => node === document.activeElement')
                chat_box_after = await draft.bounding_box()
                assert chat_box_after == chat_box_before, (chat_box_before, chat_box_after)
                message_after = await page.get_by_text('Isolated original request', exact=True).bounding_box()
                assert message_after['x'] == message_before['x']
                assert message_after['width'] == message_before['width']
                assert await page.get_by_label('Conversation activities').count() == 0
                assert await page.locator('iframe').count() == 0
                assert await draft.evaluate('(node) => node.getBoundingClientRect().width') >= 600
                await page.screenshot(path='/tmp/bigbrain-work-widgets-building.png')
                await draft.focus()
                await emit('task.routing', 'board', description='P1 board action')
                await emit('task.received', 'board')
                await emit('subtask.started', 'board', subtask_id='task', brain='taskboard', description='Add task')
                await page.get_by_label('Travail consulté').locator('option[value="board"]').wait_for(state='attached')
                assert await page.get_by_label('Travail consulté').input_value() == 'web'
                assert await draft.evaluate('(node) => node === document.activeElement')
                separator = page.get_by_role('separator', name='Largeur de la surface')
                await separator.focus()
                await separator.press('ArrowLeft')
                assert await separator.get_attribute('aria-valuenow') == '420'
                await emit('workspace.file_written', 'web', path='sandbox/p1-demo/example.py')
                await pane.get_by_role('button', name='Fichiers', exact=True).click()
                await pane.get_by_role('button', name='sandbox/p1-demo/example.py', exact=True).click()
                await page.get_by_text('P1 isolated file fixture', exact=False).last.wait_for()
                await page.get_by_role('button', name='Close', exact=True).click()
                await pane.get_by_role('button', name='Vue d’ensemble', exact=True).click()
                await pane.get_by_label('Composition proposée').locator('summary').click()
                await pane.get_by_role('button', name='Utiliser cette composition', exact=True).click()
                await pane.get_by_label('Widget fichiers').wait_for()
                assert await pane.get_by_label('Widget aperçu').count() == 0
                await emit('workspace.proposal', 'web', producer='architect', proposal={'version': 1, 'revision': 2, 'widgets': ['verification']})
                await pane.get_by_label('Widget fichiers').wait_for()
                await emit('subtask.complete', 'web', subtask_id='build')
                await emit('task.complete', 'web', project_name='P1 demo', project_path='sandbox/p1-demo', entry_point='index.html', deliverable_type='web_app', runnable=True)
                await pane.get_by_text('Terminé', exact=True).first.wait_for()
                assert await page.get_by_label('Travail consulté').input_value() == 'web'
                await pane.get_by_label('Widget aperçu').wait_for()
                assert await page.locator('iframe').count() == 0
                await page.reload()
                pane = page.get_by_role('complementary', name='Surface contextuelle')
                await pane.get_by_text('Le résultat est disponible', exact=True).wait_for()
                await pane.get_by_label('Widget aperçu').wait_for()
                assert await page.get_by_label('Travail consulté').input_value() == 'web'
                assert await separator.get_attribute('aria-valuenow') == '420'
                await page.wait_for_function("Number(getComputedStyle(document.querySelector('textarea').closest('[style*=opacity]')).opacity) > .99")
                await page.screenshot(path='/tmp/bigbrain-morphable-p1-desktop.png')
                await page.get_by_role('button', name='Fermer la surface').click()
                await pane.wait_for(state='detached')
                await page.wait_for_timeout(350)
                assert await pane.count() == 0
                centered = await draft.bounding_box()
                assert abs(centered['x'] + centered['width'] / 2 - 838) < 30, centered
                await page.screenshot(path='/tmp/bigbrain-chat-centered.png')
                await page.get_by_role('button', name='Afficher le résultat', exact=True).click()
                await pane.frame_locator('iframe').get_by_text('Isolated P1 application', exact=True).wait_for()
                assert await page.locator('iframe').count() == 1
                await pane.frame_locator('iframe').get_by_label('Notes').fill('Keep storage across tabs')
                await draft.fill('Keep my draft and focus')
                # Layout changes must preserve the mounted application, including
                # unsaved state that localStorage does not protect.
                await pane.frame_locator('iframe').locator('body').evaluate('(node) => { node.dataset.layoutSentinel = "preserved"; }')
                await page.get_by_role('button', name='Donner la place principale à cette activité').click()
                assert await page.locator('.context-layout').evaluate("node => node.getAnimations().some(a => a.transitionProperty === 'grid-template-columns')"), 'Expansion must animate the layout'
                await page.wait_for_timeout(350)
                assert await pane.evaluate('(node) => node.getBoundingClientRect().width') > 1000
                assert await pane.frame_locator('iframe').locator('body').get_attribute('data-layout-sentinel') == 'preserved'
                assert await draft.input_value() == 'Keep my draft and focus'
                await page.screenshot(path='/tmp/bigbrain-morphable-p1-expanded.png')
                await page.get_by_role('button', name='Redonner la place principale au chat').click()
                assert await pane.frame_locator('iframe').locator('body').get_attribute('data-layout-sentinel') == 'preserved'
                assert await draft.input_value() == 'Keep my draft and focus'
                await pane.get_by_role('button', name='Fichiers', exact=True).click()
                assert await page.locator('iframe').count() == 0
                await pane.get_by_role('button', name='Aperçu', exact=True).click()
                await pane.frame_locator('iframe').get_by_text('Isolated P1 application', exact=True).wait_for()
                assert await pane.frame_locator('iframe').get_by_label('Notes').input_value() == 'Keep storage across tabs'
                await page.screenshot(path='/tmp/bigbrain-morphable-p1-desktop.png')
                assert await page.get_by_label('Travail consulté').input_value() == 'web'
                await page.get_by_role('button', name='History', exact=True).click()
                await page.get_by_role('button', name='P1 separate conversation', exact=True).click()
                await page.get_by_text('Isolated separate request', exact=True).wait_for()
                await pane.wait_for(state='detached')
                assert await pane.count() == 0
                await page.get_by_role('button', name='History', exact=True).click()
                await page.get_by_role('button', name='P1 original conversation', exact=True).click()
                await pane.frame_locator('iframe').get_by_text('Isolated P1 application', exact=True).wait_for()
                await page.get_by_role('button', name='Close panel', exact=True).wait_for(state='hidden')
                await page.set_viewport_size({'width': 390, 'height': 844})
                await page.wait_for_timeout(400)
                await page.get_by_role('button', name='Retour au chat', exact=True).wait_for()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.screenshot(path='/tmp/bigbrain-morphable-p1-mobile.png')
                mobile_pane = await pane.bounding_box()
                assert mobile_pane['x'] >= 0 and mobile_pane['x'] + mobile_pane['width'] <= 390, mobile_pane
                await page.get_by_role('button', name='Retour au chat', exact=True).click()
                await pane.wait_for(state='detached')
                assert await draft.is_visible()
                assert await pane.count() == 0
                await page.set_viewport_size({'width': 320, 'height': 700})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await emit('task.routing', 'later', description='P1 later work')
                await page.get_by_role('button', name='Ouvrir l’espace de travail').wait_for()
                assert await pane.count() == 0
                await emit('task.complete', 'board', result_kind='taskboard')
                await emit('task.complete', 'later')
                await page.get_by_label('Conversation activities').wait_for(state='hidden')
                # A real local Python execution, not a fabricated console response.
                await page.set_viewport_size({'width': 1600, 'height': 950})
                await emit('task.routing', 'python', description='Python widget fixture')
                await emit('task.received', 'python')
                await emit('subtask.started', 'python', subtask_id='fixture-check', brain='python_brain_0', description='Validate the isolated Python fixture')
                await emit('task.progress', 'python', subtask_id='fixture-check', stage='file_written', file_path='example.py')
                await emit('subtask.complete', 'python', subtask_id='fixture-check')
                await emit('workspace.file_written', 'python', path='sandbox/p1-demo/example.py')
                await emit('task.complete', 'python', project_name='Python widget fixture', project_path='sandbox/p1-demo', entry_point='example.py', deliverable_type='python', runnable=True)
                await page.get_by_role('button', name='Ouvrir l’espace de travail').click()
                await page.get_by_label('Travail consulté').select_option('python')
                await pane.get_by_role('button', name='Lancer le projet', exact=True).click()
                console = pane.get_by_label('Console Python')
                await console.get_by_label('Sortie Python').filter(has_text='P1 isolated file fixture').wait_for()
                await console.get_by_text('Terminé · code 0', exact=True).wait_for()
                assert 'Python execution complete' in await console.get_by_label('Sortie Python').inner_text()
                await page.get_by_role('button', name='Run project', exact=True).click()
                await console.get_by_text('Terminé · code 0', exact=True).wait_for()
                await page.screenshot(path='/tmp/bigbrain-work-widgets-python.png')
                composer = await draft.bounding_box()
                assert composer['y'] + composer['height'] < 950, composer
                await page.get_by_role('button', name='Donner la place principale à cette activité').click()
                assert 'Python execution complete' in await console.get_by_label('Sortie Python').inner_text()
                await page.wait_for_timeout(350)
                await page.screenshot(path='/tmp/bigbrain-python-expanded.png')
                artifact_box = await pane.get_by_label('Objet du travail').bounding_box()
                console_box = await console.bounding_box()
                assert abs(artifact_box['y'] - console_box['y']) < 2
                assert console_box['x'] > artifact_box['x'] + artifact_box['width']
                island = await pane.bounding_box()
                assert island['y'] + island['height'] <= 950 - 10, island
                journal = pane.locator('.work-journal').filter(has_text='Activité et journal technique')
                await journal.locator('summary').first.click()
                await pane.get_by_label('Étapes du run').wait_for()
                await journal.scroll_into_view_if_needed()
                await page.screenshot(path='/tmp/bigbrain-expanded-journal.png')
                await page.set_viewport_size({'width': 1200, 'height': 760})
                await page.wait_for_timeout(400)
                compact_artifact = await pane.get_by_label('Objet du travail').bounding_box()
                compact_console = await console.bounding_box()
                assert abs(compact_artifact['x'] - compact_console['x']) < 2
                assert compact_console['y'] >= compact_artifact['y'] + compact_artifact['height']
                island = await pane.bounding_box()
                assert island['y'] + island['height'] <= 750, island
                await page.set_viewport_size({'width': 1600, 'height': 950})
                await page.wait_for_timeout(400)
                await page.reload()
                await page.get_by_label('Console Python').get_by_text('Terminé · code 0', exact=True).wait_for()
                assert await pane.get_by_text('Fichier enregistré · example.py', exact=True).count() > 0
                assert 'Python execution complete' in await page.get_by_label('Sortie Python').inner_text()
                assert not errors, errors
                # History actions are real persisted mutations, including two tabs.
                await page.get_by_role('button', name='History', exact=True).click()
                await page.get_by_role('button', name='Renommer P1 separate conversation', exact=True).click()
                await page.get_by_label('Titre de la conversation', exact=True).fill('Renamed conversation')
                assert await page.get_by_label('Enregistrer le titre').evaluate("el => getComputedStyle(el).color === getComputedStyle(el.closest('form')).color")
                await page.get_by_role('button', name='Enregistrer le titre', exact=True).click()
                await page.get_by_role('button', name='Renommer Renamed conversation', exact=True).wait_for()
                assert server._sessions.get(other)['title'] == 'Renamed conversation'
                await page.get_by_role('button', name='Renamed conversation', exact=True).click()
                await page.get_by_text('Isolated separate request', exact=True).wait_for()
                second = await context.new_page()
                await second.goto(f'http://127.0.0.1:{port}')
                await second.get_by_text('Isolated separate request', exact=True).wait_for()
                await page.get_by_role('button', name='History', exact=True).click()
                await page.get_by_role('button', name='Supprimer Renamed conversation', exact=True).click()
                await page.screenshot(path='/tmp/bigbrain-history-delete-contrast.png')
                assert await page.get_by_label('Confirmer la suppression').evaluate("el => getComputedStyle(el).color !== 'rgb(0, 0, 0)'")
                await page.get_by_role('button', name='Annuler', exact=True).click()
                assert server._sessions.get(other) is not None
                await page.get_by_role('button', name='Supprimer Renamed conversation', exact=True).click()
                await page.get_by_role('button', name='Supprimer définitivement', exact=True).click()
                await page.get_by_role('button', name='Supprimer Renamed conversation', exact=True).wait_for(state='detached')
                await second.get_by_text('Isolated separate request', exact=True).wait_for(state='detached')
                await second.reload()
                await second.get_by_role('button', name='History', exact=True).click()
                await second.get_by_role('button', name='P1 original conversation', exact=True).wait_for()
                assert await second.get_by_text('Renamed conversation', exact=True).count() == 0
                assert server._sessions.get(original) is not None
                assert project.joinpath('example.py').is_file()
                await second.close()
                await page.get_by_role('button', name='P1 original conversation', exact=True).click()
                opener = page.get_by_role('button', name='Ouvrir l’espace de travail')
                if await opener.is_visible():
                    await opener.click()
                await page.get_by_label('Travail consulté').select_option('python')
                await emit('task.routing', 'repair', description='Repair existing project', project_path='sandbox/p1-demo')
                try:
                    await page.wait_for_function("document.querySelector('[aria-label=\"Travail consulté\"]')?.value === 'repair'")
                except Exception:
                    print({'page_errors': errors, 'body': (await page.locator('body').inner_text())[:1800]})
                    raise
                await emit('planning.stage', 'repair', stage='architecture', status='running', description='Preparing repair')
                await pane.get_by_text('Preparing repair', exact=True).first.wait_for()
                await emit('task.failed', 'repair', error='Isolated repair planning failure', project_path='sandbox/p1-demo')
                await pane.get_by_text('Isolated repair planning failure', exact=True).first.wait_for()
                assert await page.get_by_label('Travail consulté').input_value() == 'repair'
                # Separate explicit user navigation from the earlier no-bump
                # regression: closing/reopening intentionally changes layout.
                await emit('task.routing', 'approval', description='Isolated contract review', project_path='sandbox/p1-demo')
                await emit('contracts.proposal', 'approval', plan_id='approval', design_id='isolated-design',
                    user_request='Isolated implementation', project_target={'mode': 'existing', 'path': 'sandbox/p1-demo'},
                    contracts=['[Stack] livrable web_app · interaction browser · point d’entrée index.html · technologies HTML/CSS/JavaScript · validation ' + 'Actual browser verification. ' * 20,
                               'An actual user-visible acceptance criterion', 'Long criterion. ' * 30])
                await pane.get_by_role('button', name='Approuver et lancer').wait_for()
                await page.get_by_text('Contrat prêt à examiner dans l’Atelier →', exact=False).wait_for()
                assert await page.get_by_text('An actual user-visible acceptance criterion', exact=True).count() == 1
                assert await page.get_by_role('button', name='Approve & run', exact=True).count() == 0
                await page.screenshot(path='/tmp/bigbrain-atelier-contract.png')
                await pane.get_by_role('button', name='Fermer la surface', exact=True).click()
                await page.get_by_role('button', name='Approve & run', exact=True).wait_for()
                await page.get_by_role('button', name='Ouvrir l’espace de travail').click()
                await pane.get_by_role('button', name='Approuver et lancer').wait_for()
                await emit('contracts.approved', 'approval', plan_id='approval', design_id='isolated-design')
                await pane.get_by_label('Proposition à approuver').wait_for(state='detached')
                print(json.dumps({'draft_focus_preserved': True, 'automatic_side_surface_no_preview': True,
                    'single_contract_owner_with_chat_fallback': True,
                    'same_project_repair_followed_through_failure': True,
                    'activity_expansion_preserves_iframe_and_draft': True,
                    'real_python_console_and_chat_launch': True, 'completed_console_reload': True,
                    'widget_acceptance_no_preview_autostart': True, 'accepted_composition_stays_pinned': True,
                    'concurrent_selection_stable': True, 'completion_kept': True,
                    'reload_restored': True, 'session_isolation': True, 'keyboard_resize': True,
                    'mobile_reflow': True, 'close_reopen': True, 'real_file_opened': True,
                    'single_result_preview': True, 'storage_preserved': True, 'finished_work_not_in_header': True, 'page_errors': errors}))
            finally:
                await context.close()
                await browser.close()
    finally:
        await server.stop()
        await bus.close()


async def main():
    with tempfile.TemporaryDirectory(prefix='bigbrain-morphable-p1-') as directory:
        with patch('bigbrain.llm.model_registry.verify_all', new=AsyncMock(return_value={})):
            await check(Path(directory))


if __name__ == '__main__':
    asyncio.run(main())
