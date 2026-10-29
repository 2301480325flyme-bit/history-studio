import React from 'react';
import {clamp, smooth} from './anim';
import type {Episode} from './types';

// atlas look (2026-10-15, after 史图记忆簿): big spaced mountain / river names on the map, a dark title bar on top
// and a chapter strip at the bottom. Only drawn when ep.theme.look === 'atlas'; the other looks are untouched.

export const AtlasFeatures: React.FC<{ep: Episode; zoom: number; screen: (x: number, y: number) => [number, number]}> = ({ep, zoom, screen}) => {
  const fs = ep.map.features ?? [];
  if (!fs.length) return null;
  // the names belong to the regional view: fade in from the national map, out again in close-ups
  const op = clamp((zoom - 0.55) / 0.3) * clamp((7 - zoom) / 2);
  if (op <= 0.01) return null;
  // only the main waterways keep their names, so they do not crowd the giant polity names
  const MAJOR_WATER = new Set(['江', '河', '淮', '汉水', '渭水']);
  return (
    <>
      {fs.filter((f) => f.kind !== 'water' || MAJOR_WATER.has(f.name)).map((f, i) => {
        const [x, y] = screen(f.x, f.y);
        if (x < -150 || x > 2070 || y < 40 || y > 1040) return null;
        const mountain = f.kind === 'mountain';
        const size = f.kind === 'sea' ? 46 : mountain ? 40 : f.name.length === 1 ? 50 : 40;
        if (ep.theme.palette === 'warm') {
          // warm (2026-10-24): physical names in atlas blue, oblique sans, spread along the feature, on a white halo
          const s = f.kind === 'sea' ? 40 : mountain ? 30 : f.name.length === 1 ? 38 : 30;
          return (
            <div key={'af' + i} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: op * 0.9, pointerEvents: 'none',
              writingMode: f.v ? 'vertical-rl' : undefined, fontFamily: 'StoryMap', fontWeight: 600, fontStyle: 'italic', fontSize: s, letterSpacing: f.name.length === 1 ? 0 : s * 1.1,
              color: f.kind === 'sea' ? '#e6edf2' : '#3b6893', whiteSpace: 'nowrap', ...(f.kind === 'sea' ? {} : {WebkitTextStroke: '4px #f6f4eecc', paintOrder: 'stroke fill' as const})}}>
              {f.name}
            </div>
          );
        }
        return (
          <div key={'af' + i} style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', opacity: op * (mountain ? 0.72 : 0.85), pointerEvents: 'none',
            writingMode: f.v ? 'vertical-rl' : undefined, fontFamily: 'StorySerif', fontWeight: 700, fontSize: size, letterSpacing: f.name.length === 1 ? 0 : size * 0.9,
            color: mountain ? '#33362d' : '#eef2f2', textShadow: mountain ? '0 0 4px #e8e6dccc, 0 0 10px #e8e6dc88' : '0 1px 3px #2a333888, 0 0 8px #2a333855', whiteSpace: 'nowrap'}}>
            {f.name}
          </div>
        );
      })}
    </>
  );
};

const episodeNo = (series: string) => (series.match(/第\s*(\d+)\s*集/) ?? [])[1] ?? '';

export const AtlasTopBar: React.FC<{ep: Episode; sec: number}> = ({ep, sec}) => {
  const op = smooth(sec / 0.6);
  const no = episodeNo(ep.series);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: 62, opacity: op, background: 'linear-gradient(180deg,#14171bf0,#1a1d22d8)', borderBottom: '1px solid #c9b07a55',
      display: 'flex', alignItems: 'center', paddingLeft: 30, gap: 26, color: '#f1e9d6', boxShadow: '0 3px 12px #0005'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
        <div style={{width: 34, height: 34, border: '2px solid #d6b36a', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'StorySerif', fontWeight: 700, color: '#d6b36a', fontSize: 22}}>{(ep.theme.channel ?? '兰台令史')[0]}</div>
        <div style={{fontFamily: 'StorySerif', fontWeight: 700, fontSize: 27, letterSpacing: 5, color: '#e8d4a2'}}>{ep.theme.channel ?? '兰台令史'}</div>
      </div>
      <div style={{width: 1, height: 30, background: '#c9b07a66'}} />
      <div style={{fontFamily: 'StorySerif', fontSize: 25, letterSpacing: 2, whiteSpace: 'nowrap'}}>
        《{ep.theme.series_title ?? ''}》{no && <>第<span style={{fontSize: 40, fontWeight: 700, color: '#ffffff', margin: '0 6px', fontFamily: 'StorySans'}}>{no}</span>集</>}：{ep.title}
      </div>
    </div>
  );
};

export const AtlasChapterBar: React.FC<{ep: Episode; sec: number}> = ({ep, sec}) => {
  const ph = ep.phases;
  if (!ph.length) return null;
  const op = smooth(sec / 0.6);
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 38, opacity: op, background: '#14171be8', borderTop: '1px solid #c9b07a44', display: 'flex'}}>
      {ph.map((p, i) => {
        const on = sec >= p.start && sec < p.end;
        const done = sec >= p.end;
        const k = on ? clamp((sec - p.start) / Math.max(0.1, p.end - p.start)) : done ? 1 : 0;
        return (
          <div key={i} style={{position: 'relative', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', borderLeft: i ? '1px solid #ffffff22' : undefined,
            background: on ? '#f1ece0' : 'transparent', color: on ? '#1d1a14' : done ? '#cfc6b2' : '#8f8a7e', fontFamily: 'StorySerif', fontSize: 21, letterSpacing: 2, fontWeight: on ? 700 : 400}}>
            {p.text}
            {/* thin progress line under the running chapter */}
            {on && <div style={{position: 'absolute', left: 0, bottom: 0, height: 3, width: `${k * 100}%`, background: '#b8322a'}} />}
          </div>
        );
      })}
    </div>
  );
};
