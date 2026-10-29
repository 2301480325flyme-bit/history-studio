import React from 'react';
import {Img, staticFile} from 'remotion';
import {easeOut, presence, smooth} from './anim';
import type {FactionBarEl, QuoteEl, Theme, TitleBarEl} from './types';

// Event cues: 事件标题条 (title_bar), 史料引文卡 (quote), 阵营提示条 (faction_bar).

// Paper grain: an inline SVG noise layer multiplied over a warm gradient.
const PaperGrain: React.FC<{id: string}> = ({id}) => (
  <svg style={{position: 'absolute', inset: 0, width: '100%', height: '100%', mixBlendMode: 'multiply', opacity: 0.45, pointerEvents: 'none'}}>
    <filter id={id}>
      <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={3} stitchTiles="stitch" />
      <feColorMatrix values="0 0 0 0 0.45  0 0 0 0 0.36  0 0 0 0 0.22  0 0 0 0.55 0" />
    </filter>
    <rect width="100%" height="100%" filter={`url(#${id})`} />
  </svg>
);

export const TitleBar: React.FC<{el: TitleBarEl; sec: number; theme: Theme}> = ({el, sec, theme}) => {
  const op = presence(sec, el, 0.35, 0.45);
  if (!op) return null;
  const t = sec - el.start;
  const slide = (1 - easeOut(t / 0.45)) * -90;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 112, display: 'flex', justifyContent: 'center', opacity: op}}>
      <div style={{position: 'relative', transform: `translateX(${slide}px)`, padding: '14px 110px 16px', textAlign: 'center'}}>
        {/* painted cinnabar brush band (brush_band_2) */}
        <Img src={staticFile('anim/brush_band_2.png')} style={{position: 'absolute', left: -30, right: -30, top: -18, bottom: -18, width: 'calc(100% + 60px)', height: 'calc(100% + 36px)', objectFit: 'fill', opacity: 0.95}} />
        <div style={{position: 'relative', fontFamily: 'StoryBrush', fontSize: 46, color: '#fff2d4', letterSpacing: 4, textShadow: '0 2px 6px #000b'}}>
          <span style={{color: theme.red, fontSize: 26, verticalAlign: 6, marginRight: 18}}>◆</span>{el.text}<span style={{color: theme.red, fontSize: 26, verticalAlign: 6, marginLeft: 18}}>◆</span>
        </div>
        {el.sub && <div style={{position: 'relative', fontSize: 19, color: '#f3e3c2', letterSpacing: 3, marginTop: 2, textShadow: '0 1px 4px #000b'}}>{el.sub}</div>}
      </div>
    </div>
  );
};

export const QuoteCard: React.FC<{el: QuoteEl; sec: number; theme: Theme}> = ({el, sec, theme}) => {
  const op = presence(sec, el, 0.45, 0.45);
  if (!op) return null;
  const t = sec - el.start;
  const s = 0.95 + 0.05 * easeOut(t / 0.5);
  const right = el.side !== 'left';
  return (
    <div style={{position: 'absolute', top: (right ? 175 : 300) + Math.sin(t * 1.3) * 2, [right ? 'right' : 'left']: 60, width: 560, opacity: op, transform: `scale(${s}) rotate(${right ? -0.8 : 0.8}deg)`, transformOrigin: right ? '100% 0' : '0 0'}}>
      <div style={{position: 'relative', padding: '30px 30px 22px 34px', background: 'linear-gradient(160deg,#f3e7cc,#e6d5b0)', borderLeft: `7px solid ${theme.red}`, boxShadow: '0 10px 26px #0008, inset 0 0 40px #b49a6a55', color: '#33241a'}}>
        <PaperGrain id={`grain${Math.round(el.start * 100)}`} />
        <div style={{position: 'absolute', top: -16, right: 22, padding: '3px 12px', border: `2px solid ${theme.red}`, color: theme.red, background: '#f4e9d0', fontSize: 17, fontFamily: 'StorySerif', fontWeight: 700}}>《{el.source}》</div>
        {/* 逐字打出 (after 纸上谈兵): the source text types itself out */}
        <div style={{position: 'relative', fontFamily: 'StorySerif', fontSize: 30, lineHeight: 1.6, fontWeight: 600}}>
          「{[...el.text].map((ch, k) => <span key={k} style={{opacity: t >= 0.25 + k * 0.06 ? 1 : 0}}>{ch}</span>)}」
        </div>
        {el.era && <div style={{textAlign: 'right', fontSize: 16, color: '#6b5640', marginTop: 8}}>— {el.era}</div>}
      </div>
    </div>
  );
};

export const FactionBars: React.FC<{els: FactionBarEl[]; sec: number}> = ({els, sec}) => {
  const live = els.filter((e) => sec >= e.start && sec <= e.end);
  return (
    <>
      {live.map((el, i) => {
        const t = sec - el.start;
        const inP = easeOut(t / 0.4), outP = smooth((sec - (el.end - 0.35)) / 0.35);
        return (
          <div key={el.text + el.start} style={{position: 'absolute', left: 40 - (1 - inP) * 420, top: 118 + i * 52, height: 44, display: 'flex', alignItems: 'center', opacity: 1 - outP, background: `linear-gradient(90deg, ${el.color.flag}f2, ${el.color.flag}cc 70%, transparent)`, paddingRight: 70, boxShadow: '0 4px 12px #0005'}}>
            <div style={{width: 44, height: 44, background: '#f2e2bd', color: el.color.flag, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StoryBrush', fontSize: 28}}>{(el.faction || el.text).slice(0, 1)}</div>
            <div style={{fontFamily: 'StoryBrush', fontSize: 28, color: '#fff4dc', marginLeft: 14, letterSpacing: 2, textShadow: '0 1px 4px #0008'}}>{el.text}</div>
          </div>
        );
      })}
    </>
  );
};
