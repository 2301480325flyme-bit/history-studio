import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, easeOut, presence, samplePath, smooth, type Pt} from './anim';
import type {ActEl, Theme} from './types';

// Map actions (`act:` element) built from the hand-painted PNGs in public/anim (03_素材/动画素材):
//   coins 卖官 · wind 狂风 · edict 诏书 · prison 下狱 · courier 信使 · beacon 烽火 · execute 处斩 · mourn 驾崩 ·
//   enthrone 登基 · arrows 箭雨 · flood 水淹 · night 夜色 · thunder 雷 · catapult 投石 · locusts 蝗灾 · fall 城陷 ·
//   refugees 流民 · prop 器物（玉玺、虎符、冕冠…） · herd 放牛马 · pontoon 浮桥
// All layers are HTML (<Img> waits for the image before a frame renders). Deterministic: every frame renders the same.

const W = 1920, H = 1080;
const rnd = (seed: number) => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const A = (name: string) => staticFile(`anim/${name}.png`);
const clampX = (x: number, w: number) => Math.min(W - w - 30, Math.max(30, x));
const clampY = (y: number, h: number) => Math.min(H - h - 200, Math.max(90, y));   // keep clear of the caption band

// every painted asset an act may show; prefetched once so nothing pops in late in the preview
export const ANIM_FILES = ['slash_ink_1', 'slash_ink_2', 'slash_ink_3', 'slash_red_1', 'slash_red_2', 'slash_red_3', 'splash_3', 'splash_5',
  'scroll_blank', 'frame_auspicious', 'coins_string', 'wind_swirl_1', 'wind_swirl_2', 'prison_cart', 'letter_scroll', 'beacon_tower',
  'mourning_banner', 'arrow_single', 'flood_tile', 'wave_2', 'moon', 'cloud_ink_1', 'cloud_ink_2', 'lightning', 'catapult', 'stone_boulder',
  'smoke_1', 'smoke_2', 'smoke_3', 'locust', 'wall_broken', 'refugees_line', 'jade_seal', 'tiger_tally', 'crown_mian', 'grain_pile',
  'bamboo_slips', 'city_gate_closed', 'warship_tower', 'boat_small', 'flame_1', 'flame_2', 'flame_3', 'seal_blank',
  'unit_cavalry', 'unit_infantry', 'dust_cloud_1', 'dust_cloud_2', 'camp_tents', 'city_walled', 'palace', 'pass_gate', 'bridge', 'tomb_mound', 'altar',
  'banquet', 'wine_jar', 'throne', 'jue_cup', 'war_drum', 'torch', 'arrow_bundle', 'horse_riderless',
  'unit_archer', 'unit_crossbow', 'unit_general', 'unit_courier', 'ink_wash_1', 'ink_wash_2', 'field_tile', 'brush_band_1', 'brush_band_2', 'paper_torn_edge',
  'sword_jian', 'court_shoes', 'jie_staff', 'yinshou', 'red_headscarf', 'watchtower', 'honey_bowl', 'belt_edict', 'thatched_cottage', 'horse_cart',
  'caption_plate', 'speech_brush', 'shou_ji', 'rope_bound', 'grain_cart',
  'ox_running', 'ox_running_2', 'horse_loose_2', 'pontoon_segment',
  // 第12批 city icons and their tint masks (staged as icon_*)
  ...['city_capital', 'city_province', 'city_commandery', 'city_county', 'fort_stockade', 'pass_gate', 'ferry_jetty', 'ruler_seat_badge']
    .flatMap((n) => [`icon_${n}`, `icon_${n}_mask`])].map((n) => `anim/${n}.png`);

// brush-script caption used by most acts
const Tag: React.FC<{x: number; y: number; text?: string | null; op: number; color?: string; size?: number}> = ({x, y, text, op, color = '#2a1d12', size = 40}) =>
  text ? (
    <div style={{position: 'absolute', left: x, top: y, transform: 'translate(-50%, -100%)', fontFamily: 'StoryBrush', fontSize: size, letterSpacing: 4, whiteSpace: 'nowrap',
                 color: '#fff6e0', WebkitTextStroke: `7px ${color}`, paintOrder: 'stroke fill', opacity: op, textShadow: '0 3px 8px #0006'}}>{text}</div>
  ) : null;

// 卖官 / 钱粮: a string of copper cash drops onto the place and swings.
const Coins: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const w = 300, h = 100;
  const k = easeOut(t / 0.45);
  const bounce = t > 0.45 && t < 0.8 ? Math.sin(((t - 0.45) / 0.35) * Math.PI) * 10 : 0;
  const x = clampX(p[0] - w / 2, w), y = clampY(p[1] - 150, h) - (1 - k) * 220 - bounce;
  return (
    <>
      <Img src={A('coins_string')} style={{position: 'absolute', left: x, top: y, width: w, height: h, opacity: smooth(t / 0.15),
                                          transform: `rotate(${Math.sin(t * 3.2) * 4 * Math.exp(-t * 0.6)}deg)`, transformOrigin: '50% 0', filter: 'drop-shadow(0 6px 8px #0006)'}} />
      <Tag x={x + w / 2} y={y - 8} text={el.text} op={smooth((t - 0.3) / 0.3)} color="#7a1f12" />
    </>
  );
};

// 狂风: painted wind swirls sweep across the place again and again.
const Wind: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const dir = el.dir === 'left' ? -1 : 1;
  const layers = [{f: 'wind_swirl_1', w: 520, dy: -90, life: 1.9, o: 0}, {f: 'wind_swirl_2', w: 440, dy: 40, life: 1.6, o: 0.6}, {f: 'wind_swirl_1', w: 380, dy: 140, life: 2.1, o: 1.1}];
  return (
    <>
      {layers.map((L, i) => {
        const ph = (((t + L.o) % L.life) + L.life) % L.life / L.life;
        const x = p[0] + dir * (-560 + ph * 1120) - L.w / 2;
        return <Img key={i} src={A(L.f)} style={{position: 'absolute', left: x, top: p[1] + L.dy - L.w / 4, width: L.w, height: L.w / 2, opacity: Math.sin(ph * Math.PI) * 0.9 * smooth(t / 0.3),
                                                 transform: `scaleX(${dir}) rotate(${Math.sin(t * 2 + i) * 3}deg)`}} />;
      })}
      <Tag x={p[0]} y={clampY(p[1] - 170, 0)} text={el.text} op={smooth(t / 0.4)} color="#3e5a6a" />
    </>
  );
};

