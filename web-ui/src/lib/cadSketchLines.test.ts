import { describe, expect, it } from 'vitest';
import { cadSketchLines } from './cadSketchLines';

describe('CAD sketch overlay', () => {
  it('draws the stored counter-clockwise arc in an oriented sketch plane', () => {
    const vertices = cadSketchLines([{
      plane: { origin: [10, 20, 30], x_dir: [0, 1, 0], y_dir: [0, 0, 1] },
      curves: [{ type: 'arc', center_at: [0, 0], start_at: [0, -2], end_at: [2, 0], radius: 2 }],
    }]);
    expect(vertices).toHaveLength(12 * 6);
    expect(vertices.slice(0, 3)).toEqual([10, 20, 28]);
    expect(vertices.slice(-3)).toEqual([10, 22, 30]);
  });
});
