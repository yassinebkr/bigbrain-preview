import { describe, expect, it } from 'vitest';
import { presentCadCheck } from './cadChecks';

const base = { criterion_id: 'volume', status: 'passed' as const, evidence_ref: 'measure.json', source_sha256: 'a'.repeat(64),
  diagnostic: 'Volume après perçages: observed (14060.764351065302,); expected (14060.707993412303,)' };
describe('CAD measurement presentation', () => {
  it('preserves angular and linear requirement units and fixed tolerances', () => {
    const angle = presentCadCheck({ ...base, label: 'Chanfrein', metric: 'angle_degree',
      observed: [45], expected: [45], absolute_tolerance: 0.001, relative_tolerance: 0 });
    expect(angle.observed).toBe('45°');
    expect(angle.tolerance).toBe('0,001 °');
    const depth = presentCadCheck({ ...base, label: 'Profondeur', metric: 'length_mm',
      observed: [5], expected: [5], absolute_tolerance: 0.001, relative_tolerance: 0 });
    expect(depth.expected).toBe('5 mm');
    expect(depth.tolerance).toBe('0,001 mm');
    const point = presentCadCheck({ ...base, label: 'Extrémité', metric: 'point_mm',
      observed: [25, 0, 55], expected: [25, 0, 55], absolute_tolerance: 0.001, relative_tolerance: 0 });
    expect(point.observed).toBe('(25 ; 0 ; 55) mm');
  });
  it('presents measured material sections and an empty through hole', () => {
    const result = presentCadCheck({ ...base, label: 'Perçage', observed_intervals_mm: [[0, 12], [18, 60]],
      expected_intervals_mm: [[0, 12], [18, 60]], absolute_tolerance: 0.05 });
    expect(result.observed).toBe('0–12 mm ; 18–60 mm');
    expect(result.tolerance).toBe('0,05 mm');
    expect(presentCadCheck({ ...base, observed_intervals_mm: [], expected_intervals_mm: [] }).observed).toBe('Vide traversant');
  });
  it('formats historical floating point diagnostics without changing their verdict', () => {
    const result = presentCadCheck(base);
    expect(result.label).toBe('Volume après perçages');
    expect(result.observed).toContain('060,764 mm³');
    expect(result.expected).toContain('060,708 mm³');
  });
  it('prefers structured evidence and units for arbitrary criterion identifiers', () => {
    const result = presentCadCheck({ ...base, criterion_id: 'custom', label: 'Encombrement', metric: 'dimensions_mm',
      observed: [60, 40, 6.00000000036], expected: [60, 40, 6], absolute_tolerance: 0.001, relative_tolerance: 0.00001 });
    expect(result.observed).toBe('60 × 40 × 6 mm');
    expect(result.tolerance).toBe('0,001 mm ou 0,001 %');
  });
  it('leaves unrecognized historical diagnostics in the technical detail', () => {
    expect(presentCadCheck({ ...base, diagnostic: 'Unknown diagnostic' }).observed).toBeUndefined();
    expect(presentCadCheck({ ...base, diagnostic: 'X: observed (nan,); expected (1,)' }).observed).toBeUndefined();
  });
  it('presents analytic radius and axis coordinates with explicit units', () => {
    const result = presentCadCheck({ ...base, label: 'Fond arrondi', metric: 'cylindrical_surface_mm',
      observed: [25, 5, 40], expected: [25, 5, 40], absolute_tolerance: 0.001 });
    expect(result.observed).toBe('R 25 mm · axe (5 ; 40) mm');
    expect(result.tolerance).toBe('0,001 mm');
  });
});