// 诏书: the painted yellow-silk scroll unrolls (left → right, a roller riding the edge), then the words appear.
const Edict: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const open = easeOut((t - 0.1) / 0.75);
  const w = 540, h = 270;
  const x = Math.min(W - w - 40, Math.max(40, el.side === 'left' ? p[0] - w - 60 : p[0] + 60));
  const y = Math.min(H - h - 230, Math.max(120, p[1] - h / 2 - 40));
  const ink = smooth((t - 0.8) / 0.35);
  const text = el.text ?? '诏';
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, transform: `scale(${0.9 + 0.1 * easeOut(t / 0.3)})`, transformOrigin: '0 50%', filter: 'drop-shadow(0 8px 14px #0006)'}}>
      <div style={{position: 'absolute', inset: 0, clipPath: `inset(0 ${(1 - open) * 100}% 0 0)`}}>
        <Img src={A('scroll_blank')} style={{width: w, height: h, filter: 'saturate(0.8) brightness(0.97)'}} />
      </div>
      {open < 0.999 && <div style={{position: 'absolute', top: h * 0.07, height: h * 0.86, left: w * open - 9, width: 18, borderRadius: 9, background: 'linear-gradient(90deg,#3d2412,#7a4a26 45%,#3d2412)', opacity: 1 - smooth((open - 0.9) / 0.1)}} />}
      <div style={{position: 'absolute', inset: '0 12%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: ink}}>
        <div style={{fontFamily: 'StoryBrush', fontSize: text.length > 2 ? 54 : 78, color: '#8f2a1c', letterSpacing: 8, lineHeight: 1.1, transform: `scale(${1.15 - 0.15 * ink})`}}>{text}</div>
        {el.sub && <div style={{fontFamily: 'StorySerif', fontSize: 25, color: '#4a3220', marginTop: 8, letterSpacing: 4}}>{el.sub}</div>}
      </div>
    </div>
  );
};

// 下狱 / 押送: the prison cart rolls in and stops on the place.
const Prison: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const w = 300, h = 200;
  const k = easeOut(t / 0.7);
  const x = clampX(p[0] - w / 2, w) - (1 - k) * 260;
  const y = clampY(p[1] - h + 20, h) - (t < 0.7 ? Math.abs(Math.sin(t * 22)) * 4 : 0);
  return (
    <>
      <Img src={A('prison_cart')} style={{position: 'absolute', left: x, top: y, width: w, height: h, opacity: smooth(t / 0.2), filter: 'drop-shadow(0 8px 8px #0005)'}} />
      <Tag x={x + w / 2} y={y + 10} text={el.text} op={smooth((t - 0.5) / 0.3)} color="#120e0a" />
    </>
  );
};

// 信使 / 告密 / 送首级: a sealed letter travels from A to B leaving a dashed trail.
const Courier: React.FC<{el: ActEl; pts: Pt[]; sec: number; theme: Theme}> = ({el, pts, sec, theme}) => {
  const t = sec - el.start;
  const line = samplePath(pts, 0.12);
  const k = smooth(t / Math.max(0.8, el.grow ?? 1.6));
  const n = Math.max(1, Math.round(k * (line.length - 1)));
  const drawn = line.slice(0, n + 1);
  const tip = drawn[drawn.length - 1];
  const hop = Math.abs(Math.sin(t * 12)) * 6;
  const color = el.color ?? theme.red;
  return (
    <>
      <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        <path d={drawn.map((q, i) => `${i ? 'L' : 'M'}${q[0]} ${q[1]}`).join('')} fill="none" stroke={color} strokeWidth={3.5} strokeDasharray="3 9" strokeLinecap="round" />
      </svg>
      {/* the courier (驿骑) gallops along the trail, facing the way he rides */}
      <Img src={A('unit_courier')} style={{position: 'absolute', left: tip[0] - 44, top: tip[1] - 80 - hop, width: 88, height: 88, filter: 'drop-shadow(0 0 2px #f6ead0) drop-shadow(0 4px 5px #0006)',
                                           transform: `scaleX(${(pts[pts.length - 1][0] >= pts[0][0]) ? 1 : -1})`}} />
      <Tag x={tip[0]} y={tip[1] - 70 - hop} text={el.text} op={smooth(t / 0.3) * (1 - smooth((sec - el.end + 0.4) / 0.4))} color={color} size={30} />
    </>
  );
};

// 烽火响应: beacon towers rise one after another, a glow ring pulsing from each.
const Beacon: React.FC<{el: ActEl; pts: Pt[]; sec: number}> = ({el, pts, sec}) => {
  const t = sec - el.start;
  const step = el.step ?? 0.28;
  const color = el.color ?? '#e8a83a';
  return (
    <>
      {pts.map((q, i) => {
        const u = t - i * step;
        if (u < 0) return null;
        const ring = (u % 1.4) / 1.4;
        const pop = easeOut(u / 0.35);
        const w = 64, h = 96;
        return (
          <React.Fragment key={i}>
            <div style={{position: 'absolute', left: q[0] - 20 - ring * 60, top: q[1] - 20 - ring * 60, width: 40 + ring * 120, height: 40 + ring * 120, borderRadius: '50%',
                         border: `${4 * (1 - ring)}px solid ${color}`, opacity: 1 - ring}} />
            <Img src={A('beacon_tower')} style={{position: 'absolute', left: q[0] - w / 2, top: q[1] - h + 8, width: w, height: h, transform: `scale(${pop})`, transformOrigin: '50% 100%',
                                                 filter: `drop-shadow(0 0 ${6 + 6 * Math.sin(u * 8)}px ${color})`}} />
          </React.Fragment>
        );
      })}
      {pts.length > 0 && <Tag x={pts[0][0]} y={pts[0][1] - 100} text={el.text} op={smooth(t / 0.4)} color="#8a5a12" />}
    </>
  );
};

