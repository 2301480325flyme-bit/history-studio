import React from 'react';
import {clamp, smooth} from './anim';
import type {CameraKey, Territory} from './types';

// Commandery-level territory: fills (world layer, multiply), outlines and
// labels (screen layer). A state change recolours commanderies one by one,
// sweeping outward from the new owner's centre, with a brief flash.

const SWEEP_S_PER_PX = 0.0011; // stagger per world pixel from the owner's centre
const SWEEP_MAX = 1.6;
const FADE = 0.7;

export const stateIndex = (t: Territory, sec: number) => {
  let s = -1;
  t.states.forEach((st, i) => {
    if (sec >= st.t) s = i;
  });
  return s;
};

export const TerritoryFill: React.FC<{t: Territory; sec: number; cam: CameraKey; width: number; height: number; breathe?: {faction: string; k: number}[]}> = ({t, sec, cam, width, height, breathe = []}) => {
  const s = stateIndex(t, sec);
  if (s < 0) return null;
  const light = t.look !== 'classic';
  const atlas = t.look === 'atlas';
  const FO = atlas ? 0.56 : light ? 0.6 : 0.9;
  // atlas: deeper greyed colours so the strong relief reads through (史图记忆簿 style)
  const P = (name: string) => (atlas ? {...t.polities[name], fill: t.polities[name].atlas ?? t.polities[name].fill} : t.polities[name]);   // light look: plain alpha (multiply blending cost ~30% of render time)   // light look: translucent pastel fills, the relief shows through
  const cur = t.states[s];
  const prev = s > 0 ? t.states[s - 1] : null;
  const fills: React.ReactNode[] = [];
  const flashes: React.ReactNode[] = [];
  // Settled commanderies are drawn per polity as one opaque group: each cell gets a
  // same-colour stroke that closes the hairline gaps between independently traced
  // cells, and the group's single opacity keeps overlaps from darkening.
  const settled: Record<string, string[]> = {};
  // 墨渗 (after 纸上谈兵, 2026-10-12): commanderies changing hands are not recoloured one by one; the new colour
  // seeps out from the centre (the captured city, or the gainer's heart) as one ragged ink front
  const changed = prev ? t.cells.filter((c) => cur.owners[c.id] !== prev.owners[c.id] && cur.owners[c.id]) : [];
  let ink: {cx: number; cy: number; r: number; spreading: boolean} | null = null;
  if (changed.length && prev) {
    const gainer = cur.owners[changed[0].id];
    // start where the gainer enters: the captured city, else the new commandery nearest his heartland
    const home = gainer ? cur.labels[gainer] : undefined;
    const entry = home ? changed.reduce((a, c) => (Math.hypot(c.anchor[0] - home[0], c.anchor[1] - home[1]) < Math.hypot(a.anchor[0] - home[0], a.anchor[1] - home[1]) ? c : a)).anchor : changed[0].anchor;
    const centre = cur.origin ?? entry;
    const far = Math.max(...changed.map((c) => Math.hypot(c.anchor[0] - centre[0], c.anchor[1] - centre[1]))) + 260 / Math.max(0.6, cam.z);
    const dur = Math.min(2.8, 0.9 + far * 0.0012);
    const tt = sec - cur.t;
    if (tt >= 0 && tt < dur + 0.1) {
      const e = clamp(tt / dur);
      ink = {cx: centre[0], cy: centre[1], r: far * (e < 0.5 ? 2 * e * e : 1 - Math.pow(-2 * e + 2, 2) / 2), spreading: true};
    }
  }
  const inkCells = new Set(ink ? changed.map((c) => c.id) : []);
  const inkNew: Record<string, string[]> = {};
  const breatheOf = (owner: string | undefined) =>
    breathe.length ? (breathe.find((b) => b.faction === owner) ? 0.82 + 0.18 * Math.sin(sec * 3.2) : 1 - 0.3 * Math.max(...breathe.map((b) => b.k))) : 1;
  for (const c of t.cells) {
    const now = cur.owners[c.id];
    const before = prev ? prev.owners[c.id] : undefined;
    if (inkCells.has(c.id) && now) {
      // under the front: old colour stays solid, the new one is drawn later through the ink mask
      if (before) fills.push(<path key={c.id + 'ib'} d={c.path} fill={P(before).fill} fillOpacity={FO} stroke={P(before).fill} strokeOpacity={0.6} strokeWidth={2.5} strokeLinejoin="round" />);
      (inkNew[now] ??= []).push(c.path);
      continue;
    }
    let p = 1;
    if (now !== before) {
      // a takeover spreads from the captured city like ink; otherwise from the new owner's centre
      const centre = cur.origin ?? (now ? cur.labels[now] : before && prev ? prev.labels[before] : undefined);
      const d = centre ? Math.hypot(c.anchor[0] - centre[0], c.anchor[1] - centre[1]) : 0;
      const delay = cur.origin ? Math.min(SWEEP_MAX, d * SWEEP_S_PER_PX * 4) : Math.min(SWEEP_MAX, d * SWEEP_S_PER_PX);
      p = smooth((sec - cur.t - delay) / (cur.origin ? 0.3 : FADE));
    }
    if (p >= 1 || now === before) {
      if (now) (settled[now] ??= []).push(c.path);
      continue;
    }
    if (before && p < 1) fills.push(<path key={c.id + 'b'} d={c.path} fill={P(before).fill} fillOpacity={now ? FO * (1 - p * p) : FO * (1 - p)} stroke={P(before).fill} strokeOpacity={now ? 0.6 * (1 - p * p) : 0.6 * (1 - p)} strokeWidth={2.5} strokeLinejoin="round" />);
    if (now && p > 0) fills.push(<path key={c.id + 'n'} d={c.path} fill={P(now).fill} fillOpacity={FO * p * breatheOf(now)} stroke={P(now).fill} strokeOpacity={0.6 * p * breatheOf(now)} strokeWidth={2.5} strokeLinejoin="round" />);
    if (now && p > 0 && p < 1)
      flashes.push(cur.origin
        ? <path key={c.id + 'f'} d={c.path} fill="none" stroke={t.polities[now].edge} strokeWidth={4 / cam.z} strokeOpacity={0.9 * Math.sin(Math.PI * p)} />
        : <path key={c.id + 'f'} d={c.path} fill="#fff6dc" fillOpacity={0.22 * Math.sin(Math.PI * p)} />);
  }
  // Once nothing is changing hands, fill each polity from its dissolved outline (traced from
  // the raster, so it has no seams where independently simplified cells meet).
  const steady = fills.length === 0;
  const groups = steady
    ? Object.entries(cur.outlines).map(([owner, d]) => (
        <g key={'o' + owner} opacity={FO * breatheOf(owner)}>
          <path d={d} fill={P(owner).fill} fillRule="evenodd" stroke={P(owner).fill} strokeWidth={2} strokeLinejoin="round" />
        </g>
      ))
    : Object.entries(settled).map(([owner, paths]) => (
    <g key={'g' + owner} opacity={FO * breatheOf(owner)}>
      {/* one path per cell: a single joined path lets overlapping, oppositely wound cells cancel into holes */}
      {paths.map((d, k) => <path key={k} d={d} fill={P(owner).fill} stroke={P(owner).fill} strokeWidth={5} strokeLinejoin="round" />)}
    </g>
  ));
  const outline = (st: typeof cur, op: number, k: string) => atlas
    // atlas borders: a broad pale line with a faint dark rim, like the reference's light frontier bands
    ? Object.entries(st.outlines).map(([name, d]) => (
        <path key={k + name} d={d} fill="none" stroke={t.polities[name]?.atlas ?? t.polities[name]?.edge ?? '#5a4632'} strokeOpacity={0.7 * op} strokeWidth={1.6} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      ))
    : Object.entries(st.outlines).map(([name, d]) => (
      <path key={k + name} d={d} fill="none" stroke={light ? '#3a2c24' : t.polities[name].edge} strokeOpacity={(light ? 0.72 : 0.8) * op} strokeWidth={light ? 1.7 : 2.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    ));
  const fadeIn = smooth((sec - cur.t - 0.6) / 0.9);
  // map memory: the old borders linger as a dashed ghost, then fade
  const ghostOp = cur.ghost && prev ? 1 - smooth((sec - cur.t - cur.ghost * 0.65) / (cur.ghost * 0.35)) : 0;
  return (
    <>
      <svg width={width} height={height} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: light ? 'normal' : 'multiply'}}>
        <defs>
          <pattern id="hatch" width={10 / cam.z} height={10 / cam.z} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1={0} y1={0} x2={0} y2={10 / cam.z} stroke="#5b4a3a" strokeWidth={2.2 / cam.z} strokeOpacity={0.55} />
          </pattern>
        </defs>
        {ink && (
          <defs>
            <filter id={`inkfront${s}`} x="-30%" y="-30%" width="160%" height="160%">
              <feTurbulence type="fractalNoise" baseFrequency={0.012 * Math.max(0.6, cam.z)} numOctaves={3} seed={s * 7 + 3} />
              <feDisplacementMap in="SourceGraphic" scale={110 / Math.max(0.6, cam.z)} xChannelSelector="R" yChannelSelector="G" />
            </filter>
            <mask id={`inkmask${s}`} maskUnits="userSpaceOnUse" x={-20000} y={-20000} width={40000} height={40000}>
              <circle cx={ink.cx} cy={ink.cy} r={ink.r} fill="#fff" filter={`url(#inkfront${s})`} />
            </mask>
            <clipPath id={`inkclip${s}`}>{changed.map((c) => <path key={c.id} d={c.path} />)}</clipPath>
          </defs>
        )}
        {groups}
        {fills}
        {ink && Object.entries(inkNew).map(([owner, paths]) => (
          <g key={'ink' + owner} mask={`url(#inkmask${s})`} opacity={FO}>
            {paths.map((d, k) => <path key={k} d={d} fill={P(owner).fill} stroke={P(owner).fill} strokeWidth={5} strokeLinejoin="round" />)}
          </g>
        ))}
        {/* the wet edge of the front: a darker rim in the gainer's edge colour */}
        {ink && ink.r > 0 && (
          <g clipPath={`url(#inkclip${s})`}>
            <circle cx={ink.cx} cy={ink.cy} r={ink.r} fill="none" stroke={t.polities[cur.owners[changed[0].id]]?.edge ?? '#5a2a14'} strokeWidth={30 / Math.max(0.6, cam.z)} strokeOpacity={0.8} filter={`url(#inkfront${s})`} />
          </g>
        )}
        {cur.uncertain.map((id) => {
          const c = t.cells.find((x) => x.id === id);
          return c ? <path key={'u' + id} d={c.path} fill="url(#hatch)" /> : null;
        })}
      </svg>
      <svg width={width} height={height} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        {flashes}
        {prev && ghostOp > 0
          ? Object.entries(prev.outlines).map(([name, d]) => (
              <path key={'g' + name} d={d} fill="none" stroke={t.polities[name].edge} strokeOpacity={0.85 * ghostOp} strokeWidth={3 / cam.z} strokeDasharray={`${10 / cam.z} ${7 / cam.z}`} strokeLinejoin="round" />
            ))
          : prev && fadeIn < 1 && outline(prev, 1 - fadeIn, 'p')}
        {outline(cur, prev ? fadeIn : smooth((sec - cur.t) / 1.2), 'c')}
        {t.look !== 'atlas' && (t.zhou_lines || []).map((d, k) => (
          <path key={'zl' + k} d={d} fill="none" stroke="#4a3a2c" strokeOpacity={0.4} strokeWidth={1.3} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        ))}
      </svg>
    </>
  );
};

