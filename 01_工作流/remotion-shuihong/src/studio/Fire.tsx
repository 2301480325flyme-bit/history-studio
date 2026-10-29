import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, smooth} from './anim';
import type {FireEl} from './types';

// Fire attack (火攻): flames catch on the target (an army camp or a city), spread outward,
// smoke rises; at the peak the whole screen is briefly engulfed — flame tongues rise from the
// edges, an orange wash, embers drift up — then it falls back to a scorched mark.
// Deterministic pseudo-random so every frame renders the same.

const rnd = (seed: number) => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// One flame tongue: base at (x, y), height h, width w; `ph` animates the flicker.
export const tongue = (x: number, y: number, h: number, w: number, ph: number) => {
  const sway = Math.sin(ph * 2.3) * w * 0.35 + Math.sin(ph * 5.1) * w * 0.12;
  const hh = h * (0.82 + 0.18 * Math.sin(ph * 3.7));
  return `M ${x - w / 2} ${y} Q ${x - w * 0.62} ${y - hh * 0.45} ${x + sway} ${y - hh} Q ${x + w * 0.62} ${y - hh * 0.45} ${x + w / 2} ${y} Z`;
};

export const FireMark: React.FC<{el: FireEl; p: [number, number]; sec: number; zoom: number; id: string}> = ({el, p, sec, zoom, id}) => {
  if (sec < el.start - 0.05 || sec > el.end + 6) return null;
  const scale = Math.min(1.6, Math.max(0.55, Math.sqrt(zoom) * 0.75)) * (el.size ?? 1);
  const r = 70 * scale * (el.radius ?? 1);
  const grow = smooth(clamp((sec - el.start) / 1.4));
  const out = 1 - smooth(clamp((sec - el.end) / 1.0));       // flames die down after `end`
  const scorch = smooth(clamp((sec - el.start - 1.0) / 1.2)) * (1 - smooth(clamp((sec - el.end - 4) / 2)));
  const [cx, cy] = p;
  const seed = Number(id) * 13 + 7;
  // painted flames (03_素材/动画素材 flame_1–3) lit from the centre outward, each flickering on its own beat
  const flames: React.ReactNode[] = [];
  for (let k = 0; k < 11; k++) {
    const a = rnd(seed + k) * Math.PI * 2;
    const d = Math.sqrt(rnd(seed + k * 3.1)) * r;
    const lit = smooth(clamp((grow * r * 1.25 - d) / (r * 0.35)));
    if (lit <= 0.02) continue;
    const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d * 0.55;
    const h = (70 + rnd(seed + k * 7.7) * 70) * scale * lit;
    const ph = sec * (5 + rnd(seed + k) * 4) + k;
    flames.push(<Img key={'f' + k} src={staticFile(`anim/flame_${1 + (k % 3)}.png`)} style={{position: 'absolute', left: x - h / 2, top: y - h * 0.92, width: h, height: h,
      transform: `scaleY(${0.86 + 0.14 * Math.sin(ph * 1.7)}) skewX(${Math.sin(ph) * 5}deg)`, transformOrigin: '50% 92%', opacity: 0.95, zIndex: Math.round(y)}} />);
  }
  // smoke columns rising and fading
  const smoke: React.ReactNode[] = [];
  for (let i = 0; i < 5; i++) {
    const life = 3.0;
    const t0 = sec - el.start - i * 0.55;
    if (t0 < 0) continue;
    const ph = (t0 % life) / life;
    const s = (90 + ph * 140) * scale;
    const x = cx + (rnd(i + 3) - 0.5) * r * 1.2 + ph * 50 * scale;
    const y = cy - 40 * scale - ph * 210 * scale;
    smoke.push(<Img key={'s' + i} src={staticFile(`anim/smoke_${1 + (i % 3)}.png`)} style={{position: 'absolute', left: x - s / 2, top: y - s / 2, width: s, height: s, opacity: (1 - ph) * 0.55 * grow}} />);
  }
  return (
    <div style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
      {/* scorched ground stays after the fire */}
      <div style={{position: 'absolute', left: cx - r * 1.15, top: cy + 6 * scale - r * 0.55, width: r * 2.3, height: r * 1.1, borderRadius: '50%', background: 'radial-gradient(ellipse, #1d140e 0, #1d140e88 50%, transparent 72%)', opacity: 0.55 * scorch}} />
      <div style={{position: 'absolute', inset: 0, opacity: out}}>
        <div style={{position: 'absolute', left: cx - r * 2.1, top: cy - 10 * scale - r * 1.4, width: r * 4.2, height: r * 2.8, borderRadius: '50%', mixBlendMode: 'screen',
                     background: 'radial-gradient(ellipse, #ffb347d9 0, #ff5a1f59 55%, transparent 72%)', opacity: 0.9 * grow * (0.85 + 0.15 * Math.sin(sec * 9))}} />
        {smoke}
        {flames}
      </div>
    </div>
  );
};