// 处斩 / 诛 / 车裂: a painted brush slash wipes in along its stroke, ink splashes out, the verb lands in
// brush script, the frame shakes. `tone: ink` (default, not gory) or `red` (for the few big killings).
const Execute: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const red = el.tone === 'red';
  const v = 1 + (Math.round(el.start * 10) % 3);          // one of the three strokes, varies per use
  const wipe = easeOut(t / 0.22);
  const burst = easeOut((t - 0.12) / 0.35);
  const drop = easeOut((t - 0.22) / 0.28);
  const shake = t < 0.45 ? Math.sin(t * 95) * 7 * (1 - t / 0.45) : 0;
  const SW = 440, SH = 220, SP = 360;
  // stay inside the safe area (a city near the frame edge would cut the stroke and the character off)
  const cx = Math.min(W - SW / 2 - 200, Math.max(SW / 2 + 40, p[0])), cy = Math.min(H - SH / 2 - 260, Math.max(SH / 2 + 160, p[1] - 40));
  return (
    <div style={{position: 'absolute', inset: 0, transform: `translate(${shake}px, ${shake * 0.4}px)`}}>
      <Img src={A(red ? 'splash_3' : 'splash_5')} style={{position: 'absolute', left: cx - SP / 2, top: cy - SP / 2, width: SP, height: SP, opacity: 0.85 * burst * (red ? 0.8 : 1), transform: `scale(${0.35 + 0.65 * burst})`}} />
      <div style={{position: 'absolute', left: cx - SW / 2, top: cy - SH / 2, width: SW, height: SH, clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)`}}>
        <Img src={A(`slash_${red ? 'red' : 'ink'}_${v}`)} style={{width: SW, height: SH}} />
      </div>
      {el.text && (
        <div style={{position: 'absolute', left: cx + SW * 0.32, top: cy - 150, fontFamily: 'StoryBrush', fontSize: el.text.length > 1 ? 66 : 96, lineHeight: 1,
                     color: red ? '#8f1f14' : '#1d1915', WebkitTextStroke: '2px #f3ead8', textShadow: '0 0 10px #f3ead8cc, 0 4px 10px #0005',
                     opacity: drop, transform: `scale(${1.7 - 0.7 * drop}) rotate(-6deg)`, transformOrigin: '0 100%', whiteSpace: 'nowrap'}}>{el.text}</div>
      )}
    </div>
  );
};

// 登基 / 称帝: the gold auspicious-cloud ring opens around the new ruler's portrait, turns slowly and glows.
const Enthrone: React.FC<{el: ActEl; sec: number}> = ({el, sec}) => {
  const t = sec - el.start;
  const k = easeOut(t / 0.7);
  const R = 480;
  const left = el.side === 'left' ? 120 : W - 120 - R;
  const top = 80;   // name plate must end above the minimap (bottom-right, y ≈ 675)
  const glow = 0.55 + 0.45 * Math.sin(t * 2.4);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at ${left + R / 2}px ${top + R / 2}px, #f6d78a40 0, #0000 ${R * 0.75}px)`, opacity: k}} />
      <div style={{position: 'absolute', left, top, width: R, height: R, transform: `scale(${0.6 + 0.4 * k})`}}>
        <div style={{position: 'absolute', inset: R * 0.13, borderRadius: '50%', overflow: 'hidden', background: 'radial-gradient(circle, #f7e7c0, #d9b876)', opacity: smooth((t - 0.15) / 0.4)}}>
          {el.image && <Img src={staticFile(el.image)} style={{position: 'absolute', left: '50%', top: '4%', width: '115%', transform: 'translateX(-50%)'}} />}
        </div>
        <Img src={A('frame_auspicious')} style={{position: 'absolute', inset: 0, width: R, height: R, transform: `rotate(${t * 6}deg)`, filter: `drop-shadow(0 0 ${10 + 18 * glow}px #f2c75acc)`}} />
      </div>
      {/* big line: the reign title (汉献帝); small line: personal name · note (刘协 · 九岁即位) */}
      <div style={{position: 'absolute', left: left + R * 0.12, width: R * 0.76, top: top + R - 6, textAlign: 'center', padding: '8px 0 10px', borderRadius: 10,
                   background: 'linear-gradient(#2a1d12e6, #1d140ce6)', border: '2px solid #c9a24a', boxShadow: '0 6px 16px #0007', opacity: smooth((t - 0.45) / 0.4)}}>
        <div style={{fontFamily: 'StoryBrush', fontSize: 60, color: '#f8e3a8', letterSpacing: 10, lineHeight: 1.15, textShadow: '0 0 12px #b8862b'}}>{el.title || el.name}</div>
        <div style={{fontFamily: 'StorySerif', fontSize: 24, color: '#e9d8b4', letterSpacing: 5}}>{[el.title ? el.name : null, el.text].filter(Boolean).join(' · ')}</div>
      </div>
    </div>
  );
};

// 驾崩: the world drains of colour, white mourning banners hang down, a dark band carries the verb.
const Mourn: React.FC<{el: ActEl; sec: number}> = ({el, sec}) => {
  const t = sec - el.start;
  const drop = easeOut((t - 0.3) / 0.8);
  return (
    <>
      <div style={{position: 'absolute', inset: 0, backdropFilter: `grayscale(${0.85 * smooth(t / 1.2)}) brightness(${1 - 0.18 * smooth(t / 1.2)})`}} />
      {[260, W - 380].map((x, i) => (
        <Img key={i} src={A('mourning_banner')} style={{position: 'absolute', left: x, top: -330 + drop * 300, width: 120, height: 320, opacity: drop,
                                                       transform: `rotate(${Math.sin(t * 1.6 + i * 2) * 3}deg)`, transformOrigin: '50% 0', filter: 'drop-shadow(0 6px 10px #0007)'}} />
      ))}
      <div style={{position: 'absolute', left: 0, right: 0, top: 430, height: 150, background: 'linear-gradient(90deg,#0000,#1a1714e8 20%,#1a1714e8 80%,#0000)', transform: `scaleX(${easeOut(t / 0.6)})`}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: 438, textAlign: 'center', fontFamily: 'StorySerif', fontWeight: 700, fontSize: 92, letterSpacing: 30, color: '#f4efe6', opacity: smooth((t - 0.4) / 0.5)}}>{el.text ?? '崩'}</div>
      {el.sub && <div style={{position: 'absolute', left: 0, right: 0, top: 545, textAlign: 'center', fontFamily: 'StorySerif', fontSize: 28, letterSpacing: 8, color: '#d8d0c4', opacity: smooth((t - 0.7) / 0.5)}}>{el.sub}</div>}
    </>
  );
};

