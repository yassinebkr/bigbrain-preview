"""Compare isolated worker geometry and history with retained native evidence."""

import argparse
import json
import math


def verify(report, reference, reopened):
    failures = []

    def require(condition, label):
        if not condition:
            failures.append(label)

    def history(value):
        return [(item['id'], item['name'], item['type'], item.get('suppressed', False)) for item in value['timeline']]

    def parameters(value):
        return {item['name']: item['expression'] for item in value['params']}

    def sketches(value):
        return [{key: item.get(key) for key in ('id', 'name', 'curves', 'profiles', 'dof', 'status')} for item in value['sketches']]

    def geometry(actual, expected, label):
        a = {body['name']: body for body in actual['bodies']}
        b = {body['name']: body for body in expected['bodies']}
        require(a.keys() == b.keys(), label + ': body inventory')
        for name in a.keys() & b.keys():
            require(a[name]['closed'] and b[name]['closed'], label + ': closed solid')
            require(math.isclose(a[name]['volume_mm3'], b[name]['volume_mm3'], rel_tol=1e-7, abs_tol=1e-5), label + ': volume')
            for side in ('min', 'max'):
                require(all(abs(x-y) <= 0.001 for x, y in zip(a[name]['bbox'][side], b[name]['bbox'][side])), label + ': bounds')

    require(report.get('status') == 'observed', 'Campaign incomplete')
    if report.get('status') != 'observed':
        return failures
    initial = report['initial']
    for label, value in [('initial', initial), ('undone', report['undone']), ('reopened', report['reopened']), ('native reopen', reopened)]:
        require(history(value) == history(reference), label + ': named history')
        require(parameters(value) == parameters(reference), label + ': parameters')
        require(sketches(value) == sketches(reference), label + ': sketch constraints')
        require(all(not item.get('error') for item in value['timeline']), label + ': feature errors')
        geometry(value, reference, label)
    initial_parameter = next(item for item in initial['params'] if item['name'] == 'flange_thickness')
    edited_parameter = next(item for item in report['edited']['params'] if item['name'] == 'flange_thickness')
    require(math.isclose(edited_parameter['value'], initial_parameter['value'] + 1), 'Edited parameter value')
    require(report['edited']['bodies'] != initial['bodies'], 'Observed geometry change')
    require(all(body['closed'] for body in report['edited']['bodies']), 'Edited solid closure')
    require(all(not item.get('error') for item in report['edited']['timeline']), 'Edited feature errors')
    require(report.get('clicks', 0) > 0, 'Interface response observed')
    require(report.get('maxHostFrameGapMs', float('inf')) < 200, 'Host frame gap below 200 ms')
    return failures


def main():
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    args = parser.parse_args()
    report = json.loads((args.evidence / 'report.json').read_text())
    reference = json.loads(args.reference.read_text())[0]
    native = json.loads((args.evidence / 'native-reopened.json').read_text())
    if isinstance(native, list):
        native = native[0]
    failures = verify(report, reference, native)
    result = {'status': 'failed' if failures else 'passed', 'failures': failures}
    (args.evidence / 'qualification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
