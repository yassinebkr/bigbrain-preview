/** Convert accepted sketch primitives from sketch coordinates to CAD world coordinates. */
import { z } from 'zod';

const point = z.tuple([z.number().finite(), z.number().finite()]);
const vector = z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]);
const sketch = z.object({
  plane: z.object({ origin: vector, x_dir: vector, y_dir: vector }),
  curves: z.array(z.unknown()),
});
const curve = z.discriminatedUnion('type', [
  z.object({ type: z.literal('line'), start_at: point, end_at: point }),
  z.object({ type: z.literal('arc'), center_at: point, start_at: point, end_at: point,
    radius: z.number().finite().positive() }),
  z.object({ type: z.literal('circle'), center_at: point, radius: z.number().finite().positive() }),
]);

export function cadSketchLines(sketches: unknown[], includePlanes = false): number[] {
  const vertices: number[] = [];
  for (const value of sketches) {
    const parsed = sketch.safeParse(value);
    if (!parsed.success) continue;
    const { origin, x_dir, y_dir } = parsed.data.plane;
    let minX = 0, minY = 0, maxX = 0, maxY = 0;
    const add = (x: number, y: number) => {
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
      for (let axis = 0; axis < 3; axis++) {
        vertices.push(origin[axis] + x * x_dir[axis] + y * y_dir[axis]);
      }
    };
    for (const value of parsed.data.curves) {
      const primitive = curve.safeParse(value);
      if (!primitive.success) continue;
      const item = primitive.data;
      if (item.type === 'line') {
        add(...item.start_at);
        add(...item.end_at);
      } else {
        const [x, y] = item.center_at;
        const turn = 2 * Math.PI;
        // SolidCraft stores arcs counter-clockwise in their sketch frame.
        const start = item.type === 'arc' ? Math.atan2(item.start_at[1] - y, item.start_at[0] - x) : 0;
        const end = item.type === 'arc' ? Math.atan2(item.end_at[1] - y, item.end_at[0] - x) : turn;
        const sweep = item.type === 'arc' ? (end - start + turn) % turn : turn;
        const segments = Math.max(1, Math.ceil(48 * sweep / turn));
        for (let segment = 0; segment < segments; segment++) {
          for (const index of [segment, segment + 1]) {
            const angle = start + index * sweep / segments;
            add(x + Math.cos(angle) * item.radius, y + Math.sin(angle) * item.radius);
          }
        }
      }
    }
    if (includePlanes) {
      // The outline represents the sketch frame. Its extent is for display.
      const margin = Math.max(maxX - minX, maxY - minY, 1) * .1;
      const left = minX - margin, right = maxX + margin;
      const bottom = minY - margin, top = maxY + margin;
      add(left, bottom); add(right, bottom);
      add(right, bottom); add(right, top);
      add(right, top); add(left, top);
      add(left, top); add(left, bottom);
    }
  }
  return vertices;
}
