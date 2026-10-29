import React from 'react';
import {Img, staticFile} from 'remotion';
import type {CameraKey} from './types';
import {easeOut, presence, smooth} from './anim';
import type {Episode, HeadlineEl, PortraitEl, Segment, Theme} from './types';

// Fixed screen furniture: title block, phase chip, year badge, caption bar,
// legend, disclosure footer, portrait cut-ins and event headlines.

export const TitleBlock: React.FC<{ep: Episode}> = ({ep}) => (
  <>
    <div style={{position: 'absolute', left: 50, top: 27, color: ep.theme.ink, fontSize: 19, letterSpacing: 3}}>{ep.series}</div>
    <div style={{position: 'absolute', left: 50, top: 54, fontFamily: 'StoryBrush', fontSize: 44, color: ep.theme.ink, fontWeight: 700}}>{ep.title}</div>
  </>
);

export const PhaseChip: React.FC<{ep: Episode; sec: number}> = ({ep, sec}) => {
  const ph = ep.phases.find((p) => sec >= p.start && sec < p.end);
  if (!ph) return null;
  const op = presence(sec, ph, 0.3, 0.2);
  return <div style={{position: 'absolute', right: 44, top: 32, opacity: op, color: '#fff4d6', background: '#594431e8', padding: '10px 23px', border: '1px solid #c7a86d', fontSize: 29, fontFamily: 'StorySerif'}}>{ph.text}</div>;
};

export const YearBadge: React.FC<{ep: Episode; sec: number}> = ({ep, sec}) => {
  const y = ep.years.find((p) => sec >= p.start && sec < p.end);
  if (!y) return null;
  const flip = easeOut((sec - y.start) / 0.35);
  return (
    <div style={{position: 'absolute', left: 26, ...(ep.theme.ui === 'clean' ? {top: 26} : {bottom: 106}), width: 166, padding: y.era ? '6px 8px 7px' : '10px 10px', background: ep.theme.yearBg, color: '#fff2d1', border: '1px solid #d3b989', borderRadius: 5, textAlign: 'center', transform: `scaleY(${0.3 + 0.7 * flip})`}}>
      {y.era && <div style={{fontFamily: 'StoryBrush', fontSize: 28, lineHeight: 1.15, letterSpacing: 2}}>{y.era}</div>}
      <div style={{fontSize: y.era ? 17 : y.text.length > 5 ? 26 : 32, fontWeight: 700, opacity: y.era ? 0.9 : 1}}>{y.text}</div>
    </div>
  );
};

export const CaptionBar: React.FC<{segments: Segment[]; sec: number; theme: Theme}> = ({segments, sec, theme}) => {
  // Clause-level captions (reference style), timed within each measured voice window.
  let text: string | undefined;
  let speaker: string | null | undefined;
  for (const g of segments) {
    const c = (g.captions || []).find((x) => sec >= x.t0 && sec <= x.t1);
    if (c) { text = c.text; speaker = g.speaker; break; }
    if (!g.captions && sec >= g.voice_onset - 0.07 && sec <= g.voice_offset + 0.07) { text = g.caption; speaker = g.speaker; break; }
  }
  const s = text ? {caption: text} : undefined;
  if (theme.look === 'atlas' && s)
    // atlas: white words in a dark rounded box above the chapter strip; a figure's own line carries his name in gold
    return (
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 62, display: 'flex', justifyContent: 'center'}}>
        <div style={{maxWidth: 1600, padding: '8px 28px 10px', borderRadius: 10, background: '#16181cd0', color: '#ffffff', fontSize: 46, fontWeight: 700, letterSpacing: 2, lineHeight: 1.25, boxShadow: '0 4px 14px #0006'}}>
          {speaker && <span style={{fontFamily: 'StoryBrush', fontWeight: 400, color: '#e2c27a', fontSize: 42, marginRight: 14}}>{speaker}</span>}
          {speaker ? `「${s.caption}」` : s.caption}
        </div>
      </div>
    );
  if (theme.ui === 'clean' && speaker && s) {
    // A line spoken by the historical figure himself: dark ink on a paper plate, his name in seal red, so it never reads as narration.
    const w = Math.min(1760, 380 + s.caption.length * 58 + speaker.length * 44);
    return (
      <div style={{position: 'absolute', left: (1920 - w) / 2, width: w, bottom: 22, height: 150, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        <Img src={staticFile('anim/caption_plate.png')} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'fill', opacity: 0.95, filter: 'drop-shadow(0 6px 14px #0009)'}} />
        <div style={{position: 'relative', fontSize: 52, fontWeight: 800, letterSpacing: 2, color: '#2a1a0e', lineHeight: 1.2, whiteSpace: 'nowrap', marginTop: 4}}>
          <span style={{fontFamily: 'StoryBrush', fontWeight: 400, color: '#9a2414', fontSize: 46, marginRight: 16}}>{speaker}</span>「{s.caption}」
        </div>
      </div>
    );
  }
  if (theme.ui === 'clean')
    // reference style: no box, big white text with a dark outline, sitting low on the map.
    // A line spoken by the historical figure himself: his name in gold, the words in quotes and warmer colour.
    return (
      <div style={{position: 'absolute', left: 120, right: 120, bottom: 54, textAlign: 'center', fontSize: 54, fontWeight: 800, letterSpacing: 2, color: '#ffffff', lineHeight: 1.25,
        WebkitTextStroke: '7px #111', paintOrder: 'stroke fill', textShadow: '0 3px 8px #000a'}}>
        {s?.caption || ''}
      </div>
    );
  return (
    <div style={{position: 'absolute', left: 207, right: 25, bottom: 105, minHeight: 89, background: theme.captionBg, borderTop: '1px solid #b2a184', padding: '14px 23px', fontSize: 44, color: '#fffaf0', textAlign: 'center', lineHeight: 1.3}}>
      {s?.caption || ' '}
    </div>
  );
};

