import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, easeOut, mirrorFor, presence, smooth, type Pt} from './anim';
import type {Element, EnterEl, ExitEl, PersonCardEl, Segment, Theme, VersusEl} from './types';

// Character components: 立绘入场 (enter), 人物卡 (person_card), 对峙卡 (versus),
// 退场 (exit). Images without transparency get a feathered frame so a painted
// portrait still reads as a standing figure; real cut-outs float freely.

const W = 1920;
const FEATHER = 'radial-gradient(ellipse 60% 56% at 50% 40%, #000 58%, transparent 100%)';

const Portrait: React.FC<{src: string | null; cutout?: boolean; w: number; h: number; grey?: number; label?: boolean; flip?: boolean}> = ({src, cutout, w, h, grey = 0, label = false, flip = false}) => {
  if (!src) return null;
  // Cut-outs are usually cropped at the waist: fade the bottom edge into the scene.
  // Cut-outs: fade the bottom (waist crop) and both sides (sleeves often touch the canvas edge).
  const mask = cutout ? 'linear-gradient(to right, transparent 0%, #000 7%, #000 93%, transparent 100%), linear-gradient(to bottom, #000 78%, transparent 100%)' : FEATHER;
  return (
    <div style={{position: 'absolute', inset: 0, width: w, height: h}}>
      <Img src={staticFile(src)} style={{width: w, height: h, objectFit: cutout ? 'contain' : 'cover', objectPosition: '50% 18%', transform: flip ? 'scaleX(-1)' : undefined, maskImage: mask, WebkitMaskImage: mask, maskComposite: cutout ? 'intersect' : undefined, WebkitMaskComposite: cutout ? 'source-in' : undefined, filter: grey ? `grayscale(${grey}) brightness(${1 - 0.35 * grey})` : undefined}} />
      {label && <div style={{position: 'absolute', right: 18, bottom: 26, fontSize: 12, color: '#f3e6cc', opacity: 0.75, letterSpacing: 1, textShadow: '0 0 3px #000'}}>AI生成示意像</div>}
    </div>
  );
};

