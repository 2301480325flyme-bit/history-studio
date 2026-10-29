/**
 * 通用历史地图图层。可用于任意朝代与年份，不含任何八王之乱专用逻辑。
 *
 * 两种政区渲染模式（由数据决定，视觉层自动适配）：
 *   areas —— 有多边形：画真实色块面（视觉密度高，接近静态史图效果）
 *   points —— 仅有治所点：画渐变晕圈（Voronoi 观感），保证信息密度不塌陷
 */
import React, { useMemo } from "react";
import type { Feature, FeatureCollection, Point, Polygon, MultiPolygon } from "geojson";
import { geoPath } from "d3-geo";
import { geoVoronoi } from "d3-geo-voronoi";
import { FONT_SCALE, PALETTE, POWER_COLORS, project, shortName, type BasemapKind } from "./geo";
import type { Tier } from "./geo";

// ---- 政权配色：按名称稳定分配色相，同一政权在各镜头颜色一致 ----
const REALM_HUES = [
  ["#c65c4a", "#8c3424"], ["#4a7ba7", "#2d5273"], ["#6b9e5a", "#456b3a"],
  ["#b8874a", "#825a28"], ["#8a6bab", "#5d4478"], ["#a85c7a", "#74394f"],
  ["#5c9a8f", "#356b63"], ["#9a8c3f", "#6b5f22"],
];

export function realmColor(name: string): { fill: string; edge: string } {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return { fill: REALM_HUES[h % REALM_HUES.length][0], edge: REALM_HUES[h % REALM_HUES.length][1] };
}

export function tierOf(ftype: string, name: string): Tier {
  if (name.includes("洛阳") || name.includes("长安") || name.includes("邺")
    || name.includes("建康") || name.includes("建业") || name.includes("成都")) return "capital";
  if (ftype.includes("郡") || ftype.includes("国") || ftype.includes("侯国")) return "jun";
  if (ftype.includes("县") || ftype.includes("邑")) return "xian";
  return "other";
}

// ================= 政区色块层 =================
export const ZoneLayer: React.FC<{
  zones: FeatureCollection;
  kind: BasemapKind;
  zoom: number;
  W: number;
  H: number;
  opacity?: number;
}> = ({ zones, kind, zoom, W, H, opacity = 1 }) => {
  const pathGen = useMemo(
    () => geoPath({ x: (p: number[]) => project(p[0], p[1], kind)[0],
                    y: (p: number[]) => project(p[0], p[1], kind)[1] } as any),
    [kind]
  );

  const isAreas = (zones as any).mode === "areas";

  const areaPaths = useMemo(() => {
    if (!isAreas) return [];
    return zones.features
      .map((f) => ({ d: pathGen(f as any), p: f.properties as any }))
      .filter((x) => x.d);
  }, [zones, isAreas, pathGen]);

  // 点模式：Voronoi 生成势力范围
  const voronoiPaths = useMemo(() => {
    if (isAreas) return [];
    const pts = zones.features
      .filter((f) => (f.properties as any).ftype === "政权" || (f.properties as any).ftype === "州")
      .map((f) => project((f as any).geometry.coordinates[0], (f as any).geometry.coordinates[1], kind))
      .filter(([x, y]) => x > -400 && x < W + 400 && y > -400 && y < H + 400) as [number, number][];
    if (pts.length < 3) return [] as string[];
    try {
      const v = geoVoronoi(pts as any, [0, 0, W, H] as any);
      const raw: any = (v as any).polygons();
      if (!raw) return [] as string[];
      const arr: string[] = typeof raw[Symbol.iterator] === "function"
        ? Array.from(raw)
        : Array.isArray(raw) ? raw : [raw];
      return arr.filter((d) => typeof d === "string" && d.length > 10);
    } catch {
      return [] as string[];
    }
  }, [zones, isAreas, kind, W, H]);

  if (isAreas) {
    return (
      <g opacity={opacity}>
        {areaPaths.map((x, i) => {
          const c = POWER_COLORS[x.p.ftype] ?? POWER_COLORS["州"];
          return (
            <path key={i} d={x.d} fill={c.fill} fillOpacity={0.55}
                  stroke={c.edge} strokeWidth={2} strokeOpacity={0.85} />
          );
        })}
      </g>
    );
  }

  return (
    <g opacity={opacity}>
      {voronoiPaths.map((d: string, i: number) => {
        const z = zones.features.filter(
          (f) => (f.properties as any).ftype === "政权" || (f.properties as any).ftype === "州"
        )[i % Math.max(zones.features.length, 1)];
        const nm = (z?.properties as any)?.name ?? "";
        const c = realmColor(nm);
        return <path key={i} d={d} fill={c.fill} fillOpacity={0.42}
                       stroke={c.edge} strokeWidth={2.5} strokeOpacity={0.8} />;
      })}
    </g>
  );
};