let HIT: CanvasRenderingContext2D | null = null;
const hitCtx = () => (HIT ??= document.createElement('canvas').getContext('2d')!);
const PATHS = new WeakMap<Territory, Map<string, Path2D>>();
// Who owns a world point, per territory state: the polity outlines painted once into a small index-colour
// raster, then every test is one array read. (2026-10-16: testing the giant names against the outline paths
// cost >1 s a frame and froze the live preview.)
const BOUNDS = new WeakMap<Territory, [number, number, number, number]>();
const worldBounds = (t: Territory) => {
  let b = BOUNDS.get(t);
  if (!b) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const c of t.cells) {
      const n = c.path.match(/-?\d+(\.\d+)?/g) ?? [];
      for (let i = 0; i + 1 < n.length; i += 2) {
        const x = +n[i], y = +n[i + 1];
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
    BOUNDS.set(t, (b = [x0, y0, x1, y1]));
  }
  return b;
};
const OWNERS = new WeakMap<object, {at: (wx: number, wy: number) => string | undefined}>();
const ownerMap = (t: Territory, st: Territory['states'][number]) => {
  let m = OWNERS.get(st);
  if (m) return m;
  const [x0, y0, x1, y1] = worldBounds(t);
  const k = Math.min(1, 900 / Math.max(1, x1 - x0, y1 - y0));   // ≤900 px on the long side
  const W = Math.max(1, Math.ceil((x1 - x0) * k)), H = Math.max(1, Math.ceil((y1 - y0) * k));
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d', {willReadFrequently: true})!;
  const names = Object.keys(st.outlines);
  g.setTransform(k, 0, 0, k, -x0 * k, -y0 * k);
  names.forEach((n, i) => { g.fillStyle = `rgb(${i + 1},0,0)`; g.fill(new Path2D(st.outlines[n]), 'evenodd'); });
  const px = g.getImageData(0, 0, W, H).data;
  m = {at: (wx, wy) => {
    const i = Math.floor((wx - x0) * k), j = Math.floor((wy - y0) * k);
    if (i < 0 || j < 0 || i >= W || j >= H) return undefined;
    const v = px[(j * W + i) * 4];
    return v ? names[v - 1] : undefined;
  }};
  OWNERS.set(st, m);
  return m;
};
const cellPath = (t: Territory, id: string): Path2D | undefined => {
  let m = PATHS.get(t);
  if (!m) {
    m = new Map(t.cells.map((c) => [c.id, new Path2D(c.path)] as const));
    PATHS.set(t, m);
  }
  return m.get(id);
};

