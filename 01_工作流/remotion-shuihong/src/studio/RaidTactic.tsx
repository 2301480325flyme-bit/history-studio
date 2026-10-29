import React from 'react';
import {Banner, Footman, Rider, type Placed} from './Army';
import {clamp, easeOut, smooth} from './anim';
import type {TacticEl} from './types';

// 战场示意 · 突袭 (layout `raid`, 2026-10-23, after 界桥 `square_wings`): a small band sallies out of a city into a
// huge layered camp. Written for 合肥/逍遥津 (张辽 八百 vs 孙权 十万, 《三国志·张辽传》) and reusable for any
// "few strike the many" raid. Phases, one per beat, played back to back:
//   deploy    the band forms a wedge at the city gate; the camp sits in layers to the right, the commander's banner below a mound
//   charge    the wedge drives through the layers to the commander's banner; men on its path fall
//   climb     the commander runs up the mound (走登高冢) while the wedge stands at its foot
//   surround  the camp closes a double ring round the wedge
//   breakout  the head of the wedge cuts out of the ring, turns back in, and brings the rest out; the ring recoils (士气崩)

const W = 1920, H = 1080;
const rnd = (i: number, k: number) => {
  const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const GATE: [number, number] = [430, 560];
const STRIKE: [number, number] = [1300, 520];     // where the wedge reaches the commander
const MOUND: [number, number] = [1500, 430];
const OUT: [number, number] = [900, 600];          // first break-out point
const HOME: [number, number] = [640, 580];         // where everyone ends up

type Man = {x: number; y: number; i: number; head: boolean; rider: boolean};
// the wedge: apex first (the general), then rows widening backwards
const WEDGE: Man[] = (() => {
  const out: Man[] = [];
  for (let r = 0; r < 6; r++)
    for (let j = 0; j <= r; j++) {
      const i = out.length;
      out.push({x: -r * 40, y: (j - r / 2) * 40, i, head: r <= 1, rider: r === 0 || (r === 1 && j === 0)});
    }
  return out;
})();
// the camp: three layers of men with gaps between them (垒)
const CAMP: Man[] = (() => {
  const out: Man[] = [];
  const bands = [{x: 900, cols: 3}, {x: 1080, cols: 3}, {x: 1300, cols: 4}];
  for (const b of bands)
    for (let c = 0; c < b.cols; c++)
      for (let r = 0; r < 12; r++) {
        const i = out.length;
        const y = 250 + r * 54 + (rnd(i, 1) - 0.5) * 14;
        if (b.x === 1300 && c >= 2 && y < 470) continue;         // the mound
        out.push({x: b.x + c * 44 + (rnd(i, 2) - 0.5) * 10, y, i, head: false, rider: false});
      }
  return out;
})();

const lerp = (a: [number, number], b: [number, number], k: number): [number, number] => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
function segDist(p: [number, number], a: [number, number], b: [number, number]) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const k = clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy));
  return Math.hypot(p[0] - a[0] - dx * k, p[1] - a[1] - dy * k);
}

