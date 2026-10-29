import React from 'react';
import {AbsoluteFill, Audio, continueRender, delayRender, Img, prefetch, staticFile, useCurrentFrame} from 'remotion';
import {cameraAt, presence, type Pt} from './anim';
import {ArrowMark, BattleMark, CardMark, CityMark, FlagMark, CampMark, GarrisonMark, TrailMark, flagSlots, labelBox, StampMark, CITY_RANKS, CLOSE_KM, iconSize, rankAt, type LabelMode} from './Marks';
import {TerritoryFill, TerritoryLabels, stateIndex} from './Territory';
import {ClashMark} from './Army';
import {Enter, ExitPortrait, PersonCard, SpeechBrush, Versus} from './People';
import {AllianceMark, CaptureMark, ReplayMark, SiegeMark, SpotMark} from './Actions';
import {FactionBars, QuoteCard, TitleBar} from './Events';
import {FireFlash, FireMark, fireFlashK} from './Fire';
import {ActMark, ANIM_FILES} from './Acts';
import {Stage} from './Stage';
import {Forces, YearScroll} from './Motion';
import {TacticMark} from './Tactic';
import {Vignette} from './Vignette';
import {AtlasChapterBar, AtlasFeatures, AtlasTopBar} from './Atlas';
import {CaptionBar, Footer, Headline, Legend, PhaseChip, Portrait, TitleBlock, YearBadge, YearFlip, MiniMap} from './Overlays';
import type {Episode as EpisodeT, Place} from './types';