// warm polity names (2026-10-24, user: "字一直在动，有时候出现两个"): a name is laid out once per camera rest pose
// and pinned to the map — it moves with the land, never slides over it. Each pose starts from where the name sat in
// the pose before, so a name only moves when its old spot no longer works. One name per patch of land; another patch
// of the same polity gets its own name only if it is well away from the first. Cached per state × camera key.
type Pinned = {n: string; wx: number; wy: number; fs: number};
const PINNED = new WeakMap<Territory, Map<string, Pinned[]>>();
const pinnedAt = (t: Territory, s: number, cams: CameraKey[], j: number, marks: [number, number][] = []): Pinned[] => {
  const memo = PINNED.get(t) ?? new Map<string, Pinned[]>();
  PINNED.set(t, memo);
  const key = s + ':' + j;
  const hit = memo.get(key);
  if (hit) return hit;
  // keys are laid out in order, so the chain behind this one is already cached (or built here, iteratively)
  let before: Pinned[] = [];
  for (let i = 0; i <= j; i++) {
    const k = s + ':' + i;
    const got = memo.get(k) ?? layoutPinned(t, s, cams[i], before, marks);
    memo.set(k, got);
    before = got;
  }
  return before;
};
// 2026-10-25 (ep18 close-ups: 曹操 sat on 定军山 and 沔阳, over the camps and the fire): the story's places — their
// icons, labels and whatever is drawn at them — are kept clear too; a name lands on one only if no other spot fits
const layoutPinned = (t: Territory, s: number, cam: CameraKey, before: Pinned[], marks: [number, number][]): Pinned[] => {
  const cur = t.states[s];
  const sc = (x: number, y: number): [number, number] => [960 + (x - cam.cx) * cam.z, 540 + (y - cam.cy) * cam.z];
  const toW = (q: [number, number]): [number, number] => [(q[0] - 960) / cam.z + cam.cx, (q[1] - 540) / cam.z + cam.cy];
  const om = ownerMap(t, cur);
  const anchorOf = new Map(t.cells.map((c) => [c.id, c.anchor] as const));
  // the overview minimap, bottom right, is never available (魏 sat half under it, 第23集)
  const boxes: {x: number; y: number; w: number; h: number}[] = [{x: 1760, y: 770, w: 300, h: 210}];
  const keepOff = [
    ...marks.map(([mx, my]) => { const [x, y] = sc(mx, my); return {x, y, w: 260, h: 70}; }),
    // and the 郡治 ◎ with its name to the right (武都, 西城 were covered)
    ...(t.cities ?? []).filter((c) => c.rank === 1).map((c) => { const [x, y] = sc(c.x, c.y); return {x: x + 45, y, w: 120, h: 34}; }),
  ];
  const out: Pinned[] = [];
  const inView = (p: [number, number]) => p[0] > 140 && p[0] < 1780 && p[1] > 170 && p[1] < 860;
  const place = (n: string, seedsIn: [number, number][], fs0: number) => tryPlace(n, seedsIn, fs0, true) ?? tryPlace(n, seedsIn, fs0, false);
  const tryPlace = (n: string, seedsIn: [number, number][], fs0: number, clear: boolean) => {
    const seeds = seedsIn.filter((q) => q[0] > -200 && q[0] < 2120 && q[1] > -100 && q[1] < 1180).slice(0, 15);
    for (const fs of [fs0, Math.round(fs0 * 0.72), Math.round(fs0 * 0.5)]) {
      const w = n.length * fs * 1.08 + 20, h = fs * 1.05;
      for (const q of seeds) {
        for (const [dx, dy] of [[0, 0], [0, 0.8], [0, -0.8], [0.4, 0], [-0.4, 0]] as const) {
          const x = q[0] + dx * w, y = q[1] + dy * h;
          // clear of the top bar and of the subtitle band
          if (x - w / 2 < 20 || x + w / 2 > 1900 || y - h / 2 < 70 || y + h / 2 > 910) continue;
          if (boxes.some((b) => Math.abs(b.x - x) < (b.w + w) / 2 && Math.abs(b.y - y) < (b.h + h) / 2)) continue;
          if (clear && keepOff.some((b) => Math.abs(b.x - x) < (b.w + w) / 2 && Math.abs(b.y - y) < (b.h + h) / 2)) continue;
          let hit = 0;
          for (let i = 0; i < 5; i++) for (let jj = 0; jj < 3; jj++) {
            const [wx, wy] = toW([x - w / 2 + (w * (i + 0.5)) / 5, y - h / 2 + (h * (jj + 0.5)) / 3]);
            if (om.at(wx, wy) === n) hit++;
          }
          if (hit < 13) continue;
          boxes.push({x, y, w, h});
          const [wx, wy] = toW([x, y]);
          return {n, wx, wy, fs};
        }
      }
    }
    return null;
  };
  // the old spot first (if it is still on screen), then the given points nearest to it
  const seedsFrom = (n: string, pts: [number, number][], prefer: [number, number]) => {
    const old = before.filter((b) => b.n === n).map((b) => sc(b.wx, b.wy)).filter(inView);
    const from = old.length ? old.sort((u, v) => Math.hypot(u[0] - prefer[0], u[1] - prefer[1]) - Math.hypot(v[0] - prefer[0], v[1] - prefer[1]))[0] : prefer;
    return [...old, prefer, ...pts].sort((u, v) => Math.hypot(u[0] - from[0], u[1] - from[1]) - Math.hypot(v[0] - from[0], v[1] - from[1]));
  };
  const big = (n: string) => (n.length > 2 ? 78 : 96), small = (n: string) => (n.length > 2 ? 64 : 78);
  const names = Object.keys(cur.labels).sort((a, b) => Number(!!t.polities[b]?.main) - Number(!!t.polities[a]?.main));
  for (const n of names) {
    const comps = cur.groups?.[n] ?? [t.cells.filter((c) => cur.owners[c.id] === n).map((c) => c.id)];
    // biggest patch on screen first: it carries the full-size name
    const onScreen = comps
      .map((comp) => ({comp, pts: comp.map((id) => anchorOf.get(id)).filter((a): a is [number, number] => !!a).map((a) => sc(a[0], a[1]))}))
      .map((c) => ({...c, seen: c.pts.filter(inView).length}))
      .sort((a, b) => b.seen - a.seen || b.comp.length - a.comp.length);
    const L = cur.labels[n];
    const mine: Pinned[] = [];
    // in a close-up a patch can fill the frame with none of its commandery centres on screen: a grid of frame
    // points on its land stands in for them
    const grid: [number, number][] = [];
    for (let gx = 0; gx < 7; gx++) for (let gy = 0; gy < 5; gy++) {
      const q: [number, number] = [260 + gx * 233, 220 + gy * 150];
      const [wx, wy] = toW(q);
      if (om.at(wx, wy) === n) grid.push(q);
    }
    if (!onScreen.some((c) => c.seen) && grid.length) onScreen.unshift({comp: [], pts: grid, seen: grid.length});
    for (const [k, {pts, seen}] of onScreen.entries()) {
      if (!seen && k > 0) continue;
      const prefer = k === 0 && L && inView(sc(L[0], L[1])) ? sc(L[0], L[1])
        : (pts.filter(inView).sort((u, v) => Math.hypot(u[0] - 960, u[1] - 520) - Math.hypot(v[0] - 960, v[1] - 520))[0] ?? [960, 520]);
      // a second patch near a name already placed stays unnamed
      if (mine.some((m) => { const q = sc(m.wx, m.wy); return Math.hypot(q[0] - prefer[0], q[1] - prefer[1]) < 600; })) continue;
      const got = place(n, seedsFrom(n, pts, prefer), k === 0 ? big(n) : small(n));
      if (got) mine.push(got);
    }
    out.push(...mine);
  }
  return out;
};

