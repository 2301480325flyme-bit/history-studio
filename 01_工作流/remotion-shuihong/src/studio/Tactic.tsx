import React from 'react';
import {Banner, Footman, Rider, type Placed} from './Army';
import {clamp, easeOut, smooth} from './anim';
import type {TacticEl} from './types';
import {RaidTactic} from './RaidTactic';

// 战场示意 (battle close-up): the map dims and a battlefield diagram takes the middle of the screen,
// drawn with the same painted soldiers as the map armies. One `tactic` element per beat, each a phase of
// the same fight, so the diagram plays on across beats:
//   deploy  the attacker forms up (infantry square in the centre, cavalry on both wings, elite riders in front);
//           the defender holds a small shield line with crossbows behind
//   charge  the wings swing out and curve in to envelop the defender (dashed arrows, then the riders follow)
//   volley  the crossbows fire; the front riders fall
//   rout    the attacker turns and runs; the defender rises and pushes forward
// Layout `square_wings` (界桥): attacker on the right facing left, defender on the left facing right.

const W = 1920, H = 1080;
const rnd = (i: number, k: number) => {
  const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};
type Unit = {kind: 'cav' | 'elite' | 'foot' | 'shield' | 'xbow'; x: number; y: number; group: string; i: number};

function grid(group: string, kind: Unit['kind'], cx: number, cy: number, cols: number, rows: number, dx: number, dy: number): Unit[] {
  const out: Unit[] = [];
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const i = out.length;
      out.push({kind, group, i, x: cx + (c - (cols - 1) / 2) * dx + (rnd(i, r) - 0.5) * 6, y: cy + (r - (rows - 1) / 2) * dy + (rnd(i, c + 9) - 0.5) * 4});
    }
  return out;
}

const UNITS: Unit[] = [
  ...grid('square', 'foot', 1440, 560, 7, 6, 36, 30),
  ...grid('elite', 'elite', 1180, 560, 3, 4, 46, 34),
  ...grid('wingN', 'cav', 1380, 330, 4, 3, 50, 34),
  ...grid('wingS', 'cav', 1380, 800, 4, 3, 50, 34),
  ...grid('shield', 'shield', 650, 560, 4, 5, 30, 30),
  ...grid('xbow', 'xbow', 470, 560, 2, 9, 36, 26),
];
// where each attacking group heads in the charge (it stops at 82 % of the way)
const CHARGE: Record<string, {dx: number; dy: number; bend: number}> = {
  elite: {dx: -400, dy: 0, bend: 0},
  wingN: {dx: -1000, dy: 20, bend: -140},
  wingS: {dx: -1000, dy: -10, bend: 140},
  square: {dx: -120, dy: 0, bend: 0},
};
const LABELS: Record<string, {x: number; y: number; text: string; side: 'a' | 'd'}> = {
  square: {x: 1440, y: 430, text: '步兵三万 · 方阵', side: 'a'},
  elite: {x: 1180, y: 455, text: '白马义从', side: 'a'},
  wingN: {x: 1380, y: 245, text: '骑兵 · 左翼', side: 'a'},
  wingS: {x: 1380, y: 890, text: '骑兵 · 右翼', side: 'a'},
  shield: {x: 650, y: 665, text: '先登八百 · 伏楯', side: 'd'},
  xbow: {x: 450, y: 420, text: '强弩千张', side: 'd'},
};

function chargePos(u: Unit, k: number): [number, number] {
  const c = CHARGE[u.group];
  if (!c || k <= 0) return [u.x, u.y];
  const e = 0.82 * k;
  // quadratic bend: wings swing outward first, then curve in
  const bx = u.x + c.dx * e, by = u.y + c.dy * e + c.bend * 4 * e * (1 - e) * -1;
  return [bx, by];
}

