"""Installed CAD command discovery and selected signature retrieval."""

from copy import deepcopy

from .cad_workflow import allowed_cad_command


class CadCommandCatalog(list):
    """Keep the initial reference compact while exposing all allowed command IDs."""

    skills = ('solidcraft-modeling', 'solidcraft-editing', 'solidcraft-checking')

    def __init__(self, initial, catalog, loader=None):
        super().__init__(initial)
        self.loader = loader
        self._retrieved_commands = {}
        self._retrieved_skills = {}
        self.catalog = {item['id']: {'id': item['id'], 'params': item['params']}
                        for item in catalog if allowed_cad_command(item['id'])}

    def selected(self, names):
        unknown = set(names) - self.catalog.keys()
        if unknown:
            raise ValueError('CAD command reference unavailable: ' + ', '.join(sorted(unknown)))
        return [self.catalog[name] for name in dict.fromkeys(names)]

    async def describe(self, names, skills=()):
        # Validate the whole request before contacting the native read-only tools.
        selected = self.selected(names)
        if set(skills) - set(self.skills):
            raise ValueError('CAD skill reference unavailable')
        if self.loader is None:
            if skills:
                raise ValueError('Native CAD skill reader is unavailable')
            result = {'command_reference': selected}
        else:
            result = await self.loader(tuple(item['id'] for item in selected), tuple(dict.fromkeys(skills)))
        # Keep observed native references on this worker-local catalog. Repairs
        # receive the same versioned signatures and guides in their first packet.
        for item in result.get('command_reference', []):
            self._retrieved_commands[item['id']] = deepcopy(item)
        self._retrieved_skills.update(deepcopy(result.get('skill_reference', {})))
        return result

    def retrieved(self):
        """Return detached evidence already read during this worker execution."""
        return deepcopy({'command_reference': list(self._retrieved_commands.values()),
                         'skill_reference': self._retrieved_skills})

    def restore(self, value):
        """Restore owned references after the controller matches the native catalog."""
        commands, skills = value.get('command_reference', []), value.get('skill_reference', {})
        self.selected([item['id'] for item in commands])
        if set(skills) - set(self.skills):
            raise ValueError('Retained CAD guide is outside the native catalog')
        self._retrieved_commands = {item['id']: deepcopy(item) for item in commands}
        self._retrieved_skills = deepcopy(skills)