// Full-screen engulf: peaks `at` seconds after the fire starts, lasts ~0.9 s.
export const fireFlashK = (el: FireEl, sec: number) => {
  if (!el.flash) return 0;
  const t0 = el.start + (el.flash_at ?? 0.7);
  const d = sec - t0;
  if (d < -0.25 || d > 1.1) return 0;
  return d < 0 ? smooth(clamp((d + 0.25) / 0.25)) : 1 - smooth(clamp((d - 0.35) / 0.75));
};

export const FireFlash: React.FC<{k: number; sec: number}> = ({k, sec}) => {
  if (k <= 0.01) return null;
  const tongues: React.ReactNode[] = [];
  const N = 46;
  for (let i = 0; i < N; i++) {
    const x = (i / (N - 1)) * 1920 + (rnd(i) - 0.5) * 40;
    const h = (220 + rnd(i * 2.7) * 380) * k;
    const w = 70 + rnd(i * 4.1) * 70;
    const ph = sec * (6 + rnd(i) * 5) + i;
    tongues.push(
      <g key={'b' + i}>
        <path d={tongue(x, 1110, h * 1.1, w * 1.2, ph)} fill="#d8361a" opacity={0.9} />
        <path d={tongue(x, 1110, h * 0.8, w * 0.85, ph + 0.8)} fill="#ff8c1a" />
        <path d={tongue(x, 1110, h * 0.45, w * 0.45, ph + 1.6)} fill="#ffe38f" />
      </g>,
    );
  }
  // side walls of flame, shorter
  for (let i = 0; i < 12; i++) {
    const y = 1080 - (i / 11) * 900;
    for (const side of [0, 1]) {
      const h = (120 + rnd(i * 9 + side) * 180) * k;
      const ph = sec * 7 + i * 1.3 + side;
      const x = side ? 1940 : -20;
      tongues.push(
        <g key={`s${side}${i}`} transform={`translate(${x},${y}) rotate(${side ? -90 : 90})`}>
          <path d={tongue(0, 0, h, 80, ph)} fill="#e0451b" opacity={0.85} />
          <path d={tongue(0, 0, h * 0.6, 50, ph + 1)} fill="#ffb02e" />
        </g>,
      );
    }
  }
  const embers: React.ReactNode[] = [];
  for (let i = 0; i < 70; i++) {
    const life = 1.6;
    const p = ((sec * 0.9 + rnd(i) * life) % life) / life;
    const x = rnd(i * 3.3) * 1920 + Math.sin(sec * 3 + i) * 30;
    const y = 1080 - p * 1000;
    embers.push(<circle key={'e' + i} cx={x} cy={y} r={2 + rnd(i * 5) * 3.5} fill={rnd(i) > 0.5 ? '#ffd27a' : '#ff7a2a'} opacity={(1 - p) * k} />);
  }
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 55%, rgba(255,150,40,0.10) 0%, rgba(255,90,20,0.45) 55%, rgba(150,20,0,0.85) 100%)', opacity: k, mixBlendMode: 'multiply'}} />
      <div style={{position: 'absolute', inset: 0, background: 'rgba(255,170,60,0.28)', opacity: k * k, mixBlendMode: 'screen'}} />
      <svg width={1920} height={1080} style={{position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none', filter: 'blur(1.5px)'}}>
        {tongues}
        {embers}
      </svg>
    </>
  );
};
