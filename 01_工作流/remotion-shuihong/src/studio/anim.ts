import type {CameraKey, Span} from './types';

export const clamp = (v: number) => Math.max(0, Math.min(1, v));
export const smooth = (v: number) => {
  const p = clamp(v);
  return p * p * (3 - 2 * p);
};
export const easeOut = (v: number) => 1 - (1 - clamp(v)) ** 3;

// Fade in over `inS` after start and out over `outS` before end.
export const presence = (sec: number, s: Span, inS = 0.4, outS = 0.35) =>
  sec < s.start || sec > s.end ? 0 : smooth((sec - s.start) / inS) * (1 - smooth((sec - (s.end - outS)) / outS));

export const visible = (sec: number, s: Span) => sec >= s.start && sec <= s.end;

export function cameraAt(keys: CameraKey[], sec: number): CameraKey {
  if (sec <= keys[0].t) return keys[0];
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i], b = keys[i + 1];
    if (sec <= b.t) {
      const p = smooth((sec - a.t) / Math.max(1e-6, b.t - a.t));
      // Interpolate zoom in log space so push-ins feel linear in perceived scale.
      const z = Math.exp(Math.log(a.z) + (Math.log(b.z) - Math.log(a.z)) * p);
      return {t: sec, z, cx: a.cx + (b.cx - a.cx) * p, cy: a.cy + (b.cy - a.cy) * p};
    }
  }
  return keys[keys.length - 1];
}

export type Pt = [number, number];

// Sample a smooth curve through points. Two points get a single bent quadratic;
// more points use Catmull-Rom so arrows pass through every `via` place.
export function samplePath(pts: Pt[], bend: number, n = 72): Pt[] {
  if (pts.length === 2) {
    const [a, b] = pts;
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const c: Pt = [mx - dy * bend, my + dx * bend];
    return Array.from({length: n + 1}, (_, i) => {
      const t = i / n;
      return [(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]];
    });
  }
  const out: Pt[] = [];
  const P = [pts[0], ...pts, pts[pts.length - 1]];
  const per = Math.ceil(n / (pts.length - 1));
  for (let i = 1; i < P.length - 2; i++) {
    const [p0, p1, p2, p3] = [P[i - 1], P[i], P[i + 1], P[i + 2]];
    for (let k = 0; k < per; k++) {
      const t = k / per, t2 = t * t, t3 = t2 * t;
      const f = (j: 0 | 1) => 0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3);
      out.push([f(0), f(1)]);
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}

// Cut a polyline to the fraction `p` of its length; also trims `trimEnd` px.
export function partial(line: Pt[], p: number, trimEnd = 0): {pts: Pt[]; angle: number} {
  const seg = line.slice(1).map((q, i) => Math.hypot(q[0] - line[i][0], q[1] - line[i][1]));
  const total = seg.reduce((a, b) => a + b, 0);
  const target = Math.max(0, (total - trimEnd) * clamp(p));
  const pts: Pt[] = [line[0]];
  let acc = 0;
  for (let i = 0; i < seg.length; i++) {
    if (acc + seg[i] >= target) {
      const r = seg[i] ? (target - acc) / seg[i] : 0;
      const a = line[i], b = line[i + 1];
      pts.push([a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r]);
      const angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
      return {pts, angle};
    }
    acc += seg[i];
    pts.push(line[i + 1]);
  }
  const a = line[line.length - 2], b = line[line.length - 1];
  return {pts, angle: Math.atan2(b[1] - a[1], b[0] - a[0])};
}

export const toD = (pts: Pt[]) => pts.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(1)} ${q[1].toFixed(1)}`).join('');

// mirror a portrait so it looks into the frame: on the right it should face left, on the left face right
export const mirrorFor = (side: 'left' | 'right' | undefined, faces: 'left' | 'right' | 'front' | undefined): boolean =>
  (faces ?? 'right') !== 'front' && (side === 'right') === ((faces ?? 'right') === 'right');
