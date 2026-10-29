import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, presence, smooth} from './anim';
import type {VignetteEl} from './types';

// 情景插画窗 (2026-10-20, after 纸上谈兵《井陉之战》): a painted scene opens in a feathered oval over the map,
// pushes in slowly while the narration runs, then fades; the map around it is dimmed but keeps moving.
// Art: 03_素材/动画素材/第N批/illus_*.png (staged as anim/illus_*.jpg at full size).
export const Vignette: React.FC<{el: VignetteEl; sec: number}> = ({el, sec}) => {
  const op = presence(sec, el, 0.45, 0.5);
  if (op < 0.01) return null;
  const k = clamp((sec - el.start) / Math.max(0.1, el.end - el.start));
  const w = 1200, h = 676;
  const cx = el.pos === 'left' ? 690 : el.pos === 'right' ? 1230 : 960, cy = 480;
  const push = 1 + (el.zoom - 1) * smooth(k);
  const open = 0.9 + 0.1 * smooth(clamp((sec - el.start) / 0.6));
  const mask = 'radial-gradient(ellipse 50% 50% at 50% 50%, #000 70%, transparent 100%)';
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 60% 60% at 50% 45%, #0000 40%, #000b 100%)', opacity: op * 0.85, pointerEvents: 'none'}} />
      <div style={{position: 'absolute', left: cx - w / 2, top: cy - h / 2, width: w, height: h, opacity: op, transform: `scale(${open})`,
                   WebkitMaskImage: mask, maskImage: mask, overflow: 'hidden'}}>
        <Img src={staticFile(el.image)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${push})`}} />
      </div>
      {el.text && (
        <div style={{position: 'absolute', left: cx - w / 2 + 90, top: cy + h / 2 - 120, opacity: op * smooth(clamp((sec - el.start - 0.5) / 0.4)),
                     fontFamily: 'StoryBrush', fontSize: 52, color: '#fff3dc', textShadow: '0 2px 8px #000c, 0 0 2px #000', letterSpacing: 4, whiteSpace: 'nowrap'}}>
          {el.text}
        </div>
      )}
    </>
  );
};
