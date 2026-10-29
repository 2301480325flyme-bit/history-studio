import React from 'react';
import {staticFile} from 'remotion';
import {tongue} from './Fire';
import {clamp, smooth, type Pt} from './anim';

// A column of small soldiers that follows an arrow along its route: a banner
// carrier in front (faction colour + commander's surname), riders or foot
// soldiers behind in loose ranks, and a dust trail. Sprites stay upright and
// face left or right by the route direction, so they read as an army on a map.

export type Troops = {kind: 'cavalry' | 'infantry' | 'archer' | 'crossbow'; banner?: string; size: number; rout?: boolean; head_image?: string; head_name?: string};

export type Placed = {x: number; y: number; face: 1 | -1; tilt: number; phase: number; row: number};

// cumulative arc length for a polyline
export function arc(line: Pt[]) {
  const acc = [0];
  for (let i = 1; i < line.length; i++) acc.push(acc[i - 1] + Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]));
  return acc;
}

export function at(line: Pt[], acc: number[], d: number): {p: Pt; ang: number} {
  d = Math.max(0, Math.min(acc[acc.length - 1], d));
  let i = 1;
  while (i < acc.length - 1 && acc[i] < d) i++;
  const a = line[i - 1], b = line[i];
  const r = acc[i] - acc[i - 1] ? (d - acc[i - 1]) / (acc[i] - acc[i - 1]) : 0;
  return {p: [a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r], ang: Math.atan2(b[1] - a[1], b[0] - a[0])};
}

