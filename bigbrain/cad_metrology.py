"""Capability-based CAD measurement providers shared by Linux and Windows."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MeasurementSource:
    native_sha256: str
    step_path: Path
    step_sha256: str
    native_bodies: list[dict]


class MeasurementProvider(Protocol):
    name: str
    capabilities: frozenset[str]

    async def inspect(self, source: MeasurementSource, session) -> dict: ...


class NativeMeasurements:
    name = 'solidcraft-native'
    # Add precise volume here only after the native implementation passes
    # the same reference and defect qualification as the STEP provider.
    capabilities = frozenset({'cylinders'})

    async def inspect(self, source, session):
        bodies = {}
        for body in source.native_bodies:
            topology = await session.tool('body_topology', {'body': body['name']})
            if topology.get('body') != body['name']:
                raise ValueError('Native topology belongs to another body')
            faces = []
            for face in topology.get('faces', []):
                # SolidCraft's exact flag describes face-name history.
                # Its cylinder geometry is obtained from the native surface API.
                faces.append({**face, 'analytic_surface': isinstance(face.get('cylinder'), dict)})
            bodies[body['name']] = {**topology, 'faces': faces}
        return {'method': self.name, 'units': 'mm', 'source_sha256': source.native_sha256,
                'bodies': bodies}


class StepMeasurements:
    name = 'occt-step-surfaces'
    capabilities = frozenset({'cylinders', 'volume', 'bounds', 'vertices', 'solid_validity'})

    async def inspect(self, source, session):
        from .cad_step import inspect_step
        result = await asyncio.to_thread(inspect_step, source.step_path, source.native_bodies)
        return {**result, 'source_sha256': source.native_sha256, 'step_sha256': source.step_sha256}


class MeasurementRouter:
    """Choose qualified capabilities while keeping acceptance criteria shared."""

    def __init__(self, providers=None):
        self.providers = tuple(providers if providers is not None else (NativeMeasurements(), StepMeasurements()))

    async def inspect(self, source, session):
        required = ('cylinders', 'volume', 'bounds', 'vertices', 'solid_validity')
        selected = {}
        for capability in required:
            provider = next((item for item in self.providers if capability in item.capabilities), None)
            if provider is None:
                raise ValueError(f'No qualified CAD measurement provider for {capability}')
            selected[capability] = provider
        results = {}
        for provider in self.providers:
            if any(item is provider for item in selected.values()):
                result = await provider.inspect(source, session)
                if result.get('units') != 'mm' or result.get('source_sha256') != source.native_sha256:
                    raise ValueError('CAD measurement provider returned inconsistent units or revision')
                if set(result.get('bodies', {})) != {body['name'] for body in source.native_bodies}:
                    raise ValueError('CAD measurement provider returned an inconsistent body inventory')
                results[provider.name] = result
        by_capability = {key: results[value.name] for key, value in selected.items()}
        bodies = {}
        for name in by_capability['solid_validity']['bodies']:
            bodies[name] = {
                **by_capability['solid_validity']['bodies'][name],
                **{key: by_capability['bounds']['bodies'][name][key]
                   for key in ('bounds_min_mm', 'bounds_max_mm')},
                'edges': by_capability['vertices']['bodies'][name]['edges'],
                'faces': by_capability['cylinders']['bodies'][name]['faces'],
                'volume_mm3': by_capability['volume']['bodies'][name]['volume_mm3'],
            }
        return {'method': 'cad-measurements/1', 'units': 'mm',
                'source_sha256': source.native_sha256, 'step_sha256': source.step_sha256,
                'capabilities': {key: provider.name for key, provider in selected.items()},
                'providers': results, 'bodies': bodies,
                'volume_mm3': sum(body['volume_mm3'] for body in bodies.values())}