export const TacticMark: React.FC<{el: TacticEl; sec: number}> = ({el, sec}) => {
  if (el.layout === 'raid') return <RaidTactic el={el} sec={sec} />;   // 突袭（张辽八百）
  if (sec < el.start || sec > el.end) return null;
  const t = sec - el.start;
  const fadeIn = el.first ? smooth(clamp(t / 0.6)) : 1;
  const fadeOut = el.last ? 1 - smooth(clamp((sec - (el.end - 0.6)) / 0.6)) : 1;
  const op = fadeIn * fadeOut;
  const ph = el.phase;
  const order = ['deploy', 'charge', 'volley', 'rout'];
  const p = order.indexOf(ph);
  // progress of each stage at this moment
  const deployK = p > 0 || !el.first ? 1 : easeOut(clamp(t / 1.4));
  const chargeK = p > 1 ? 1 : p === 1 ? smooth(clamp((t - 0.4) / 2.6)) : 0;
  const volleyK = p > 2 ? 1 : p === 2 ? clamp(t / 1.6) : 0;
  const routK = p === 3 ? smooth(clamp(t / 3)) : 0;
  const A = el.colors.a, D = el.colors.d;
  const placed: React.ReactNode[] = [];
  const sorted = [...UNITS].sort((a, b) => a.y - b.y);
  for (const u of sorted) {
    const att = u.group in CHARGE;
    let [x, y] = att ? chargePos(u, chargeK) : [u.x, u.y];
    let dim = 1, face: 1 | -1 = att ? -1 : 1, tilt = 0;
    if (att) {
      // slide in from the right while deploying
      x += (1 - deployK) * (260 + rnd(u.i, 3) * 80);
      // volley: the front of the charge falls (riders nearest the shield line)
      const front = u.group !== 'square' && rnd(u.i, u.group.length) < 0.55;
      if (volleyK > 0 && front) {
        const hit = clamp((volleyK - 0.35 - rnd(u.i, 5) * 0.3) / 0.25);
        tilt = -70 * hit;
        dim = 1 - 0.75 * hit;
      }
      if (routK > 0) {
        face = 1;
        x += routK * (520 + rnd(u.i, 7) * 160);
        y += (rnd(u.i, 8) - 0.5) * 120 * routK;
        dim *= 1 - 0.6 * routK;
      }
    } else {
      // the 800 crouch under their shields until the volley, then rise; in the rout they push forward
      const crouch = u.group === 'shield' ? (p < 2 ? 1 : 1 - clamp(volleyK / 0.3)) : 0;
      y += crouch * 7;
      dim = 1 - 0.25 * crouch;
      if (routK > 0) x += routK * 260;
    }
    const s: Placed = {x, y, face, tilt, phase: sec * (att && (chargeK > 0 && chargeK < 1 || routK > 0) ? 14 : 3) + u.i, row: 0};
    const col = att ? A : D;
    placed.push(u.kind === 'cav' || u.kind === 'elite'
      ? <Rider key={u.group + u.i} s={s} color={u.kind === 'elite' ? '#f6f1e4' : col} dim={dim} />
      : <Footman key={u.group + u.i} s={s} color={col} dim={dim} kind={u.kind === 'xbow' ? 'crossbow' : 'infantry'} />);
  }
  // envelopment arrows during the charge
  const arrows = ['wingN', 'wingS', 'elite'].map((g) => {
    const c = CHARGE[g], base = LABELS[g];
    const x0 = g === 'elite' ? 1120 : 1340, y0 = g === 'wingN' ? 330 : g === 'wingS' ? 800 : 560;
    const x1 = x0 + c.dx * 0.82, y1 = y0 + c.dy * 0.82;
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2 - c.bend * 1.6;
    return {g, d: `M${x0} ${y0} Q${mx} ${my} ${x1} ${y1}`, base};
  });
  const arrowK = p === 1 ? easeOut(clamp(t / 0.8)) * (1 - smooth(clamp((t - 2.6) / 0.8))) : 0;
  // crossbow bolts
  const bolts: React.ReactNode[] = [];
  if (volleyK > 0 && volleyK < 1) {
    for (let i = 0; i < 46; i++) {
      const delay = rnd(i, 1) * 0.35;
      const q = clamp((volleyK - delay) / 0.4);
      if (q <= 0 || q >= 1) continue;
      const x0 = 480 + rnd(i, 2) * 40, y0 = 440 + rnd(i, 3) * 240;
      const tx = 900 + rnd(i, 4) * 300, ty = 260 + rnd(i, 5) * 600;
      const x = x0 + (tx - x0) * q, y = y0 + (ty - y0) * q - Math.sin(Math.PI * q) * 60;
      const ang = Math.atan2(ty - y0 - Math.cos(Math.PI * q) * 60 * Math.PI, tx - x0) * 180 / Math.PI;
      bolts.push(<g key={i} transform={`translate(${x} ${y}) rotate(${ang})`}><line x1={-60} y1={0} x2={0} y2={0} stroke="#ffe9b0" strokeOpacity={0.35} strokeWidth={6} /><line x1={-36} y1={0} x2={0} y2={0} stroke="#1a0f08" strokeWidth={3} /><path d="M0 -5 L11 0 L0 5 Z" fill="#1a0f08" /></g>);
    }
  }
  const lab = (g: string, k: number) => {
    const L = LABELS[g];
    if (k <= 0) return null;
    const col = L.side === 'a' ? A : D;
    const dx = g in CHARGE && chargeK > 0 ? CHARGE[g].dx * 0.82 * chargeK : 0;
    const dy = g in CHARGE && chargeK > 0 ? CHARGE[g].dy * 0.82 * chargeK : 0;
    return (
      <g key={'l' + g} opacity={k * (routK > 0 && L.side === 'a' ? 1 - routK : 1)} transform={`translate(${L.x + dx} ${L.y + dy})`}>
        <rect x={-L.text.length * 13 - 12} y={-19} width={L.text.length * 26 + 24} height={34} rx={6} fill="#1b130cdd" stroke={col} strokeWidth={2} />
        <text x={0} y={7} textAnchor="middle" fontFamily="StoryBrush" fontSize={24} fill="#fff1d2">{L.text}</text>
      </g>
    );
  };
  const labelK = (i: number) => (p > 0 || !el.first ? 1 : smooth(clamp((t - 0.6 - i * 0.25) / 0.4)));
  return (
    <div style={{position: 'absolute', inset: 0, opacity: op}}>
      {/* the field: darkened map, a soft earthen battlefield panel */}
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 72% 64% at 50% 52%, rgba(70,58,34,.97), rgba(20,15,9,.99))'}} />
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        <defs>
          <marker id="tacArrow" viewBox="0 0 10 10" refX={6} refY={5} markerWidth={5} markerHeight={5} orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill={A} /></marker>
          <filter id="tacGlow"><feGaussianBlur stdDeviation={3} /></filter>
        </defs>
        {/* ground texture: faint furrows */}
        {Array.from({length: 18}, (_, i) => <path key={i} d={`M120 ${150 + i * 45} Q960 ${130 + i * 45 + (i % 2 ? 18 : -18)} 1800 ${150 + i * 45}`} stroke="#c8a96a" strokeOpacity={0.07} strokeWidth={2} fill="none" />)}
        <g transform="translate(960 560) scale(1.32) translate(-960 -560)">
        {arrowK > 0 && arrows.map((a) => (
          <g key={a.g} opacity={arrowK}>
            <path d={a.d} stroke={A} strokeWidth={16} strokeOpacity={0.35} fill="none" filter="url(#tacGlow)" />
            <path d={a.d} stroke={A} strokeWidth={7} fill="none" strokeDasharray="22 12" strokeDashoffset={-sec * 60} markerEnd="url(#tacArrow)" />
          </g>
        ))}
        {placed}
        <Banner x={1500 + (routK ? routK * 600 : 0) + (1 - deployK) * 300} y={380} face={-1} t={sec} color={A} text={el.banners?.a ?? '公'} dim={1 - 0.6 * routK} />
        <Banner x={600 + routK * 260} y={420} face={1} t={sec} color={D} text={el.banners?.d ?? '麴'} dim={1} />
        {bolts}
        {Object.keys(LABELS).map((g, i) => lab(g, labelK(i)))}
        </g>
        {p === 1 && arrowK > 0.3 && <text x={960} y={140} textAnchor="middle" fontFamily="StoryBrush" fontSize={54} fill="#ffe4a6" opacity={arrowK} style={{paintOrder: 'stroke'}} stroke="#1b130c" strokeWidth={8}>两翼包抄</text>}
        {p === 2 && volleyK > 0.1 && volleyK < 1 && <text x={700} y={300} textAnchor="middle" fontFamily="StoryBrush" fontSize={60} fill="#ffd27a" stroke="#1b130c" strokeWidth={8} style={{paintOrder: 'stroke'}}>强弩齐发</text>}
      </svg>
      <div style={{position: 'absolute', left: 60, top: 120, fontFamily: 'StoryBrush', fontSize: 40, color: '#f3dfb4', textShadow: '0 2px 8px #000'}}>{el.title ?? '战场示意'}<span style={{fontFamily: 'StorySans', fontSize: 18, marginLeft: 12, color: '#c9b48c'}}>示意图，非实际兵力比例</span></div>
    </div>
  );
};