// deterministic jitter so every frame places the same soldier in the same spot
const rnd = (i: number, k: number) => {
  const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// Painted sprites (unit_cavalry / unit_infantry, facing right). They are neutral in colour: the faction shows as a
// coloured disc underfoot and on the column's banner. Drawn as SVG <image>; Episode preloads every anim file
// (delayRender) so each frame has them.
const CAV = staticFile('anim/unit_cavalry.png');
const FOOT: Record<string, string> = {infantry: staticFile('anim/unit_infantry.png'), archer: staticFile('anim/unit_archer.png'), crossbow: staticFile('anim/unit_crossbow.png')};
const GENERAL = staticFile('anim/unit_general.png');

export const Rider: React.FC<{s: Placed; color: string; dim: number}> = ({s, color, dim}) => {
  const bob = -Math.abs(Math.cos(s.phase)) * 2.4;          // gallop
  const sz = 62;
  return (
    <g transform={`translate(${s.x} ${s.y}) rotate(${s.tilt})`} opacity={dim}>
      <ellipse cx={0} cy={1} rx={19} ry={4.6} fill={color} opacity={0.75} stroke="#1c120b" strokeOpacity={0.35} strokeWidth={1} />
      <g transform={`translate(0 ${bob}) scale(${s.face} 1)`}>
        <image href={CAV} x={-sz / 2} y={-sz + 4} width={sz} height={sz} />
      </g>
    </g>
  );
};

// foot soldier: spear-and-shield infantry, archer or crossbowman
export const Footman: React.FC<{s: Placed; color: string; dim: number; kind?: string}> = ({s, color, dim, kind = 'infantry'}) => {
  const bob = -Math.abs(Math.cos(s.phase)) * 1.4;
  const w = 30, h = 45;
  return (
    <g transform={`translate(${s.x} ${s.y}) rotate(${s.tilt})`} opacity={dim}>
      <ellipse cx={0} cy={1} rx={10} ry={3} fill={color} opacity={0.75} stroke="#1c120b" strokeOpacity={0.35} strokeWidth={1} />
      <g transform={`translate(0 ${bob}) scale(${s.face} 1)`}>
        <image href={FOOT[kind] ?? FOOT.infantry} x={-w / 2} y={-h + 3} width={w} height={h} />
      </g>
    </g>
  );
};

export const Banner: React.FC<{x: number; y: number; face: 1 | -1; t: number; color: string; text?: string; dim: number; lean?: number}> = ({x, y, face, t, color, text, dim, lean = 0}) => {
  const wave = Math.sin(t * 7);
  const flag = `M0 -64 Q${-14 - 3 * wave} ${-62 + 2 * wave} -30 ${-63 + 3 * wave} L-30 ${-37 + 3 * wave} Q${-14 + 3 * wave} ${-38 - 2 * wave} 0 -38 Z`;
  return (
    <g transform={`translate(${x} ${y}) scale(1.35) rotate(${-face * lean})`} opacity={dim}>
      <ellipse cx={0} cy={1} rx={9} ry={2.2} fill="#000" opacity={0.3} />
      <path d="M0 0 L0 -68" stroke="#3b2414" strokeWidth={2.6} strokeLinecap="round" />
      <circle cx={0} cy={-69} r={2.4} fill="#d8b46a" />
      <g transform={`scale(${face} 1)`}>
        <path d={flag} fill={color} stroke="#fff1d6" strokeWidth={1.6} />
        <path d={`M-30 ${-37 + 3 * wave} l-5 4 l5 2 l-5 4 l5 1`} fill="none" stroke={color} strokeWidth={2} />
      </g>
      {text && <text x={-face * 15} y={-45} textAnchor="middle" fontSize={20} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif" stroke="#00000055" strokeWidth={0.6}>{text}</text>}
    </g>
  );
};

// A commander's portrait as a round medallion (2026-10-19: 原型头像带兵). Faction-coloured ring, his name under it.
export const Medallion: React.FC<{x: number; y: number; r?: number; src: string; name?: string; color: string; id: string; dim?: number; fs?: number}> = ({x, y, r = 30, src, name, color, id, dim = 1, fs = 20}) => (
  <g transform={`translate(${x} ${y})`} opacity={dim}>
    <defs><clipPath id={`medal-${id}`}><circle r={r} /></clipPath></defs>
    <circle r={r + 4} fill={color} stroke="#1c120b" strokeOpacity={0.5} strokeWidth={2} />
    <image href={staticFile(src)} x={-r} y={-r} width={2 * r} height={2 * r} preserveAspectRatio="xMidYMid slice" clipPath={`url(#medal-${id})`} />
    {name && <text y={r + fs + 2} textAnchor="middle" fontSize={fs} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif" stroke="#00000066" strokeWidth={3} paintOrder="stroke">{name}</text>}
  </g>
);

// Two commanders on one road (2026-10-19, after 纸上谈兵《井陉之战》): the leader rides the route, the pursuer
// closes in on him. Each head has a glow and pops in; a pulsing ring, dust and crossed-sword sparks mark the moment
// the pursuer catches up. The pursuer's lag shrinks as the chase runs, so the gap reads as pressure, not a fixed offset.
export const ChaseMark: React.FC<{line: Pt[]; prog: number; sec: number; start: number; lag: number; leader: {src: string; name: string; color: string}; pursuer: {src: string; name: string; color: string}; id: string}> = ({line, prog, sec, start, lag, leader, pursuer, id}) => {
  const acc = arc(line);
  const total = acc[acc.length - 1];
  const t = sec - start;
  const lp = Math.max(0, Math.min(1, prog));
  if (lp <= 0.001) return null;
  const pp = Math.max(0, lp - lag * (1 - 0.6 * lp));            // the gap closes as the chase runs
  const L = at(line, acc, total * lp);
  const P = at(line, acc, total * pp);
  const gap = lp - pp;
  const contact = smooth(clamp((0.06 - gap) / 0.04));           // 1 when the pursuer is almost on the leader
  const pop = (k: number) => 0.6 + 0.4 * smooth(clamp(k / 0.35));
  const pulse = 1 + 0.12 * Math.sin(t * 9) * contact;
  const dust = [0, 1, 2].map((k) => {
    const life = ((t * 1.4 + k / 3) % 1);
    const d = total * pp - 22 - life * 30;
    if (d < 4) return null;
    const q = at(line, acc, d).p;
    const w = 46 + life * 40;
    return <image key={k} href={staticFile(`anim/dust_cloud_${1 + (k % 2)}.png`)} x={q[0] - w / 2} y={q[1] - 6 - life * 8} width={w} height={w / 2} opacity={0.5 * (1 - life)} />;
  });
  return (
    <g opacity={smooth(clamp(t / 0.3))}>
      {pp > 0.001 && <g>{dust}</g>}
      {pp > 0.001 && (
        <g transform={`translate(${P.p[0]} ${P.p[1]}) scale(${pop(t)})`}>
          <circle r={22} fill={pursuer.color} opacity={0.28} />
          <Medallion x={0} y={0} src={pursuer.src} name={pursuer.name} color={pursuer.color} id={`${id}-p`} r={15} fs={11} />
        </g>
      )}
      <g transform={`translate(${L.p[0]} ${L.p[1]}) scale(${pop(t) * pulse})`}>
        <circle r={26} fill={leader.color} opacity={0.22} />
        <Medallion x={0} y={0} src={leader.src} name={leader.name} color={leader.color} id={`${id}-l`} r={18} fs={12} />
      </g>
      {contact > 0.02 && (
        <g opacity={contact}>
          <circle cx={L.p[0]} cy={L.p[1]} r={22 + 8 * Math.sin(t * 9)} fill="none" stroke={pursuer.color} strokeWidth={3} />
          <path d={`M${L.p[0] - 11} ${L.p[1] - 26} L${L.p[0] + 11} ${L.p[1] - 10} M${L.p[0] + 11} ${L.p[1] - 26} L${L.p[0] - 11} ${L.p[1] - 10}`} stroke="#fff3d8" strokeWidth={2.4} strokeLinecap="round" />
          <circle cx={L.p[0] + 4} cy={L.p[1] - 22} r={2 + 1.2 * Math.sin(t * 20)} fill="#ffd27a" />
        </g>
      )}
    </g>
  );
};

export const ArmyColumn: React.FC<{line: Pt[]; prog: number; trim: number; sec: number; start: number; color: string; troops: Troops; id: string}> = ({line, prog, trim, sec, start, color, troops, id}) => {
  const acc = arc(line);
  const total = acc[acc.length - 1];
  const head = Math.max(0, (total - trim) * prog - 26);         // banner stays just behind the arrowhead
  const moving = prog < 0.995;
  const cav = troops.kind === 'cavalry';
  const ranks = Math.max(2, Math.round(troops.size * (cav ? 2.2 : 2.0)));
  const files = cav ? 2 : 3;
  const rowGap = cav ? 46 : 27;
  const colGap = cav ? 34 : 22;
  const t = sec - start;
  const rout = !!troops.rout;
  const soldiers: Placed[] = [];
  for (let r = 0; r < ranks; r++) {
    for (let c = 0; c < files; c++) {
      const i = r * files + c;
      // a routed army straggles: uneven gaps, wide scatter, some lag far behind
      const d = rout ? head - 40 - r * rowGap * (0.8 + rnd(i, 7) * 0.9) - rnd(i, 1) * 30 : head - 48 - r * rowGap - rnd(i, 1) * 6;
      if (d < 4) continue;                                       // still "inside" the start city
      const {p, ang} = at(line, acc, d);
      const nx = -Math.sin(ang), ny = Math.cos(ang);
      const off = (c - (files - 1) / 2 + (r % 2 ? 0.35 : -0.35)) * colGap + (rnd(i, 2) - 0.5) * (rout ? 46 : 5);
      const face: 1 | -1 = Math.cos(ang) >= 0 ? 1 : -1;
      const tilt = Math.max(-14, Math.min(14, ((face === 1 ? ang : Math.PI - ang) * 180) / Math.PI * 0.35));
      soldiers.push({x: p[0] + nx * off, y: p[1] + ny * off * 0.75, face, tilt: face * tilt, phase: (moving ? t * (cav ? 15 : 10) * (rout ? 1.5 : 1) : 0.4) + rnd(i, 3) * 6.28, row: r});
    }
  }
  soldiers.sort((a, b) => a.y - b.y);
  const lead = at(line, acc, Math.max(4, head));
  const leadFace: 1 | -1 = Math.cos(lead.ang) >= 0 ? 1 : -1;
  // dust: puffs dropped behind the column while it moves
  const dust = moving ? Array.from({length: 9}, (_, k) => {
    const life = ((t * 1.6 + k / 9) % 1);
    const d = head - 40 - ranks * rowGap * (0.3 + 0.8 * life) ;
    if (d < 4) return null;
    const {p} = at(line, acc, d);
    const w = 70 + life * 90;
    return <image key={k} href={staticFile(`anim/dust_cloud_${1 + (k % 2)}.png`)} x={p[0] + (rnd(k, 5) - 0.5) * 30 - w / 2} y={p[1] - 8 - life * 12 - w / 4} width={w} height={w / 2} opacity={0.55 * (1 - life)} />;
  }) : null;
  const appear = smooth(clamp(t / 0.4));
  return (
    <g opacity={appear}>
      <defs>
        <filter id={`dust-${id}`}><feGaussianBlur stdDeviation={4} /></filter>
        {/* light paper-coloured outline so dark sprites read against the terrain */}
        <filter id={`halo-${id}`} x="-10%" y="-10%" width="120%" height="120%">
          <feMorphology in="SourceAlpha" operator="dilate" radius={2} result="d" />
          <feFlood floodColor="#f6ead0" floodOpacity={0.9} />
          <feComposite in2="d" operator="in" result="o" />
          <feMerge><feMergeNode in="o" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      <g>{dust}</g>
      <g filter={`url(#halo-${id})`}>{soldiers.map((s, k) => cav ? <Rider key={k} s={s} color={color} dim={rout ? 0.85 : 1} /> : <Footman key={k} s={s} color={color} dim={rout ? 0.85 : 1} kind={troops.kind} />)}</g>
      {/* the general rides at the head of a cavalry column, just behind its banner */}
      {cav && head > 6 && !rout && (() => {
        const g = at(line, acc, Math.max(4, head - 30));
        const face: 1 | -1 = Math.cos(g.ang) >= 0 ? 1 : -1;
        const bob = moving ? -Math.abs(Math.cos(t * 15)) * 2.4 : 0;
        return <g filter={`url(#halo-${id})`} transform={`translate(${g.p[0]} ${g.p[1] + bob}) scale(${face} 1)`}><image href={GENERAL} x={-40} y={-76} width={80} height={80} /></g>;
      })()}
      {head > 6 && troops.head_image && <Medallion x={lead.p[0]} y={lead.p[1] - 46} r={28} src={troops.head_image} name={troops.head_name} color={color} id={`${id}-h`} dim={rout ? 0.8 : 1} />}
      {head > 6 && !troops.head_image && <Banner x={lead.p[0]} y={lead.p[1]} face={leadFace} t={t} color={color} text={troops.banner} dim={rout ? 0.8 : 1} lean={rout ? 32 : 0} />}
    </g>
  );
};

// Two armies locked in battle at one place: each side's soldiers stand on the
// side they came from, lunging at each other; dust, sparks and crossed swords
// mark the fight. When the loser breaks, its soldiers fall back and fade while
// the rout column (a separate arrow) carries the survivors away.
export type ClashSide = {faction: string; color: string; kind: 'cavalry' | 'infantry' | 'archer' | 'crossbow'; banner?: string};
export const ClashMark: React.FC<{sides: ClashSide[]; froms: Pt[]; p: Pt; sec: number; start: number; end: number; loser?: number; loserAt?: number; title?: string; id: string; traceEnd?: number; burnSide?: number; burnAt?: number}> = ({sides, froms, p, sec, start, end, loser, loserAt, title, id, traceEnd, burnSide, burnAt}) => {
  if (sec < start) return null;
  if (sec > end + 0.6) {
    // battle trace: a small faded crossed-swords mark (and the battle's name) stays on the site
    if (!traceEnd || sec > traceEnd) return null;
    const k = smooth(clamp((sec - end - 0.3) / 0.6)) * (1 - smooth(clamp((sec - traceEnd + 0.6) / 0.6)));
    return (
      <g opacity={0.8 * k} transform={`translate(${p[0]} ${p[1] - 26})`}>
        <circle r={13} fill="#6a2a1e" stroke="#ead2a0" strokeWidth={2} />
        <path d="M-6 -6L6 6M6 -6L-6 6" stroke="#fff3d8" strokeWidth={2.4} strokeLinecap="round" />
        {title && <text x={18} y={6} fontSize={18} fill="#5a2a1a" fontFamily="StorySerif" fontWeight={700} stroke="#f4ecdc" strokeWidth={3} paintOrder="stroke">{title}</text>}
      </g>
    );
  }
  const t = sec - start;
  const op = smooth(clamp(t / 0.35)) * (1 - smooth(clamp((sec - end) / 0.6)));
  const broken = loserAt != null && sec >= loserAt ? smooth(clamp((sec - loserAt) / 0.8)) : 0;
  const fighting = 1 - broken;
  const soldiers: {s: Placed; color: string; cav: boolean; kind: string; dim: number; burn: number}[] = [];
  sides.forEach((side, k) => {
    const f = froms[k] ?? [p[0] + (k ? 1 : -1) * 100, p[1]];
    let dx = f[0] - p[0], dy = f[1] - p[1];
    const n = Math.hypot(dx, dy) || 1;
    dx /= n; dy /= n;
    if (Math.abs(dx) < 0.35) dx = (k ? 1 : -1) * 0.35;     // keep the two sides apart left / right
    const cav = side.kind === 'cavalry';
    const lost = loser === k ? broken : 0;
    for (let i = 0; i < 11; i++) {
      const along = 34 + (i % 4) * 34 + rnd(i + k * 9, 1) * 14 + lost * 80;
      const across = ((Math.floor(i / 4) - 1) * 40 + (rnd(i + k * 9, 2) - 0.5) * 18);
      // fire attack: soldiers of the burnt side catch fire one after another and stagger
      const burn = burnSide === k && burnAt != null ? smooth(clamp((sec - burnAt - rnd(i, 7) * 0.9) / 0.35)) : 0;
      const lunge = fighting * Math.sin(t * 9 + i * 1.7) * 5 + burn * Math.sin(sec * 23 + i * 2.1) * 4;
      const x = p[0] + dx * (along - lunge) - dy * across;
      const y = p[1] + dy * (along - lunge) * 0.6 + dx * across * 0.5;
      const face: 1 | -1 = p[0] >= x ? 1 : -1;
      const fallen = lost * (rnd(i, 4) < 0.6 ? 1 : 0);
      soldiers.push({s: {x, y, face, tilt: face * 80 * fallen, phase: t * 18 * fighting + i, row: i}, color: side.color, cav, kind: side.kind, dim: (1 - lost * 0.75) * (1 - burn * 0.2), burn});
    }
  });
  soldiers.sort((a, b) => a.s.y - b.s.y);
  const banners = sides.map((side, k) => {
    if (!side.banner) return null;
    const f = froms[k] ?? [p[0] + (k ? 1 : -1) * 100, p[1]];
    let dx = f[0] - p[0], dy = f[1] - p[1];
    const n = Math.hypot(dx, dy) || 1;
    dx /= n; dy /= n;
    if (Math.abs(dx) < 0.35) dx = (k ? 1 : -1) * 0.35;
    const lost = loser === k ? broken : 0;
    const bx = p[0] + dx * (150 + lost * 80), by = p[1] + dy * 90 + 10;
    return <Banner key={'b' + k} x={bx} y={by} face={p[0] >= bx ? 1 : -1} t={t} color={side.color} text={side.banner} dim={1 - 0.6 * lost} lean={lost * 35} />;
  });
  const seed = Math.floor(sec * 12);
  const sparks = fighting > 0.2 ? Array.from({length: 7}, (_, k) => {
    const sx = p[0] + (rnd(seed, k) - 0.5) * 90, sy = p[1] - 24 + (rnd(seed, k + 9) - 0.5) * 50;
    const r = 5 + rnd(seed, k + 3) * 7;
    return <path key={k} d={`M${sx - r} ${sy}L${sx + r} ${sy}M${sx} ${sy - r}L${sx} ${sy + r}M${sx - r * 0.6} ${sy - r * 0.6}L${sx + r * 0.6} ${sy + r * 0.6}`} stroke="#fff4c2" strokeWidth={2.2} opacity={0.9 * fighting} strokeLinecap="round" />;
  }) : null;
  const dust = Array.from({length: 7}, (_, k) => {
    const ang = k / 7 * Math.PI * 2 + t * 0.4;
    const rr = 60 + 24 * Math.sin(t * 2 + k);
    return <circle key={k} cx={p[0] + Math.cos(ang) * rr} cy={p[1] - 10 + Math.sin(ang) * rr * 0.5} r={40 + 12 * Math.sin(t * 3 + k)} fill="#c9a77a" opacity={0.32 * (0.4 + 0.6 * fighting)} />;
  });
  const pop = smooth(clamp(t / 0.3));
  const swords = (
    <g transform={`translate(${p[0]} ${p[1] - 130}) scale(${0.6 + 0.4 * pop + 0.06 * Math.sin(t * 8) * fighting})`} opacity={pop}>
      <circle r={26} fill="#7a1f16" stroke="#f3d79a" strokeWidth={3} />
      <g stroke="#fff3d8" strokeWidth={4} strokeLinecap="round">
        <path d="M-13 -13L13 13M13 -13L-13 13" />
        <path d="M-15 -7L-7 -15M7 15L15 7M15 -7L7 -15M-7 15L-15 7" strokeWidth={3} />
      </g>
    </g>
  );
  return (
    <g opacity={op}>
      <defs>
        <filter id={`cdust-${id}`}><feGaussianBlur stdDeviation={9} /></filter>
        <filter id={`cfire-${id}`} x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation={0.8} /></filter>
        <filter id={`chalo-${id}`} x="-10%" y="-10%" width="120%" height="120%">
          <feMorphology in="SourceAlpha" operator="dilate" radius={2} result="d" />
          <feFlood floodColor="#f6ead0" floodOpacity={0.9} />
          <feComposite in2="d" operator="in" result="o" />
          <feMerge><feMergeNode in="o" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      <g filter={`url(#cdust-${id})`}>{dust}</g>
      {banners}
      <g filter={`url(#chalo-${id})`}>{soldiers.map((x, k) => x.cav ? <Rider key={k} s={x.s} color={x.color} dim={x.dim} /> : <Footman key={k} s={x.s} color={x.color} dim={x.dim} kind={x.kind} />)}</g>
      {burnSide != null && burnAt != null && sec >= burnAt && (() => {
        // a few fires burning in the crowd (not one on every soldier)
        const own = soldiers.filter((x) => x.burn > 0 || (x.color === sides[burnSide]?.color));
        if (!own.length) return null;
        const picks = [0.15, 0.45, 0.7, 0.92].map((q) => own[Math.min(own.length - 1, Math.floor(q * own.length))]);
        return (
          <g filter={`url(#cfire-${id})`}>
            {picks.map((x, c) => {
              const g = smooth(clamp((sec - burnAt - c * 0.25) / 0.5));
              if (g <= 0.02) return null;
              const bx = x.s.x + (c % 2 ? 8 : -6), by = x.s.y - 8;
              const smoke = ((sec * 0.7 + c * 0.37) % 1);
              return (
                <g key={'fc' + c}>
                  <circle cx={bx + smoke * 16} cy={by - 46 * g - smoke * 70} r={(9 + smoke * 22) * g} fill="#3a302a" opacity={0.35 * (1 - smoke) * g} />
                  {[-11, 0, 11].map((dx, j) => {
                    const h = (34 + (j === 1 ? 14 : 0)) * g * (0.85 + 0.15 * Math.sin(sec * 10 + c * 2 + j));
                    const w = 17 * g, ph = sec * 8 + c * 1.7 + j;
                    return (
                      <g key={j}>
                        <path d={tongue(bx + dx * g, by + 12, h * 1.1, w * 1.2, ph)} fill="#e2401a" opacity={0.9} />
                        <path d={tongue(bx + dx * g, by + 12, h * 0.8, w * 0.85, ph + 0.8)} fill="#ff8a1f" />
                        <path d={tongue(bx + dx * g, by + 12, h * 0.45, w * 0.45, ph + 1.6)} fill="#ffe08a" />
                      </g>
                    );
                  })}
                </g>
              );
            })}
          </g>
        );
      })()}
      {sparks}
      {swords}
      {title && (
        <g opacity={smooth(clamp((t - 0.3) / 0.4))} transform={`translate(${p[0]} ${p[1] - 186})`}>
          <rect x={-title.length * 15 - 14} y={-20} width={title.length * 30 + 28} height={40} rx={4} fill="#3b2418e8" stroke="#d9b06a" strokeWidth={2} />
          <text y={11} textAnchor="middle" fontSize={28} fill="#fff1d2" fontFamily="StorySerif" fontWeight={700}>{title}</text>
        </g>
      )}
    </g>
  );
};