// 箭雨 / 伏击: a volley of arrows arcs from A (or from the upper left) onto B and sticks there.
const Arrows: React.FC<{el: ActEl; pts: Pt[]; sec: number}> = ({el, pts, sec}) => {
  const t = sec - el.start;
  const to = pts[pts.length - 1];
  const from: Pt = pts.length > 1 ? pts[0] : [to[0] - 420, to[1] - 260];
  const N = el.n ?? 16;
  const out: React.ReactNode[] = [];
  for (let i = 0; i < N; i++) {
    const d0 = rnd(i) * 0.55;
    const k = clamp((t - d0) / 0.75);
    if (k <= 0) continue;
    const s: Pt = [from[0] + (rnd(i * 2.3) - 0.5) * 80, from[1] + (rnd(i * 3.1) - 0.5) * 60];
    const e: Pt = [to[0] + (rnd(i * 4.7) - 0.5) * 120, to[1] + (rnd(i * 5.9) - 0.5) * 60];
    const lift = 140 + rnd(i * 6.1) * 80;
    const x = s[0] + (e[0] - s[0]) * k;
    const y = s[1] + (e[1] - s[1]) * k - lift * 4 * k * (1 - k);
    const dx = e[0] - s[0], dy = e[1] - s[1] - lift * 4 * (1 - 2 * k);    // tangent of the arc
    const ang = (Math.atan2(dy, dx) * 180) / Math.PI;
    out.push(<Img key={i} src={A('arrow_single')} style={{position: 'absolute', left: x - 100, top: y - 13, width: 120, height: 30, transform: `rotate(${ang}deg)`, transformOrigin: '83% 50%'}} />);
  }
  return (
    <>
      {out}
      <Tag x={to[0]} y={to[1] - 70} text={el.text} op={smooth((t - 0.6) / 0.3)} color="#3a2a1a" />
    </>
  );
};

// 放牛马 / 惊群 (2026-10-20, 潼关之战 丁斐): oxen and loose horses stampede from A toward B and scatter as they go,
// each throwing up a little dust. Sprites (第9批) face right and are flipped when the herd runs left.
const HERD = ['ox_running', 'horse_loose_2', 'ox_running_2', 'horse_riderless'];
const Herd: React.FC<{el: ActEl; pts: Pt[]; sec: number}> = ({el, pts, sec}) => {
  const t = sec - el.start;
  const from = pts[0], to = pts[pts.length - 1];
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const L = Math.hypot(dx, dy) || 1;
  const nx = -dy / L, ny = dx / L;                       // across the run
  const flip = dx < 0 ? -1 : 1;
  const fade = presence(sec, el, 0.3, 0.6);
  const N = el.n ?? 10;
  const sz = (el.size ?? 1) * 66;
  const out: React.ReactNode[] = [];
  for (let i = 0; i < N; i++) {
    const d0 = rnd(i * 1.7) * 0.9;
    const T = 2.0 + rnd(i * 2.9) * 0.9;
    const k = easeOut(clamp((t - d0) / T));
    if (t < d0) continue;
    const spread = (rnd(i * 3.3) - 0.5) * (50 + 170 * k);    // the herd fans out as it runs
    const x = from[0] + dx * k * (0.85 + rnd(i * 4.1) * 0.3) + nx * spread;
    const y = from[1] + dy * k * (0.85 + rnd(i * 4.1) * 0.3) + ny * spread * 0.6 - Math.abs(Math.sin(t * 11 + i)) * 5 * (k < 1 ? 1 : 0);
    const moving = k < 0.999;
    if (moving) {
      const w = sz * (1.1 + rnd(i * 5.2) * 0.5);
      out.push(<Img key={'d' + i} src={A('dust_cloud_' + (1 + (i % 2)))} style={{position: 'absolute', left: x - flip * sz * 0.55 - w / 2, top: y + sz * 0.05, width: w, height: w / 2, opacity: 0.45 * fade}} />);
    }
    out.push(<Img key={'h' + i} src={A(HERD[i % HERD.length])} style={{position: 'absolute', left: x - sz / 2, top: y - sz * 0.8, width: sz, height: sz, opacity: fade,
      transform: `scaleX(${flip})`, filter: 'drop-shadow(0 0 2px #f6ead0) drop-shadow(0 0 1px #f6ead0)'}} />);
  }
  return (
    <>
      {out}
      <Tag x={from[0]} y={from[1] - sz - 20} text={el.text} op={smooth((t - 0.2) / 0.3) * fade} color="#3a2a1a" />
    </>
  );
};

// 浮桥 (2026-10-20, 潼关之战 夜渡渭水): boats with planks laid across the river one after another along `angle`
// (0 = east–west, 90 = north–south), `len` pixels long; it stays until the act ends. Segment art: 第8批 pontoon_segment.
const Pontoon: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p: at, sec}) => {
  const t = sec - el.start;
  const p: Pt = [at[0] + (el.offset?.[0] ?? 0), at[1] + (el.offset?.[1] ?? 0)];   // on the river beside the city
  const fade = presence(sec, el, 0.2, 0.6);
  const len = el.len ?? 170;
  const segW = (el.size ?? 1) * 74;                       // drawn width of one segment image (planks ≈ 55% of it)
  const step = segW * 0.5;
  const n = Math.max(2, Math.ceil(len / step));
  const out: React.ReactNode[] = [];
  for (let j = 0; j < n; j++) {
    const tj = t - j * 0.16;
    if (tj <= 0) continue;
    const pop = 0.6 + 0.4 * easeOut(clamp(tj / 0.35));
    const x = -len / 2 + step * (j + 0.5);
    out.push(<Img key={j} src={A('pontoon_segment')} style={{position: 'absolute', left: x - segW / 2, top: -segW / 4, width: segW, height: segW / 2,
      opacity: smooth(clamp(tj / 0.25)), transform: `scale(${pop})`}} />);
  }
  return (
    <>
      <div style={{position: 'absolute', left: p[0], top: p[1], width: 0, height: 0, transform: `rotate(${el.angle ?? 0}deg)`, opacity: fade,
                   filter: 'drop-shadow(0 1px 2px #0008)'}}>
        {out}
      </div>
      <Tag x={p[0]} y={p[1] - segW * 0.9} text={el.text} op={smooth((t - 0.4) / 0.3) * fade} color="#1e4a66" />
    </>
  );
};

// 水淹 / 决堤 / 灌城: water spreads over the place in a widening pool, waves heaving at its edge.
const Flood: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const R = (el.radius ?? 1) * 170 * easeOut(t / 1.6);
  const flow = t * 40;
  return (
    <>
      <div style={{position: 'absolute', left: p[0] - R, top: p[1] - R * 0.62, width: 2 * R, height: 1.24 * R, borderRadius: '50%',
                   background: `url(${A('flood_tile')}) ${flow}px ${flow * 0.3}px / 150px 150px repeat, rgba(64,108,138,0.45)`,
                   WebkitMaskImage: 'radial-gradient(ellipse at center, #000 55%, transparent 72%)', maskImage: 'radial-gradient(ellipse at center, #000 55%, transparent 72%)'}} />
      <Img src={A('wave_2')} style={{position: 'absolute', left: p[0] - R * 0.9, top: p[1] + R * 0.3 + Math.sin(t * 3) * 6, width: R * 1.8, height: R * 0.9, opacity: smooth((t - 0.4) / 0.5) * 0.95}} />
      <Tag x={p[0]} y={p[1] - R * 0.62 - 6} text={el.text} op={smooth((t - 0.6) / 0.4)} color="#1e4a66" />
    </>
  );
};

