import { describe, expect, it } from 'vitest';
import { presentCadCheck } from './cadChecks';

const base = { criterion_id: 'volume', status: 'passed' as const, evidence_ref: 'measure.json', source_sha256: 'a'.repeat(64),
  diagnostic: 'Volume après perçages: observed (14060.764351065302,); expected (14060.707993412303,)' };
describe('CAD measurement presentation', () => {
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
});
