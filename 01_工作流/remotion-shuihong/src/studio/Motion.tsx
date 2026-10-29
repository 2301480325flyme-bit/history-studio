import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, easeOut, mirrorFor, smooth} from './anim';
import type {Episode, ForcesEl} from './types';

// Motion pieces learned from 抖音「纸上谈兵」(2026-10-12):
//   Forces     兵力对比分屏 — a slanted cut slides in, two halves in the sides' colours, VS; the loser's half shatters like glass
//   YearScroll 年代卷轴     — a gold-rodded scroll top-left unrolls at the start and at every chapter / year change,
//                             lists the episode's years and slides to the current one; otherwise it rests rolled up

const W = 1920, H = 1080;
// the cut: from (CUT_TOP, 0) to (CUT_BOT, H)
const CUT_TOP = 1080, CUT_BOT = 840;
const LEFT_POLY: [number, number][] = [[0, 0], [CUT_TOP, 0], [CUT_BOT, H], [0, H]];
const RIGHT_POLY: [number, number][] = [[CUT_TOP, 0], [W, 0], [W, H], [CUT_BOT, H]];
const poly = (pts: [number, number][]) => `polygon(${pts.map(([x, y]) => `${x}px ${y}px`).join(',')})`;
const cutX = (y: number) => CUT_TOP + (CUT_BOT - CUT_TOP) * (y / H);

