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
  z.object({ type: z.literal('circle'), center_at: point, radius: z.number().finite().positive() }),
]);

export function cadSketchLines(sketches: unknown[]): number[] {
  const vertices: number[] = [];
  for (const value of sketches) {
    const parsed = sketch.safeParse(value);
    if (!parsed.success) continue;
    const { origin, x_dir, y_dir } = parsed.data.plane;
    const add = (x: number, y: number) => {
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
        for (let segment = 0; segment < 48; segment++) {
          for (const index of [segment, segment + 1]) {
            const angle = index * Math.PI / 24;
            add(x + Math.cos(angle) * item.radius, y + Math.sin(angle) * item.radius);
          }
        }
      }
    }
  }
  return vertices;
}