// warm palette (2026-10-24, after 地图知天下): map type is one sans family — 国名 heavy oblique, 州 upright bold,
// 郡县 oblique — every name on a white halo, as in a printed Chinese atlas
export const HALO = (w: number) => ({WebkitTextStroke: `${w}px #fbfaf5`, paintOrder: 'stroke fill' as const});

export const TerritoryLabels: React.FC<{t: Territory; sec: number; screen: (x: number, y: number) => [number, number]; zoom: number; warm?: boolean;
  avoid?: {x: number; y: number; w: number; h: number}[]; cams?: CameraKey[]; marks?: [number, number][]}> = ({t, sec, screen, zoom, warm = false, avoid = [], cams = [], marks = []}) => {
  // warm: the narrated places' labels (top-left boxes, widened left over the icon) are kept clear of every map name
  const keep = warm ? avoid.map((b) => ({x: b.x - 40 + (b.w + 40) / 2, y: b.y + b.h / 2, w: b.w + 40, h: b.h + 8})) : [];
  const s = stateIndex(t, sec);
  const zhouOp = clamp((2.6 - zoom) / 0.6) * clamp((zoom - 0.35) / 0.15);
  // 'always' = reference-style dense labels from medium zoom; true = only when pushed in.
  const junOp = t.look === 'atlas' ? clamp((zoom - 1.6) / 0.4) : t.jun_labels === 'always' ? clamp((zoom - 0.8) / 0.3) : clamp((zoom - 1.5) / 0.4);
  const out: React.ReactNode[] = [];
  // Atlas towns (2026-10-15, thinned the same day after "密密麻麻看不清"): 郡治 carry the names — large, haloed,
  // at most a dozen a frame, centre first, well apart; 县治 are faint dots for texture and are only named, a few
  // nearest the centre, once the camera is right in on a district.
  if (t.cities?.length) {
    // warm: 郡 named from the regional view, 县 dotted and named once the camera is in (reference: 新蔡 · at ~11px)
    const op1 = warm ? clamp((zoom - 1.0) / 0.4) : t.look === 'atlas' ? clamp((zoom - 1.2) / 0.4) : clamp((zoom - 0.75) / 0.25);
    const lab1 = warm ? clamp((zoom - 1.4) / 0.4) : t.look === 'atlas' ? clamp((zoom - 1.8) / 0.4) : clamp((zoom - 1.15) / 0.3);
    const op2 = warm ? clamp((zoom - 1.9) / 0.5) * 0.85 : t.look === 'atlas' ? 0 : clamp((zoom - 2.2) / 0.5) * 0.55;
    const lab2 = warm ? clamp((zoom - 2.4) / 0.6) : clamp((zoom - 6) / 1);
    const placed: [number, number, number, number][] = keep.map((b) => [b.x, b.y, b.w, b.h]);
    const gap = warm ? 14 : 40;
    const free = (x: number, y: number, w: number, h = 40) =>
      !placed.some(([px, py, pw, ph]) => Math.abs(px - x) < (pw + w) / 2 + gap && Math.abs(py - y) < (warm ? (ph + h) / 2 + 4 : 40));
    const seen = t.cities
      .map((c) => ({c, p: screen(c.x, c.y)}))
      .filter(({p: [x, y]}) => x > 0 && x < 1920 && y > 110 && y < 870)
      .sort((a, b) => a.c.rank - b.c.rank || Math.hypot(a.p[0] - 960, a.p[1] - 520) - Math.hypot(b.p[0] - 960, b.p[1] - 520));
    let named1 = 0, named2 = 0;
    for (const {c, p: [x, y]} of seen) {
      const dot = c.rank === 1 ? op1 : op2;
      if (dot <= 0.01) continue;
      const lab = c.rank === 1 ? lab1 : lab2;
      const name = warm && c.rank === 1 ? c.jun ?? c.name : c.name;
      const fs = warm ? (c.rank === 1 ? 21 : 15) : c.rank === 1 ? 22 : 18;
      const w = name.length * fs * (warm ? 1.05 : 1);
      const h = warm ? fs + 6 : 40;
      const room = c.rank === 1 ? named1 < (warm ? 16 : 12) : named2 < (warm ? 24 : 6);
      const showName = lab > 0.01 && room && free(x + 9 + w / 2, y, w, h);
      if (showName) {
        placed.push([x + 9 + w / 2, y, w, h]);
        if (c.rank === 1) named1++; else named2++;
      }
      if (warm) {
        // 郡治 ◎ (ring and centre dot), 县 a small dot; names oblique, haloed
        const r = c.rank === 1 ? 6 : 2.5;
        out.push(
          <div key={'ct' + c.name + c.x} style={{position: 'absolute', left: x, top: y, pointerEvents: 'none'}}>
            <div style={{position: 'absolute', left: -r, top: -r, width: 2 * r, height: 2 * r, opacity: dot, borderRadius: 999, boxSizing: 'border-box',
              ...(c.rank === 1 ? {border: '1.6px solid #1e1e1e', background: 'radial-gradient(circle, #1e1e1e 0 2px, #fbfaf5 2.5px)', boxShadow: '0 0 0 1.5px #fbfaf5cc'}
                : {background: '#3a3a3a', boxShadow: '0 0 0 1.2px #fbfaf5cc'})}} />
            {showName && (
              <div style={{position: 'absolute', left: r + 4, top: 0, transform: 'translateY(-54%)', opacity: lab * dot, fontFamily: 'StoryMap', fontStyle: 'italic',
                fontWeight: c.rank === 1 ? 700 : 500, fontSize: fs, color: c.rank === 1 ? '#1c1c1c' : '#363636', whiteSpace: 'nowrap', ...HALO(c.rank === 1 ? 4 : 3)}}>
                {name}
              </div>
            )}
          </div>,
        );
        continue;
      }
      const size = c.rank === 1 ? 8 : 5;
      out.push(
        <div key={'ct' + c.name + c.x} style={{position: 'absolute', left: x, top: y, pointerEvents: 'none'}}>
          <div style={{position: 'absolute', left: -size / 2, top: -size / 2, width: size, height: size, opacity: dot,
            borderRadius: c.rank === 1 ? 1 : 999, background: c.rank === 1 ? '#4a3726' : '#6b5843', boxShadow: '0 0 0 1.5px #f4ecdcdd'}} />
          {showName && (
            <div style={{position: 'absolute', left: 9, top: 0, transform: 'translateY(-52%)', opacity: lab * op1, fontFamily: 'StorySerif', fontWeight: 700, fontSize: fs, letterSpacing: 1,
              color: '#2a1d12', textShadow: '0 0 2px #f4ecdc, 0 0 4px #f4ecdc, 0 0 7px #f4ecdccc', whiteSpace: 'nowrap'}}>
              {c.name}
            </div>
          )}
        </div>,
      );
    }
  }
  if (zhouOp > 0) {
    for (const z of t.zhou_labels) {
      const [x, y] = screen(z.x, z.y);
      if (x < -200 || x > 2120 || y < 80 || y > 860) continue;
      out.push(warm ? (
        <div key={'z' + z.name} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: 0.8 * zhouOp, fontFamily: 'StoryMap', fontWeight: 800,
          fontSize: 30, letterSpacing: 8, paddingLeft: 8, color: '#2a2a2a', whiteSpace: 'nowrap', ...HALO(5)}}>
          {z.name}
        </div>
      ) : (
        <div key={'z' + z.name} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: 0.78 * zhouOp, fontFamily: 'StorySerif', fontWeight: 700, fontSize: 40, letterSpacing: 10, color: '#4a3a2b', textShadow: '0 0 4px #f4ecdccc, 0 0 10px #f4ecdc88', whiteSpace: 'nowrap'}}>
          {z.name}
        </div>
      ));
    }
  }
  // warm: the 郡治 ◎ already carries the commandery's name, so no second name over the commandery
  if (junOp > 0 && t.jun_labels && !(warm && t.cities?.length)) {
    for (const c of t.cells) {
      const [x, y] = screen(c.anchor[0], c.anchor[1]);
      if (x < 0 || x > 1920 || y < 120 || y > 860) continue;
      out.push(
        <div key={'j' + c.id} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', ...(t.look === 'atlas'
            ? {opacity: 0.85 * junOp, fontFamily: 'StoryBrush', fontSize: 26, letterSpacing: 3, color: '#8a3a1e', textShadow: '0 0 3px #f2ead8, 0 0 6px #f2ead8cc'}
            : {opacity: 0.72 * junOp, fontFamily: 'StorySerif', fontSize: 19, letterSpacing: 4, color: '#5a4632', textShadow: '0 0 3px #f4ecdc, 0 0 6px #f4ecdcaa'}), whiteSpace: 'nowrap'}}>
          {c.name}
        </div>,
      );
    }
  }
  if (s >= 0 && warm && cams.length) {
    // pinned names: during a camera move the names of the pose being left fade out early, the next pose's fade in late
    const cur = t.states[s], prev = s > 0 ? t.states[s - 1] : null;
    const stateOp = (st: number) => st === s ? (prev ? smooth((sec - cur.t - 0.8) / 0.8) : smooth((sec - cur.t - 0.4) / 0.8)) : 1 - smooth((sec - cur.t - 0.8) / 0.8);
    let j = cams.findIndex((k) => k.t >= sec);
    if (j < 0) j = cams.length - 1;
    const a = cams[Math.max(0, j - 1)], b = cams[j];
    const moving = j > 0 && sec > a.t && (a.cx !== b.cx || a.cy !== b.cy || a.z !== b.z);
    const u = moving ? clamp((sec - a.t) / Math.max(0.01, b.t - a.t)) : 1;
    const sets: [Pinned[], number][] = [];
    for (const st of prev && stateOp(s) < 1 ? [s - 1, s] : [s]) {
      const op = stateOp(st);
      if (moving) {
        // a name in both poses glides from its old spot to its new one as one label (crossfading two copies read as
        // a smeared double name in playback); only a name that appears or goes fades
        const A = pinnedAt(t, st, cams, j - 1, marks), B = pinnedAt(t, st, cams, j, marks);
        const used = new Set<Pinned>(), glide: Pinned[] = [], gone: Pinned[] = [];
        const e = smooth(u);
        for (const p of A) {
          const q = B.filter((x) => x.n === p.n && !used.has(x)).sort((x, y) => Math.hypot(x.wx - p.wx, x.wy - p.wy) - Math.hypot(y.wx - p.wx, y.wy - p.wy))[0];
          if (!q) { gone.push(p); continue; }
          used.add(q);
          glide.push({n: p.n, wx: p.wx + (q.wx - p.wx) * e, wy: p.wy + (q.wy - p.wy) * e, fs: Math.round(p.fs + (q.fs - p.fs) * e)});
        }
        sets.push([glide, op]);
        sets.push([gone, op * (1 - smooth(u / 0.45))]);
        sets.push([B.filter((x) => !used.has(x)), op * smooth((u - 0.55) / 0.45)]);
      } else sets.push([pinnedAt(t, st, cams, j, marks), op]);
    }
    sets.forEach(([list, op], si) => {
      if (op <= 0.01) return;
      list.forEach((p, pi) => {
        const [x, y] = screen(p.wx, p.wy);
        const w = p.n.length * p.fs * 1.08, h = p.fs;
        // a narrated place's label wins over a polity name that happens to sit on it
        // fades with how much of the name the label covers, so a gliding name dims smoothly instead of popping
        const cover = avoid.reduce((m, q) => {
          const ox = Math.min(x + w / 2, q.x + q.w + 10) - Math.max(x - w / 2, q.x - 50), oy = Math.min(y + h / 2, q.y + q.h) - Math.max(y - h / 2, q.y);
          return ox > 0 && oy > 0 ? Math.max(m, (ox * oy) / (w * h)) : m;
        }, 0);
        const dim = 1 - 0.85 * clamp(cover / 0.25);
        const pol = t.polities[p.n];
        if (!pol) return;
        out.push(
          <div key={'pn' + si + '_' + pi + p.n} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: 0.88 * op * dim,
            color: pol.edge, fontFamily: 'StoryMap', fontWeight: 900, fontStyle: 'italic', fontSize: p.fs, letterSpacing: p.fs * 0.08, paddingLeft: p.fs * 0.08, whiteSpace: 'nowrap', ...HALO(p.fs > 70 ? 7 : 6)}}>
            {p.n}
          </div>,
        );
      });
    });
  } else if (s >= 0) {
    const cur = t.states[s];
    const prev = s > 0 ? t.states[s - 1] : null;
    const fade = smooth((sec - cur.t - 0.8) / 0.8);
    // atlas: the giant names must not pile on each other (曹操 over 汉室 in the first sample) — each takes a box,
    // the main polity first; a name that finds no free spot near its anchor is left out of this frame
    const giant = (n: string) => (warm ? (n.length > 2 ? 78 : 96) : n.length > 2 ? 104 : 130);
    // hit test against the commandery outlines (screen → world), so a name only ever lands on its own land
    const o0 = screen(0, 0);
    const toWorld = (q: [number, number]): [number, number] => [(q[0] - o0[0]) / zoom, (q[1] - o0[1]) / zoom];
    const ctx = hitCtx();
    const inside = (ids: string[], q: [number, number]) => {
      const [wx, wy] = toWorld(q);
      return ids.some((id) => { const path = cellPath(t, id); return !!path && ctx.isPointInPath(path, wx, wy); });
    };
    const anchorOf = new Map(t.cells.map((c) => [c.id, c.anchor] as const));
    // atlas giant names (2026-10-15): no piling on each other, and — in close-ups especially — never across a
    // border onto someone else's land. A spot counts only if ≥85% of a 5×3 grid over the word's box is the
    // polity's own commanderies; candidates are the preferred point and the polity's own commandery centres on
    // screen, nearest first, at full size and then smaller. No spot → no name this frame.
    const boxes: {x: number; y: number; w: number; h: number}[] = [...keep];
    const place = (n: string, ids: string[], prefer: [number, number], fs0: number, whole = false): {x: number; y: number; fs: number} | null => {
      // one array read per test (ownerMap); antialiased edges may read as the neighbour, which only makes it stricter
      void ids; void whole;
      const om = ownerMap(t, cur);
      const on = (q: [number, number]) => { const [wx, wy] = toWorld(q); return om.at(wx, wy) === n; };
      const seeds = [prefer, ...ids.map((id) => anchorOf.get(id)).filter((a): a is [number, number] => !!a).map((a) => screen(a[0], a[1]))]
        .filter((q) => q[0] > -200 && q[0] < 2120 && q[1] > -100 && q[1] < 1180)
        .sort((u, v) => Math.hypot(u[0] - prefer[0], u[1] - prefer[1]) - Math.hypot(v[0] - prefer[0], v[1] - prefer[1]))
        .slice(0, 14);
      for (const fs of [fs0, Math.round(fs0 * 0.72), Math.round(fs0 * 0.5)]) {
        const w = n.length * (fs + fs * 0.18) + 20, h = fs * 1.05;
        for (const q of seeds) {
          for (const [dx, dy] of [[0, 0], [0, 0.8], [0, -0.8], [0.4, 0], [-0.4, 0]] as const) {
            const x = q[0] + dx * w, y = q[1] + dy * h;
            if (x - w / 2 < 20 || x + w / 2 > 1900 || y - h / 2 < 70 || y + h / 2 > 1030) continue;
            if (boxes.some((b) => Math.abs(b.x - x) < (b.w + w) / 2 && Math.abs(b.y - y) < (b.h + h) / 2)) continue;
            let hit = 0;
            for (let i = 0; i < 5; i++) for (let j = 0; j < 3; j++) if (on([x - w / 2 + (w * (i + 0.5)) / 5, y - h / 2 + (h * (j + 0.5)) / 3])) hit++;
            if (hit < 13) continue;
            boxes.push({x, y, w, h});
            return {x, y, fs};
          }
        }
      }
      return null;
    };
    const ownCells = (n: string) => t.cells.filter((c) => cur.owners[c.id] === n).map((c) => c.id);
    const atlasAt = new Map<string, {x: number; y: number; fs: number} | null>();
    const namedAt = new Map<string, {x: number; y: number; fs: number}[]>();
    if (t.look === 'atlas')
      Object.entries(cur.labels)
        .sort(([a], [b]) => Number(!!t.polities[b]?.main) - Number(!!t.polities[a]?.main))
        .forEach(([n, at]) => atlasAt.set(n, place(n, ownCells(n), screen(at[0], at[1]), giant(n), true)));
    const pill = (name: string, at: [number, number], op: number, k: string) => {
      let [x, y] = screen(at[0], at[1]);
      let fs = giant(name);
      if (t.look === 'atlas') {
        if (k !== 'pc') return null;   // atlas: the outgoing state's names just go; the new ones fade in on their own land
        const q = atlasAt.get(name);
        if (!q) return null;
        ({x, y, fs} = q);
      }
      if (op <= 0.01 || x < 140 || x > 1780 || y < 170 || y > 860) return null;   // a name the frame would cut off is left to the in-view label
      const p = t.polities[name];
      if (t.look === 'atlas')
        // atlas: the polity name as a huge pale brush word over its land (刘备 / 曹魏 in the reference);
        // warm: a heavy oblique sans in the polity's deep colour (前秦 / 东晋 in 地图知天下)
        return warm ? (
          <div key={k + name} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: 0.88 * op, color: p.edge, fontFamily: 'StoryMap', fontWeight: 900,
            fontStyle: 'italic', fontSize: fs, letterSpacing: fs * 0.08, paddingLeft: fs * 0.08, whiteSpace: 'nowrap', ...HALO(7)}}>
            {name}
          </div>
        ) : (
          <div key={k + name} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: 0.62 * op, color: p.atlas ?? p.edge, fontFamily: 'StoryBrush', fontSize: fs,
            letterSpacing: fs * 0.18, paddingLeft: fs * 0.18, whiteSpace: 'nowrap', WebkitTextStroke: '3px #f1ede2', paintOrder: 'stroke fill', textShadow: '0 4px 14px #0003'}}>
            {name}
          </div>
        );
      if (t.look !== 'classic')
        return (
          <div key={k + name} style={{position: 'absolute', left: x, top: y, transform: `translate(-50%,-120%) scale(${p.main ? 1.15 : 1})`, opacity: op, color: '#fffdf6', fontFamily: 'StorySerif', fontWeight: 700, fontSize: name.length > 2 ? 34 : 40, letterSpacing: name.length > 2 ? 10 : 22, paddingLeft: name.length > 2 ? 10 : 22, whiteSpace: 'nowrap', textShadow: `0 0 2px ${p.edge}, 0 0 6px ${p.edge}aa, 0 1px 3px #0005`}}>
            {name}
          </div>
        );
      return (
        <div key={k + name} style={{position: 'absolute', left: x, top: y, transform: `translate(-50%,-135%) scale(${p.main ? 1.2 : 1})`, opacity: op, padding: '4px 18px 6px', borderRadius: 999, background: p.edge, color: '#fff7e6', fontFamily: 'StoryBrush', fontSize: 34, letterSpacing: 4, whiteSpace: 'nowrap', boxShadow: '0 2px 6px #0004', border: '2px solid #fff3dccc'}}>
          {name}
        </div>
      );
    };
    const ghostOp = cur.ghost && prev ? 1 - smooth((sec - cur.t - cur.ghost * 0.65) / (cur.ghost * 0.35)) : 0;
    if (prev && ghostOp > 0) {
      // old names stay as hollow ghost tags where the polity no longer sits
      Object.entries(prev.labels).forEach(([n, at]) => {
        const moved = !cur.labels[n] || Math.hypot(cur.labels[n][0] - at[0], cur.labels[n][1] - at[1]) > 40;
        if (!moved) return;
        const [x, y] = screen(at[0], at[1]);
        if (x < -100 || x > 2020 || y < 100 || y > 880) return;
        out.push(
          <div key={'gh' + n} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-135%)', opacity: 0.75 * ghostOp, padding: '2px 14px 4px', borderRadius: 999, border: `2px dashed ${t.polities[n].edge}`, color: t.polities[n].edge, background: '#f4ecdc99', fontFamily: 'StoryBrush', fontSize: 28, letterSpacing: 3, whiteSpace: 'nowrap'}}>
            {n}
          </div>,
        );
      });
    } else if (prev && fade < 1) Object.entries(prev.labels).forEach(([n, at]) => out.push(pill(n, at, 1 - fade, 'pp')));
    Object.entries(cur.labels).forEach(([n, at]) => out.push(pill(n, at, prev ? fade : smooth((sec - cur.t - 0.4) / 0.8), 'pc')));
    // Every connected patch of a polity that shows on screen carries its name once (2026-10-13): 袁术's 汝南 filled the
    // bottom of the frame while his name sat off-screen at 寿春; one big 曹操 area must not get two names.
    const inView = (p: [number, number]) => p[0] > 140 && p[0] < 1780 && p[1] > 170 && p[1] < 860;
    // a patch whose commandery centres are off-screen: walk from the nearest centre toward the frame centre and
    // take the first in-frame spot that is still on that patch
    const near = (comp: string[], p: [number, number]): [number, number] | null => {
      for (let k = 0; k <= 12; k++) {
        const q: [number, number] = [p[0] + (960 - p[0]) * k / 12, p[1] + (520 - p[1]) * k / 12];
        if (inView(q) && inside(comp, q)) return q;
      }
      return null;
    };
    const taken: [number, number][] = Object.values(cur.labels).map((at) => screen(at[0], at[1])).filter(inView);
    const op = prev ? fade : smooth((sec - cur.t - 0.4) / 0.8);
    for (const [n, comps] of Object.entries(cur.groups ?? {})) {
      const p = t.polities[n];
      if (!p) continue;
      const main = cur.labels[n] ? screen(cur.labels[n][0], cur.labels[n][1]) : null;
      const L = cur.labels[n];
      const homeCell = L ? comps.flat().reduce<string | null>((best, id) => {
        const a = anchorOf.get(id), b = best ? anchorOf.get(best) : null;
        return a && (!b || Math.hypot(a[0] - L[0], a[1] - L[1]) < Math.hypot(b[0] - L[0], b[1] - L[1])) ? id : best;
      }, null) : null;
      for (const comp of comps) {
        const pts = comp.map((id) => anchorOf.get(id)).filter((a): a is [number, number] => !!a).map((a) => screen(a[0], a[1]));
        // the patch holding the polity's main label (the cell nearest to it) is already named when that label is on screen
        if (main && inView(main) && homeCell && comp.includes(homeCell)) continue;
        const vis = pts.map((q) => (inView(q) ? q : near(comp, q))).filter((q): q is [number, number] => !!q)
          .sort((u, v) => Math.hypot(u[0] - 960, u[1] - 520) - Math.hypot(v[0] - 960, v[1] - 520));
        let at: [number, number] | null | undefined;
        let pfs = warm ? (n.length > 2 ? 64 : 78) : n.length > 2 ? 84 : 104;
        if (t.look === 'atlas') {
          // one giant name per polity per neighbourhood: a second patch close to where the name already sits stays unnamed
          const named = [atlasAt.get(n), ...(namedAt.get(n) ?? [])].filter((q): q is {x: number; y: number; fs: number} => !!q);
          if (vis.length && named.some((q) => Math.hypot(q.x - vis[0][0], q.y - vis[0][1]) < 500)) continue;
          const got = vis.length ? place(n, comp, vis[0], pfs) : null;
          if (got) namedAt.set(n, [...(namedAt.get(n) ?? []), got]);
          if (got) { at = [got.x, got.y]; pfs = got.fs; }
        } else at = vis.find((q) => !taken.some((r) => Math.hypot(r[0] - q[0], r[1] - q[1]) < 150));
        if (!at) continue;
        taken.push(at);
        out.push(warm ? (
          <div key={'pv' + n + Math.round(at[0]) + '_' + Math.round(at[1])} style={{position: 'absolute', left: at[0], top: at[1], transform: 'translate(-50%,-50%)', opacity: 0.8 * op, color: p.edge, fontFamily: 'StoryMap',
            fontWeight: 900, fontStyle: 'italic', fontSize: pfs, letterSpacing: pfs * 0.08, paddingLeft: pfs * 0.08, whiteSpace: 'nowrap', ...HALO(6)}}>
            {n}
          </div>
        ) : t.look === 'atlas' ? (
          <div key={'pv' + n + Math.round(at[0]) + '_' + Math.round(at[1])} style={{position: 'absolute', left: at[0], top: at[1], transform: 'translate(-50%,-50%)', opacity: 0.55 * op, color: p.atlas ?? p.edge, fontFamily: 'StoryBrush',
            fontSize: pfs, letterSpacing: pfs * 0.17, paddingLeft: pfs * 0.17, whiteSpace: 'nowrap', WebkitTextStroke: '2.5px #f1ede2', paintOrder: 'stroke fill'}}>
            {n}
          </div>
        ) : (
          <div key={'pv' + n + Math.round(at[0]) + '_' + Math.round(at[1])} style={{position: 'absolute', left: at[0], top: at[1], transform: 'translate(-50%,-50%)', opacity: 0.92 * op, color: '#fffdf6', fontFamily: 'StorySerif', fontWeight: 700, fontSize: n.length > 2 ? 28 : 32, letterSpacing: n.length > 2 ? 8 : 16, paddingLeft: n.length > 2 ? 8 : 16, whiteSpace: 'nowrap', textShadow: `0 0 2px ${p.edge}, 0 0 6px ${p.edge}aa, 0 1px 3px #0005`}}>
            {n}
          </div>
        ));
      }
    }
  }
  return <>{out}</>;
};