// deterministic shards: a jittered 8×6 grid split into triangles
const rnd = (i: number) => {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const SHARDS: {pts: [number, number][]; c: [number, number]; r: number}[] = (() => {
  const nx = 8, ny = 6, out: {pts: [number, number][]; c: [number, number]; r: number}[] = [];
  const v = (i: number, j: number): [number, number] => {
    const edge = i === 0 || j === 0 || i === nx || j === ny;
    return [(i / nx) * W + (edge ? 0 : (rnd(i * 31 + j) - 0.5) * 150), (j / ny) * H + (edge ? 0 : (rnd(i * 17 + j * 7 + 3) - 0.5) * 120)];
  };
  for (let i = 0; i < nx; i++)
    for (let j = 0; j < ny; j++) {
      const a = v(i, j), b = v(i + 1, j), c = v(i + 1, j + 1), d = v(i, j + 1);
      const tris: [number, number][][] = rnd(i * 5 + j * 11) > 0.5 ? [[a, b, c], [a, c, d]] : [[a, b, d], [b, c, d]];
      for (const t of tris) out.push({pts: t, c: [(t[0][0] + t[1][0] + t[2][0]) / 3, (t[0][1] + t[1][1] + t[2][1]) / 3], r: rnd(out.length * 13 + 5)});
    }
  return out;
})();

const Half: React.FC<{s: ForcesEl['left']; side: 'left' | 'right'; t: number}> = ({s, side, t}) => {
  const left = side === 'left';
  const drift = t * 6 * (left ? 1 : -1);
  return (
    <div style={{position: 'absolute', inset: 0, clipPath: poly(left ? LEFT_POLY : RIGHT_POLY)}}>
      <div style={{position: 'absolute', inset: 0, background: `linear-gradient(${left ? 100 : 260}deg, ${s.color.flag} 0%, ${s.color.edge} 55%, #120c08 100%)`}} />
      {s.image && (
        <Img src={staticFile(s.image)} style={{position: 'absolute', top: 60, [left ? 'left' : 'right']: 40 + drift, height: 1080, width: 720, objectFit: 'cover', objectPosition: '50% 10%',
          opacity: 0.55, mixBlendMode: 'luminosity', transform: mirrorFor(side, s.faces) ? 'scaleX(-1)' : undefined,
          maskImage: 'linear-gradient(to bottom, #000 70%, transparent 100%)', WebkitMaskImage: 'linear-gradient(to bottom, #000 70%, transparent 100%)'}} />
      )}
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(ellipse at ${left ? '30%' : '70%'} 50%, transparent 30%, #0008 100%)`}} />
      <div style={{position: 'absolute', top: 330, ...(left ? {right: W - cutX(400) + 150 + drift} : {left: cutX(400) + 150 - drift}), textAlign: left ? 'right' : 'left', color: '#fff3dc', textShadow: '0 4px 18px #000c'}}>
        <div style={{fontFamily: 'StoryBrush', fontSize: 130, lineHeight: 1, letterSpacing: 8}}>{s.name}</div>
        <div style={{fontFamily: 'StoryBrush', fontSize: 64, marginTop: 18, color: '#ffe3a8', whiteSpace: 'nowrap'}}>{s.sub}</div>
      </div>
    </div>
  );
};

export const Forces: React.FC<{el: ForcesEl; sec: number}> = ({el, sec}) => {
  if (sec < el.start || sec > el.end) return null;
  const t = sec - el.start;
  const dur = el.end - el.start;
  const breakAt = Math.max(1.6, dur - 1.0);          // the loser shatters for the last second
  const slide = easeOut(clamp(t / 0.45));
  const vs = easeOut(clamp((t - 0.35) / 0.35));
  const br = clamp((t - breakAt) / 0.85);           // 0 → 1 while the shards fly
  const winnerOut = el.loser ? smooth(clamp((t - breakAt - 0.45) / 0.45)) : smooth(clamp((t - (dur - 0.5)) / 0.5));
  const loserSide = el.loser;
  const halves = (['left', 'right'] as const).map((side) => {
    const s = el[side];
    const isLoser = side === loserSide;
    // halves slide in from their own side
    const dx = (1 - slide) * (side === 'left' ? -W * 0.6 : W * 0.6);
    if (isLoser && br > 0) {
      // glass: every shard of this half flies off from the crack, spinning and falling
      const crack: [number, number] = [cutX(H * 0.45), H * 0.45];
      return (
        <div key={side} style={{position: 'absolute', inset: 0}}>
          {SHARDS.filter((sh) => (side === 'left' ? sh.c[0] < cutX(sh.c[1]) + 60 : sh.c[0] > cutX(sh.c[1]) - 60)).map((sh, k) => {
            const dirx = sh.c[0] - crack[0], diry = sh.c[1] - crack[1];
            const n = Math.hypot(dirx, diry) || 1;
            const delay = (n / 1400) * 0.25;
            const p = clamp((br * 0.85 - delay) / 0.75);
            const e = p * p;
            const tx = (dirx / n) * (220 + 420 * sh.r) * e;
            const ty = (diry / n) * (160 + 260 * sh.r) * e + 520 * e * e;
            const rot = (sh.r - 0.5) * 140 * e;
            return (
              <div key={k} style={{position: 'absolute', inset: 0, clipPath: poly(sh.pts), transformOrigin: `${sh.c[0]}px ${sh.c[1]}px`,
                transform: `translate(${tx}px,${ty}px) rotate(${rot}deg) scale(${1 - 0.25 * e})`, opacity: 1 - smooth(clamp((p - 0.55) / 0.45)),
                filter: p > 0 ? `brightness(${1 + 0.5 * (1 - p)})` : undefined}}>
                <Half s={s} side={side} t={t} />
                {/* glass edge glint */}
                <svg width={W} height={H} style={{position: 'absolute', inset: 0}}><polygon points={sh.pts.map((q) => q.join(',')).join(' ')} fill="none" stroke="#fff" strokeOpacity={0.55 * (1 - p)} strokeWidth={2.5} /></svg>
              </div>
            );
          })}
        </div>
      );
    }
    return (
      <div key={side} style={{position: 'absolute', inset: 0, transform: `translateX(${dx}px)`, opacity: isLoser ? 1 : 1 - winnerOut}}>
        <Half s={s} side={side} t={t} />
      </div>
    );
  });
  // cracks race across the loser's half just before it breaks
  const crackP = el.loser ? clamp((t - (breakAt - 0.35)) / 0.35) : 0;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      {halves}
      {crackP > 0 && br === 0 && (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
          {SHARDS.filter((sh) => (loserSide === 'left' ? sh.c[0] < cutX(sh.c[1]) : sh.c[0] > cutX(sh.c[1]))).map((sh, k) => (
            <polygon key={k} points={sh.pts.map((q) => q.join(',')).join(' ')} fill="none" stroke="#fff" strokeOpacity={0.8 * crackP * (0.4 + 0.6 * sh.r)} strokeWidth={1.6} />
          ))}
        </svg>
      )}
      {/* the bright cut line and the VS seal */}
      <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: (1 - winnerOut) * slide}}>
        <line x1={CUT_TOP} y1={0} x2={CUT_BOT} y2={H} stroke="#fff3d0" strokeWidth={6} opacity={br > 0 ? 1 - br : 1} />
      </svg>
      <div style={{position: 'absolute', left: cutX(500) - 90, top: 430, width: 180, textAlign: 'center', fontFamily: 'StorySerif', fontWeight: 700, fontSize: 110, color: '#e9c46a',
        textShadow: '0 0 24px #000, 0 0 6px #000', opacity: vs * (1 - Math.max(br, winnerOut)), transform: `scale(${1.6 - 0.6 * vs})`}}>VS</div>
    </div>
  );
};

