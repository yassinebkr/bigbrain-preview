"""Parametric design intent and native document quality checks."""

import json
import math
import zipfile
from typing import Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, Identity


ORGANIZATION_COMMANDS = frozenset({
    'body.rename', 'timeline.rename', 'timeline.group', 'timeline.rename_group',
    'timeline.move_to_group', 'browser.group', 'browser.rename_group',
    'browser.move', 'browser.visibility', 'parameters.import', 'parameters.rename',
    'parameters.comment',
})


def allowed_cad_command(name):
    return isinstance(name, str) and (name.startswith(('solid.', 'sketch.', 'pattern.', 'construct.'))
                                     or name == 'parameters.change' or name in ORGANIZATION_COMMANDS)


class DesignParameter(Contract):
    name: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
    expression: str = Field(min_length=1, max_length=500)
    unit: Literal['mm', 'deg', '']
    purpose: str = Field(min_length=3, max_length=500)
    source_dimension: Identity | None = None
    dependencies: tuple[str, ...] = Field(default=(), max_length=32)


class SketchIntent(Contract):
    name: Identity
    purpose: str = Field(min_length=3, max_length=500)
    expected_dof: int = Field(default=0, strict=True, ge=0, le=64)
    freedom_reason: str | None = Field(default=None, min_length=10, max_length=500)

    @model_validator(mode='after')
    def explain_freedom(self):
        if self.expected_dof and not self.freedom_reason:
            raise ValueError('Intentional sketch freedom requires an explanation')
        return self


class FeatureIntent(Contract):
    name: Identity
    purpose: str = Field(min_length=3, max_length=500)


class DesignGroup(Contract):
    name: Identity
    features: tuple[Identity, ...] = Field(default=(), max_length=32)
    sketches: tuple[Identity, ...] = Field(default=(), max_length=16)
    bodies: tuple[Identity, ...] = Field(default=(), max_length=8)


