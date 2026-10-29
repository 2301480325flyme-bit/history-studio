import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, easeOut, mirrorFor, presence, smooth} from './anim';
import type {StageEl} from './types';

// 对话舞台 (after 安州牧《两晋十六国》): the map fades to an old-book page printed with faint columns of text;
// the people talking stand large on the left and right, the speaker lit and the listener dimmed;
// what he says floats beside him in brush script (the 原文 when the beat has a `quote`).

const W = 1920, H = 1080;
const PW = 660, PH = 900;
// faint "book text" for the paper: rows of classical-looking characters (decoration only, never read)
const BOOK = '太祖与绍相持官渡军粮方尽书与荀彧议欲还许彧以为绍悉众聚官渡欲与公决胜负公以至弱当至强若不能制必为所乘是天下之大机也' +
  '且绍布衣之雄耳能聚人而不能用夫以公之神武明哲而辅以大顺何向而不济公从之遂坚守以待其变时公兵不满万伤者十二三';

// a painted room (第6批 scene_*) instead of the paper: slow push-in, a little blur so the people stay in front
const Room: React.FC<{src: string; t: number}> = ({src, t}) => (
  <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#2a1d10'}}>
    <Img
      src={staticFile(src)}
      style={{
        position: 'absolute',
        inset: 0,
        width: W,
        height: H,
        objectFit: 'cover',
        transform: `scale(${1.02 + t * 0.004})`,
        translate: '-65.7px 0px'
      }}
    />
    <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 80% 75% at 50% 45%, transparent 55%, #2e1d0c66 100%)'}} />
  </div>
);

const Paper: React.FC<{t: number; scene: string}> = ({t, scene}) => {
  const cols = 30;
  const drift = t * 3;
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: 'radial-gradient(ellipse 75% 70% at 50% 45%, #eadcbc 0%, #dcc79c 62%, #b89c6c 100%)'}}>
      <div style={{position: 'absolute', top: -40, right: -20 + drift, height: H + 80, display: 'flex', flexDirection: 'row-reverse', gap: 26, opacity: 0.085}}>
        {Array.from({length: cols}, (_, c) => (
          <div key={c} style={{writingMode: 'vertical-rl', fontFamily: 'StorySerif', fontSize: 34, lineHeight: 1, letterSpacing: 6, color: '#3d2a14', whiteSpace: 'nowrap'}}>
            {(BOOK + BOOK).slice((c * 17) % BOOK.length, (c * 17) % BOOK.length + 34)}
          </div>
        ))}
      </div>
      {/* fibres and stains */}
      <Img src={staticFile('anim/paper_fibre.png')} style={{position: 'absolute', inset: 0, width: W, height: H, mixBlendMode: 'multiply', opacity: 0.55}} />
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 80% 75% at 50% 45%, transparent 55%, #5a3f1c55 100%)'}} />
    </div>
  );
};

