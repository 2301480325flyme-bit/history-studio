/**
 * DirectorComposition —— 消费脚本 JSON，把一个 episode 的全部镜头串成一条视频。
 *
 * 这是「断链」的最后一环：`compile_story.py` / 手写 JSON 产出的脚本，
 * 由这里读入并渲染。之前 Remotion 里没有任何地方读 director.json。
 *
 * 脚本路径：public/scripts/<episodeId>.json
 * 数据来源：public/dynasty/<dataDir>/{labels,zones}.json + public/maindata/places.json
 */
import React from "react";
import {
  AbsoluteFill, Sequence, continueRender, delayRender, staticFile, useVideoConfig,
} from "remotion";
import type { FeatureCollection } from "geojson";
import { PALETTE } from "./geo";
import { DirectorShot, type Episode, type EpisodeShot, type KingBundle } from "./DirectorShot";
import { hydrateCities, loadMainData, type MainPlace } from "./MainData";

/** 镜头可单独指定数据目录（一集可跨多个场景目录） */
export type EpisodeShotWithData = EpisodeShot & { dataDir?: string };

export type PlaceGeo = { lon: number; lat: number; name: string };

type Loaded = {
  episode: Episode;
  coords: Record<string, PlaceGeo>;
  data: Record<string, { labels: FeatureCollection; zones: FeatureCollection }>;
  kings: Record<string, KingBundle | null>;
};

/** 空 FeatureCollection：场景数据缺失时的占位，保证仍能渲染底图与符号 */
const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

const fetchJson = async (paths: string[]) => {
  for (const p of paths) {
    try {
      const r = await fetch(staticFile(p));
      if (r.ok) return await r.json();
    } catch { /* 试下一个 */ }
  }
  return null;
};

const useEpisode = (episodeId: string) => {
  const [loaded, setLoaded] = React.useState<Loaded | null>(null);

  React.useEffect(() => {
    const h = delayRender("载入脚本 " + episodeId);
    (async () => {
      const episode = await fetchJson([`scripts/${episodeId}.json`]);
      if (!episode) {
        console.error("[Director] 找不到脚本 scripts/%s.json", episodeId);
        continueRender(h);
        return;
      }
      const shots = (episode.shots ?? []) as EpisodeShotWithData[];
      const dirs = Array.from(new Set(shots.map((s) => s.dataDir ?? episode.id)));
      const md = await loadMainData();

      // 地点坐标 + 显示名：优先主表（权威），其次集数据自带
      const coords: Record<string, PlaceGeo> = {};
      const idx = new Map<string, MainPlace>();
      for (const p of md.places) {
        idx.set(p.id, p);
        for (const a of p.aliases ?? []) if (!idx.has(a)) idx.set(a, p);
      }
      const displayName = (entry: MainPlace | undefined, fallback: string) =>
        entry?.names?.[0]?.text ?? fallback;

      const data: Loaded["data"] = {};
      const kings: Loaded["kings"] = {};
      await Promise.all(dirs.map(async (dir) => {
        const labels = await fetchJson([
          `dynasty/${dir}/labels.byid.json`,
          `dynasty/${dir}/labels.resolved.json`,
          `dynasty/${dir}/labels.json`,
        ]);
        const zones = await fetchJson([`dynasty/${dir}/zones.json`]);
        if (!labels || !zones) return;
        data[dir] = { labels, zones };
        if (labels.kings) {
          const hydrated = hydrateCities(labels.cities ?? [], md.places, labels.year ?? episode.year);
          kings[dir] = { kings: labels.kings, cities: hydrated, routes: labels.routes ?? [] };
          for (const c of hydrated) {
            if (c.placeId) coords[c.placeId] = { lon: c.lon, lat: c.lat, name: c.name };
            coords[c.name] = { lon: c.lon, lat: c.lat, name: c.name };
          }
        }
      }));

      // 脚本里 places[] 只给 placeId，坐标与中文名都从主表补
      for (const s of shots) {
        for (const p of s.places ?? []) {
          const entry = idx.get(p.placeId);
          if (entry?.coordinates) {
            coords[p.placeId] = {
              lon: entry.coordinates[0], lat: entry.coordinates[1],
              name: displayName(entry, p.placeId),
            };
          }
        }
        for (const a of s.actions ?? []) {
          for (const field of ["at", "from", "to"] as const) {
            const v = (a as any)[field];
            if (v && typeof v === "string") {
              const entry = idx.get(v);
              if (entry?.coordinates) (a as any)[field] = {
                lon: entry.coordinates[0], lat: entry.coordinates[1],
              };
            }
          }
        }
      }

      setLoaded({ episode, coords, data, kings });
      continueRender(h);
    })().catch((e) => { console.error(e); continueRender(h); });
  }, [episodeId]);

  return loaded;
};

export const DirectorComposition: React.FC<{ episodeId: string }> = ({ episodeId }) => {
  const loaded = useEpisode(episodeId);
  const { fps } = useVideoConfig();
  void fps;

  if (!loaded) {
    return <AbsoluteFill style={{ background: PALETTE.paper }} />;
  }
  const { episode, coords, data, kings } = loaded;
  const shots = episode.shots as EpisodeShotWithData[];

  // 计算每个镜头的起始帧
  const offsets: number[] = [];
  let acc = 0;
  for (const s of shots) { offsets.push(acc); acc += s.durationInFrames; }

  return (
    <AbsoluteFill style={{ background: PALETTE.paper }}>
      {shots.map((s, i) => {
        const dir = s.dataDir ?? episode.id;
        // ⚠️ 场景数据可选：由模板生成的脚本可能没有对应的 dynasty 目录，
        //    此时仍应渲染底图 + 符号 + 动作（只是没有疆域底图层）。
        const d = data[dir] ?? { labels: EMPTY_FC, zones: EMPTY_FC };
        return (
          <Sequence key={i} from={offsets[i]} durationInFrames={s.durationInFrames}>
            <DirectorShot
              shot={s}
              episode={episode}
              data={d}
              kings={kings[dir] ?? null}
              coords={coords}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

/** 一集的默认时长 = 所有镜头之和 */
export const episodeDuration = (episode: Episode) =>
  episode.shots.reduce((a, s) => a + (s.durationInFrames ?? 0), 0);
