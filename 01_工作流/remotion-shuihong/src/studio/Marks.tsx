import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, easeOut, partial, presence, samplePath, smooth, toD, type Pt} from './anim';
import {ArmyColumn, ChaseMark, Medallion} from './Army';
import type {ArrowEl, BattleEl, CampEl, CardEl, TrailEl, CityEl, FlagEl, Place, StampEl, Theme} from './types';

// Map marks live in screen space so their size stays constant while the
// camera zooms; only the basemap, rivers and regions scale with the camera.

const W = 1920, H = 1080;
const SAFE_TOP = 120, SAFE_BOTTOM = 880;
export const YEAR_ZONE = {w: 330, h: 300};   // top-left corner taken by the year scroll + chapter chip
const onScreen = (x: number, y: number, m = 40) => x > -m && x < W + m && y > -m && y < H + m;

const TIER_R: Record<Place['tier'], number> = {capital: 9, province: 8, commandery: 7, county: 6, city: 6.5, stronghold: 7, pass: 6, ferry: 6, region: 0};

// City icons (第12批, 2026-10-24): one painting per rank, tinted by whoever holds the place. Sizes are the width of
// the whole 512² canvas on screen, for a wide view and a battle close-up; the anchor is at (0.5, 0.875).
const ICON: Partial<Record<Place['tier'], [string, number, number]>> = {
  capital: ['city_capital', 90, 90], province: ['city_province', 72, 78], commandery: ['city_commandery', 58, 64],
  county: ['city_county', 40, 44], city: ['city_county', 40, 44], stronghold: ['fort_stockade', 46, 52],
  pass: ['pass_gate', 58, 64], ferry: ['ferry_jetty', 52, 58],
};
export const CITY_RANKS: Place['tier'][] = ['capital', 'province', 'commandery', 'county', 'city', 'stronghold'];
export const CLOSE_KM = 2.2;   // screen px per km from which a view counts as a battle close-up
export const iconSize = (tier: Place['tier'], close: boolean) => {
  const ic = ICON[tier];
  return ic ? (close ? ic[2] : ic[1]) : 0;
};
// a place's rank and ruler badge at this moment of the story
export const rankAt = (el: CityEl | undefined, place: Place, sec: number) => {
  let tier = place.tier, seat = false;
  for (const ph of el?.phases ?? []) {
    if (sec >= ph.t) {
      tier = ph.tier;
      seat = ph.seat;
    }
  }
  return {tier, seat};
};

// The painting, with the holder's colour multiplied into the walls through the icon's mask
// (out = base·(1−m) + base·colour·m, m = mask alpha × 0.65 — 第12批 README).
const Tinted: React.FC<{name: string; x: number; y: number; size: number; color?: string | null}> = ({name, x, y, size, color}) => (
  <div style={{position: 'absolute', left: x - size * 0.5, top: y - size * 0.875, width: size, height: size}}>
    <Img src={staticFile(`anim/icon_${name}.png`)} style={{position: 'absolute', inset: 0, width: size, height: size, filter: 'drop-shadow(0 0 1px #fff3dc) drop-shadow(0 1px 1.5px #0006)'}} />
    {color && (
      <div style={{position: 'absolute', inset: 0, background: color, opacity: 0.65, mixBlendMode: 'multiply',
        WebkitMaskImage: `url(${staticFile(`anim/icon_${name}_mask.png`)})`, WebkitMaskSize: '100% 100%',
        maskImage: `url(${staticFile(`anim/icon_${name}_mask.png`)})`, maskSize: '100% 100%'}} />
    )}
  </div>
);

export type LabelMode = 'full' | 'name' | 'none';