export const Stage: React.FC<{el: StageEl; sec: number}> = ({el, sec}) => {
  const op = presence(sec, el, 0.7, 0.7);
  if (!op) return null;
  const t = sec - el.start;
  // who is lit: the one speaking, else the next to speak (a lead-in "许攸就问："), else the last
  const litAt = (x: number) => (el.lines.find((l) => x >= l.t0 - 0.15 && x <= l.t1 + 0.15) ?? el.lines.find((l) => l.t0 > x) ?? el.lines[el.lines.length - 1])?.who;
  // the light follows the talk with a soft 0.35 s swap (average of recent samples), not a cut
  const litK = (who: string) => {
    let n = 0;
    for (let j = 0; j < 8; j++) n += litAt(sec - j * 0.05) === who ? 1 : 0;
    return smooth(n / 8);
  };
  // the brush text stays until the next line is about to start
  const shown = [...el.lines].reverse().find((l) => sec >= l.t0 - 0.1);
  const after = shown ? el.lines[el.lines.indexOf(shown) + 1] : undefined;
  const textOut = after ? smooth(clamp((sec - (after.t0 - 0.35)) / 0.25)) : 0;
  const zoom = 1 + 0.035 * clamp(t / Math.max(1, el.end - el.start));
  return (
    <div style={{position: 'absolute', inset: 0, opacity: op}}>
      <div style={{position: 'absolute', inset: 0, transform: `scale(${zoom})`}}>{el.image ? <Room src={el.image} t={t} /> : <Paper t={t} scene={el.scene} />}</div>
      {el.actors.map((a, i) => {
        const aop = Math.min(smooth(clamp((sec - a.start) / 0.5)), 1 - smooth(clamp((sec - (a.end - 0.4)) / 0.4)));
        if (aop <= 0) return null;
        const rise = (1 - easeOut(clamp((sec - a.start) / 0.7))) * 60;
        // death on stage: a beat of full colour, then grey within 0.6 s (斩/诛/杀 also leave a red slash)
        const dk = a.die_at != null ? smooth(clamp((sec - a.die_at - 0.35) / 0.6)) : 0;
        const slash = a.die_at != null && ['斩', '诛', '杀'].includes(a.verb ?? '') ? easeOut(clamp((sec - a.die_at - 0.3) / 0.25)) : 0;
        const k = litK(a.who) * (1 - dk) + dk;
        const left = a.side === 'left';
        const x0 = left ? 30 : W - 30 - PW;
        const mask = 'linear-gradient(to right, transparent 0%, #000 8%, #000 92%, transparent 100%), linear-gradient(to bottom, #000 80%, transparent 100%)';
        return (
          <div key={i} style={{position: 'absolute', inset: 0, opacity: aop}}>
            <div style={{position: 'absolute', left: x0, top: H - PH + 20 + rise + (1 - k) * 24, width: PW, height: PH, transformOrigin: `${left ? '30%' : '70%'} 100%`,
                         transform: `scale(${0.93 + 0.07 * k})`, transition: 'none',
                         filter: `brightness(${(0.62 + 0.38 * k) * (1 - 0.3 * dk)}) saturate(${(0.65 + 0.35 * k) * (1 - dk)}) drop-shadow(0 10px 24px #3a240f66)`}}>
              {a.image ? (
                <Img src={staticFile(a.image)} style={{width: PW, height: PH, objectFit: a.cutout ? 'contain' : 'cover', objectPosition: '50% 12%', transform: mirrorFor(a.side, a.faces) ? 'scaleX(-1)' : undefined, maskImage: mask, WebkitMaskImage: mask, maskComposite: 'intersect', WebkitMaskComposite: 'source-in'}} />
              ) : (
                <div style={{width: PW, height: PH, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StoryBrush', fontSize: 220, color: '#3a2814'}}>{a.name.slice(-1)}</div>
              )}
              {slash > 0 && <Img src={staticFile('anim/slash_red_1.png')} style={{position: 'absolute', left: PW * 0.05, top: PH * 0.3, width: PW * 0.9, opacity: 0.9 * slash, mixBlendMode: 'multiply',
                                                                              clipPath: `inset(0 ${(1 - slash) * 100}% 0 0)`, transform: 'rotate(-24deg)'}} />}
            </div>
            {/* vertical brush name beside the head, with a faction-coloured seal stroke */}
            <div style={{position: 'absolute', top: (left ? 300 : 120) + rise, [left ? 'left' : 'right']: 44,   // left name starts under the year scroll
                          display: 'flex', flexDirection: left ? 'row' : 'row-reverse', alignItems: 'flex-start', gap: 10, opacity: 0.55 + 0.45 * k}}>
              <div style={{width: 7, height: a.name.length * 84 + 10, background: a.color.flag, borderRadius: 4, marginTop: 6}} />
              <div style={{writingMode: 'vertical-rl', fontFamily: 'StoryBrush', fontSize: 84, lineHeight: 1, color: '#22160c', textShadow: '0 0 16px #f2e6cc, 0 0 6px #f2e6cc'}}>{a.name}</div>
              {a.title && <div style={{writingMode: 'vertical-rl', fontSize: 26, color: '#4a3520', letterSpacing: 4, marginTop: 12}}>{a.title}</div>}
            </div>
          </div>
        );
      })}
      {shown && (() => {
        const sp = el.actors.find((a) => a.who === shown.who && sec >= a.start && sec <= a.end);
        const left = !sp || sp.side === 'left';
        const lt = sec - shown.t0;
        const chars = [...shown.text];
        const dur = Math.max(0.6, (shown.t1 - shown.t0) * 0.7);
        const n = Math.ceil(chars.length * clamp(lt / dur));
        const tOp = (1 - textOut) * smooth(clamp((lt + 0.1) / 0.3));
        if (tOp <= 0) return null;
        const size = chars.length > 40 ? 50 : chars.length > 22 ? 60 : 74;
        return (
          <div style={{position: 'absolute', top: 210, [left ? 'left' : 'right']: PW - 20, width: 680,
                       fontFamily: 'StoryBrush', fontSize: size, lineHeight: 1.45, color: '#1d130a', textAlign: left ? 'left' : 'right', opacity: tOp,
                       textShadow: '0 0 18px #f3e8cf, 0 0 8px #f3e8cf, 0 0 3px #f3e8cf'}}>
            {chars.map((c, i) => <span key={i} style={{opacity: i < n ? 1 : 0}}>{c}</span>)}
            {shown.original && <div style={{fontFamily: 'StorySans', fontSize: 22, color: '#5a4024', marginTop: 10, letterSpacing: 2, textShadow: '0 0 8px #f3e8cf, 0 0 3px #f3e8cf'}}>— 史书原文</div>}
          </div>
        );
      })()}
    </div>
  );
};
