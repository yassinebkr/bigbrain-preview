"""Version-scoped native limitations and editable construction strategies."""


QUALIFIED_HELIX_BUILDS = frozenset({
    '866a8ded1f66e0fbd6f01d6046502b2a62e98da6403c127edfdbce8a8e7a549e',
})


def native_input_diagnostics(commands, version='0.28.0'):
    """Reject a known untyped native axis fallback before opening a transaction."""
    if version != '0.28.0':
        return []
    errors = []
    for item in commands:
        if item['command'] != 'solid.revolve':
            continue
        axis = item['params'].get('axis')
        if not isinstance(axis, dict) or 'origin' not in axis:
            continue
        origin = axis['origin']
        values = ([origin.get(key) for key in ('x', 'y', 'z')] if isinstance(origin, dict)
                  else origin if isinstance(origin, list) else [])
        if len(values) != 3 or not all(type(value) in (int, float) and -1e9 < value < 1e9 for value in values):
            errors.append('solid.revolve axis.origin requires three finite numeric coordinates in 0.28.0. '
                          'The native parser silently replaces unsupported expressions with the world origin. '
                          'Use a named parametric construction axis for an editable axis position.')
    return errors


def construction_guidance(version, engine_sha256=None):
    """Expose measured examples and retirement cases for the current adapter."""
    if version != '0.28.0':
        return []
    guidance = [
        {'id': 'outer-union-before-continuous-bore', 'status': 'qualified_examples',
         'condition': 'A curved hollow pipe and annular flange fail native union.',
         'strategy': 'Join the solid exterior and solid flange, then remove the continuous bore.',
         'invariants': 'Preserve wall thickness, openings, original dimensions and native editable history.',
         'retirement_case': 'test_native_pipe_flange_union_and_parameter_edit[quarter-bend]',
         'qualified_cases': 'test_native_outer_union_before_bore_and_parameter_edit[aligned-tool-30/60]'},
        {'id': 'measured-opening-alignment', 'status': 'qualified_examples',
         'condition': 'Native Boolean healing displaces an opening within confirmed length tolerance.',
         'strategy': 'Declare alignment_tolerance_mm on the opening, bounded by confirmed tolerance and 0.05 mm. '
                     'The guard resolves the actual outward material plane and checks overruns against every body.',
         'invariants': 'Keep the strict collision check and explicit targets. Zero allowance remains strict.',
         'retirement_case': 'test_native_outer_union_before_bore_and_parameter_edit[extended-tool-60]',
         'qualified_cases': 'test_native_outer_union_before_bore_and_parameter_edit[aligned-tool-30/60]'},
        {'id': 'native-bore-mouth-chamfer', 'status': 'qualified_example',
         'condition': 'An explicit conical mouth cut stalls or fails.',
         'strategy': 'Observe actual bore-mouth topology, then use solid.chamfer on the intended edge.',
         'invariants': 'Preserve the chamfer dimension and independently check local geometry.',
         'qualified_cases': 'test_native_bore_mouth_chamfer_and_parameter_edit'},
        {'id': 'dimensioned-rounded-profile', 'status': 'qualified_example',
         'condition': 'sketch.draw.dimensioned creates a sketch.rectangle.rounded profile.',
         'strategy': 'Use numeric p0/p1 placement seeds. Bind functional width/height dimensions and '
                     'the native corner-radius expression to declared driving parameters; use locate:true.',
         'invariants': 'Preserve measured dimensions and verify the solver before extrusion. '
                       'Coordinate seeds alone do not establish driving dimensions.',
         'qualified_cases': 'test_native_rounded_profile_constraints_and_parameter_edit'},
        {'id': 'revolve-parametric-axis', 'status': 'qualified_example',
         'condition': 'solid.revolve explicit axis.origin contains parameter expressions.',
         'limitation': 'The 0.28.0 parser silently substitutes [0,0,0] for nonnumeric origins; '
                       'BigBrain rejects this input before mutation.',
         'strategy': 'Create named offset datum planes driven by the parameters, then '
                     'construct.axis.two_planes and use that axis by name in solid.revolve. '
                     'Observe its actual orientation before choosing the rotation direction.',
         'qualified_cases': 'test_native_revolve_with_parametric_datum_axis: quarter-circle solid profile, '
                            'radius and axial-plane edits, independent volume and bounds.',
         'invariants': 'Preserve parameter links, native history and measured geometry. '
                       'Combined flange/pipe geometry requires separate qualification.',
         'retirement_case': 'Replay the nonnumeric explicit-origin failure against a corrected native parser.'},
        {'id': 'axial-coil-volume', 'status': 'limited',
         'condition': 'A native coil uses a circular axial section in a screw sweep.',
         'limitation': 'The strict 1e-5 relative volume case fails. Integration convergence does not remove '
                       'the discrepancy. Quarter-turn composition and subdivided profile experiments also '
                       'fail that threshold. Local dimensional accuracy requires its own evidence.',
         'invariants': 'Preserve nominal radii, pitch, turns and verification tolerances. '
                       'Do not compensate by changing dimensions or reported volume.',
         'retirement_case': 'test_native_coil_and_parameter_edit'},
    ]
    if engine_sha256 in QUALIFIED_HELIX_BUILDS:
        guidance[-1] = {'id': 'axial-coil-volume', 'status': 'qualified_examples',
            'condition': 'The selected isolated 0.28.0 executable has the qualified helix interpolation patch.',
            'qualified_cases': 'Seven circular axial-section cases, 0.25 to seven turns, both pitch signs; '
                               'construction, pitch edit and reopening pass independent volume checks at 1e-5.',
            'limitation': 'Other profiles, local dimensions, high-turn performance and complete parts '
                          'require their own checks. The desktop installation retains its original kernel.',
            'invariants': 'Preserve nominal dimensions, editability and the confirmed verification tolerances.',
            'retirement_case': 'test_native_coil_and_parameter_edit and test_native_coil_precision_matrix'}
    return guidance
