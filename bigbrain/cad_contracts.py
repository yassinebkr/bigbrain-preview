"""Versioned CAD artifacts, geometry observations and delivery gates."""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Hash = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Identity = Annotated[str, Field(min_length=1, max_length=160)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Vector = tuple[Finite, Finite, Finite]


class Contract(BaseModel):
    """Immutable records assembled by the runtime from captured observations."""

    model_config = ConfigDict(extra='forbid', frozen=True, revalidate_instances='always')
    schema_version: Literal['1.0'] = '1.0'


class CadArtifact(Contract):
    path: str = Field(min_length=1, max_length=500)
    format: Literal['solidcraft', 'step', 'stl', 'png']
    sha256: Hash
    size_bytes: int = Field(strict=True, gt=0)
    source_sha256: Hash | None = None

    @field_validator('path')
    @classmethod
    def canonical_path(cls, value):
        # Keep references portable, including Windows drive and stream rules.
        path = PurePosixPath(value)
        if ('\\' in value or '\x00' in value or ':' in value
                or PureWindowsPath(value).drive or path.is_absolute()
                or path.as_posix() != value or not path.parts
                or any(part.startswith('.') for part in path.parts)):
            raise ValueError('Artifact path must be canonical and project-relative')
        return value


class CadRevision(Contract):
    project_id: Identity
    document_id: Identity
    revision: int = Field(strict=True, ge=1)
    engine: Literal['solidcraft'] = 'solidcraft'
    engine_version: Identity
    units: Literal['mm'] = 'mm'
    native: CadArtifact
    exports: tuple[CadArtifact, ...] = Field(default=(), max_length=16)

    @model_validator(mode='after')
    def artifact_bindings(self):
        if self.native.format != 'solidcraft' or self.native.source_sha256 is not None:
            raise ValueError('Native artifact must identify the editable source')
        paths = [self.native.path, *(item.path for item in self.exports)]
        if len(paths) != len(set(paths)):
            raise ValueError('Artifact paths must be unique')
        for item in self.exports:
            if item.format not in {'step', 'stl'} or item.source_sha256 != self.native.sha256:
                raise ValueError('Export must reference this native revision')
        return self


class GeometryObservation(Contract):
    source_sha256: Hash
    evidence_ref: Identity
    body_count: int = Field(strict=True, ge=0)
    closed_solid: bool = Field(strict=True)
    bounds_min_mm: Vector
    bounds_max_mm: Vector
    volume_mm3: Finite = Field(ge=0)

    @model_validator(mode='after')
    def ordered_bounds(self):
        if any(low > high for low, high in zip(self.bounds_min_mm, self.bounds_max_mm)):
            raise ValueError('Geometry bounds must be ordered')
        return self


class CriterionObservation(Contract):
    criterion_id: Identity
    source_sha256: Hash
    status: Literal['passed', 'failed', 'inconclusive']
    evidence_ref: Identity
    diagnostic: str = Field(min_length=1, max_length=2000)
    label: str | None = Field(default=None, max_length=500)
    metric: Literal['dimensions_mm', 'volume_mm3', 'body_count', 'closed_solid'] | None = None
    observed: tuple[Finite, ...] | None = Field(default=None, max_length=3)
    expected: tuple[Finite, ...] | None = Field(default=None, max_length=3)
    absolute_tolerance: Finite | None = None
    relative_tolerance: Finite | None = None
    observed_intervals_mm: tuple[tuple[Finite, Finite], ...] | None = Field(default=None, max_length=16)
    expected_intervals_mm: tuple[tuple[Finite, Finite], ...] | None = Field(default=None, max_length=16)


class CadDelivery(Contract):
    """Closed-part result assembled after measurements and contract checks."""

    specification_id: Identity
    required_criteria: tuple[Identity, ...] = Field(min_length=1, max_length=64)
    required_exports: tuple[Literal['step', 'stl'], ...] = Field(default=(), max_length=2)
    document: CadRevision
    geometry: GeometryObservation
    checks: tuple[CriterionObservation, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def delivery_gate(self):
        native_hash = self.document.native.sha256
        observed_ids = [check.criterion_id for check in self.checks]
        if (len(set(self.required_criteria)) != len(self.required_criteria)
                or len(set(observed_ids)) != len(observed_ids)
                or set(observed_ids) != set(self.required_criteria)):
            raise ValueError('Delivery requires exactly the specified criteria')
        if (self.geometry.source_sha256 != native_hash
                or any(check.source_sha256 != native_hash for check in self.checks)):
            raise ValueError('Delivery observations must match the native revision')
        geometry = self.geometry
        if (geometry.body_count < 1 or not geometry.closed_solid or geometry.volume_mm3 <= 0
                or any(low >= high for low, high in zip(geometry.bounds_min_mm, geometry.bounds_max_mm))):
            raise ValueError('Delivery requires a measured closed solid with positive dimensions')
        if any(check.status != 'passed' for check in self.checks):
            raise ValueError('Delivery requires passing criterion observations')
        if not set(self.required_exports) <= {item.format for item in self.document.exports}:
            raise ValueError('Delivery is missing a required export')
        return self


class CadPreview(Contract):
    project_id: Identity
    document_id: Identity
    revision: int = Field(strict=True, ge=1)
    image: CadArtifact
    width: int = Field(strict=True, gt=0, le=4096)
    height: int = Field(strict=True, gt=0, le=4096)

    @model_validator(mode='after')
    def image_binding(self):
        if self.image.format != 'png' or self.image.source_sha256 is None:
            raise ValueError('Preview requires a PNG bound to its native source')
        return self

    def is_current(self, document: CadRevision) -> bool:
        return ((self.project_id, self.document_id, self.revision, self.image.source_sha256)
                == (document.project_id, document.document_id, document.revision, document.native.sha256))


TRANSITIONS = {
    'queued': {'modeling', 'failed', 'cancelled', 'blocked'},
    'modeling': {'checking', 'failed', 'cancelled', 'blocked'},
    'checking': {'modeling', 'ready', 'failed', 'cancelled', 'blocked'},
    'ready': set(), 'failed': set(), 'cancelled': set(), 'blocked': set(),
}


class CadRun(Contract):
    run_id: Identity
    project_id: Identity
    document_id: Identity
    specification_id: Identity
    state: Literal['queued', 'modeling', 'checking', 'ready', 'failed', 'cancelled', 'blocked'] = 'queued'
    delivery: CadDelivery | None = None
    diagnostic: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode='after')
    def outcome(self):
        if (self.state == 'ready') != (self.delivery is not None):
            raise ValueError('Ready state requires a validated delivery')
        if self.state in {'failed', 'cancelled', 'blocked'} and not self.diagnostic:
            raise ValueError('Stopped work requires a diagnostic')
        if self.delivery is not None:
            document = self.delivery.document
            if ((document.project_id, document.document_id, self.delivery.specification_id)
                    != (self.project_id, self.document_id, self.specification_id)):
                raise ValueError('Delivery must belong to this run project, document and specification')
        return self

    def transition(self, state: str, *, delivery=None, diagnostic=None):
        """Keep terminal outcomes stable; repairs return checking to modeling."""
        if state not in TRANSITIONS[self.state]:
            raise ValueError(f'Invalid CAD transition: {self.state} → {state}')
        return type(self).model_validate({**self.model_dump(), 'state': state,
                                         'delivery': delivery, 'diagnostic': diagnostic})