export const CityMark: React.FC<{el: CityEl; place: Place; p: Pt; sec: number; theme: Theme; mode: LabelMode; close?: boolean; holder?: string | null}> = ({el, place, p, sec, theme, mode, close = false, holder}) => {
  const op = presence(sec, el, 0.5, 0.4);
  if (!op || !onScreen(p[0], p[1], 200)) return null;
  const active = el.active.some(([a, b]) => sec >= a && sec <= b);
  const glow = el.active.reduce((m, [a, b]) => Math.max(m, presence(sec, {start: a, end: b}, 0.35, 0.35)), 0);
  const {tier, seat} = rankAt(el, place, sec);
  const size = iconSize(tier, close) * (1 + 0.12 * glow);
  const r = TIER_R[tier] + glow * 3;
  const [tx, ty] = labelAt(el, p, size);
  const showText = mode !== 'none' && ty > SAFE_TOP && ty + 60 < SAFE_BOTTOM;
  const isRegion = tier === 'region';
  const badge = close ? 24 : 22;
  return (
    <div style={{position: 'absolute', left: 0, top: 0, opacity: op, color: theme.ink}}>
      {size > 0 && glow > 0 && (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          <ellipse cx={p[0]} cy={p[1] - size * 0.3} rx={size * 0.62} ry={size * 0.45} fill={theme.red} opacity={0.2 * glow} />
        </svg>
      )}
      {size > 0 && <Tinted name={ICON[tier]![0]} x={p[0]} y={p[1]} size={size} color={holder} />}
      {size > 0 && seat && <Tinted name="ruler_seat_badge" x={p[0] - size * 0.42} y={p[1] - size * 0.42} size={badge} color={holder} />}
      {!isRegion && size === 0 && (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          {glow > 0 && <circle cx={p[0]} cy={p[1]} r={r + 10 * glow} fill={theme.red} opacity={0.18 * glow} />}
          {place.tier === 'capital' && <rect x={p[0] - r - 3} y={p[1] - r - 3} width={2 * r + 6} height={2 * r + 6} fill="none" stroke={active ? theme.red : theme.ink} strokeWidth={2} />}
          <circle cx={p[0]} cy={p[1]} r={r} fill={active ? theme.red : '#463526'} stroke="#fff0d0" strokeWidth={2} />
        </svg>
      )}
      {showText && (
        <div style={{position: 'absolute', left: tx, top: ty, whiteSpace: 'nowrap', opacity: isRegion ? 0.62 : 1, letterSpacing: isRegion ? 10 : 1, ...(theme.palette === 'warm'
          // warm (2026-10-24): the places the narration names — upright bold sans on a white halo, a step above the oblique 郡县
          ? {fontFamily: 'StoryMap', fontWeight: 800, fontSize: isRegion ? 38 : 27 + glow * 6, color: '#161616', WebkitTextStroke: '5px #fbfaf5', paintOrder: 'stroke fill' as const}
          : {textShadow: '0 0 3px #fff5dc, 1px 1px 2px #fff5dc', fontFamily: 'StorySerif', fontWeight: 700, fontSize: isRegion ? 40 : 27 + glow * 8})}}>
          {place.name}
          {el.detail && mode === 'full' && <div style={{fontFamily: 'StorySans', fontSize: 16, fontWeight: 500, marginTop: 2, letterSpacing: 0}}>{el.detail}</div>}
        </div>
      )}
    </div>
  );
};

// Rough screen box of a city label, used for greedy collision avoidance.
export const labelBox = (el: CityEl, place: Place, p: Pt, withDetail: boolean, size = 0) => {
  const big = place.tier === 'region';
  const w = Math.max(place.name.length * (big ? 50 : 30), withDetail && el.detail ? el.detail.length * 16 : 0) + 6;
  const h = (big ? 46 : 34) + (withDetail && el.detail ? 22 : 0);
  const [x, y] = labelAt(el, p, size);
  return {x, y, w, h};
};

// the name sits beside the icon, not on it: pushed out by the painted body (≈ 0.42 of the canvas each side)
const labelAt = (el: CityEl, p: Pt, size: number): Pt => {
  const push = size ? size * 0.42 - 12 : 0;
  return [p[0] + el.dx + (el.dx >= 0 ? push : -push), p[1] + el.dy - (el.dy < -40 ? size * 0.6 : 0)];
};

