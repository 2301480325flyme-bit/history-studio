import React from "react";
import { geoMercator, geoPath } from "d3-geo";
import type { FeatureCollection, Point } from "geojson";

export const W = 1920;
export const H = 1080;
export const FPS = 30;

/**
 * 三套底图 = 三套投影参数，覆盖不同视野层级：
 *
 *   national  全国      69.06–139.07°E / 16.64–48.92°N  —— 只负责覆盖，不追求城市特写
 *   wide      区域      104.3–122.7°E / 30.9–39.3°N    —— 中原及周边（原有，未改动）
 *   core      核心      109.4–117.6°E / 33.3–37.1°N    —— 中原核心（原有，未改动）
 *
 * ⚠️ national 的 center/scale 由 z6 瓦片范围反算得出：
 *    经度方向算得 scale 1571.4，纬度方向 1571.5，偏差 0.01%
 *    —— 说明与 Web Mercator 完全自洽，不会产生拉伸变形。
 *    ⚠️ 参数若改，必须重新反算，不能手调（会让经纬度与像素脱钩）。
 */
export const VIEW: Record<string, { center: [number, number]; scale: number }> = {
  national: { center: [104.0625, 34.3071], scale: 1571.5 },
  wide: { center: [113.5, 35.2], scale: 6000 },
  core: { center: [113.5, 35.2], scale: 13500 },
};

/** 各层级对应的底图文件（同一投影，只是视野不同） */
export const BASEMAP_FILE: Record<string, string> = {
  national: "basemap_national.png",
  wide: "basemap_wide.png",
  core: "basemap_core.png",
};

/** 各层级的视野覆盖范围（供 pick_basemap 之类的自动选择使用） */
export const VIEW_BOUNDS: Record<string, { lon: [number, number]; lat: [number, number] }> = {
  national: { lon: [69.06, 139.07], lat: [16.64, 48.92] },
  wide: { lon: [104.3, 122.7], lat: [30.9, 39.3] },
  core: { lon: [109.4, 117.6], lat: [33.3, 37.1] },
};

/**
 * 层级由紧到松：core（最清晰，覆盖最小）→ wide（区域）→ national（全覆盖，最粗）。
 * 自动选择时**优先取最紧的** —— 能装下就用更清晰的层级。
 */
const BASEMAP_ORDER: BasemapKind[] = ["core", "wide", "national"];

/**
 * 按目标地点自动选底图层级。
 *
 * @param lon,lat  目标点
 * @param margin   需要留的余量（度）。默认 0（点在视野内即可）；
 *                 若镜头还要展示周边，可给 1–2 度避免地点贴边。
 * @returns 能装下该点、且**最紧**的层级；都装不下则回退 national
 */
export function pickBasemap(lon: number, lat: number, margin = 0): BasemapKind {
  return pickBasemapForPoints([[lon, lat]], margin);
}

/**
 * 多目标点版本：一个镜头常涉及起点与终点（如行军），
 * 必须选**能同时装下所有点**的最紧层级。
 */
export function pickBasemapForPoints(
  points: [number, number][],
  margin = 0,
): BasemapKind {
  if (!points.length) return "national";
  for (const k of BASEMAP_ORDER) {
    const b = VIEW_BOUNDS[k];
    const ok = points.every(([lon, lat]) =>
      lon >= b.lon[0] + margin && lon <= b.lon[1] - margin &&
      lat >= b.lat[0] + margin && lat <= b.lat[1] - margin);
    if (ok) return k;
  }
  return "national";   // 兜底：全国图只负责覆盖
}

/** 该层级是否已被底图覆盖（用于判断某地点能否出图） */
export function isCovered(lon: number, lat: number): boolean {
  const b = VIEW_BOUNDS.national;
  return lon >= b.lon[0] && lon <= b.lon[1] && lat >= b.lat[0] && lat <= b.lat[1];
}

export function projectionFor(kind: BasemapKind) {
  const v = VIEW[kind] ?? VIEW.wide;
  return geoMercator().center(v.center).scale(v.scale).translate(TRANSLATE_XY);
}

const TRANSLATE_XY: [number, number] = [960, 540];

export const CENTER: [number, number] = VIEW.wide.center;
export const SCALE = VIEW.wide.scale;
export const TRANSLATE: [number, number] = TRANSLATE_XY;