export const Enter: React.FC<{el: EnterEl; sec: number; anchor: Pt | null; theme: Theme}> = ({el, sec, anchor, theme}) => {
  // settle: in the last second the portrait flies to its city and shrinks into a banner
  const fly = el.settle && anchor ? smooth(clamp((sec - (el.end - 1.0)) / 1.0)) : 0;
  const op = el.settle && anchor ? (sec < el.start || sec > el.end ? 0 : smooth(clamp((sec - el.start) / 0.6))) : presence(sec, el, 0.6, 0.5);
  if (!op) return null;
  const t = sec - el.start;
  const rise = (1 - easeOut(t / 0.8)) * 40 - (!el.settle && sec > el.end - 0.5 ? smooth((sec - (el.end - 0.5)) / 0.5) * 16 : 0);
  const left = el.side !== 'right';
  const PW = 580, PH = 820, top = 120;
  const x0 = left ? 70 : W - 70 - PW;
  const chrome = 1 - smooth(clamp(fly / 0.4));          // backdrop, title slip and name leave first
  const k = 1 - 0.8 * fly;                                // portrait scale on its way to the banner size
  const tx = fly && anchor ? (anchor[0] + 20 - x0) * fly : 0;
  const ty = fly && anchor ? (anchor[1] - 150 - top) * fly : 0;
  const pOp = op * (1 - smooth(clamp((fly - 0.75) / 0.25)));
  const line1 = smooth((t - 0.3) / 0.4), line2 = smooth((t - 0.65) / 0.4);
  const link = smooth((t - 0.5) / 0.8);
  const from: Pt = [left ? x0 + PW - 40 : x0 + 40, top + PH * 0.42];
  return (
    <>
      <div style={{position: 'absolute', top: 0, bottom: 0, [left ? 'left' : 'right']: 0, width: 1120, opacity: op * chrome, background: `linear-gradient(${left ? 'to right' : 'to left'}, rgba(14,11,9,.72), rgba(14,11,9,.45) 55%, transparent)`}} />
      {anchor && link > 0 && (
        <svg width={W} height={1080} style={{position: 'absolute', inset: 0, opacity: op * chrome}}>
          <path d={`M${from[0]} ${from[1]}L${from[0] + (anchor[0] - from[0]) * link} ${from[1] + (anchor[1] - from[1]) * link}`} stroke={el.color.fill} strokeWidth={2.5} strokeDasharray="10 7" fill="none" />
          {link > 0.95 && <circle cx={anchor[0]} cy={anchor[1]} r={10 + 8 * Math.sin(t * 5) ** 2} fill="none" stroke={el.color.fill} strokeWidth={3} />}
        </svg>
      )}
      {/* 题签: vertical title slip behind the portrait */}
      <div style={{position: 'absolute', left: left ? x0 + PW - 70 : x0 - 30, top: top + 30 + rise * 0.5, width: 104, height: 500, opacity: op * 0.95 * chrome, background: 'linear-gradient(#f2e6cb, #e6d6b2)', border: `3px solid ${el.color.edge}`, outline: '1px solid #f2e6cb', outlineOffset: -9, boxShadow: '0 8px 22px #0006', display: 'flex', alignItems: 'center', justifyContent: 'center', writingMode: 'vertical-rl', fontFamily: 'StoryBrush', fontSize: el.name.length > 3 ? 46 : 58, color: '#2b1d12', letterSpacing: 6}}>
        {el.name}
      </div>
      <div style={{position: 'absolute', left: x0, top: top + rise, width: PW, height: PH, opacity: pOp, transformOrigin: '0 0', transform: fly ? `translate(${tx}px,${ty}px) scale(${k})` : undefined, filter: fly ? `drop-shadow(0 0 ${14 * fly}px ${el.color.fill})` : undefined}}>
        {el.image ? <Portrait src={el.image} cutout={el.cutout} w={PW} h={PH} flip={mirrorFor(el.side, el.faces)} /> : (
          <div style={{width: PW, height: PH, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
            <div style={{width: 220, height: 220, borderRadius: '50%', border: `4px solid ${el.color.edge}`, background: '#2a211bcc', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StoryBrush', fontSize: 120, color: '#f2dfb3'}}>{el.name.slice(-1)}</div>
          </div>
        )}
      </div>
      {/* name, then title · role, appearing in two steps */}
      <div style={{position: 'absolute', left: left ? x0 + 10 : undefined, right: left ? undefined : W - x0 - PW + 10, top: top + PH - 200, width: PW - 20, textAlign: left ? 'left' : 'right', opacity: op * chrome}}>
        <div style={{fontFamily: 'StoryBrush', fontSize: 66, color: '#fff3d8', textShadow: '0 3px 12px #000c', opacity: line1, transform: `translateY(${(1 - line1) * 14}px)`}}>{el.name}</div>
        <div style={{height: 5, width: 150 * line1, background: el.color.fill, margin: left ? '4px 0 8px' : '4px 0 8px auto', boxShadow: '0 0 8px #0008'}} />
        {(el.title || el.role) && <div style={{fontSize: 25, color: '#f0dfbd', letterSpacing: 2, textShadow: '0 2px 8px #000', opacity: line2}}>{[el.title, el.role].filter(Boolean).join(' · ')}</div>}
      </div>
    </>
  );
};

export const PersonCard: React.FC<{el: PersonCardEl; sec: number}> = ({el, sec}) => {
  if (sec < el.start || sec > el.end) return null;
  const right = el.side !== 'left';
  const inP = easeOut((sec - el.start) / 0.45), outP = smooth((sec - (el.end - 0.4)) / 0.4);
  const slide = (1 - inP + outP) * 440;
  return (
    <div style={{position: 'absolute', top: 128, [right ? 'right' : 'left']: 40 - slide, width: 400, height: 112, display: 'flex', alignItems: 'center', gap: 16, padding: '0 18px 0 0', background: 'linear-gradient(90deg,#1d1814f2,#2a221cf0)', borderLeft: `8px solid ${el.color.flag}`, borderRadius: 6, boxShadow: '0 8px 22px #0007', opacity: 1 - outP}}>
      <div style={{width: 86, height: 86, marginLeft: 14, borderRadius: '50%', overflow: 'hidden', border: `3px solid ${el.color.fill}`, flex: 'none', background: '#3a2f26', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StoryBrush', fontSize: 46, color: '#f2dfb3'}}>
        {el.image ? <Img src={staticFile(el.image)} style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 12%'}} /> : el.name.slice(-1)}
      </div>
      <div style={{minWidth: 0}}>
        <div style={{fontFamily: 'StoryBrush', fontSize: 38, color: '#f8e9c8', lineHeight: 1.1}}>{el.name}</div>
        {(el.title || el.role) && <div style={{fontSize: 18, color: '#dccaa6', marginTop: 2}}>{[el.title, el.role].filter(Boolean).join(' · ')}</div>}
        {el.base && <div style={{fontSize: 15, color: '#b9a888', marginTop: 2}}>据点 · {el.base}</div>}
      </div>
    </div>
  );
};

export const Versus: React.FC<{el: VersusEl; sec: number; theme: Theme}> = ({el, sec, theme}) => {
  const op = presence(sec, el, 0.4, 0.5);
  if (!op) return null;
  const t = sec - el.start;
  const slide = 1 - easeOut(t / 0.7);
  const seal = easeOut((t - 0.5) / 0.35);
  const PW = 460, PH = 640, top = 110;
  const side = (s: VersusEl['left'], isLeft: boolean) => (
    <div style={{position: 'absolute', top, left: isLeft ? 230 - slide * 520 : undefined, right: isLeft ? undefined : 230 - slide * 520, width: PW}}>
      <div style={{position: 'relative', width: PW, height: PH}}>
        {s.image ? <Portrait src={s.image} cutout={s.cutout} w={PW} h={PH} flip={mirrorFor(isLeft ? 'left' : 'right', s.faces)} /> : <div style={{width: PW, height: PH, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StoryBrush', fontSize: 140, color: '#f2dfb3'}}>{s.name.slice(-1)}</div>}
      </div>
      <div style={{textAlign: 'center', marginTop: -70, position: 'relative'}}>
        <div style={{fontFamily: 'StoryBrush', fontSize: 60, color: '#fff3d8', textShadow: '0 3px 12px #000c'}}>{s.name}</div>
        <div style={{height: 5, width: 160, background: s.color.fill, margin: '4px auto 6px'}} />
        {s.title && <div style={{fontSize: 22, color: '#f0dfbd', textShadow: '0 2px 8px #000'}}>{s.title}</div>}
      </div>
    </div>
  );
  return (
    <div style={{position: 'absolute', inset: 0, opacity: op}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 45%, rgba(20,15,12,.55), rgba(10,8,6,.82))'}} />
      {side(el.left, true)}
      {side(el.right, false)}
      <div style={{position: 'absolute', left: W / 2 - 85, top: 300, width: 170, height: 170, borderRadius: 18, background: theme.red, border: '5px solid #f6dfb0', boxShadow: `0 0 40px ${theme.red}aa`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StoryBrush', fontSize: el.label.length > 1 ? 60 : 110, color: '#fff6e2', transform: `scale(${0.4 + 0.6 * seal}) rotate(${(1 - seal) * -20}deg)`, opacity: clamp(seal * 1.5)}}>
        {el.label}
      </div>
      {el.caption && <div style={{position: 'absolute', left: 0, right: 0, top: 500, textAlign: 'center', fontSize: 30, color: '#f3e3c2', textShadow: '0 2px 10px #000', opacity: smooth((t - 0.9) / 0.4)}}>{el.caption}</div>}
    </div>
  );
};

export const ExitPortrait: React.FC<{el: ExitEl; sec: number}> = ({el, sec}) => {
  if (!el.show_portrait || !el.image) return null;
  const op = presence(sec, el, 0.3, 0.9);
  if (!op) return null;
  const t = sec - el.start;
  // full colour for a beat, then the life drains out of him: grey within 0.6 s, sinking a little
  const k = smooth(clamp((t - 0.35) / 0.6));
  const left = el.side !== 'right';
  const violent = el.verb === '诛' || el.verb === '斩';
  const splash = easeOut(clamp((t - 0.3) / 0.25));
  const PW = 560, PH = 790;
  return (
    <div style={{position: 'absolute', top: 130 + k * 30, [left ? 'left' : 'right']: 60, width: PW, height: PH, opacity: op * (1 - 0.25 * k)}}>
      <Portrait src={el.image} cutout={el.cutout} w={PW} h={PH} grey={k} flip={mirrorFor(el.side, el.faces)} />
      {splash > 0 && (
        <Img src={staticFile(violent ? 'anim/slash_red_1.png' : 'anim/ink_wash_1.png')} style={{position: 'absolute', left: violent ? PW * 0.05 : PW * 0.18, top: violent ? PH * 0.34 : PH * 0.2, width: violent ? PW * 0.9 : PW * 0.7,
             opacity: (violent ? 0.9 : 0.4) * splash, mixBlendMode: 'multiply',
             clipPath: violent ? `inset(0 ${(1 - splash) * 100}% 0 0)` : undefined, transform: violent ? 'rotate(-24deg)' : `scale(${0.6 + 0.4 * splash})`}} />
      )}
      <div style={{position: 'absolute', bottom: 40, left: 0, right: 0, textAlign: 'center', fontFamily: 'StoryBrush', fontSize: 64, color: `rgb(${243 - 40 * k},${230 - 30 * k},${204 - 10 * k})`, textShadow: '0 2px 10px #000'}}>{el.name}</div>
    </div>
  );
};

// 说话气息线: while a figure speaks his own line, an ink breath stroke unrolls beside his portrait (enter or versus).
export const SpeechBrush: React.FC<{els: Element[]; segments: Segment[]; sec: number}> = ({els, segments, sec}) => {
  const g = segments.find((x) => x.speaker && sec >= x.voice_onset - 0.1 && sec <= x.voice_offset + 0.2);
  if (!g) return null;
  let spot: {x: number; y: number; flip: boolean} | null = null;
  for (const e of els) {
    if (sec < e.start || sec > e.end) continue;
    if (e.type === 'enter' && e.name === g.speaker)
      spot = e.side === 'right' ? {x: W - 70 - 580 - 30 - 300, y: 140, flip: true} : {x: 70 + 580 + 10, y: 140, flip: false};
    else if (e.type === 'versus' && (e.left.name === g.speaker || e.right.name === g.speaker))
      spot = e.left.name === g.speaker ? {x: 230 + 460 - 60, y: 140, flip: false} : {x: W - 230 - 460 + 60 - 300, y: 140, flip: true};
  }
  if (!spot) return null;
  const t = sec - (g.voice_onset - 0.1);
  const wipe = easeOut(clamp(t / 0.6));
  const out = smooth(clamp((sec - g.voice_offset) / 0.2));
  return (
    <div style={{position: 'absolute', left: spot.x, top: spot.y + Math.sin(t * 2.2) * 4, width: 300, height: 150, opacity: 0.9 * (1 - out), transform: spot.flip ? 'scaleX(-1)' : undefined,
                 clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)`}}>
      <Img src={staticFile('anim/speech_brush.png')} style={{width: 300, height: 150, filter: 'invert(0.92) drop-shadow(0 0 6px #0008)'}} />
    </div>
  );
};
