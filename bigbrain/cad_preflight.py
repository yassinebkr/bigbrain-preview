"""Aggregate CAD verification diagnostics before native construction."""

import math


def measurement_diagnostics(plan):
    errors, covered = [], set()
    if plan.drawing is None:
        return (['Requirement measurements require a drawing definition'] if plan.measurements else []) + [
            f'{section.id}: Raw section requires a drawing requirement measurement'
            for section in plan.sections if section.intervals_mm is None]
    dimensions = {item.id: item for item in plan.drawing.dimensions}

    def bind(identity, value, *, angular=False):
        dimension = dimensions.get(identity)
        if dimension is None or dimension.value is None or (dimension.unit == 'degree') != angular:
            raise ValueError(f'Drawing measurement {identity!r} requires a declared, resolved linear dimension')
        target = dimension.value * (25.4 if dimension.unit == 'inch' else 1)
        if not math.isclose(value, target, abs_tol=1e-8, rel_tol=1e-10):
            raise ValueError(f'Measurement target differs from drawing dimension {identity}: {value:g} versus {target:g}')
        covered.add(identity)

    def attempt(label, operation):
        try:
            operation()
        except (ValueError, IndexError, KeyError) as error:
            errors.append(f'{label}: {error}')

    for criterion in plan.criteria:
        for identity, index in criterion.dimension_bindings.items():
            attempt(criterion.id, lambda: bind(identity, criterion.expected[index]))
    for cylinder in plan.cylinders:
        if cylinder.radius_binding:
            def radius():
                dimension = dimensions.get(cylinder.radius_binding)
                if dimension is None or dimension.kind not in {'radius', 'diameter'}:
                    raise ValueError('Analytic round-surface binding requires a radius or diameter dimension')
                bind(cylinder.radius_binding, cylinder.radius_mm * (2 if dimension.kind == 'diameter' else 1))
            attempt(cylinder.id, radius)
        for identity, axis in cylinder.center_bindings.items():
            attempt(cylinder.id, lambda: bind(identity, cylinder.center_mm[axis]))
    for section in plan.sections:
        for binding in section.bindings:
            def section_binding():
                value = section.quantity(binding)
                if binding.subtract is not None:
                    target = next((item for item in plan.sections if item.id == binding.subtract.section_id), None)
                    if target is None:
                        raise ValueError('Dimension difference references an unknown measured section')
                    if target.axis != section.axis:
                        raise ValueError('Dimension difference requires the same coordinate axis')
                    if (target.id == section.id and binding.quantity == binding.subtract.quantity
                            and binding.interval == binding.subtract.interval):
                        raise ValueError('Dimension difference requires distinct measurements')
                    value -= target.quantity(binding.subtract)
                if binding.angle_denominator is not None:
                    operand = binding.angle_denominator
                    target = next((item for item in plan.sections if item.id == operand.section_id), None)
                    if target is None:
                        raise ValueError('Angle references an unknown measured section')
                    if target.axis == section.axis:
                        raise ValueError('Angle rise and run require perpendicular measurement axes')
                    run = target.quantity(operand)
                    if value <= 0 or run <= 0:
                        raise ValueError('Angle requires positive measured rise and run')
                    value = math.degrees(math.atan2(value, run))
                bind(binding.dimension_id, value, angular=binding.angle_denominator is not None)
            attempt(f'{section.id}/{binding.dimension_id}', section_binding)
    for measurement in plan.measurements:
        def method():
            measurement.validate_sources(plan)
            covered.add(measurement.dimension_id)
        attempt(measurement.id, method)
    used_sections = {operand.reference for method in plan.measurements
        for operand in (method.first, method.second, method.rise_origin, method.run_origin)
        if operand is not None and operand.source == 'section'}
    for section in plan.sections:
        if section.intervals_mm is None and section.id not in used_sections:
            errors.append(f'{section.id}: Raw section must feed a requirement measurement')
    missing = [item.id for item in plan.drawing.dimensions if item.critical and item.id not in covered]
    if missing:
        errors.append('Every critical drawing dimension requires a geometric measurement binding: ' + ', '.join(missing))
    return errors


def command_diagnostics(commands, *, existing_document=False):
    """Check parameter creation rules documented by the qualified engine."""
    if existing_document:
        return []
    known, errors = set(), []
    for index, command in enumerate(commands):
        if command.command != 'parameters.change':
            continue
        params = command.params
        if isinstance(params.get('changes'), dict):
            missing = set(params['changes']) - known
            if missing:
                errors.append(f'commands[{index}]: parameter changes requires existing names: '
                              + ', '.join(sorted(missing)) + '. Create parameters with name/expression first.')
        if isinstance(params.get('name'), str) and 'expression' in params:
            known.add(params['name'])
    return errors