export const FLAG_W = 108, FLAG_H = 220;
type Box = {x: number; y: number; w: number; h: number};

// Candidate flag positions around an anchor, preferred side first. The episode
// picks the first one that does not collide with flags already placed.
export const flagSlots = (p: Pt, side: 'left' | 'right'): Box[] => {
  const sides = side === 'right' ? [1, -1] : [-1, 1];
  const out: Box[] = [];
  for (const dy of [0, -120, 110, -230]) {
    for (const s of sides) {
      let x = s > 0 ? p[0] + 70 : p[0] - 70 - FLAG_W;
      let y = p[1] - FLAG_H - 30 + dy;
      x = Math.max(20, Math.min(W - FLAG_W - 20, x));
      y = Math.max(SAFE_TOP + 10, Math.min(SAFE_BOTTOM - FLAG_H, y));
      out.push({x, y, w: FLAG_W + 20, h: FLAG_H});
    }
  }
  return out;
};

// Trail: the route a unit took, drawn faint and dashed so the audience can see where it came from (2026-10-19).
export const TrailMark: React.FC<{el: TrailEl; pts: Pt[]; sec: number}> = ({el, pts, sec}) => {
  const op = presence(sec, el, 0.5, 0.6) * 0.5;
  if (op < 0.01 || pts.length < 2) return null;
  const d = pts.map((q, i) => `${i ? 'L' : 'M'}${q[0]} ${q[1]}`).join(' ');
  // the label rides a third of the way along, clear of the city icon and name at the start (第12批)
  const a = pts[0], b = pts[pts.length - 1];
  const x0 = a[0] + (b[0] - a[0]) * 0.35, y0 = a[1] + (b[1] - a[1]) * 0.35;
  return (
    <g opacity={op}>
      <path d={d} fill="none" stroke={el.color} strokeWidth={3} strokeDasharray="10 9" strokeLinecap="round" strokeLinejoin="round" />
      {el.label && <text x={x0} y={y0 - 12} textAnchor="middle" fontSize={17} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif" stroke="#1c140c" strokeWidth={3} paintOrder="stroke">{el.label}</text>}
    </g>
  );
};

// Camp: tents on the map where the army is encamped. It fades in when the army arrives and stays until its end.
export const CampMark: React.FC<{el: CampEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const op = presence(sec, el, 0.4, 0.5);
  if (op < 0.01) return null;
  const grow = 0.85 + 0.15 * easeOut((sec - el.start) / 0.6);
  const [dx, dy] = el.offset ?? [0, 0];
  const labelW = Math.max(84, el.text.length * 18 + 26);   // longer names need a wider plate
  return (
    <g transform={`translate(${p[0] + dx} ${p[1] + dy}) scale(${grow})`} opacity={op} style={{pointerEvents: 'none'}}>
      <ellipse cx={0} cy={26} rx={48} ry={10} fill="#000" opacity={0.28} />
      <image href={staticFile('anim/camp_tents.png')} x={-56} y={-58} width={112} height={86} />
      <rect x={-labelW / 2} y={30} width={labelW} height={24} rx={5} fill={el.color} stroke="#fff1d6" strokeWidth={1.5} />
      <text x={0} y={47} textAnchor="middle" fontSize={17} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif">{el.text}</text>
    </g>
  );
};

// Garrison: a unit inside a city it holds is its commander's medallion at the city's upper right with a thin lead
// to the walls — no tents in a city (user, 2026-10-24). Several units in one city line up to the right.
export const GarrisonMark: React.FC<{el: CampEl; p: Pt; sec: number; size: number; close: boolean; slot: number}> = ({el, p, sec, size, close, slot}) => {
  const op = presence(sec, el, 0.4, 0.5);
  if (op < 0.01) return null;
  const r = close ? 21 : 18;
  const pop = 0.7 + 0.3 * easeOut((sec - el.start) / 0.5);
  const x = p[0] + size * 0.42 + 6 + r + slot * (2 * r + 10), y = p[1] - size * 0.7 - r;
  return (
    <g opacity={op} style={{pointerEvents: 'none'}}>
      <line x1={p[0] + size * 0.3} y1={p[1] - size * 0.45} x2={x - r * 0.7} y2={y + r * 0.7} stroke={el.color} strokeWidth={1.5} opacity={0.8} />
      <g transform={`translate(${x} ${y}) scale(${pop}) translate(${-x} ${-y})`}>
        {el.image ? <Medallion x={x} y={y} r={r} src={el.image} name={el.text} color={el.color} id={`gar-${el.place}-${slot}`} fs={13} />
          : <g>
              <circle cx={x} cy={y} r={r + 4} fill={el.color} stroke="#1c120b" strokeOpacity={0.5} strokeWidth={2} />
              <text x={x} y={y + 7} textAnchor="middle" fontSize={20} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif">{el.text.slice(0, 1)}</text>
              <text x={x} y={y + r + 17} textAnchor="middle" fontSize={13} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif" stroke="#00000066" strokeWidth={3} paintOrder="stroke">{el.text}</text>
            </g>}
        <text x={x + r + 2} y={y - r + 6} fontSize={14} fontWeight={700} fill="#fff6e3" fontFamily="StorySerif" stroke={el.color} strokeWidth={4} paintOrder="stroke">守</text>
      </g>
    </g>
  );
};

export const FlagMark: React.FC<{el: FlagEl; p: Pt; sec: number; theme: Theme; pos?: Box}> = ({el, p, sec, theme, pos}) => {
  // Fade out when the anchor city leaves the frame instead of pinning the flag
  // to the screen edge, which would misplace it geographically.
  const off = Math.max(0, -p[0], p[0] - W, SAFE_TOP - 40 - p[1], p[1] - SAFE_BOTTOM);
  // Exit: the flag sinks, greys and fades (被杀 / 兵败 / 被囚).
  const sink = el.exit_at != null ? smooth((sec - el.exit_at) / 1.3) : 0;
  const op = presence(sec, el, 0.45, 0.35) * (1 - smooth(off / 120)) * (1 - 0.85 * sink);
  if (op < 0.01) return null;
  const rise = easeOut((sec - el.start) / 0.6) - sink * 0.6;
  const w = FLAG_W, h = FLAG_H;
  const {x, y} = pos ?? flagSlots(p, el.side)[0];
  const poleX = x + 6, poleY = y + h - 10;
  const link = smooth((sec - el.start) / 0.8);
  // change of side: the banner turns over (scaleX → 0 → 1) and comes back in the new colour
  const turn = el.turn_at != null ? clamp((sec - el.turn_at) / 0.7) : 0;
  const flipX = turn > 0 && turn < 1 ? Math.abs(Math.cos(Math.PI * turn)) : 1;
  const turned = turn >= 0.5;
  const flagColor = turned && el.turn_color ? el.turn_color : el.color;
  const sub = turned && el.turn_sub ? el.turn_sub : el.sub;
  const glow = turn > 0.5 && turn < 1 ? Math.sin(Math.PI * (turn - 0.5) * 2) : 0;
  if (theme.look === 'atlas') {
    // atlas: a person with a portrait shows as a round badge with a name tag; others as a swallow-tail pennant
    const fx = x + 10, fy = y + (1 - rise) * 40;
    const filt = sink ? `grayscale(${sink}) brightness(${1 - 0.3 * sink})` : glow ? `drop-shadow(0 0 ${12 * glow}px ${flagColor})` : 'drop-shadow(0 3px 6px #0006)';
    return (
      <>
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: op}}>
          <path d={`M${p[0]} ${p[1]}L${p[0] + (fx + 45 - p[0]) * link} ${p[1] + (fy + (el.image ? 150 : 175) - p[1]) * link}`} stroke="#f2ede0" strokeOpacity={0.8} strokeWidth={2} strokeDasharray="6 6" fill="none" />
        </svg>
        {el.image ? (
          <div style={{position: 'absolute', left: fx - 10, top: fy + 30, width: 110, opacity: op, transform: `scaleX(${flipX})`, filter: filt, display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
            <div style={{width: 96, height: 96, borderRadius: 999, overflow: 'hidden', border: `4px solid ${flagColor}`, boxShadow: '0 0 0 2px #f2ede0', background: '#d9d2c2'}}>
              <Img src={staticFile(el.image)} style={{width: '100%', height: '160%', objectFit: 'cover', objectPosition: '50% 4%'}} />
            </div>
            <div style={{marginTop: -6, padding: '2px 12px 3px', background: flagColor, color: '#fffaf0', fontFamily: 'StoryBrush', fontSize: 24, borderRadius: 4, border: '1.5px solid #f2ede0', whiteSpace: 'nowrap'}}>{el.name}</div>
            {sub && <div style={{marginTop: 3, padding: '1px 7px', background: '#1d1f22cc', color: '#efe7d2', fontSize: 16, whiteSpace: 'nowrap'}}>{sub}</div>}
          </div>
        ) : (
          <div style={{position: 'absolute', left: fx, top: fy, width: 90, height: 200, opacity: op, transform: `scaleX(${flipX})`, filter: filt}}>
            <svg width={90} height={200} style={{position: 'absolute', inset: 0}}>
              <path d="M8 6H82V168L45 150L8 168Z" fill={flagColor} stroke="#e8cf8f" strokeWidth={3} />
              <path d="M14 12H76V158L45 143L14 158Z" fill="none" stroke="#f6e8c6" strokeOpacity={0.5} strokeWidth={1.2} />
            </svg>
            <div style={{position: 'absolute', left: 8, width: 74, top: 14, height: 132, display: 'flex', justifyContent: 'center', alignItems: 'center', writingMode: 'vertical-rl', color: '#fffaf0',
              fontFamily: 'StoryBrush', fontSize: el.name.length > 3 ? 26 : 36, letterSpacing: 3, lineHeight: 1}}>{el.name}</div>
            {sub && <div style={{position: 'absolute', left: -2, top: 172, background: '#1d1f22cc', color: '#efe7d2', padding: '2px 7px', whiteSpace: 'nowrap', fontSize: 17}}>{sub}</div>}
          </div>
        )}
      </>
    );
  }
  return (
    <>
      <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: op}}>
        <path d={`M${p[0]} ${p[1]}L${p[0] + (poleX - p[0]) * link} ${p[1] + (poleY - p[1]) * link}`} stroke={theme.blue} strokeWidth={2} strokeDasharray="8 7" fill="none" />
      </svg>
      <div style={{position: 'absolute', left: x, top: y + (1 - rise) * 40, width: w, height: h, opacity: op, color: '#fbe5b6', transform: `scaleX(${flipX})`, transformOrigin: '6px 50%', filter: sink ? `grayscale(${sink}) brightness(${1 - 0.3 * sink})` : glow ? `drop-shadow(0 0 ${12 * glow}px ${flagColor})` : undefined}}>
        <svg width={w} height={h}>
          <path d="M6 210V8M0 12H105" stroke="#7e582b" strokeWidth={5} />
          <path d="M14 18H98V149L56 139L14 149Z" fill={flagColor} stroke={theme.gold} strokeWidth={4} />
          <path d="M8 7L16 0L24 7" fill={theme.gold} />
        </svg>
        <div style={{position: 'absolute', left: 0, width: 112, top: 26, height: 112, display: 'flex', justifyContent: 'center', alignItems: 'center', writingMode: 'vertical-rl', fontFamily: 'StoryBrush', fontSize: el.name.length > 4 ? 22 : el.name.length > 3 ? 27 : 36, letterSpacing: el.name.length > 3 ? 1 : 4, lineHeight: 1, fontWeight: 700}}>{el.name}</div>
        {sub && <div style={{position: 'absolute', left: -3, top: 162, background: '#493b2ddb', padding: '6px 8px', whiteSpace: 'nowrap', fontSize: 20}}>{sub}</div>}
        {el.note && <div style={{position: 'absolute', left: 14, top: 204, fontSize: 13, whiteSpace: 'nowrap', color: '#224c70', background: '#efe0c9e8', padding: '2px 5px'}}>{el.note}</div>}
      </div>
    </>
  );
};