export const RaidTactic: React.FC<{el: TacticEl; sec: number}> = ({el, sec}) => {
  if (sec < el.start || sec > el.end) return null;
  const t = sec - el.start;
  const op = (el.first ? smooth(clamp(t / 0.6)) : 1) * (el.last ? 1 - smooth(clamp((sec - (el.end - 0.6)) / 0.6)) : 1);
  const order = ['deploy', 'charge', 'climb', 'surround', 'breakout'];
  const p = order.indexOf(el.phase);
  const deployK = p > 0 || !el.first ? 1 : easeOut(clamp(t / 1.2));
  const chargeK = p > 1 ? 1 : p === 1 ? smooth(clamp((t - 0.3) / 3.2)) : 0;
  const climbK = p > 2 ? 1 : p === 2 ? smooth(clamp((t - 0.2) / 1.4)) : 0;
  const ringK = p > 3 ? 1 : p === 3 ? smooth(clamp((t - 0.05) / 0.8)) : 0;   // the ring closes fast: the narration moves straight on to the break-out
  const breakK = p === 4 ? clamp(t / 5.2) : 0;
  const outK = smooth(clamp(breakK / 0.42));                    // the head cuts its way out
  const backK = smooth(clamp((breakK - 0.45) / 0.55));          // …turns back and brings everyone out
  const A = el.colors.a, D = el.colors.d;
  const L = el.labels ?? {};

  // wedge centre
  let centre = lerp(GATE, STRIKE, chargeK);
  const headPos = backK > 0 ? lerp(OUT, HOME, backK) : lerp(STRIKE, OUT, outK);
  const restPos = backK > 0 ? lerp(STRIKE, HOME, backK) : STRIKE;
  if (p < 4) centre = lerp(GATE, STRIKE, chargeK);
  const men: React.ReactNode[] = [];
  const marching = (p === 1 && chargeK < 1) || (p === 4 && breakK < 1);
  for (const m of WEDGE) {
    const base = p === 4 ? (m.head ? headPos : restPos) : centre;
    const x = base[0] + m.x - (1 - deployK) * 120, y = base[1] + m.y;
    const face: 1 | -1 = p === 4 && ((m.head && outK > 0 && backK === 0) || backK > 0.05) ? -1 : 1;
    const s: Placed = {x, y, face, tilt: 0, phase: sec * (marching ? 14 : 3) + m.i, row: 0};
    men.push(m.rider ? <Rider key={'w' + m.i} s={s} color={m.i === 0 ? '#f6f1e4' : A} dim={deployK} /> : <Footman key={'w' + m.i} s={s} color={A} dim={deployK} />);
  }
  // camp: men on the path fall; then the nearest close a double ring; then the ring breaks and recoils
  const strikeAt = (k: number) => lerp(GATE, STRIKE, k);
  const ringIds = [...CAMP].map((m) => ({m, d: Math.hypot(m.x - STRIKE[0], m.y - STRIKE[1])})).sort((a, b) => a.d - b.d).slice(0, 34).map((x) => x.m.i);
  const camp = CAMP.map((m) => {
    let [x, y] = [m.x, m.y];
    let dim = 1, tilt = 0, face: 1 | -1 = -1;
    const onPath = segDist([m.x, m.y], GATE, STRIKE) < 62;
    if (onPath) {
      const passed = clamp((strikeAt(chargeK)[0] - m.x + 40) / 60);
      tilt = -75 * passed;
      dim = 1 - 0.7 * passed;
    }
    const ri = ringIds.indexOf(m.i);
    if (ri >= 0 && !onPath) {
      const outer = ri % 2 === 1;
      const ang = (ri / ringIds.length) * Math.PI * 2 + (outer ? 0.09 : 0);
      const rad = (outer ? 205 : 140) + (rnd(m.i, 4) - 0.5) * 16;
      let target: [number, number] = [STRIKE[0] + Math.cos(ang) * rad, STRIKE[1] + Math.sin(ang) * rad * 0.72];
      // the break-out: the west side of the ring is pushed apart, then the whole ring falls back
      const west = Math.cos(ang) < -0.55;
      if (outK > 0 && west) target = [target[0] + Math.cos(ang) * 70 * outK, target[1] + Math.sin(ang) * 90 * outK];
      if (backK > 0) target = [target[0] + Math.cos(ang) * 120 * backK, target[1] + Math.sin(ang) * 80 * backK];
      [x, y] = lerp([m.x, m.y], target, ringK);
      face = x < STRIKE[0] ? 1 : -1;
      dim = 1 - 0.45 * backK;
    } else if (backK > 0) {
      dim *= 1 - 0.35 * backK;
    }
    const s: Placed = {x, y, face, tilt, phase: sec * (ringK > 0 && ringK < 1 ? 10 : 2) + m.i, row: 0};
    return {y, node: <Footman key={'c' + m.i} s={s} color={D} dim={dim} />};
  });
  const all = [...camp, ...men.map((n, k) => ({y: (p === 4 ? (WEDGE[k].head ? headPos : restPos) : centre)[1] + WEDGE[k].y, node: n}))].sort((a, b) => a.y - b.y);
  const bannerD: [number, number] = lerp([MOUND[0] - 70, MOUND[1] + 110], [MOUND[0], MOUND[1] - 34], climbK);
  const caption = p === 1 && chargeK > 0.25 ? L.charge ?? '冲垒入，至麾下'
    : p === 2 && climbK > 0.2 ? L.climb ?? '走登高冢'
    : p === 3 && ringK > 0.3 ? L.ring ?? '聚围数重'
    : p === 4 ? (backK > 0.15 ? L.back ?? '复还突围，拔出余众' : outK > 0.2 ? L.out ?? '围开' : null) : null;
  const tag = (x: number, y: number, text: string, color: string, k = 1) => (
    <g opacity={k} transform={`translate(${x} ${y})`}>
      <rect x={-text.length * 13 - 12} y={-19} width={text.length * 26 + 24} height={34} rx={6} fill="#1b130cdd" stroke={color} strokeWidth={2} />
      <text x={0} y={7} textAnchor="middle" fontFamily="StoryBrush" fontSize={24} fill="#fff1d2">{text}</text>
    </g>
  );
  const labK = p > 0 || !el.first ? 1 : smooth(clamp((t - 0.6) / 0.5));
  return (
    <div style={{position: 'absolute', inset: 0, opacity: op}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 72% 64% at 50% 52%, rgba(70,58,34,.97), rgba(20,15,9,.99))'}} />
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        {Array.from({length: 18}, (_, i) => <path key={i} d={`M120 ${150 + i * 45} Q960 ${130 + i * 45 + (i % 2 ? 18 : -18)} 1800 ${150 + i * 45}`} stroke="#c8a96a" strokeOpacity={0.07} strokeWidth={2} fill="none" />)}
        <g transform="translate(960 560) scale(1.12) translate(-960 -560)">
          {/* the city the band comes out of */}
          <g opacity={0.95}>
            <rect x={150} y={380} width={120} height={380} fill="#5a4a32" stroke="#d8c08a" strokeWidth={3} />
            {Array.from({length: 9}, (_, k) => <rect key={k} x={142} y={384 + k * 42} width={16} height={20} fill="#d8c08a" opacity={0.8} />)}
            <rect x={262} y={530} width={14} height={60} fill="#1b130c" />
          </g>
          {/* the camp's palisades (垒) and the mound (高冢) */}
          {[870, 1050, 1270].map((x, k) => <rect key={k} x={x} y={225} width={k === 2 ? 180 : 150} height={660} rx={10} fill="none" stroke={D} strokeOpacity={0.35} strokeWidth={3} strokeDasharray="14 10" />)}
          <ellipse cx={MOUND[0]} cy={MOUND[1]} rx={130} ry={52} fill="#7a6a48" stroke="#c9b383" strokeOpacity={0.6} strokeWidth={2} />
          <ellipse cx={MOUND[0]} cy={MOUND[1] - 14} rx={80} ry={28} fill="#8c7a52" />
          {/* the wedge's track */}
          {p >= 1 && <path d={`M${GATE[0]} ${GATE[1]} L${strikeAt(chargeK)[0]} ${strikeAt(chargeK)[1]}`} stroke={A} strokeOpacity={0.45} strokeWidth={10} strokeDasharray="20 14" fill="none" />}
          {all.map((x) => x.node)}
          <Banner x={(p === 4 ? headPos : centre)[0] + 14} y={(p === 4 ? headPos : centre)[1] - 18} face={p === 4 && (backK > 0.05 || outK > 0) ? -1 : 1} t={sec} color={A} text={el.banners?.a ?? ''} dim={deployK} />
          <Banner x={bannerD[0]} y={bannerD[1]} face={-1} t={sec} color={D} text={el.banners?.d ?? ''} dim={1 - 0.3 * backK} />
          {tag(210, 340, L.city ?? '城', A, labK)}
          {tag(1150, 245, L.d ?? '十万大军', D, labK)}
          {tag(MOUND[0] + 120, MOUND[1] - 70, L.mound ?? '高冢', '#c9b383', labK * (p >= 1 ? 1 : 0.6))}
          {tag((p === 4 ? headPos : centre)[0] - 60, (p === 4 ? headPos : centre)[1] + 150, L.a ?? '敢死之士', A, labK)}
        </g>
        {caption && <text x={960} y={128} textAnchor="middle" fontFamily="StoryBrush" fontSize={56} fill="#ffe4a6" stroke="#1b130c" strokeWidth={8} style={{paintOrder: 'stroke'}}>{caption}</text>}
      </svg>
      {/* below the year badge (atlas look puts it top-left) */}
      <div style={{position: 'absolute', left: 60, top: 172, fontFamily: 'StoryBrush', fontSize: 40, color: '#f3dfb4', textShadow: '0 2px 8px #000'}}>{el.title ?? '战场示意'}</div>
    </div>
  );
};