// 夜色 / 夜袭: the map darkens to night, a moon rises in the corner, ink clouds drift across it.
const Night: React.FC<{el: ActEl; sec: number; pts?: Pt[]}> = ({el, sec, pts}) => {
  const t = sec - el.start;
  const k = smooth(t / 0.9);
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 55%, rgba(12,20,44,0.35), rgba(6,10,26,0.72))', opacity: k}} />
      <Img src={A('moon')} style={{position: 'absolute', left: W - 360, top: 150 - 40 * k, width: 170, height: 170, opacity: k, filter: 'drop-shadow(0 0 30px #f6e3a0aa)'}} />
      <Img src={A('cloud_ink_2')} style={{position: 'absolute', left: W - 560 + t * 22, top: 190, width: 420, height: 210, opacity: 0.55 * k}} />
      {el.text && <Tag x={W - 275} y={110} text={el.text} op={smooth((t - 0.5) / 0.4)} color="#16203a" size={36} />}
      {/* torches at the given places (夜袭、举火) */}
      {(pts ?? []).map((q, i) => (
        <Img key={i} src={A('torch')} style={{position: 'absolute', left: q[0] - 16, top: q[1] - 92, width: 32, height: 64 * 1.0, opacity: smooth((t - 0.4 - i * 0.2) / 0.3),
                                             transform: `scaleY(${0.95 + 0.05 * Math.sin(t * 13 + i)})`, transformOrigin: '50% 100%', filter: `drop-shadow(0 0 ${10 + 5 * Math.sin(t * 9 + i)}px #ffb347)`}} />
      ))}
    </>
  );
};

// 雷 / 天象异变: a dark cloud gathers over the place, lightning strikes twice, the screen flashes.
const Thunder: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const strike = (a: number) => Math.max(0, 1 - Math.abs(t - a) / 0.09);
  const flash = Math.max(strike(0.45), strike(0.8) * 0.7);
  return (
    <>
      <Img src={A('cloud_ink_1')} style={{position: 'absolute', left: p[0] - 260, top: clampY(p[1] - 330, 0), width: 520, height: 260, opacity: smooth(t / 0.4) * 0.85}} />
      <Img src={A('lightning')} style={{position: 'absolute', left: p[0] - 70, top: clampY(p[1] - 240, 0), width: 140, height: 280, opacity: flash, filter: 'drop-shadow(0 0 18px #fff6c8)'}} />
      <div style={{position: 'absolute', inset: 0, background: '#fffbe8', opacity: flash * 0.35}} />
      <Tag x={p[0]} y={clampY(p[1] - 330, 0)} text={el.text} op={smooth((t - 0.5) / 0.3)} color="#2a2a3a" />
    </>
  );
};

// 投石车 / 霹雳车: the catapult at A hurls stones that arc onto B and burst into dust.
const Catapult: React.FC<{el: ActEl; pts: Pt[]; sec: number}> = ({el, pts, sec}) => {
  const t = sec - el.start;
  const [a, b] = pts;
  const w = 190, h = 127;
  const shots = [0.3, 1.3, 2.3].filter((s) => s < el.end - el.start - 0.4);
  return (
    <>
      <Img src={A('catapult')} style={{position: 'absolute', left: a[0] - w / 2, top: a[1] - h + 10, width: w, height: h, opacity: smooth(t / 0.3), transform: `scaleX(${b[0] < a[0] ? -1 : 1})`}} />
      {shots.map((s0, i) => {
        const k = clamp((t - s0) / 0.9);
        const hit = t - s0 - 0.9;
        const x = a[0] + (b[0] - a[0]) * k, y = a[1] - h * 0.8 + (b[1] - a[1] + h * 0.8) * k - 220 * 4 * k * (1 - k);
        return (
          <React.Fragment key={i}>
            {k > 0 && k < 1 && <Img src={A('stone_boulder')} style={{position: 'absolute', left: x - 22, top: y - 22, width: 44, height: 44, transform: `rotate(${k * 540}deg)`}} />}
            {hit > 0 && hit < 1.2 && <Img src={A('smoke_3')} style={{position: 'absolute', left: b[0] - 90, top: b[1] - 150 - hit * 30, width: 180, height: 180, opacity: 1 - hit / 1.2, transform: `scale(${0.5 + hit * 0.6})`}} />}
          </React.Fragment>
        );
      })}
      <Tag x={a[0]} y={a[1] - h - 4} text={el.text} op={smooth((t - 0.2) / 0.3)} color="#4a2a12" />
    </>
  );
};

// 蝗灾: a swarm of locusts crosses the place, the air going brown.
const Locusts: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const k = smooth(t / 0.6);
  const bugs: React.ReactNode[] = [];
  for (let i = 0; i < 42; i++) {
    const life = 2.2 + rnd(i) * 1.2;
    const ph = ((t + rnd(i * 2.7) * life) % life) / life;
    const x = p[0] - 520 + ph * 1040 + Math.sin(t * 5 + i) * 18;
    const y = p[1] - 170 + rnd(i * 4.4) * 300 + Math.sin(t * 7 + i * 1.7) * 14;
    const s = 26 + rnd(i * 6.6) * 22;
    bugs.push(<Img key={i} src={A('locust')} style={{position: 'absolute', left: x - s / 2, top: y - s / 2, width: s, height: s, opacity: Math.sin(ph * Math.PI) * k,
                                                     transform: `rotate(${90 + Math.sin(t * 9 + i) * 20}deg)`}} />);
  }
  return (
    <>
      <div style={{position: 'absolute', left: p[0] - 560, top: p[1] - 230, width: 1120, height: 420, borderRadius: '50%', background: 'radial-gradient(ellipse, rgba(120,92,40,0.28), transparent 70%)', opacity: k}} />
      {bugs}
      <Tag x={p[0]} y={p[1] - 190} text={el.text} op={smooth((t - 0.4) / 0.3)} color="#5a4012" />
    </>
  );
};