const STOP_PX = {at: 10, near: 34, approach: 70};

// tapered brush band along a polyline: thin at the tail, swelling to w1 at the head
const ribbon = (ps: Pt[], w0: number, w1: number) => {
  if (ps.length < 2) return '';
  const L = [0];
  for (let i = 1; i < ps.length; i++) L.push(L[i - 1] + Math.hypot(ps[i][0] - ps[i - 1][0], ps[i][1] - ps[i - 1][1]));
  const tot = L[L.length - 1] || 1;
  const a: string[] = [], b: string[] = [];
  ps.forEach((q, i) => {
    const p0 = ps[Math.max(0, i - 1)], p1 = ps[Math.min(ps.length - 1, i + 1)];
    const dx = p1[0] - p0[0], dy = p1[1] - p0[1], n = Math.hypot(dx, dy) || 1;
    const f = L[i] / tot, w = (w0 + (w1 - w0) * Math.pow(f, 0.7)) / 2;
    a.push(`${(q[0] - (dy / n) * w).toFixed(1)} ${(q[1] + (dx / n) * w).toFixed(1)}`);
    b.push(`${(q[0] + (dy / n) * w).toFixed(1)} ${(q[1] - (dx / n) * w).toFixed(1)}`);
  });
  return `M${a.join('L')}L${b.reverse().join('L')}Z`;
};

