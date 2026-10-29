import React from 'react';
import {clamp, easeOut, partial, presence, samplePath, smooth, toD, type Pt} from './anim';
import type {AllianceEl, CaptureEl, ReplayEl, SiegeEl, SpotEl, Theme} from './types';

// Map actions, batch 2: 围城 siege, 易手 capture, 会盟 alliance, 路线回放 replay, 地点高亮 spot.

const W = 1920, H = 1080;

export const SiegeMark: React.FC<{el: SiegeEl; p: Pt; sec: number; theme: Theme}> = ({el, p, sec, theme}) => {
  const op = presence(sec, el, 0.4, 0.4);
  if (!op) return null;
  const t = sec - el.start;
  const color = el.color ?? theme.red;
  const close = 1 - 0.25 * easeOut(t / 1.5);          // the ring tightens
  const r = 62 * close;
  const flick = 0.75 + 0.25 * Math.abs(Math.sin(t * 7));
  const ticks = Array.from({length: 18}, (_, i) => (i / 18) * Math.PI * 2 + t * 0.6);
  return (
    <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: op, overflow: 'visible'}}>
      <circle cx={p[0]} cy={p[1]} r={r + 10} fill={color} opacity={0.08 * flick} />
      <circle cx={p[0]} cy={p[1]} r={r} fill="none" stroke={color} strokeWidth={4} strokeDasharray="14 9" opacity={flick} transform={`rotate(${t * 40} ${p[0]} ${p[1]})`} />
      {ticks.map((a, i) => (
        <path key={i} d={`M${p[0] + Math.cos(a) * (r + 6)} ${p[1] + Math.sin(a) * (r + 6)}L${p[0] + Math.cos(a) * (r - 6)} ${p[1] + Math.sin(a) * (r - 6)}`} stroke={color} strokeWidth={3} opacity={0.8} />
      ))}
      <g transform={`translate(${p[0] + r * 0.75} ${p[1] - r * 0.95})`} opacity={smooth((t - 0.3) / 0.3)}>
        <rect x={-22} y={-22} width={44} height={44} fill={color} stroke="#f6e1b4" strokeWidth={2} rx={4} />
        <text x={0} y={11} textAnchor="middle" fontSize={30} fill="#fff6e0" fontFamily="StoryBrush">{el.text}</text>
      </g>
    </svg>
  );
};

export const CaptureMark: React.FC<{el: CaptureEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  if (sec < el.start || sec > el.end) return null;
  const t = sec - el.start;
  const flash = 1 - smooth(t / 0.9);
  const tag = presence(sec, {start: el.start, end: Math.min(el.end, el.start + 2.6)}, 0.3, 0.5);
  return (
    <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
      {flash > 0 && <circle cx={p[0]} cy={p[1]} r={14 + 70 * (1 - flash)} fill="none" stroke={el.color} strokeWidth={6 * flash} opacity={flash} />}
      {/* 冲击波 (after 纸上谈兵): three rings ripple out from the city */}
      {[0, 0.28, 0.56].map((d, k) => {
        const q = clamp((t - d) / 1.3);
        return q > 0 && q < 1 ? <circle key={'w' + k} cx={p[0]} cy={p[1]} r={20 + 150 * easeOut(q)} fill="none" stroke={el.color} strokeWidth={10 * (1 - q)} opacity={0.75 * (1 - q)} /> : null;
      })}
      {/* the new side's banners pop up around it one by one */}
      {Array.from({length: 9}, (_, k) => {
        const a = (k / 9) * Math.PI * 2 + 0.4, rr = 34 + (k % 3) * 16;
        const q = easeOut(clamp((t - 0.25 - k * 0.07) / 0.25));
        const out = 1 - smooth(clamp((t - 3.2) / 0.6));
        if (q <= 0 || out <= 0) return null;
        const x = p[0] + Math.cos(a) * rr * 1.5, y = p[1] + Math.sin(a) * rr * 0.8;
        return (
          <g key={'b' + k} opacity={q * out} transform={`translate(${x} ${y}) scale(${0.4 + 0.6 * q})`}>
            <line x1={0} y1={0} x2={0} y2={-30} stroke="#3a2a1c" strokeWidth={2} />
            <path d="M0 -30 L18 -26 L14 -20 L18 -14 L0 -16 Z" fill={el.color} stroke="#fff3d8" strokeWidth={1} />
          </g>
        );
      })}
      {/* new controller: coloured dot with a ring, stays until the element ends */}
      <circle cx={p[0]} cy={p[1]} r={12} fill={el.color} stroke="#fff3d8" strokeWidth={3} opacity={easeOut(t / 0.4)} />
      <circle cx={p[0]} cy={p[1]} r={19} fill="none" stroke={el.color} strokeWidth={2.5} opacity={easeOut(t / 0.4)} />
      {tag > 0 && (
        <g opacity={tag} transform={`translate(${p[0] - 40} ${p[1] + 30})`}>
          <rect width={80} height={30} rx={4} fill={el.color} />
          <text x={40} y={22} textAnchor="middle" fontSize={20} fill="#fff6e0" fontFamily="StoryBrush">{el.text}</text>
        </g>
      )}
    </svg>
  );
};