// 城陷 / 城破: a broken wall drops onto the city with a jolt, smoke rising behind it.
const Fall: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const w = 250, h = 125;
  const k = easeOut(t / 0.3);
  const shake = t < 0.5 ? Math.sin(t * 80) * 6 * (1 - t / 0.5) : 0;
  return (
    <div style={{position: 'absolute', inset: 0, transform: `translate(${shake}px, 0)`}}>
      {['smoke_1', 'smoke_2'].map((s, i) => {
        const u = t - 0.2 - i * 0.3;
        return u > 0 ? <Img key={s} src={A(s)} style={{position: 'absolute', left: p[0] - 90 + i * 60, top: p[1] - 230 - u * 25, width: 160, height: 160, opacity: smooth(u / 0.5) * 0.85}} /> : null;
      })}
      <Img src={A('wall_broken')} style={{position: 'absolute', left: p[0] - w / 2, top: p[1] - h + 15 - (1 - k) * 120, width: w, height: h, opacity: smooth(t / 0.15), filter: 'drop-shadow(0 6px 8px #0006)'}} />
      <Tag x={p[0]} y={p[1] - h - 10} text={el.text} op={smooth((t - 0.3) / 0.3)} color="#5a2a12" />
    </div>
  );
};

// 流民 / 迁都驱民: a column of refugees trudges from A to B.
const Refugees: React.FC<{el: ActEl; pts: Pt[]; sec: number}> = ({el, pts, sec}) => {
  const t = sec - el.start;
  const [a, b] = pts;
  const k = smooth(t / Math.max(1.5, el.grow ?? (el.end - el.start) * 0.9));
  const w = 330, h = 124;
  const x = a[0] + (b[0] - a[0]) * k, y = a[1] + (b[1] - a[1]) * k;
  return (
    <>
      <Img src={A('refugees_line')} style={{position: 'absolute', left: x - w / 2, top: y - h + 10 + Math.sin(t * 6) * 2, width: w, height: h, opacity: smooth(t / 0.4) * 0.92,
                                            transform: `scaleX(${b[0] < a[0] ? -1 : 1})`}} />
      <Tag x={x} y={y - h} text={el.text} op={smooth((t - 0.3) / 0.3)} color="#3a2a1a" size={32} />
    </>
  );
};

// 器物: a painted object pops up on the place with a gold glow (传国玉玺、虎符、冕冠、粮仓…).
const PROPS: Record<string, string> = {玉玺: 'jade_seal', 传国玉玺: 'jade_seal', 虎符: 'tiger_tally', 兵符: 'tiger_tally', 冕冠: 'crown_mian', 冠冕: 'crown_mian',
  铜钱: 'coins_string', 粮仓: 'grain_pile', 粮草: 'grain_pile', 书信: 'letter_scroll', 密信: 'letter_scroll', 竹简: 'bamboo_slips', 城门: 'city_gate_closed',
  楼船: 'warship_tower', 战船: 'warship_tower', 小船: 'boat_small', 烽火台: 'beacon_tower', 囚车: 'prison_cart', 投石车: 'catapult', 断墙: 'wall_broken',
  营寨: 'camp_tents', 军营: 'camp_tents', 城池: 'city_walled', 宫殿: 'palace', 皇宫: 'palace', 关隘: 'pass_gate', 关: 'pass_gate', 桥: 'bridge', 木桥: 'bridge',
  帝陵: 'tomb_mound', 陵墓: 'tomb_mound', 会盟坛: 'altar', 盟坛: 'altar', 宴饮: 'banquet', 酒宴: 'banquet', 酒瓮: 'wine_jar', 御座: 'throne', 爵: 'jue_cup',
  战鼓: 'war_drum', 火把: 'torch', 箭: 'arrow_bundle', 惊马: 'horse_riderless',
  剑: 'sword_jian', 佩剑: 'sword_jian', 朝履: 'court_shoes', 鞋: 'court_shoes', 节: 'jie_staff', 符节: 'jie_staff', 印绶: 'yinshou', 官印: 'yinshou',
  赤帻: 'red_headscarf', 头巾: 'red_headscarf', 望楼: 'watchtower', 楼橹: 'watchtower', 蜜水碗: 'honey_bowl', 蜜水: 'honey_bowl', 衣带诏: 'belt_edict',
  草庐: 'thatched_cottage', 茅庐: 'thatched_cottage', 马车: 'horse_cart', 车驾: 'horse_cart',
  手戟: 'shou_ji', 戟: 'shou_ji', 绳索: 'rope_bound', 缚绳: 'rope_bound', 粮车: 'grain_cart', 辎重: 'grain_cart',
  幡: 'banner_tall_blank', 旗: 'banner_tall_blank', 旗帜: 'banner_tall_blank', 驺虞幡: 'banner_tall_blank'};
// long or tall items keep their own aspect instead of the square box
const PROP_BOX: Record<string, [number, number]> = {sword_jian: [2.4, 0.8], jie_staff: [0.5, 2.0], belt_edict: [2.0, 1.0], horse_cart: [2.0, 1.0], grain_cart: [2.0, 1.0], shou_ji: [1.33, 1.0], rope_bound: [1.33, 1.0], thatched_cottage: [1.5, 1.0], watchtower: [0.9, 1.35]};
const Prop: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const file = PROPS[el.item ?? ''] ?? el.item ?? 'jade_seal';
  const s = 170 * (el.size ?? 1);
  const [bw, bh] = PROP_BOX[file] ?? [1, 1];
  const w = s * bw, h = s * bh;
  const pop = easeOut(t / 0.4);
  const over = t < 0.55 ? Math.sin(clamp((t - 0.25) / 0.3) * Math.PI) * 0.12 : 0;
  const x = clampX(p[0] - w / 2, w), y = clampY(p[1] - h - 20, h);
  const glow = 0.6 + 0.4 * Math.sin(t * 3);
  const g = Math.max(w, h);
  return (
    <>
      <div style={{position: 'absolute', left: x + w / 2 - g * 0.75, top: y + h / 2 - g * 0.75, width: g * 1.5, height: g * 1.5, borderRadius: '50%', background: 'radial-gradient(circle, #f6d98a66, transparent 65%)', opacity: pop * glow}} />
      <Img src={A(file)} style={{position: 'absolute', left: x, top: y, width: w, height: h, objectFit: 'contain', transform: `scale(${pop + over})`, transformOrigin: '50% 100%', filter: 'drop-shadow(0 6px 10px #0007)'}} />
      <Tag x={x + w / 2} y={y + h + 46} text={el.text ?? el.item} op={smooth((t - 0.35) / 0.3)} color="#6a4a12" size={36} />
    </>
  );
};