export const Legend: React.FC<{items: string[]}> = ({items}) =>
  items.length ? <div style={{position: 'absolute', left: 28, bottom: 66, color: '#274f6b', fontSize: 17, background: '#e8dcc4d9', padding: '3px 7px'}}>{items.join('　')}</div> : null;

export const Footer: React.FC<{ep: Episode}> = ({ep}) => (
  <footer style={{position: 'absolute', left: 27, right: 27, bottom: 22, color: '#443c30', fontSize: 17, display: 'flex', justifyContent: 'space-between'}}>
    <span>{ep.footer.left}</span>
    <span>{ep.footer.right}</span>
  </footer>
);

export const Portrait: React.FC<{el: PortraitEl; sec: number}> = ({el, sec}) => {
  const op = presence(sec, el, 0.35, 0.45);
  if (!op) return null;
  const slide = easeOut((sec - el.start) / 0.5);
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: '#111318', opacity: op * 0.55}} />
      <div style={{position: 'absolute', left: 80 - (1 - slide) * 60, top: 190, width: 280, height: 490, opacity: op, boxShadow: '0 12px 38px #0008', border: '2px solid #d8bc80', background: '#252225'}}>
        <div style={{height: 380, overflow: 'hidden'}}>
          {el.image ? (
            <Img src={staticFile(el.image)} style={{width: '100%', height: 420, objectFit: 'cover', objectPosition: '50% 20%'}} />
          ) : (
            // No portrait available: a typographic seal card, never a made-up face.
            <div style={{height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'radial-gradient(circle at 50% 40%, #4a3a2c, #1c1714 75%)'}}>
              <div style={{width: 168, height: 250, border: '3px solid #b8322a', outline: '1px solid #b8322a66', outlineOffset: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', writingMode: 'vertical-rl', fontFamily: 'StorySerif', fontWeight: 700, color: '#f0d9a8', fontSize: el.name.replace(/[ ·]/g, '').length > 4 ? 46 : 64, letterSpacing: 6}}>
                {el.name.replace(/.*· ?/, '')}
              </div>
            </div>
          )}
        </div>
        <div style={{color: '#f2deaa', fontFamily: 'StorySerif', fontSize: el.name.length > 7 ? 30 : 38, textAlign: 'center', marginTop: 10}}>{el.name}</div>
        {(el.title || el.note) && <div style={{color: '#dfd2be', fontSize: 17, textAlign: 'center', marginTop: 3}}>{[el.title, el.note].filter(Boolean).join(' · ')}</div>}
      </div>
    </>
  );
};

