"""Native CAD handoff through revision-bound, independent working copies."""

import os
from pathlib import Path
import shutil
import subprocess
import uuid

from .solidcraft import CadError, solidcraft_executable


def desktop_executable():
    """Resolve the GUI beside the selected engine or from an explicit setting."""
    configured = os.environ.get('BIGBRAIN_SOLIDCRAFT_GUI')
    if configured:
        candidate = Path(configured)
    else:
        candidate = solidcraft_executable().with_name('solidcraft.exe' if os.name == 'nt' else 'solidcraft')
    if not candidate.is_file():
        raise CadError('SolidCraft GUI unavailable; configure BIGBRAIN_SOLIDCRAFT_GUI')
    if os.name == 'posix' and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise CadError('A local desktop session is required to open SolidCraft')
    return candidate.resolve(strict=True)


class CadDesktop:
    """Bound launch concurrency while leaving immutable published files intact."""

    def __init__(self):
        self.processes = []

    def capability(self):
        try:
            desktop_executable()
            return {'available': True, 'platform': 'windows' if os.name == 'nt' else 'linux',
                    'diagnostic': None}
        except CadError as error:
            return {'available': False, 'diagnostic': str(error)}

    def open(self, store, document_id, session_id, revision):
        executable = desktop_executable()
        self.processes = [process for process in self.processes if process.poll() is None]
        if len(self.processes) >= 4:
            raise CadError('Four CAD handoff windows are already active; close one before opening another')
        # Artifact resolution verifies the recorded hash before any launch.
        _, data = store.artifact(document_id, session_id, revision, 'native')
        directory = store.authorize(document_id, session_id) / ('desktop-' + uuid.uuid4().hex)
        directory.mkdir(mode=0o700)
        native = directory / 'part.sc'
        with native.open('xb') as handle:
            handle.write(data)
        try:
            options = {'start_new_session': True} if os.name == 'posix' else {
                'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
            process = subprocess.Popen([str(executable), str(native)], cwd=directory,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        except OSError as error:
            shutil.rmtree(directory)
            raise CadError('SolidCraft GUI launch failed: ' + str(error)) from error
        self.processes.append(process)
        return {'status': 'requested', 'revision': revision,
                'message': 'Ouverture demandée dans SolidCraft. Les modifications restent dans une copie indépendante.'}