// 剑履上殿: centre stage over a dimmed map — the palace hall faintly behind, the sword slides in and lands,
// then the court shoes stride in after it, step by step; the four characters seal the moment.
const JianLv: React.FC<{el: ActEl; sec: number}> = ({el, sec}) => {
  const t = sec - el.start;
  const k = el.size ?? 1;
  const sw = 760 * k, sh = sw / 3, shw = 380 * k, shh = shw * 0.75;
  const cx = W / 2, cy = 470;
  const a = easeOut(t / 0.6);                                 // sword: slides from the left and drops
  const land = t > 0.6 && t < 0.85 ? Math.sin(((t - 0.6) / 0.25) * Math.PI) * 8 : 0;
  const steps = clamp((t - 1.0) / 1.3);                       // shoes: three strides in from the right
  const stride = Math.floor(steps * 3) + smooth((steps * 3) % 1);
  const lift = steps > 0 && steps < 1 ? Math.abs(Math.sin(steps * 3 * Math.PI)) * 22 : 0;
  const shx = cx + 60 * k + (3 - Math.min(3, stride)) * 170 * k;
  const glow = smooth((t - 2.3) / 0.5);
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 48%, rgba(30,22,16,.8), rgba(12,9,7,.92))', opacity: smooth(t / 0.4)}} />
      <Img src={A('palace')} style={{position: 'absolute', left: cx - 520, top: 90, width: 1040, height: 620, objectFit: 'contain', opacity: 0.22 * smooth(t / 0.6), filter: 'sepia(0.5) blur(1px)'}} />
      <div style={{position: 'absolute', left: cx - 620, top: cy + 30, width: 1240, height: 200, borderRadius: '50%', background: 'radial-gradient(ellipse, #f6d98a40, transparent 70%)', opacity: smooth(t / 0.5)}} />
      <Img src={A('sword_jian')} style={{position: 'absolute', left: cx - sw / 2 - (1 - a) * 520, top: cy - sh - (1 - a) * 140 + land, width: sw, height: sh, opacity: smooth(t / 0.25),
                                         transform: `rotate(${(1 - a) * -14}deg)`, filter: 'drop-shadow(0 12px 14px #000a)'}} />
      {t > 1.0 && <Img src={A('court_shoes')} style={{position: 'absolute', left: shx - shw / 2, top: cy + sh * 0.05 - lift, width: shw, height: shh, opacity: smooth((t - 1.0) / 0.25),
                                                    filter: `drop-shadow(0 ${8 + lift / 2}px 10px #000a) drop-shadow(0 0 ${16 * glow}px #f6d98a)`}} />}
      <Tag x={cx} y={cy + sh * 0.05 + shh + 110} text={el.text ?? '剑履上殿'} op={smooth((t - 2.1) / 0.4)} color="#6a1a12" size={84} />
    </>
  );
};

// 疑兵计: centre stage, a walled city. Night: a few riders slip out of the gate to the left, quietly;
// day: a bigger column with banners rides back in, drums and dust. Repeats `n` times (default 2) over the act.
const Feint: React.FC<{el: ActEl; sec: number; theme: Theme}> = ({el, sec, theme}) => {
  const t = sec - el.start;
  const dur = el.end - el.start;
  const n = el.n ?? 2;
  const cyc = dur / n;
  const k = Math.min(n - 1, Math.floor(t / cyc));
  const u = (t - k * cyc) / cyc;                    // 0–0.5 night (out), 0.5–1 day (in)
  const night = u < 0.5;
  const v = night ? u / 0.5 : (u - 0.5) / 0.5;
  const dark = night ? smooth(clamp(u / 0.08)) * (1 - smooth(clamp((u - 0.44) / 0.06))) : 0;
  const cx = W / 2 + 150, cy = 470, gateX = cx - 250, gateY = cy + 90;
  const riders = night ? 4 : 9;
  const color = el.color ?? theme.red;
  const rows = Array.from({length: riders}, (_, i) => i);
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 50%, rgba(40,30,20,.55), rgba(14,10,8,.86))', opacity: smooth(t / 0.4)}} />
      <Img src={A('city_walled')} style={{position: 'absolute', left: cx - 300, top: cy - 280, width: 600, height: 450, objectFit: 'contain', filter: 'drop-shadow(0 10px 18px #000a)'}} />
      <div style={{position: 'absolute', inset: 0, background: 'rgba(8,14,36,.62)', opacity: dark}} />
      {night && <Img src={A('moon')} style={{position: 'absolute', left: cx + 230, top: 120, width: 140, height: 140, opacity: dark, filter: 'drop-shadow(0 0 26px #f6e3a0aa)'}} />}
      {rows.map((i) => {
        // night: leave the gate leftward one by one; day: enter from the left toward the gate, in ranks
        const lag = i * (night ? 0.12 : 0.06);
        const q = clamp((v - lag) / (night ? 0.55 : 0.6));
        const row = i % 3, col = Math.floor(i / 3);
        const x = night ? gateX - q * 620 - row * 30 : gateX - 640 + q * 600 - col * 70;
        const y = gateY - 10 + row * 46 + (night ? 0 : col * 6);
        const op = night ? smooth(clamp(q / 0.15)) * (1 - smooth(clamp((q - 0.75) / 0.25))) * 0.75 : smooth(clamp(q / 0.1)) * (1 - smooth(clamp((q - 0.9) / 0.1)));
        const bob = Math.sin((t + i) * 14) * 2;
        return (
          <div key={i} style={{position: 'absolute', left: x - 60, top: y - 90 + bob, width: 120, height: 120, opacity: op, transform: night ? 'scaleX(-1)' : undefined}}>
            <div style={{position: 'absolute', left: 30, top: 96, width: 60, height: 14, borderRadius: '50%', background: color, opacity: 0.55}} />
            <Img src={A('unit_cavalry')} style={{width: 120, height: 120, filter: night ? 'brightness(0.55) saturate(0.6)' : 'drop-shadow(0 4px 4px #0008)'}} />
            {!night && i % 3 === 0 && (
              <svg width={60} height={90} style={{position: 'absolute', left: 58, top: -52}}>
                <path d="M6 88V4" stroke="#6b4a22" strokeWidth={4} />
                <path d="M8 6H50L44 22L50 38H8Z" fill={color} stroke="#f2d79a" strokeWidth={2} />
                <text x={28} y={30} textAnchor="middle" fontSize={22} fill="#fff3d8" fontFamily="StoryBrush">{el.sub ?? '董'}</text>
              </svg>
            )}
          </div>
        );
      })}
      {!night && <Img src={A('dust_cloud_1')} style={{position: 'absolute', left: gateX - 760 + v * 560, top: gateY - 60, width: 420, height: 180, opacity: 0.5 * Math.sin(Math.PI * clamp(v)), transform: 'scaleX(-1)'}} />}
      <Tag x={W / 2} y={190} text={night ? '夜 · 悄悄出城' : '昼 · 大张旗鼓入城'} op={smooth(clamp(v / 0.2)) * (1 - smooth(clamp((v - 0.9) / 0.1)))} color={night ? '#16203a' : '#6a1a12'} size={50} />
      {el.text && <Tag x={W / 2} y={880} text={`${el.text}${n > 1 ? ` · 第${'一二三四'[k]}回` : ''}`} op={smooth(t / 0.5)} color="#3a2a1a" size={34} />}
    </>
  );
};