export const Headline: React.FC<{el: HeadlineEl; sec: number; theme: Theme}> = ({el, sec, theme}) => {
  const op = presence(sec, el, 0.4, 0.4);
  if (!op) return null;
  const spread = smooth((sec - el.start) / 0.7);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 330, textAlign: 'center', opacity: op}}>
      <div style={{position: 'relative', display: 'inline-block', padding: '26px 120px'}}>
        {/* painted ink brush band (03_素材/动画素材 brush_band_1), swept in left → right */}
        <div style={{position: 'absolute', left: -40, right: -40, top: -30, bottom: -30, clipPath: `inset(0 ${(1 - easeOut((sec - el.start) / 0.45)) * 100}% 0 0)`}}>
          <Img src={staticFile('anim/brush_band_1.png')} style={{width: '100%', height: '100%', objectFit: 'fill', opacity: 0.93}} />
        </div>
        <div style={{position: 'relative', fontFamily: 'StoryBrush', fontSize: 96, fontWeight: 400, color: '#f6e2b0', letterSpacing: 6 + 10 * (1 - spread), textShadow: `0 0 18px ${theme.red}, 0 3px 8px #000c`}}>{el.text}</div>
        {el.sub && <div style={{position: 'relative', fontSize: 28, color: '#efe0c0', marginTop: 8, letterSpacing: 4, textShadow: '0 2px 6px #000c'}}>{el.sub}</div>}
      </div>
    </div>
  );
};

// A big calendar card at the top: the old year flips down into the new one, holds, then
// shrinks away toward the year badge. Used when a beat jumps across years.
export const YearFlip: React.FC<{el: {start: number; end: number; from: {era?: string | null; text: string}; to: {era?: string | null; text: string}}; sec: number; theme: Episode['theme']}> = ({el, sec, theme}) => {
  if (sec < el.start || sec > el.end) return null;
  const t = sec - el.start;
  const appear = easeOut(t / 0.35);
  const flip = Math.min(1, Math.max(0, (t - 0.6) / 0.55));
  const leave = Math.min(1, Math.max(0, (sec - (el.end - 0.6)) / 0.6));
  const face = flip < 0.5 ? el.from : el.to;
  const rot = flip < 0.5 ? flip * 180 : (flip - 1) * 180;
  return (
    <div style={{position: 'absolute', left: '50%', top: 150, transform: `translate(-50%,0) scale(${(0.7 + 0.3 * appear) * (1 - 0.5 * leave)})`, opacity: appear * (1 - leave), perspective: 900}}>
      <div style={{minWidth: 360, padding: '16px 34px 20px', background: theme.yearBg, border: '3px solid #d3b989', borderRadius: 8, color: '#fff2d1', textAlign: 'center', boxShadow: '0 10px 30px #0006', transform: `rotateX(${rot}deg)`}}>
        {face.era && <div style={{fontFamily: 'StoryBrush', fontSize: 48, letterSpacing: 6, lineHeight: 1.1}}>{face.era}</div>}
        <div style={{fontSize: face.era ? 30 : 64, fontWeight: 700, opacity: 0.92}}>{face.text}</div>
      </div>
    </div>
  );
};

// Corner overview map: fades in when the camera pushes in to battle scale, with a box
// showing the current view, so viewers keep track of "where in the country we are".
export const MiniMap: React.FC<{ep: Episode; cam: CameraKey}> = ({ep, cam}) => {
  const mm = ep.map.minimap, r = ep.map.raster;
  if (!mm || !r) return null;
  // show only when the current view is a small part of the overview (a pushed-in, local shot)
  const ratio = ep.width / cam.z / mm.width;
  const op = smooth((0.3 - ratio) / 0.08);
  if (op <= 0.01) return null;
  const MW = 270, MH = Math.round(270 * mm.height / mm.width);
  const k = MW / mm.width;
  const vw = (ep.width / cam.z) * k, vh = (ep.height / cam.z) * k;
  const vx = (cam.cx - mm.x) * k - vw / 2, vy = (cam.cy - mm.y) * k - vh / 2;
  return (
    <div style={{position: 'absolute', right: 26, bottom: 214, width: MW, height: MH, opacity: op, overflow: 'hidden', border: '3px solid #8a6a3e', outline: '1px solid #f0e2c2', outlineOffset: -6, boxShadow: '0 6px 18px #0006', background: '#d8ccb4'}}>
      <Img src={staticFile(r.src)} style={{position: 'absolute', left: (r.x - mm.x) * k, top: (r.y - mm.y) * k, width: r.width * k, height: r.height * k, filter: 'saturate(0.7) brightness(1.05)'}} />
      <div style={{position: 'absolute', left: vx, top: vy, width: Math.max(8, vw), height: Math.max(6, vh), border: '2.5px solid #b02a1a', background: '#b02a1a22', boxShadow: '0 0 0 1px #fff8'}} />
      <div style={{position: 'absolute', left: 6, top: 4, fontSize: 15, color: '#3b2a1a', fontFamily: 'StorySerif', textShadow: '0 0 3px #f4ecdc'}}>全图</div>
    </div>
  );
};