/** 预构建各层级的投影（national / wide / core 共用同一套 Mercator 公式） */
export const PROJECTIONS: Record<string, ReturnType<typeof geoMercator>> = {
  national: projectionFor("national"),
  wide: projectionFor("wide"),
  core: projectionFor("core"),
};

export const projection = PROJECTIONS.wide;

export const pathGen = geoPath(projection);

/**
 * 与底图同一投影：把经纬度直接当 1920x1080 像素用。
 * 三个层级共用同一公式，只是 center/scale 不同 —— 所以切换层级不会改变经纬度语义。
 */
export function project(lon: number, lat: number, kind: BasemapKind = "wide"): [number, number] {
  const p = PROJECTIONS[kind]?.([lon, lat]);
  return p ? [p[0], p[1]] : [0, 0];
}

/** 按类型分档，决定标签样式与显示密度 */
export type BasemapKind = "national" | "wide" | "core";

export type Tier = "capital" | "jun" | "xian" | "other";

export function tierOf(ftype: string, name: string): Tier {
  if (name.includes("洛阳") || name.includes("邺") || name.includes("长安")) return "capital";
  if (ftype.includes("郡") || ftype.includes("国")) return "jun";
  if (ftype.includes("县") || ftype.includes("邑")) return "xian";
  return "other";
}

export type PlaceProps = {
  name: string;
  place_id: string;
  ftype: string;
  parent: string;
  beg_yr: number;
  end_yr: number;
};

/** 去掉通名后缀用于画面标注 */
export function shortName(n: string): string {
  return n.replace(/(縣|县|郡|國|国|城|邑)$/, "");
}

export const PALETTE = {
  paper: "#f2ede2",
  ink: "#2a221b",
  inkSoft: "#6b5a49",
  realm: "#c65c4a",
  realmEdge: "#8c3424",
  river: "#5b8fa8",
  accent: "#9a2824",
};

/**
 * 政权/政区配色 —— 参考「秋水制图」实测风格：
 * 高明度、低饱和（实测其饱和度均值 0.24~0.26，高饱和区仅占 40%），
 * 靠色相差异而非明暗对比区分层级。色值取自其作品量化主色的邻近区间。
 */
export const POWER_COLORS: Record<string, { fill: string; edge: string; label: string }> = {
  州: { fill: "#c8a882", edge: "#8f7350", label: "#4a3a26" },
  郡: { fill: "#d9c4a4", edge: "#a8906a", label: "#5a4a34" },
  国: { fill: "#c6a9b4", edge: "#93787f", label: "#4d3a42" },
  侯国: { fill: "#cdbdc6", edge: "#98858c", label: "#52444a" },
  县: { fill: "#ddd0b8", edge: "#b09c82", label: "#5f5140" },
};

export function colorFor(ftype: string) {
  // 注意顺序：必须先判「侯国」「国」，否则会被「国」抢先匹配
  if (ftype.includes("侯国")) return POWER_COLORS["侯国"];
  if (ftype.includes("州")) return POWER_COLORS["州"];
  if (ftype.includes("郡")) return POWER_COLORS["郡"];
  if (ftype.includes("国")) return POWER_COLORS["国"];
  if (ftype.includes("县")) return POWER_COLORS["县"];
  return { fill: "#d8cdb8", edge: "#a89a80", label: "#5a5040" };
}

/** 字号层级（实测其比例 21:18:10 ≈ 2.1:1.8:1） */
export const FONT_SCALE = {
  title: 42,
  subtitle: 26,
  capital: 30,
  jun: 22,
  xian: 15,
};

export type Shot = {
  title: string;
  subtitle: string;
  year: number;
  /** 镜头中心经纬�� */
  focus: [number, number];
  /** 镜头缩放：1 = 底图原生视野 */
  zoom: number;
  durationInFrames: number;
  /** 高亮这些地名（画面聚焦对象） */
  highlight?: string[];
  narration?: string;
  /** 使用哪套底图（对应两套投影参数） */
  basemap?: BasemapKind;
};

/** 一集视频的完整配置：换朝代只改这个对象，渲染代码零改动 */
export type Episode = {
  id: string;                 // 数据目录名，如 "东晋十六国-409"
  title: string;
  year: number;
  dynasty: string;
  shots: {
    title?: string;
    subtitle?: string;
    year?: number;
    yearLabel?: string;
    focus: [number, number];
    zoom: number;
    durationInFrames: number;
    highlight?: string[];
    narration?: string;
    basemap?: BasemapKind;
    disclaimer?: string;
  }[];
};