// ================= 地名标注层 =================
type Occupied = { x: number; y: number; w: number; h: number }[];

const Label: React.FC<{
  f: Feature<Point>;
  kind: BasemapKind;
  tier: Tier;
  highlight: boolean;
  occupied: Occupied;
  base: number;
  showCity: boolean;
}> = ({ f, kind, tier, highlight, occupied, base, showCity }) => {
  const p = f.properties as any;
  const [lon, lat] = (f as any).geometry.coordinates;
  const [x, y] = project(lon, lat, kind);
  if (!isFinite(x) || !isFinite(y)) return null;
  if (x < -150 || x > 1920 + 150 || y < -150 || y > 1080 + 150) return null;

  const name = shortName(p.name as string);
  const ftype = p.ftype as string;
  const size = highlight ? FONT_SCALE.capital
    : tier === "capital" ? FONT_SCALE.capital
    : tier === "jun" ? FONT_SCALE.jun
    : FONT_SCALE.xian;
  const isCity = tier === "capital";
  const color = highlight ? PALETTE.accent : isCity ? PALETTE.ink : PALETTE.inkSoft;
  const r = highlight ? 7 : isCity ? 5 : 3;
  const w = name.length * size * 1.02 + 14;
  const h = size + 8;

  // 视野外/低缩放时的小地名直接不画，省去大量避让计算
  if (!isCity && !showCity) return null;

  const cand = [
    { x: x + 12, y: y - h / 2, w, h },
    { x: x + 12, y: y - h / 2 - h, w, h },
    { x: x + 12, y: y - h / 2 + h, w, h },
    { x: x - 12 - w, y: y - h / 2, w, h },
    { x: x - 12 - w, y: y - h / 2 - h, w, h },
  ];
  let slot: Occupied[number] | null = null;
  for (const c of cand) {
    const hit = occupied.some(
      (o) => c.x < o.x + o.w && c.x + c.w > o.x && c.y < o.y + o.h && c.y + c.h > o.y
    );
    if (!hit) { slot = c; break; }
  }
  if (!slot) return null;
  occupied.push(slot);

  return (
    <g>
      {highlight && <circle cx={x} cy={y} r={16} fill="none" stroke={PALETTE.accent} strokeWidth={2} opacity={0.5} />}
      <circle cx={x} cy={y} r={r} fill="#fffdf7" stroke={color} strokeWidth={highlight ? 3 : 2} />
      <text x={slot.x + 7} y={slot.y + h / 2} fontSize={size} fill={color}
            stroke="#fdfaf2" strokeWidth={highlight ? 4.5 : 3.5} paintOrder="stroke"
            style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: highlight || isCity ? 500 : 400 }}>
        {name}
      </text>
    </g>
  );
};