export const AllianceMark: React.FC<{el: AllianceEl; p: Pt; sec: number; theme: Theme}> = ({el, p, sec, theme}) => {
  const op = presence(sec, el, 0.3, 0.4);
  if (!op) return null;
  const s = easeOut((sec - el.start) / 0.45);
  return (
    <div style={{position: 'absolute', left: p[0] - 70, top: p[1] - 120, width: 140, textAlign: 'center', opacity: op, transform: `scale(${0.5 + 0.5 * s})`}}>
      <div style={{display: 'inline-block', padding: '6px 16px', background: '#2c4f6e', border: '3px solid #f2dfb0', color: '#fff6e0', fontFamily: 'StoryBrush', fontSize: 34, letterSpacing: 4, boxShadow: `0 0 18px ${theme.blue}`}}>{el.text}</div>
    </div>
  );
};

export const ReplayMark: React.FC<{el: ReplayEl; pts: Pt[]; sec: number; theme: Theme; id: string}> = ({el, pts, sec, theme, id}) => {
  const op = presence(sec, el, 0.2, 0.5);
  if (!op) return null;
  const dur = Math.max(1.2, Math.min(3, (el.end - el.start) * 0.7));
  const prog = smooth((sec - el.start) / dur);
  const line = samplePath(pts, 0.08);
  const {pts: drawn} = partial(line, prog, 0);
  const tip = drawn[drawn.length - 1];
  const color = el.color ?? '#e8b34a';
  return (
    <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: op, overflow: 'visible'}}>
      <defs><filter id={`rp${id}`}><feGaussianBlur stdDeviation={4} /></filter></defs>
      <path d={toD(line)} fill="none" stroke={color} strokeWidth={3} strokeOpacity={0.25} strokeDasharray="4 8" />
      <path d={toD(drawn)} fill="none" stroke={color} strokeWidth={10} strokeOpacity={0.45} filter={`url(#rp${id})`} strokeLinecap="round" />
      <path d={toD(drawn)} fill="none" stroke={color} strokeWidth={4} strokeLinecap="round" />
      <circle cx={tip[0]} cy={tip[1]} r={9} fill="#fff4cf" stroke={color} strokeWidth={4} />
      {pts.map((q, i) => i > 0 && i < pts.length && prog * (pts.length - 1) >= i - 0.02 ? <circle key={i} cx={q[0]} cy={q[1]} r={6} fill={color} /> : null)}
      {el.label && (
        <text x={pts[0][0]} y={pts[0][1] - 26} textAnchor="middle" fontSize={24} fill={color} fontFamily="StoryBrush" stroke="#1a140f" strokeWidth={4} paintOrder="stroke" opacity={smooth((sec - el.start) / 0.4)}>{el.label}</text>
      )}
    </svg>
  );
};

export const SpotMark: React.FC<{el: SpotEl; p: Pt; sec: number; theme: Theme}> = ({el, p, sec, theme}) => {
  const op = presence(sec, el, 0.25, 0.4);
  if (!op) return null;
  const t = sec - el.start;
  const pop = easeOut(t / 0.35);
  const rings = [0, 0.5, 1].map((o) => (((t - o) % 1.5) + 1.5) % 1.5 / 1.5);
  return (
    <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: op, overflow: 'visible'}}>
      {rings.map((r, i) => <circle key={i} cx={p[0]} cy={p[1]} r={16 + r * 64} fill="none" stroke={theme.gold} strokeWidth={4 * (1 - r)} opacity={(1 - r) * 0.9} />)}
      <circle cx={p[0]} cy={p[1]} r={13 * pop} fill={theme.red} stroke="#fff3d8" strokeWidth={3} />
      {el.text && <text x={p[0]} y={p[1] - 34} textAnchor="middle" fontSize={34} fontFamily="StoryBrush" fill="#fff3d8" stroke="#2a1d12" strokeWidth={5} paintOrder="stroke" opacity={clamp(pop)}>{el.text}</text>}
    </svg>
  );
};