export const ArrowMark: React.FC<{el: ArrowEl; pts: Pt[]; sec: number; theme: Theme; id: string}> = ({el, pts, sec, theme, id}) => {
  const op = presence(sec, el, 0.2, 0.4);
  if (!op) return null;
  // armies march at a steady pace; plain arrows shoot out and settle — warm: they draw at a near-even pace too,
  // only softened at both ends (地图知天下: the line grows evenly, the camera trails its head)
  const u = clamp((sec - el.start) / el.grow);
  const prog = el.troops ? smooth(u) : theme.palette === 'warm' ? 0.75 * u + 0.25 * smooth(u) : easeOut(u);
  const line = samplePath(pts, el.bend);
  const {pts: drawn, angle} = partial(line, prog, STOP_PX[el.stop]);
  const d = toD(drawn);
  const tip = drawn[drawn.length - 1];
  const relation = el.kind === 'relation';
  const flee = el.kind === 'flee';
  const color = el.color ?? (relation || flee ? theme.blue : theme.red);
  const pulse = prog > 0.98 ? 1 + 0.18 * Math.sin((sec - el.start - el.grow) * 8) ** 2 : 1;   // head pulses on arrival
  const end = line[line.length - 1];
  return (
    <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: op, overflow: 'visible'}}>
      <defs>
        <filter id={`glow-${id}`} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation={9} />
        </filter>
        <filter id={`ink-${id}`} x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves={2} seed={3} />
          <feDisplacementMap in="SourceGraphic" scale={5} />
        </filter>
      </defs>
      {relation ? (
        <path d={d} fill="none" stroke={color} strokeWidth={3} strokeDasharray="10 8" strokeLinecap="round" />
      ) : flee ? (
        <>
          {/* 逃亡 / 败退: thin, hurried, broken tail */}
          <path d={d} fill="none" stroke={color} strokeWidth={4} strokeLinecap="round" strokeDasharray="16 7 5 7" />
          {prog > 0.04 && <path d="M3 0L-20 -10L-15 0L-20 10Z" fill={color} transform={`translate(${tip[0]} ${tip[1]}) rotate(${(angle * 180) / Math.PI})`} />}
        </>
      ) : (
        <>
          {/* 进军: a tapered ink-brush band with a hot glow, light flowing toward a big head */}
          <path d={d} fill="none" stroke={color} strokeWidth={46} opacity={0.45} filter={`url(#glow-${id})`} strokeLinecap="round" />
          <path d={ribbon(drawn, 7, 34)} fill={color} stroke="#2a0e06" strokeWidth={2.5} strokeOpacity={0.55} filter={`url(#ink-${id})`} />
          <path d={ribbon(drawn, 2, 10)} fill="#ffcf9a" opacity={0.35} />
          <path d={d} fill="none" stroke="#fff0d0" strokeWidth={5} strokeLinecap="round" strokeDasharray="6 34" strokeDashoffset={-(sec - el.start) * 140} opacity={0.75 * smooth(prog / 0.2)} />
          {prog > 0.04 && (
            <g transform={`translate(${tip[0]} ${tip[1]}) rotate(${(angle * 180) / Math.PI}) scale(${pulse})`} filter={`url(#ink-${id})`}>
              <path d="M14 0L-52 -38L-36 0L-52 38Z" fill={color} stroke="#2a0e06" strokeWidth={3} strokeOpacity={0.6} strokeLinejoin="round" />
              <path d="M4 0L-34 -18L-26 0L-34 18Z" fill="#ffcf9a" opacity={0.35} />
            </g>
          )}
          {prog > 0.98 && <circle cx={end[0]} cy={end[1]} r={26 + 10 * (pulse - 1) * 5} fill="none" stroke={color} strokeWidth={5} opacity={0.75} />}
        </>
      )}
      {el.troops && !relation && <ArmyColumn line={line} prog={prog} trim={STOP_PX[el.stop]} sec={sec} start={el.start} color={color} troops={el.troops} id={id} />}
      {el.chase && !relation && <ChaseMark line={line} prog={prog} sec={sec} start={el.start} lag={el.chase.lag ?? 0.12} leader={el.chase.leader} pursuer={el.chase.pursuer} id={id} />}
      {relation && prog > 0.04 && <circle cx={tip[0]} cy={tip[1]} r={5} fill={color} />}
      {el.label && prog > 0.5 && (() => {
        const mid = line[Math.floor(line.length / 2)];
        return (
          <g opacity={smooth((prog - 0.5) / 0.3)}>
            <rect x={mid[0] - el.label.length * 12 - 14} y={mid[1] - 52} width={el.label.length * 24 + 28} height={36} rx={4} fill="#f1dfbcee" stroke={color} />
            <text x={mid[0]} y={mid[1] - 26} textAnchor="middle" fontSize={22} fill={color} fontFamily="StorySans" fontWeight={700}>{el.label}</text>
          </g>
        );
      })()}
    </svg>
  );
};

