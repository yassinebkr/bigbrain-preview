import type { CadView } from './cad';

type Check = NonNullable<CadView['snapshot']>['checks'][number];
const number = (value: number) => value.toLocaleString('fr-FR', value !== 0 && Math.abs(value) < 0.001
  ? { maximumSignificantDigits: 3 } : { maximumFractionDigits: 3 });

/** Read the previous diagnostic serialization solely for historical display. */
function legacy(check: Check) {
  const match = /^(.*): observed \(([^()]*)\); expected \(([^()]*)\)$/.exec(check.diagnostic);
  if (!match) return null;
  const values = (text: string) => text.split(',').map(item => item.trim()).filter(Boolean).map(Number);
  const observed = values(match[2]), expected = values(match[3]);
  if (!observed.length || observed.length !== expected.length || observed.length > 3
    || [...observed, ...expected].some(value => !Number.isFinite(value))) return null;
  // Earlier records carried no metric. Only these original IDs identify units.
  const metric = observed.length === 3 ? 'dimensions_mm' : check.criterion_id === 'volume' ? 'volume_mm3' : undefined;
  return { label: match[1], metric, observed, expected };
}

export function presentCadCheck(check: Check) {
  if (check.metric === 'cylindrical_surface_mm' && check.observed && check.expected) {
    const format = (values: number[]) => `R ${number(values[0])} mm · axe (${number(values[1])} ; ${number(values[2])}) mm`;
    return { label: check.label || 'Surface cylindrique', observed: format(check.observed),
      expected: format(check.expected), tolerance: check.absolute_tolerance != null
        ? `${number(check.absolute_tolerance)} mm` : undefined };
  }
  if (check.observed_intervals_mm) {
    const intervals = (values: [number, number][]) => values.length
      ? values.map(([start, end]) => `${number(start)}–${number(end)} mm`).join(' ; ')
      : 'Vide traversant';
    return { label: check.label || 'Section de la pièce',
      observed: intervals(check.observed_intervals_mm), expected: check.expected_intervals_mm ? intervals(check.expected_intervals_mm) : undefined,
      tolerance: check.expected_intervals_mm && check.absolute_tolerance != null ? `${number(check.absolute_tolerance)} mm` : undefined };
  }
  const data = check.observed && check.expected ? check : legacy(check);
  const format = (values: number[]) => {
    if (data?.metric === 'closed_solid') return values[0] === 1 ? 'Solide fermé' : 'Surface ouverte';
    if (data?.metric === 'point_mm') return `(${values.map(number).join(' ; ')}) mm`;
    const unit = ['dimensions_mm', 'length_mm', 'point_mm'].includes(data?.metric || '') ? ' mm' : data?.metric === 'angle_degree' ? '°' : data?.metric === 'volume_mm3' ? ' mm³' : data?.metric === 'body_count' ? ' corps' : '';
    return values.map(number).join(' × ') + unit;
  };
  const tolerance = check.absolute_tolerance != null && check.relative_tolerance != null
    && ['dimensions_mm', 'volume_mm3', 'length_mm', 'angle_degree', 'point_mm'].includes(check.metric || '')
    ? `${number(check.absolute_tolerance)} ${check.metric === 'volume_mm3' ? 'mm³' : check.metric === 'angle_degree' ? '°' : 'mm'}${check.relative_tolerance ? ` ou ${number(check.relative_tolerance * 100)} %` : ''}` : undefined;
  return { label: data?.label || check.label || 'Contrôle géométrique',
    observed: data?.observed ? format(data.observed) : undefined,
    expected: data?.expected ? format(data.expected) : undefined, tolerance };
}