class CadWorkflow(Contract):
    parameters: tuple[DesignParameter, ...] = Field(default=(), max_length=32)
    sketches: tuple[SketchIntent, ...] = Field(default=(), max_length=16)
    features: tuple[FeatureIntent, ...] = Field(min_length=1, max_length=32)
    bodies: tuple[Identity, ...] = Field(min_length=1, max_length=8)
    groups: tuple[DesignGroup, ...] = Field(min_length=1, max_length=16)
    primitive_reason: str | None = Field(default=None, min_length=10, max_length=500)

    @model_validator(mode='after')
    def references(self):
        for items in (self.parameters, self.sketches, self.features, self.groups):
            if len({item.name for item in items}) != len(items):
                raise ValueError('Design names must be unique within their category')
        if len(set(self.bodies)) != len(self.bodies):
            raise ValueError('Body names must be unique')
        if not self.sketches and not self.primitive_reason:
            raise ValueError('A construction using primitives requires its design rationale')
        parameters = {item.name: item for item in self.parameters}
        visiting, visited = set(), set()
        def visit(name):
            if name in visiting:
                raise ValueError('Parameter dependencies contain a cycle')
            if name in visited:
                return
            visiting.add(name)
            for dependency in parameters[name].dependencies:
                if dependency not in parameters:
                    raise ValueError(f'Unknown parameter dependency {dependency}')
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
        for name in parameters:
            visit(name)
        for field, expected in [('features', {item.name for item in self.features}),
                                ('sketches', {item.name for item in self.sketches}), ('bodies', set(self.bodies))]:
            members = [name for group in self.groups for name in getattr(group, field)]
            if len(set(members)) != len(members) or set(members) != expected:
                raise ValueError(f'Organization must place every {field} item in exactly one group')
        if not {item.name for item in self.sketches} <= {item.name for item in self.features}:
            raise ValueError('Every sketch must be a declared history feature')
        return self

    def parameter_command(self):
        return {'command': 'parameters.import', 'params': {'text': json.dumps([
            {'name': item.name, 'expression': item.expression, 'unit': item.unit, 'comment': item.purpose}
            for item in self.parameters], ensure_ascii=False)}}

    def sketch_diagnostics(self, sketch):
        """Check an observed profile before a solid operation consumes it."""
        name = sketch.get('name')
        intent = next((item for item in self.sketches if item.name == name), None)
        if intent is None:
            return [f'{name}: sketch has no declared design intent']
        errors = []
        if (sketch.get('status') != 'solved' or sketch.get('failing') or
                sketch.get('dof') != intent.expected_dof or
                (intent.expected_dof == 0 and sketch.get('fully_constrained') is not True)):
            errors.append(f'{name}: solver status or degrees of freedom differ from design intent')
        projected_links = {link.get('id') for link in sketch.get('links', [])
                           if link.get('kind') == 'project' and isinstance(link.get('source'), dict)
                           and link['source'].get('type') and link.get('id')}
        # Native dimension placement projects a fixed construction axis. Its
        # source link distinguishes a reference from a fixed functional curve.
        if any(curve.get('fixed') and not (curve.get('construction')
                and curve.get('link') in projected_links) for curve in sketch.get('curves', [])):
            errors.append(f'{name}: blanket curve fixation replaces dimensional intent')
        dimensional = {'length', 'diameter', 'radius', 'distance_x', 'distance_y', 'angle'}
        if not intent.expected_dof and not sketch.get('links') and not any(
                item.get('type') in dimensional and not item.get('reference', False)
                for item in sketch.get('constraints', [])):
            errors.append(f'{name}: no driving dimension or projected reference')
        return errors

    def diagnostics(self, design, graph, drawing=None):
        """Compare design intent to solver and dependency observations."""
        errors = []
        if (not all(isinstance(design.get(key), list) for key in ('params', 'timeline', 'sketches', 'bodies'))
                or not all(key in graph for key in ('cycles', 'errors', 'edges', 'nodes'))):
            return ['Native design or dependency observation is incomplete']
        if graph.get('cycles') or graph.get('errors'):
            errors.append('Native parameter graph reports cycles or errors')
        actual_params = {item['name']: item for item in design.get('params', []) if not item.get('model')}
        expected_params = {item.name: item for item in self.parameters}
        if set(actual_params) != set(expected_params):
            errors.append('Native user parameter inventory differs from declared parameters')
        dimensions = {item.id: item for item in drawing.dimensions} if drawing else {}
        edges = {tuple(item) for item in graph.get('edges', [])}
        for parameter in self.parameters:
            observed = actual_params.get(parameter.name, {})
            value = observed.get('value')
            if observed.get('error') or observed.get('unit') != parameter.unit or isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                errors.append(f'{parameter.name}: native value, unit or evaluation error')
            elif str(observed.get('expression', '')).strip() != parameter.expression.strip():
                errors.append(f'{parameter.name}: native expression differs from design intent')
            elif parameter.source_dimension:
                dimension = dimensions.get(parameter.source_dimension)
                unit = 'deg' if dimension and dimension.unit == 'degree' else 'mm'
                expected = dimension.value * (25.4 if dimension.unit == 'inch' else 1) if dimension and dimension.value is not None else None
                # The native evaluator stores angular values in radians while
                # the parameter's declared display unit remains degrees.
                canonical = math.degrees(value) if parameter.unit == 'deg' else value
                if expected is None or unit != parameter.unit or not math.isclose(canonical, expected, abs_tol=1e-8, rel_tol=1e-10):
                    errors.append(f'{parameter.name}: value differs from its authoritative dimension')
            actual_dependencies = {dependency for user, dependency in edges
                                   if user == parameter.name and dependency in expected_params}
            if actual_dependencies != set(parameter.dependencies):
                errors.append(f'{parameter.name}: declared dependencies differ from the native graph')
        features = design.get('timeline', [])
        if {item.get('name') for item in features} != {item.name for item in self.features} or len(features) != len(self.features):
            errors.append('Native history differs from the named feature inventory')
        for feature in features:
            if feature.get('error') or feature.get('warning') or feature.get('suppressed') or feature.get('rolled_back'):
                errors.append(f'{feature.get("name")}: history error, warning or inactive feature')
        sketches = {item.get('name'): item for item in design.get('sketches', [])}
        if set(sketches) != {item.name for item in self.sketches}:
            errors.append('Native sketch inventory differs from the declared sketches')
        for intent in self.sketches:
            sketch = sketches.get(intent.name, {})
            errors.extend(self.sketch_diagnostics(sketch))
        if {item.get('name') for item in design.get('bodies', [])} != set(self.bodies):
            errors.append('Native bodies differ from the named body inventory')
        return errors

    async def arrange(self, session, design, existing_native=None):
        """Resolve names to native IDs before grouping and hide consumed sketches."""
        sketches = {item['name']: str(item['id']) for item in design['sketches']}
        existing = self.read_native(existing_native) if existing_native else {}
        for group in self.groups:
            commands = []
            if group.features:
                old = [item for item in existing.get('timeline_groups', []) if item['name'] == group.name]
                if len(old) > 1:
                    raise ValueError('History group name is ambiguous')
                commands.append({'command': 'timeline.move_to_group' if old else 'timeline.group',
                    'params': {'group': old[0]['id'], 'features': list(group.features)} if old else
                              {'name': group.name, 'features': list(group.features)}})
            for folder, members in [('sketches', [sketches[name] for name in group.sketches]), ('bodies', list(group.bodies))]:
                if members:
                    old = [item for item in existing.get('browser_groups', []) if item['name'] == group.name and item['folder'] == folder]
                    if len(old) > 1:
                        raise ValueError('Browser group name is ambiguous')
                    commands.append({'command': 'browser.move' if old else 'browser.group',
                        'params': {'group': old[0]['id'], 'folder': folder, 'items': members} if old else
                                  {'name': group.name, 'folder': folder, 'items': members}})
            if commands:
                await session.batch(commands)
        if sketches:
            await session.batch([{'command': 'browser.visibility', 'params': {'items': list(sketches), 'visible': False}}])

    @staticmethod
    def read_native(path):
        with zipfile.ZipFile(path) as archive:
            entry = archive.getinfo('document.json')
            if entry.file_size > 16000000:
                raise ValueError('Native document organization exceeds its inspection size limit')
            document = json.loads(archive.read(entry))
        if document.get('format') != 'solidcraft/45':
            raise ValueError('Native organization reader requires the qualified solidcraft/45 format')
        return document

    def saved_diagnostics(self, path, design):
        """Inspect group membership from the exact native artifact being delivered."""
        document = self.read_native(path)
        features = {item['name']: item['id'] for item in design['timeline']}
        sketches = {item['name']: str(item['id']) for item in design['sketches']}
        errors = []
        for group in self.groups:
            if group.features:
                actual = [item for item in document.get('timeline_groups', []) if item['name'] == group.name]
                if len(actual) != 1 or set(actual[0].get('features', [])) != {features[name] for name in group.features}:
                    errors.append(f'{group.name}: saved history group membership differs')
            for folder, members in [('sketches', {sketches[name] for name in group.sketches}), ('bodies', set(group.bodies))]:
                if members:
                    actual = [item for item in document.get('browser_groups', []) if item['name'] == group.name and item['folder'] == folder]
                    if len(actual) != 1 or set(actual[0].get('items', [])) != members:
                        errors.append(f'{group.name}: saved {folder} group membership differs')
        if any(item.get('visible') for item in design.get('sketches', [])):
            errors.append('Consumed construction sketches remain visible')
        return errors