// 墨晕转场: two ink washes bloom from the sides and cover the frame, the words hold, then the ink clears.
const InkWash: React.FC<{el: ActEl; sec: number}> = ({el, sec}) => {
  const t = sec - el.start;
  const dur = el.end - el.start;
  const grow = easeOut(t / 0.7);
  const clear = smooth((t - (dur - 0.8)) / 0.8);
  const op = (1 - clear) * smooth(t / 0.2);
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: '#efe6d4', opacity: 0.55 * grow * (1 - clear)}} />
      <Img src={A('ink_wash_1')} style={{position: 'absolute', left: -300, top: 120, width: 1500, height: 750, opacity: op, transform: `scale(${0.5 + 0.9 * grow}) translateX(${(1 - grow) * -300}px)`, transformOrigin: '0 50%'}} />
      <Img src={A('ink_wash_2')} style={{position: 'absolute', left: W - 1200, top: 160, width: 1500, height: 750, opacity: op, transform: `scale(${0.5 + 0.9 * grow}) translateX(${(1 - grow) * 300}px)`, transformOrigin: '100% 50%'}} />
      {el.text && <div style={{position: 'absolute', left: 0, right: 0, top: 440, textAlign: 'center', fontFamily: 'StoryBrush', fontSize: 104, letterSpacing: 18, color: '#f8efdc',
                                textShadow: '0 0 20px #000a', opacity: smooth((t - 0.45) / 0.35) * (1 - clear)}}>{el.text}</div>}
      {el.sub && <div style={{position: 'absolute', left: 0, right: 0, top: 580, textAlign: 'center', fontFamily: 'StorySerif', fontSize: 30, letterSpacing: 8, color: '#efe3c8',
                               textShadow: '0 0 12px #000c', opacity: smooth((t - 0.7) / 0.35) * (1 - clear)}}>{el.sub}</div>}
    </>
  );
};

// 屯田: fields around the place turn from bare earth to green, plot by plot.
const Farm: React.FC<{el: ActEl; p: Pt; sec: number}> = ({el, p, sec}) => {
  const t = sec - el.start;
  const s = 64;
  const plots: React.ReactNode[] = [];
  const order = [4, 1, 5, 7, 3, 0, 2, 8, 6];     // spread out from the middle
  order.forEach((cell, k) => {
    const r = Math.floor(cell / 3) - 1, c = (cell % 3) - 1;
    const u = clamp((t - 0.15 - k * 0.22) / 0.5);
    if (u <= 0) return;
    plots.push(<Img key={cell} src={A('field_tile')} style={{position: 'absolute', left: p[0] + c * (s + 6) - s / 2, top: p[1] + 30 + r * (s * 0.62 + 4) - s * 0.31, width: s, height: s * 0.62, objectFit: 'cover',
                                                                borderRadius: 4, opacity: easeOut(u), filter: `sepia(${1 - u}) saturate(${0.4 + 0.6 * u})`, boxShadow: '0 2px 4px #0004'}} />);
  });
  return (
    <>
      {plots}
      <Tag x={p[0]} y={p[1] - 22} text={el.text} op={smooth((t - 0.3) / 0.3)} color="#3a5a1a" />
    </>
  );
};

export const ActMark: React.FC<{el: ActEl; pts: Pt[]; sec: number; theme: Theme}> = ({el, pts, sec, theme}) => {
  const op = presence(sec, el, 0.2, 0.45);
  if (!op) return null;
  const p = pts[0];
  const body =
    el.act === 'mourn' ? <Mourn el={el} sec={sec} /> :
    el.act === 'night' ? <Night el={el} sec={sec} pts={pts} /> :
    el.act === 'inkwash' ? <InkWash el={el} sec={sec} /> :
    el.act === 'farm' ? <Farm el={el} p={p} sec={sec} /> :
    el.act === 'enthrone' ? <Enthrone el={el} sec={sec} /> :
    el.act === 'execute' ? <Execute el={el} p={p} sec={sec} /> :
    el.act === 'edict' ? <Edict el={el} p={p} sec={sec} /> :
    el.act === 'coins' ? <Coins el={el} p={p} sec={sec} /> :
    el.act === 'wind' ? <Wind el={el} p={p} sec={sec} /> :
    el.act === 'prison' ? <Prison el={el} p={p} sec={sec} /> :
    el.act === 'courier' ? <Courier el={el} pts={pts} sec={sec} theme={theme} /> :
    el.act === 'beacon' ? <Beacon el={el} pts={pts} sec={sec} /> :
    el.act === 'arrows' ? <Arrows el={el} pts={pts} sec={sec} /> :
    el.act === 'herd' ? <Herd el={el} pts={pts} sec={sec} /> :
    el.act === 'pontoon' ? <Pontoon el={el} p={p} sec={sec} /> :
    el.act === 'flood' ? <Flood el={el} p={p} sec={sec} /> :
    el.act === 'thunder' ? <Thunder el={el} p={p} sec={sec} /> :
    el.act === 'catapult' ? <Catapult el={el} pts={pts} sec={sec} /> :
    el.act === 'locusts' ? <Locusts el={el} p={p} sec={sec} /> :
    el.act === 'fall' ? <Fall el={el} p={p} sec={sec} /> :
    el.act === 'refugees' ? <Refugees el={el} pts={pts} sec={sec} /> :
    el.act === 'prop' ? <Prop el={el} p={p} sec={sec} /> :
    el.act === 'jianlv' ? <JianLv el={el} sec={sec} /> :
    el.act === 'feint' ? <Feint el={el} sec={sec} theme={theme} /> : null;
  return <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: op}}>{body}</div>;
};