export const BattleMark: React.FC<{el: BattleEl; p: Pt; sec: number; theme: Theme}> = ({el, p, sec, theme}) => {
  const op = presence(sec, el, 0.3, 0.4);
  if (!op) return null;
  const t = sec - el.start;
  const rings = [0, 0.45, 0.9].map((o) => ((t - o) % 1.4 + 1.4) % 1.4 / 1.4);
  const pop = easeOut(t / 0.4);
  const cardX = el.side === 'left' ? p[0] - 330 : p[0] + 70;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: op}}>
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        {rings.map((r, i) => <circle key={i} cx={p[0]} cy={p[1]} r={20 + r * 70} fill="none" stroke={theme.red} strokeWidth={5 * (1 - r)} opacity={1 - r} />)}
        <g transform={`translate(${p[0]} ${p[1]}) scale(${pop})`} stroke="#fff3d8" strokeWidth={4} strokeLinecap="round">
          <circle r={22} fill={theme.red} stroke="#fff3d8" strokeWidth={3} />
          <path d="M-11 -11L11 11M11 -11L-11 11" />
        </g>
      </svg>
      {(el.title || el.text) && (
        <div style={{position: 'absolute', left: Math.max(20, Math.min(W - 280, cardX)), top: Math.max(SAFE_TOP, p[1] - 140), width: 260, padding: '12px 16px', color: '#fff3d8', background: '#653622eb', border: '2px solid #be8758', opacity: smooth((t - 0.3) / 0.4)}}>
          {el.text && <div style={{fontSize: 24}}>{el.text}</div>}
          {el.title && <div style={{fontSize: 33, fontWeight: 700, fontFamily: 'StorySerif'}}>{el.title}</div>}
        </div>
      )}
    </div>
  );
};

