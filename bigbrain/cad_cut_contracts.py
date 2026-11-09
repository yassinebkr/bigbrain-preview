"""Removal intent and geometric end limits for native CAD cuts."""

import math
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator
from .cad_resources import check_cut_index

from .cad_contracts import Contract, Finite, Identity, Vector

Coordinate = Finite | Annotated[str, Field(min_length=1, max_length=200)]


class CutBoundary(Contract):
    label: str = Field(min_length=1, max_length=200)
    origin_mm: tuple[Coordinate, Coordinate, Coordinate] = Field(
        description='A point on the actual material opening or stop plane. For an opening, choose existing material on that face rather than the center of an already empty bore.')
    outward_normal: Vector
    role: Literal['opening', 'stop']
    alignment_tolerance_mm: float = Field(default=0, ge=0, le=0.05, allow_inf_nan=False)

    @model_validator(mode='after')
    def unit_normal(self):
        if self.alignment_tolerance_mm and self.role != 'opening':
            raise ValueError('Only opening boundaries support measured alignment')
        if not math.isclose(sum(value * value for value in self.outward_normal), 1, abs_tol=1e-8):
            raise ValueError('Cut boundary requires a unit outward normal')
        return self


class CutIntent(Contract):
    id: Identity
    command_index: Annotated[int, AfterValidator(check_cut_index)] = Field(strict=True, ge=0, le=95,
        description='Zero-based command index in this list. Group indices restart at zero; the runtime assembles cumulative recipe indices.')
    feature_id: Identity = Field(description='The drawing feature_id of a referenced dimension; native timeline feature names belong in command.params.name.')
    dimension_ids: tuple[Identity, ...] = Field(min_length=1, max_length=16)
    kind: Literal['through', 'blind']
    targets: tuple[Identity, ...] = Field(min_length=1, max_length=16)
    boundaries: tuple[CutBoundary, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def bounded_removal(self):
        if len(set(self.targets)) != len(self.targets):
            raise ValueError('Cut target identities must be unique')
        openings = sum(boundary.role == 'opening' for boundary in self.boundaries)
        stops = sum(boundary.role == 'stop' for boundary in self.boundaries)
        if self.kind == 'through' and (openings < 2 or stops):
            raise ValueError('Through cuts require at least two opening limits')
        if self.kind == 'blind' and (not openings or not stops):
            raise ValueError('Blind cuts require entry and stop limits')
        return self


def is_removal_command(command):
    name, params = command['command'], command['params']
    return name == 'solid.hole' or str(params.get('operation', '')).lower() in {'cut', 'subtract', 'difference'}


def validate_cut_intents(commands, intents, drawing=None):
    """Bind removal limits to their command, explicit targets and drawing provenance."""
    commands = [item if isinstance(item, dict) else {'command': item.command, 'params': item.params}
                for item in commands]
    indices = [intent.command_index for intent in intents]
    if len(set(indices)) != len(indices) or len({intent.id for intent in intents}) != len(intents):
        raise ValueError('Cut intents require unique command indices and identities')
    required = {index for index, command in enumerate(commands) if is_removal_command(command)}
    if set(indices) != required:
        raise ValueError('Every removal command requires its own cut intent; '
                         f'missing indices={sorted(required - set(indices))}; '
                         f'non-removal indices={sorted(set(indices) - required)}; '
                         f'required indices={sorted(required)}')
    dimensions = {item.id: item for item in drawing.dimensions} if drawing else None
    for intent in intents:
        params = commands[intent.command_index]['params']
        targets = [params.get('target')] if commands[intent.command_index]['command'] == 'solid.combine' else params.get('targets')
        if not isinstance(targets, (list, tuple)) or set(targets) != set(intent.targets) or '*' in targets:
            raise ValueError('Cut intent requires the exact explicit command targets')
        if dimensions is not None:
            if not set(intent.dimension_ids) <= dimensions.keys():
                raise ValueError('Cut intent references an unknown drawing dimension')
            if intent.feature_id not in {dimensions[key].feature_id for key in intent.dimension_ids}:
                expected = sorted({dimensions[key].feature_id for key in intent.dimension_ids})
                raise ValueError(f'Cut intent feature must match its drawing dimensions: '
                                 f'{intent.feature_id!r} is a native name or unknown drawing feature; '
                                 f'use one of {expected}. Keep the native feature name in command.params.name.')