// mapOnly: just the basemap, territory, polity names and cities at this frame — a clean background for covers.
export const EpisodeView: React.FC<{episode: EpisodeT | null; mapOnly?: boolean}> = ({episode: ep, mapOnly}) => {
  const frame = useCurrentFrame();
  // Painted sprites inside SVG (<image>: soldiers, dust) are not awaited by Remotion: load them all before any frame.
  const [animHandle] = React.useState(() => delayRender('painted assets'));
  React.useEffect(() => {
    let left = ANIM_FILES.length;
    const done = () => { if (--left <= 0) continueRender(animHandle); };
    ANIM_FILES.forEach((f) => { const im = new Image(); im.onload = done; im.onerror = done; im.src = staticFile(f); });
  }, [animHandle]);
  // Preload the basemap and every portrait once, so cut-ins never pop in late in the preview.
  React.useEffect(() => {
    if (!ep) return;
    const srcs = new Set<string>();
    if (ep.map.raster) srcs.add(ep.map.raster.src);
    for (const e of ep.elements as {image?: string | null}[]) if (e.image) srcs.add(e.image);
    for (const e of ep.elements) if (e.type === 'forces') { if (e.left.image) srcs.add(e.left.image); if (e.right.image) srcs.add(e.right.image); }
    for (const e of ep.elements) if (e.type === 'stage') { e.actors.forEach((a) => a.image && srcs.add(a.image)); if (e.image) srcs.add(e.image); }
    if (ep.elements.some((e) => e.type === 'act' || e.type === 'fire' || e.type === 'stamp')) ANIM_FILES.forEach((f) => srcs.add(f));
    const handles = [...srcs].map((s) => prefetch(staticFile(s)));
    return () => handles.forEach((h) => h.free());
  }, [ep]);
  if (!ep) return <AbsoluteFill style={{background: '#222', color: '#eee', fontSize: 40, padding: 80}}>episode.json 未加载</AbsoluteFill>;
  const sec = frame / ep.fps;
  const cam = cameraAt(ep.camera, sec);
  const byId = new Map<string, Place>(ep.places.map((p) => [p.id, p]));
  const screen = (id: string): Pt => {
    const p = byId.get(id)!;
    return [ep.width / 2 + (p.x - cam.cx) * cam.z, ep.height / 2 + (p.y - cam.cy) * cam.z];
  };
  const t = ep.theme;
  const atlas = t.look === 'atlas';
  const els = ep.elements;
  const regions = new Map(ep.map.regions.map((r) => [r.id, r]));
  // city icons (第12批): battle close-up or wide view, the rank at this moment, and who holds the place now
  const close = (ep.map.km ?? 0) * cam.z >= CLOSE_KM;
  const cityOf = new Map(els.flatMap((e) => (e.type === 'city' ? [[e.place, e] as const] : [])));
  const ts = ep.territory ? stateIndex(ep.territory, sec) : -1;
  const holderOf = (place: string) => (ts >= 0 ? ep.territory!.states[ts].places?.[place] ?? null : null);
  const holderColor = (place: string) => {
    const h = holderOf(place);
    return h ? ep.territory!.polities[h]?.flag ?? null : null;
  };
  const sizeOf = (place: string) => iconSize(rankAt(cityOf.get(place), byId.get(place)!, sec).tier, close);
  // a unit in a city its side holds is a garrison (medallion); elsewhere tents, which only a close-up shows
  const garrisonSlot = new Map<number, number>();
  const perCity = new Map<string, number>();
  els.forEach((e, i) => {
    if (e.type !== 'camp' || sec < e.start - 0.5 || sec > e.end + 0.6) return;
    const tier = rankAt(cityOf.get(e.place), byId.get(e.place)!, sec).tier;
    const h = holderOf(e.place);
    if (CITY_RANKS.includes(tier) && (!h || !e.faction || h === e.faction || !ep.territory!.polities[e.faction])) {
      const k = perCity.get(e.place) ?? 0;
      garrisonSlot.set(i, k);
      perCity.set(e.place, k + 1);
    }
  });

  // Greedy label placement: active cities first, then capitals, then the rest.
  // A label that would collide drops its detail line, then its text (dot stays).
  // Detail lines only appear at theatre zoom or while the city is in focus.
  // the story's places (world coords), kept clear of the pinned polity names
  const marks = els.flatMap((e) => (e.type === 'city' ? [[byId.get(e.place)!.x, byId.get(e.place)!.y] as [number, number]] : []));
  const modes = new Map<number, LabelMode>();
  const placed: {x: number; y: number; w: number; h: number}[] = [];
  const hit = (b: {x: number; y: number; w: number; h: number}) => placed.some((q) => b.x < q.x + q.w && q.x < b.x + b.w && b.y < q.y + q.h && q.y < b.y + b.h);
  const rank = (i: number) => {
    const e = els[i];
    if (e.type !== 'city') return 9;
    const active = e.active.some(([a, b]) => sec >= a && sec <= b);
    return active ? 0 : byId.get(e.place)!.tier === 'capital' ? 1 : 2;
  };
  els.map((_, i) => i).filter((i) => els[i].type === 'city').sort((a, b) => rank(a) - rank(b)).forEach((i) => {
    const e = els[i];
    if (e.type !== 'city') return;
    const pl = byId.get(e.place)!, p = screen(e.place);
    const wantDetail = cam.z >= 1.2 || rank(i) === 0;
    for (const m of (wantDetail ? ['full', 'name'] : ['name']) as LabelMode[]) {
      const b = labelBox(e, pl, p, m === 'full', sizeOf(e.place));
      if (!hit(b)) {
        placed.push(b);
        modes.set(i, m);
        return;
      }
    }
    modes.set(i, 'none');
  });

  // Flags pick a slot once, at their entrance (camera and other flags as they
  // are then), and keep that slot for their whole life so nothing jumps later.
  const at = (id: string, c: {cx: number; cy: number; z: number}): Pt => {
    const p = byId.get(id)!;
    return [ep.width / 2 + (p.x - c.cx) * c.z, ep.height / 2 + (p.y - c.cy) * c.z];
  };
  const flags = els.map((_, i) => i).filter((i) => els[i].type === 'flag').sort((a, b) => els[a].start - els[b].start);
  const slotOf = new Map<number, number>();
  for (const i of flags) {
    const e = els[i];
    if (e.type !== 'flag') continue;
    const c = cameraAt(ep.camera, e.start);
    const taken = flags.filter((j) => slotOf.has(j) && els[j].end > e.start).map((j) => {
      const f = els[j];
      return f.type === 'flag' ? flagSlots(at(f.place, c), f.side)[slotOf.get(j)!] : null;
    }).filter((b): b is NonNullable<typeof b> => !!b);
    const slots = flagSlots(at(e.place, c), e.side);
    const k = slots.findIndex((b) => !taken.some((q) => b.x < q.x + q.w && q.x < b.x + b.w && b.y < q.y + q.h && q.y < b.y + b.h));
    slotOf.set(i, Math.max(0, k));
  }
  const flagPos = new Map(flags.map((i) => {
    const e = els[i];
    return [i, e.type === 'flag' ? flagSlots(screen(e.place), e.side)[slotOf.get(i)!] : undefined] as const;
  }));
  // Clashes shake the frame: a hard jolt when the armies meet, then a tremor while they fight.
  let shake = 0;
  for (const c of els) {
    if (c.type !== 'clash' || sec < c.start) continue;
    const dt = sec - c.start;
    const fighting = c.loser_at == null || sec < c.loser_at;
    shake += 9 * Math.exp(-dt * 5) + (fighting && sec < c.end ? 1.4 : 0);
  }
  // Fire attacks: a strong jolt at the full-screen burst.
  let flashK = 0;
  for (const f of els) {
    if (f.type !== 'fire') continue;
    const k = fireFlashK(f, sec);
    flashK = Math.max(flashK, k);
    shake += 7 * k;
  }
  // on a dialogue stage the minimap hides; a line already written out in brush script (no 原文) needs no caption below
  const onStage = els.some((e) => e.type === 'stage' && sec > e.start + 0.4 && sec < e.end - 0.4);
  const brushed = els.flatMap((e) => (e.type === 'stage' ? e.lines.filter((l) => !l.original) : []));
  const shakeT = shake > 0.05 ? `translate(${(shake * Math.sin(sec * 61)).toFixed(2)}px,${(shake * Math.cos(sec * 47)).toFixed(2)}px) scale(1.012)` : undefined;
  return (
    <AbsoluteFill style={{background: t.paper, fontFamily: 'StorySans', overflow: 'hidden', transform: shakeT}}>
      <style>{`@font-face{font-family:StorySans;src:url('${staticFile('fonts/Sans.ttf')}')}@font-face{font-family:StorySerif;src:url('${staticFile('fonts/Serif.ttf')}')}@font-face{font-family:StoryMap;font-weight:100 900;src:url('${staticFile('fonts/MapSans.ttf')}')}@font-face{font-family:StoryBrush;src:url('${staticFile('fonts/Brush.ttf')}')}*{box-sizing:border-box}`}</style>
      {ep.audio && !mapOnly && <Audio src={staticFile(ep.audio)} />}

      {/* World layer: scales with the camera. */}
      <div style={{position: 'absolute', left: 0, top: 0, width: ep.width, height: ep.height, transformOrigin: '0 0', transform: `translate(${ep.width / 2}px,${ep.height / 2}px) scale(${cam.z}) translate(${-cam.cx}px,${-cam.cy}px)`}}>
        {ep.map.raster && <Img
          src={staticFile(ep.map.raster.src)}
          style={{
            position: 'absolute',
            left: ep.map.raster.x,
            top: ep.map.raster.y,
            width: ep.map.raster.width,
            height: ep.map.raster.height,
            translate: '-10.2px -5.1px'
          }}
        />}
        {ep.territory && <TerritoryFill t={ep.territory} sec={sec} cam={cam} width={ep.width} height={ep.height} breathe={els.flatMap((x) => (x.type === 'breathe' && presence(sec, x, 0.6, 0.6) > 0 ? [{faction: x.faction, k: presence(sec, x, 0.6, 0.6)}] : []))} />}
        {/* atlas look: pale river bands stay light above the polity colours */}
        {ep.map.river_overlay && <Img src={staticFile(ep.map.river_overlay.src)} style={{position: 'absolute', left: ep.map.river_overlay.x, top: ep.map.river_overlay.y, width: ep.map.river_overlay.width, height: ep.map.river_overlay.height, translate: '11.5px -9.6px'}} />}
        <svg width={ep.width} height={ep.height} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
          {els.map((e, i) => {
            if (e.type !== 'region') return null;
            const r = regions.get(e.region);
            const op = presence(sec, e, 0.8, 0.6);
            if (!r || !op) return null;
            return <path key={i} d={r.path} fill={r.fill} fillOpacity={0.88 * op} fillRule="evenodd" stroke="none" />;
          })}
        </svg>
        <svg width={ep.width} height={ep.height} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          {els.map((e, i) => {
            if (e.type !== 'region') return null;
            const r = regions.get(e.region);
            const op = presence(sec, e, 0.8, 0.6);
            if (!r || !op) return null;
            return <path key={i} d={r.path} fill="none" stroke={r.edge} strokeOpacity={0.55 * op} strokeWidth={1.6 / cam.z} strokeLinejoin="round" />;
          })}
          {atlas
            // atlas: pale river bands with a dark rim, fixed on-screen width by river size, drawn over the polity colours
            ? [...ep.map.rivers].filter((r) => (r.rank ?? 9) <= 6 || r.name === 'Huai').sort((a, b) => (b.rank ?? 9) - (a.rank ?? 9)).flatMap((r, i) => {
                const w = Math.max(2.4, 6 - 0.6 * (r.rank ?? 6));
                return [
                  <path key={'rr' + i} d={r.path} fill="none" stroke="#4f7fa3" strokeOpacity={0.3} strokeWidth={(w + 2) / cam.z} strokeLinecap="round" strokeLinejoin="round" />,
                  <path key={'rc' + i} d={r.path} fill="none" stroke="#9fc6e2" strokeOpacity={0.8} strokeWidth={w / cam.z} strokeLinecap="round" strokeLinejoin="round" />,
                ];
              })
            : ep.map.rivers.map((r, i) => <path key={i} d={r.path} fill="none" stroke={t.river} strokeWidth={2.8 / cam.z} strokeOpacity={0.9} strokeLinecap="round" strokeLinejoin="round" />)}
        </svg>
      </div>
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg,#1b180c26,transparent 18%,transparent 72%,#24190f1c)'}} />
      {ep.map.watermark && t.ui !== 'clean' && <div style={{position: 'absolute', left: 30, top: 300, fontFamily: 'StorySerif', fontSize: 65, color: '#765b3870', writingMode: 'vertical-rl', letterSpacing: 8}}>{ep.map.watermark}</div>}

      {atlas && <AtlasFeatures ep={ep} zoom={cam.z} screen={(x, y) => [ep.width / 2 + (x - cam.cx) * cam.z, ep.height / 2 + (y - cam.cy) * cam.z]} />}
      {ep.territory && <TerritoryLabels t={ep.territory} warm={ep.theme.palette === 'warm'} avoid={placed} cams={ep.camera} marks={marks} sec={sec} zoom={cam.z} screen={(x, y) => [ep.width / 2 + (x - cam.cx) * cam.z, ep.height / 2 + (y - cam.cy) * cam.z]} />}
      {/* Polity name pills (atlas style). */}
      {els.map((e, i) => {
        if (e.type !== 'region') return null;
        const r = regions.get(e.region);
        const op = presence(sec, e, 0.8, 0.6);
        if (!r || !r.anchor || !op) return null;
        const x = ep.width / 2 + (r.anchor[0] - cam.cx) * cam.z, y = ep.height / 2 + (r.anchor[1] - cam.cy) * cam.z;
        if (x < -100 || x > ep.width + 100 || y < 60 || y > ep.height - 200) return null;
        const big = r.main ? 1.25 : 1;
        return (
          <div key={'pill' + i} style={{position: 'absolute', left: x, top: y, transform: `translate(-50%,-50%) scale(${big})`, opacity: op, padding: '4px 18px 6px', borderRadius: 999, background: r.edge, color: '#fff7e6', fontFamily: 'StoryBrush', fontSize: 34, letterSpacing: 4, whiteSpace: 'nowrap', boxShadow: '0 2px 6px #0004', border: '2px solid #fff3dccc'}}>{r.name}</div>
        );
      })}
      {/* Screen layer, painter's order: cities → arrows → flags → events. Region names are region-tier city marks. */}
      {els.map((e, i) => e.type === 'city' && <CityMark key={i} el={e} place={byId.get(e.place)!} p={screen(e.place)} sec={sec} theme={t} mode={modes.get(i) ?? 'none'} close={close} holder={holderColor(e.place)} />)}
      {!mapOnly && (<>
      {els.map((e, i) => e.type === 'arrow' && <ArrowMark key={i} id={String(i)} el={e} pts={e.points.map(screen)} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'spot' && <SpotMark key={i} el={e} p={screen(e.place)} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'siege' && <SiegeMark key={i} el={e} p={screen(e.place)} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'capture' && <CaptureMark key={i} el={e} p={screen(e.place)} sec={sec} />)}
      {els.map((e, i) => e.type === 'replay' && <ReplayMark key={i} id={String(i)} el={e} pts={e.points.map(screen)} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'alliance' && <AllianceMark key={i} el={e} p={screen(e.place)} sec={sec} theme={t} />)}
      <svg width={ep.width} height={ep.height} style={{position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none'}}>
        {els.map((e, i) => e.type === 'clash' && <ClashMark key={i} id={String(i)} sides={e.sides} froms={e.sides.map((sd) => (sd.from ? screen(sd.from) : (null as unknown as Pt)))} p={screen(e.place)} sec={sec} start={e.start} end={e.end} loser={e.loser} loserAt={e.loser_at} title={e.title} traceEnd={e.trace_end} burnSide={e.burn_side} burnAt={e.burn_at} />)}
      </svg>
      {els.map((e, i) => e.type === 'act' && <ActMark key={'act' + i} el={e} pts={(e.places ?? (e.place ? [e.place] : [])).map((n) => screen(n))} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'fire' && <FireMark key={'fire' + i} id={String(i)} el={e} p={screen(e.place)} sec={sec} zoom={cam.z} />)}
      {els.map((e, i) => e.type === 'flag' && <FlagMark key={i} el={e} p={screen(e.place)} sec={sec} theme={t} pos={flagPos.get(i)} />)}
      <svg width={ep.width} height={ep.height} style={{position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none'}}>
        {els.map((e, i) => e.type === 'trail' && <TrailMark key={'trail' + i} el={e} pts={e.points.map(screen)} sec={sec} />)}
        {els.map((e, i) => e.type === 'camp' && (garrisonSlot.has(i)
          ? <GarrisonMark key={i} el={e} p={screen(e.place)} sec={sec} size={sizeOf(e.place)} close={close} slot={garrisonSlot.get(i)!} />
          : close && <CampMark key={i} el={e} p={screen(e.place)} sec={sec} />))}
      </svg>
      {els.map((e, i) => e.type === 'battle' && <BattleMark key={i} el={e} p={screen(e.place)} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'stamp' && <StampMark key={i} el={e} p={screen(e.place)} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'card' && !(onStage && !e.place) && <CardMark key={i} el={e} p={e.place ? screen(e.place) : null} sec={sec} theme={t} />)}

      {t.ui !== 'clean' && <TitleBlock ep={ep} />}
      <FactionBars els={els.filter((x): x is Extract<typeof x, {type: 'faction_bar'}> => x.type === 'faction_bar')} sec={sec} />
      {els.map((e, i) => e.type === 'vignette' && <Vignette key={'vg' + i} el={e} sec={sec} />)}
      {els.map((e, i) => e.type === 'title_bar' && <TitleBar key={i} el={e} sec={sec} theme={t} />)}
      {!onStage && els.map((e, i) => e.type === 'quote' && <QuoteCard key={i} el={e} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'person_card' && <PersonCard key={i} el={e} sec={sec} />)}
      {!atlas && <PhaseChip ep={ep} sec={sec} />}
      {els.map((e, i) => e.type === 'portrait' && <Portrait key={i} el={e} sec={sec} />)}
      {els.map((e, i) => e.type === 'enter' && <Enter key={i} el={e} sec={sec} theme={t} anchor={e.place ? screen(e.place) : null} />)}
      {els.map((e, i) => e.type === 'exit' && <ExitPortrait key={i} el={e} sec={sec} />)}
      {els.map((e, i) => e.type === 'versus' && <Versus key={i} el={e} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'headline' && <Headline key={i} el={e} sec={sec} theme={t} />)}
      {els.map((e, i) => e.type === 'yearflip' && <YearFlip key={i} el={e} sec={sec} theme={t} />)}
      <FireFlash k={flashK} sec={sec} />
      {!onStage && <MiniMap ep={ep} cam={cam} />}
      {els.map((e, i) => e.type === 'tactic' && <TacticMark key={'tac' + i} el={e} sec={sec} />)}
      {els.map((e, i) => e.type === 'stage' && <Stage key={'stage' + i} el={e} sec={sec} />)}
      {/* notes without a place (据说 / 史书原文 cards, quotes) stay readable on the stage */}
      {onStage && els.map((e, i) => e.type === 'card' && !e.place && <CardMark key={'sc' + i} el={e} p={null} sec={sec} theme={t} stage />)}
      {onStage && els.map((e, i) => e.type === 'quote' && <QuoteCard key={'sq' + i} el={e} sec={sec} theme={t} />)}
      {t.ui === 'clean' ? <YearScroll ep={ep} sec={sec} top={atlas ? 80 : 22} /> : <YearBadge ep={ep} sec={sec} />}
      {els.map((e, i) => e.type === 'forces' && <Forces key={'forces' + i} el={e} sec={sec} />)}
      {t.ui === 'clean' && !onStage && <SpeechBrush els={els} segments={ep.segments} sec={sec} />}
      <CaptionBar segments={brushed.length ? ep.segments.filter((g) => !brushed.some((l) => Math.abs(l.t0 - g.voice_onset) < 0.01)) : ep.segments} sec={sec} theme={t} />
      {atlas && !onStage && <AtlasTopBar ep={ep} sec={sec} />}
      {atlas && <AtlasChapterBar ep={ep} sec={sec} />}
      {t.ui !== 'clean' && <Legend items={ep.legend} />}
      {t.ui !== 'clean' && <Footer ep={ep} />}
      </>)}
    </AbsoluteFill>
  );
};