export const LabelLayer: React.FC<{
  labels: FeatureCollection;
  kind: BasemapKind;
  zoom: number;
  highlight: string[];
  W: number;
  H: number;
  base?: number;
}> = ({ labels, kind, zoom, highlight, W, H, base = 15 }) => {
  const hl = useMemo(
    () => new Set(highlight.map((s) => s.replace(/(縣|县|郡|國|国|城|邑|府|路|省)$/, ""))),
    [highlight]
  );
  const minRank = zoom >= 2.2 ? 2 : zoom >= 1.5 ? 1 : 0;
  const gap = zoom >= 2.2 ? 40 : zoom >= 1.5 ? 52 : 62;
  const maxN = zoom >= 2.2 ? 150 : zoom >= 1.5 ? 70 : 48;
  const RANK: Record<Tier, number> = { capital: 0, jun: 1, xian: 2, other: 3 };

  const kept = useMemo(() => {
    const items = labels.features
      .map((f) => {
        const p = f.properties as any;
        const nm = shortName(p.name as string);
        return { f, nm, tier: tierOf(p.ftype, p.name), h: hl.has(nm) };
      })
      .filter((it) => it.h || RANK[it.tier] >= minRank)
      .sort((a, b) => Number(b.h) - Number(a.h) || RANK[a.tier] - RANK[b.tier]);

    const out: typeof items = [];
    const g2 = gap * gap;
    for (const it of items) {
      if (out.length >= maxN) break;
      const [x, y] = project((it.f as any).geometry.coordinates[0],
                              (it.f as any).geometry.coordinates[1], kind);
      if (out.some((k) => {
        const [kx, ky] = project((k.f as any).geometry.coordinates[0],
                                  (k.f as any).geometry.coordinates[1], kind);
        return (x - kx) ** 2 + (y - ky) ** 2 < g2;
      })) continue;
      out.push(it);
    }
    return out;
  }, [labels, minRank, gap, maxN, hl, kind]);

  const occupied: Occupied = useMemo(() => ([
    { x: 0, y: 0, w: 760, h: 150 },
    { x: W - 360, y: 0, w: 360, h: 165 },
    { x: 0, y: H - 140, w: W, h: 140 },
    { x: 0, y: H - 340, w: 880, h: 210 },
  ]), [W, H]);

  return (
    <g>
      {kept.map((it, i) => (
        <Label key={i} f={it.f as Feature<Point>} kind={kind} tier={it.tier}
              highlight={it.h} occupied={occupied} base={base}
              showCity={zoom < 2.2 || it.tier !== "xian"} />
      ))}
    </g>
  );
};

// ================= 政区名（色块面模式用） =================
export const ZoneNameLayer: React.FC<{
  zones: FeatureCollection;
  kind: BasemapKind;
  W: number;
  H: number;
}> = ({ zones, kind, W, H }) => {
  const isAreas = (zones as any).mode === "areas";
  const items = useMemo(() => {
    if (!isAreas) return [];
    return zones.features
      .filter((f) => ["政权", "州", "省", "路"].includes((f.properties as any).ftype))
      .map((f) => {
        const g = (f as any).geometry;
        const polys: number[][][] = g.type === "MultiPolygon"
          ? g.coordinates
          : [g.coordinates];
        let bx = 0, by = 0, n = 0;
        for (const poly of polys) for (const ring of poly)
          for (const pt of ring) { bx += pt[0]; by += pt[1]; n++; }
        return n ? { name: (f.properties as any).name as string,
                     lon: bx / n, lat: by / n } : null;
      })
      .filter(Boolean) as { name: string; lon: number; lat: number }[];
  }, [zones, isAreas]);

  return (
    <g>
      {items.map((it, i) => {
        const [x, y] = project(it.lon, it.lat, kind);
        if (x < 60 || x > W - 60 || y < 60 || y > H - 60) return null;
        return (
          <text key={i} x={x} y={y} fontSize={FONT_SCALE.jun + 6} fill={PALETTE.inkSoft}
                fillOpacity={0.85} textAnchor="middle" stroke="#fdfaf2" strokeWidth={4}
                paintOrder="stroke" style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500 }}>
            {shortName(it.name)}
          </text>
        );
      })}
    </g>
  );
};