export const StampMark: React.FC<{el: StampEl; p: Pt; sec: number; theme: Theme}> = ({el, p, sec, theme}) => {
  const op = presence(sec, el, 0.15, 0.4);
  if (!op) return null;
  const t = clamp((sec - el.start) / 0.35);
  const s = 1.8 - 0.8 * easeOut(t);
  return (
    // painted cinnabar seal (03_素材/动画素材 seal_blank) with the word set in serif
    <div style={{position: 'absolute', left: p[0] - 100, top: p[1] - 100, width: 82, height: 82, opacity: op * Math.min(1, t * 2), transform: `scale(${s}) rotate(-8deg)`, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
      <Img src={staticFile('anim/seal_blank.png')} style={{position: 'absolute', inset: 0, width: 82, height: 82}} />
      <div style={{position: 'relative', color: theme.red, fontFamily: 'StorySerif', fontSize: el.text.length > 1 ? 28 : 46, fontWeight: 700, lineHeight: 1.05, writingMode: el.text.length > 1 ? 'vertical-rl' : undefined, textShadow: '0 0 4px #f6e7cb'}}>{el.text}</div>
    </div>
  );
};

export const CardMark: React.FC<{el: CardEl; p: Pt | null; sec: number; theme: Theme; stage?: boolean}> = ({el, p, sec, theme, stage}) => {
  const op = presence(sec, el, 0.35, 0.35);
  if (!op) return null;
  const w = 340;
  // Unanchored cards sit under the title block, clear of map marks on the right.
  // on a dialogue stage the speakers fill the sides: the card goes bottom-centre, above the caption
  const x = p ? (el.side === 'left' ? p[0] - w - 50 : p[0] + 50) : stage ? (W - w) / 2 : 50;
  const y = p ? p[1] - 210 : stage ? 700 : 130;
  const left = Math.max(20, Math.min(W - w - 20, x));
  let top = Math.max(SAFE_TOP, Math.min(SAFE_BOTTOM - 160, y));
  // the year scroll (and its chapter chip) sits top-left: keep cards clear of it (2026-10-23, user saw them overlap)
  if (left < YEAR_ZONE.w && top < YEAR_ZONE.h) top = YEAR_ZONE.h;
  return (
    <div style={{position: 'absolute', left, top, width: w, opacity: op, padding: '14px 18px', background: '#f3e5c8f0', borderLeft: `6px solid ${theme.red}`, boxShadow: '0 6px 18px #0004', color: theme.ink}}>
      <div style={{fontFamily: 'StorySerif', fontSize: 30, fontWeight: 700}}>{el.title}</div>
      {el.body && <div style={{fontSize: 21, lineHeight: 1.45, marginTop: 6}}>{el.body}</div>}
      {/* torn rice-paper edge (paper_torn_edge) under the card */}
      <Img src={staticFile('anim/paper_torn_edge.png')} style={{position: 'absolute', left: -6, right: -6, bottom: -15, width: 'calc(100% + 12px)', height: 22, objectFit: 'fill', filter: 'sepia(0.45) brightness(0.97)'}} />
    </div>
  );
};