// ── 年代卷轴 ────────────────────────────────────────────────────────────────
export const YearScroll: React.FC<{ep: Episode; sec: number; top?: number}> = ({ep, sec, top = 22}) => {
  const years = ep.years;
  if (!years.length) return null;
  const cur = years.findIndex((y) => sec >= y.start && sec < y.end);
  if (cur < 0) return null;
  // windows when the scroll is open: the opening, every chapter, every new year
  const opens: {t: number; len: number}[] = [{t: 0.4, len: 6}];
  for (const p of ep.phases) opens.push({t: p.start + 0.2, len: 5});
  for (const y of years.slice(1)) opens.push({t: y.start, len: 4});
  let u = 0;
  for (const o of opens) u = Math.max(u, Math.min(smooth(clamp((sec - o.t) / 0.7)), smooth(clamp((o.t + o.len - sec) / 0.6))));
  const ph = [...ep.phases].reverse().find((p) => sec >= p.start);
  const title = ph?.text ?? ep.title;
  const ITEM = 64, SHOW = 4;
  const fullH = 96 + ITEM * Math.min(SHOW, years.length) + 26;
  const restH = 84;
  const h = restH + (fullH - restH) * u;
  // the list slides to the current year
  const y = years[cur];
  const slideP = easeOut(clamp((sec - y.start) / 0.6));
  const idx = cur - 1 + slideP;
  const first = Math.max(0, Math.min(years.length - SHOW, Math.round(cur - 1)));
  const offset = (idx - first) * ITEM;
  const rod = (top: number) => (
    <div style={{position: 'absolute', left: -12, right: -12, top, height: 14, borderRadius: 7, background: 'linear-gradient(#f6dc8c,#b68a2e 55%,#7a5a18)', boxShadow: '0 3px 6px #0007'}}>
      <div style={{position: 'absolute', left: -6, top: -3, width: 12, height: 20, borderRadius: 4, background: '#8e2a1c'}} />
      <div style={{position: 'absolute', right: -6, top: -3, width: 12, height: 20, borderRadius: 4, background: '#8e2a1c'}} />
    </div>
  );
  return (
    <div style={{position: 'absolute', left: 30, top, width: 230}}>
      {rod(0)}
      <div style={{position: 'absolute', left: 0, right: 0, top: 8, height: h - 14, overflow: 'hidden', background: 'linear-gradient(#20323a,#162329)', border: '2px solid #c9a55a', borderTop: 'none', borderBottom: 'none', boxShadow: '0 8px 20px #0008'}}>
        {/* plaque: the chapter while open, the year while rolled */}
        <div style={{position: 'absolute', left: 12, right: 12, top: 10, height: 58, background: 'linear-gradient(#f2e3be,#dcc690)', border: '2px solid #a8823a', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', color: '#2a1c10'}}>
          {u > 0.5 ? (
            <div style={{fontFamily: 'StoryBrush', fontSize: title.length > 4 ? 26 : 32, letterSpacing: 2, whiteSpace: 'nowrap', opacity: smooth((u - 0.5) / 0.5)}}>{title}</div>
          ) : (
            <>
              <div style={{fontFamily: 'StoryBrush', fontSize: 27, lineHeight: 1.05, letterSpacing: 2, opacity: 1 - smooth(u / 0.5)}}>{y.era ?? y.text}</div>
              {y.era && <div style={{fontSize: 15, fontWeight: 700, opacity: 1 - smooth(u / 0.5)}}>{y.text}</div>}
            </>
          )}
        </div>
        {/* the years */}
        <div style={{position: 'absolute', left: 0, right: 0, top: 90, opacity: smooth(clamp((u - 0.3) / 0.5))}}>
          <div style={{position: 'absolute', left: 114, top: 0, width: 2, height: ITEM * Math.min(SHOW, years.length), background: 'linear-gradient(#c9a55a00,#c9a55a,#c9a55a00)'}} />
          {years.map((yy, k) => {
            const rel = k - first;
            if (rel < -1 || rel > SHOW) return null;
            const on = k === cur;
            return (
              <div key={k} style={{position: 'absolute', left: 14, right: 14, top: rel * ITEM + 4, height: ITEM - 10, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                background: '#162329', color: on ? '#ffe7a6' : '#c9d2cf', opacity: on ? 1 : 0.6}}>
                <div style={{fontFamily: 'StoryBrush', fontSize: on ? 26 : 22, lineHeight: 1.05}}>{yy.era ?? yy.text}</div>
                {yy.era && <div style={{fontSize: 14}}>{yy.text}</div>}
              </div>
            );
          })}
          {/* the gold frame rides to the current year */}
          <div style={{position: 'absolute', left: 8, right: 8, top: offset, height: ITEM - 2, border: '2px solid #e9c46a', borderRadius: 6, boxShadow: '0 0 10px #e9c46a88'}} />
        </div>
      </div>
      {rod(h - 6)}
    </div>
  );
};
