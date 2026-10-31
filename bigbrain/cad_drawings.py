"""Drawing evidence, dimension dependencies and clarification gates for CAD."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, Finite, Hash, Identity

Text = Annotated[str, Field(min_length=1, max_length=1000)]


class DrawingSource(Contract):
    attachment_id: str = Field(pattern=r'^att-[a-f0-9]{12}$')
    sha256: Hash
    # Normalized image coordinates identify the passage read by the model.
    region: tuple[Finite, Finite, Finite, Finite] = (0, 0, 1, 1)

    @model_validator(mode='after')
    def bounded_region(self):
        x0, y0, x1, y1 = self.region
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError('Drawing region must lie within the source image')
        return self


class DrawingDimension(Contract):
    id: Identity
    feature_id: Identity
    label: Text
    kind: Literal['length', 'diameter', 'radius', 'depth', 'position', 'angle']
    value: Finite | None = None
    unit: Literal['mm', 'inch', 'degree']
    origin: Literal['explicit', 'derived', 'unresolved']
    sources: tuple[DrawingSource, ...] = Field(min_length=1, max_length=8)
    annotation: Text
    dependencies: tuple[Identity, ...] = Field(default=(), max_length=16)
    derivation: Text | None = None
    critical: bool = True

    @model_validator(mode='after')
    def evidence_shape(self):
        if (self.value is None) != (self.origin == 'unresolved'):
            raise ValueError('Resolved dimensions require a finite value')
        if self.origin == 'derived':
            if not self.dependencies or not self.derivation:
                raise ValueError('Derived dimensions require dependencies and reasoning')
        elif self.dependencies or self.derivation:
            raise ValueError('Only derived dimensions carry dependencies')
        if self.kind == 'angle' and self.unit != 'degree':
            raise ValueError('Angles require degree units')
        if self.kind != 'angle' and self.unit == 'degree':
            raise ValueError('Linear dimensions require length units')
        if self.value is not None and self.kind != 'position' and self.value <= 0:
            raise ValueError('Feature sizes must be positive')
        return self


class DrawingIssue(Contract):
    id: Identity
    question: Text
    dimension_ids: tuple[Identity, ...] = Field(default=(), max_length=16)
    reason: Literal['illegible', 'missing', 'conflicting', 'unsupported', 'units']
    blocking: bool = True


class DrawingSpecification(Contract):
    """Model interpretation retained alongside the immutable CAD contract."""

    title: str = Field(min_length=1, max_length=160)
    sources: tuple[DrawingSource, ...] = Field(min_length=1, max_length=8)
    views: tuple[Text, ...] = Field(min_length=1, max_length=16)
    dimensions: tuple[DrawingDimension, ...] = Field(min_length=1, max_length=64)
    issues: tuple[DrawingIssue, ...] = Field(default=(), max_length=32)

    @model_validator(mode='after')
    def references(self):
        ids = {item.id for item in self.dimensions}
        if len(ids) != len(self.dimensions):
            raise ValueError('Drawing dimension identifiers must be unique')
        if len({item.id for item in self.issues}) != len(self.issues):
            raise ValueError('Drawing issue identifiers must be unique')
        bindings = {(source.attachment_id, source.sha256) for source in self.sources}
        for item in self.dimensions:
            if any((source.attachment_id, source.sha256) not in bindings for source in item.sources):
                raise ValueError('Dimension evidence must reference the declared image bytes')
            if not set(item.dependencies) <= ids:
                raise ValueError('Derived dimension references an unknown dimension')
        if any(not set(issue.dimension_ids) <= ids for issue in self.issues):
            raise ValueError('Drawing issue references an unknown dimension')
        by_id = {item.id: item for item in self.dimensions}
        visited = set()

        def visit(identity, stack):
            if identity in stack:
                raise ValueError('Drawing dimension dependencies must be acyclic')
            if identity in visited:
                return
            dimension = by_id[identity]
            for dependency in dimension.dependencies:
                if by_id[dependency].origin == 'unresolved' and dimension.origin != 'unresolved':
                    raise ValueError('A resolved derivation depends on an unresolved dimension')
                visit(dependency, stack | {identity})
            visited.add(identity)

        for identity in ids:
            visit(identity, set())
        return self

    def clarification_questions(self) -> tuple[str, ...]:
        questions = [issue.question for issue in self.issues if issue.blocking]
        covered = {identity for issue in self.issues if issue.blocking for identity in issue.dimension_ids}
        questions.extend(f'Préciser la cote : {item.label} ({item.annotation}).'
                         for item in self.dimensions
                         if item.critical and item.origin == 'unresolved' and item.id not in covered)
        return tuple(questions)

    def require_resolved(self):
        questions = self.clarification_questions()
        if questions:
            raise ValueError('Drawing requires clarification: ' + ' ; '.join(questions))
        return self
