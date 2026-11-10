"""Compare observed browser round trips with retained native CAD evidence."""

import argparse
import json
import math
from pathlib import Path

from bigbrain.cad_step import inspect_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--case', choices=['plate', 'drawing42'], required=True)
    parser.add_argument('--native-inspection', type=Path, required=True)
    parser.add_argument('--native-roundtrip', type=Path, required=True)
    parser.add_argument('--reference-step', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.evidence / 'browser-report.json').read_text())['cases'][args.case]
    native = json.loads(args.native_inspection.read_text())[0]
    roundtrip = json.loads(args.native_roundtrip.read_text())[0]
    failures = []

    def require(condition, label):
        if not condition:
            failures.append(label)

    def history(value):
        return [(entry['id'], entry['name'], entry['type'], entry.get('suppressed', False)) for entry in value['timeline']]

    def parameters(value):
        return {entry['name']: entry['expression'] for entry in value['params']}

    def sketches(value):
        return [{key: entry.get(key) for key in ['id', 'name', 'curves', 'profiles', 'dof', 'status']}
                for entry in value['sketches']]

    def geometry(value):
        return {body['name']: body for body in value['bodies']}

    def compare_geometry(actual, expected, label):
        a, b = geometry(actual), geometry(expected)
        require(a.keys() == b.keys(), label + ': body inventory')
        for name in a.keys() & b.keys():
            require(a[name]['closed'] and b[name]['closed'], label + ': closed solid')
            require(math.isclose(a[name]['volume_mm3'], b[name]['volume_mm3'], rel_tol=1e-7, abs_tol=1e-5), label + ': native volume')
            for side in ['min', 'max']:
                require(all(abs(x-y) <= 0.001 for x, y in zip(a[name]['bbox'][side], b[name]['bbox'][side])), label + ': bounds')

    require(report.get('status') == 'observed', report.get('error', 'Browser campaign incomplete'))
    if report.get('status') == 'observed':
        initial = report['initial']
        for stage in ['initial', 'edited', 'undone', 'redone', 'reopened']:
            value = report[stage]
            require(all(not entry.get('error') for entry in value['timeline']), stage + ': feature error')
            require(len(value['bodies']) == len(native['bodies']) and all(body['closed'] for body in value['bodies']), stage + ': closed body inventory')
        require(history(initial) == history(native), 'Initial named history differs from native')
        require(sketches(initial) == sketches(native), 'Initial sketch constraints differ from native')
        require(parameters(initial) == parameters(native), 'Initial parameters differ from native')
        compare_geometry(initial, native, 'Initial browser/native')
        require(history(roundtrip) == history(native), 'Native reopen history differs')
        require(sketches(roundtrip) == sketches(native), 'Native reopen sketch constraints differ')
        require(parameters(roundtrip) == parameters(native), 'Native reopen parameters differ')
        compare_geometry(roundtrip, native, 'Native reopen')
        name = report['parameter']['name']
        require(parameters(report['edited'])[name] != parameters(initial)[name], 'Parameter edit missing')
        edited_parameter = next(entry for entry in report['edited']['params'] if entry['name'] == name)
        require(math.isclose(edited_parameter['value'], report['parameter']['value'] + 1), 'Edited parameter value differs')
        require(geometry(report['edited']) != geometry(initial), 'Parameter edit has no observed geometric effect')
        for stage in ['undone', 'reopened']:
            value = report[stage]
            require(history(value) == history(initial), stage + ': history differs')
            require(sketches(value) == sketches(initial), stage + ': sketch constraints differ')
            require(parameters(value) == parameters(initial), stage + ': parameters differ')
            require(all(not entry.get('error') for entry in value['timeline']), stage + ': feature error')
            compare_geometry(value, initial, stage)
        require(parameters(report['redone']) == parameters(report['edited']), 'Redo parameters differ')
        compare_geometry(report['redone'], report['edited'], 'Redo')
        reference = inspect_step(args.reference_step, native['bodies'])
        exported = inspect_step(args.evidence / args.case / f'{args.case}-roundtrip.step', report['reopened']['bodies'])
        for body_name in reference['bodies']:
            a, b = exported['bodies'][body_name], reference['bodies'][body_name]
            require(math.isclose(a['volume_mm3'], b['volume_mm3'], rel_tol=1e-5), 'Independent STEP volume differs')
            for key in ['bounds_min_mm', 'bounds_max_mm']:
                require(all(abs(x-y) <= 0.001 for x, y in zip(a[key], b[key])), 'Independent STEP bounds differ')
        (args.evidence / args.case / 'step-inspection.json').write_text(json.dumps(exported, indent=2))
    result = {'case': args.case, 'status': 'failed' if failures else 'passed', 'failures': failures}
    (args.evidence / args.case / 'qualification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
