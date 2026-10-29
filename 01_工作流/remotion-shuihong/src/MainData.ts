/**
 * 主表解析器 —— 让渲染层按 placeId 取坐标。
 *
 * 解决的根本问题：同一份坐标原先在「主表 / kings.json / labels.json」存了三份，
 * 改一处忘一处就会分叉。现在各集数据只留 placeId，坐标唯一来源于 maindata/places.json。
 *
 * 渲染流程：
 *   *.byid.json（只有 placeId）→ hydrateCities() 查主表 → 带 lon/lat 的 city
 */
import { staticFile } from "remotion";

export type MainPlaceName = { text: string; from: number | null; to: number | null; note?: string };
export type MainPlaceTier = { from: number | null; to: number | null; tier: string };

export type MainPlace = {
  id: string;
  aliases: string[];
  coordinates: [number, number] | null;
  coordinatePrecision?: string;
  coordinateSource?: string | null;
  names: MainPlaceName[];
  tiers: MainPlaceTier[];
  roles?: string[];
  usedIn?: string[];
  reviewNote?: string;
  coordinateConflict?: string;
  /** 坐标状态：confirmed（有权威证据）/ approximate（临时近似）/ unregistered（无坐标）。
   *  ⚠️ approximate 不是已考证坐标，画面上只能当示意点用。 */
  coordinateStatus?: "confirmed" | "approximate" | "unregistered";
  coordinatesAlt?: { value: [number, number]; source: string; deviationKm?: number }[];
};

export type MainPerson = {
  id: string;
  names: { formal: string; title: string };
  aliases: string[];
  color?: string | null;
  portrait?: string;
  realm?: string;
  realmSeat?: [number, number] | null;
  note?: string;
  /** ⚠️ 来自近似层（词频发现，身份未核实）。
   *  **不得用于正片人物身份标签** —— 旗标/肖像/阵营关系一律不得引用。 */
  fromApproxLayer?: boolean;
  identityStatus?: "unverified";
};

export type MainData = {
  places: MainPlace[];
  persons: MainPerson[];
  /** ★ 正片人物白名单：仅正式层。渲染端的人物标签必须用这个。 */
  personsVerified: MainPerson[];
};

const norm = (v: unknown) => String(v ?? "").toLowerCase().replace(/\s+/g, "");

let cache: Promise<MainData> | null = null;

/** 载入主表（进程内缓存，避免每集重复请求） */
export const loadMainData = (): Promise<MainData> => {
  if (!cache) {
    // 近似层是可选的：文件不存在时静默跳过，正式层照常工作。
    const optJson = (p: string) =>
      fetch(staticFile(p))
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
    cache = Promise.all([
      fetch(staticFile("maindata/places.json")).then((r) => r.json()),
      fetch(staticFile("maindata/persons.json")).then((r) => r.json()),
      optJson("maindata/places_approximate.json"),
    ]).then(([p, s, apx]) => {
      const places = (p.places ?? []) as MainPlace[];
      const known = new Set(places.map((x) => x.id));
      // ⚠️ 临时近似层：只用于「有个点能画」，不是已考证坐标。
      //    加载时强制校验状态，防止近似值被当成 confirmed 使用。
      for (const e of ((apx?.places ?? []) as MainPlace[])) {
        if (e.coordinateStatus !== "approximate") {
          console.warn("[MainData] 近似层条目状态异常，已跳过：%s", e.id);
          continue;
        }
        if (!known.has(e.id)) places.push(e);
      }
      const persons = (s.persons ?? []) as MainPerson[];
      return {
        places,
        persons,
        // ⚠️ 白名单只含正式层。人物旗标/肖像/阵营必须从这里取，
        //    绝不能直接用 persons —— 那里混了词频发现的近似层人物（unverified）。
        personsVerified: persons.filter((x) => !x.fromApproxLayer),
      };
    }).catch((e) => {
      console.error("[MainData] 主表载入失败", e);
      return { places: [], persons: [], personsVerified: [] } as MainData;
    });
  }
  return cache;
};

/** 建立「别名 → 主表条目」索引 */
export const indexPlaces = (places: MainPlace[]) => {
  const idx = new Map<string, MainPlace>();
  for (const p of places) {
    idx.set(norm(p.id), p);
    for (const a of p.aliases ?? []) if (!idx.has(norm(a))) idx.set(norm(a), p);
    for (const n of p.names ?? []) if (!idx.has(norm(n.text))) idx.set(norm(n.text), p);
  }
  return idx;
};

export const indexPersons = (persons: MainPerson[]) => {
  const idx = new Map<string, MainPerson>();
  for (const p of persons) {
    idx.set(norm(p.id), p);
    for (const a of p.aliases ?? []) if (!idx.has(norm(a))) idx.set(norm(a), p);
  }
  return idx;
};

type RawCity = {
  name: string; lon?: number; lat?: number; placeId?: string;
  role?: string; control?: [number, number, string | null][];
};

export type HydratedCity = RawCity & { lon: number; lat: number; placeId: string; tier?: string };

/**
 * 按 placeId（或名称）从主表补全坐标与等级。
 *
 * 解析优先级：
 *   1. 主表有坐标 → 用主表（权威）
 *   2. 主表无坐标但数据自身带 lon/lat → 用数据自身，并告警
 *   3. 都无 → 丢弃该城并告警（**不编造坐标**）
 */
export const hydrateCities = (
  cities: RawCity[],
  places: MainPlace[],
  year: number,
): HydratedCity[] => {
  const idx = indexPlaces(places);
  const out: HydratedCity[] = [];
  for (const c of cities ?? []) {
    const entry = idx.get(norm(c.placeId ?? c.name));
    const coords = entry?.coordinates ?? null;
    const tier = entry?.tiers?.find(
      (t) => (t.from == null || year >= t.from) && (t.to == null || year <= t.to),
    )?.tier;

    if (coords) {
      out.push({ ...c, placeId: entry!.id, lon: coords[0], lat: coords[1], tier });
      continue;
    }
    if (typeof c.lon === "number" && typeof c.lat === "number") {
      console.warn(`[MainData] 「${c.name}」主表无坐标，回退数据自带值（应补录主表）`);
      out.push({ ...c, lon: c.lon, lat: c.lat, placeId: c.placeId ?? c.name, tier });
      continue;
    }
    console.error(`[MainData] 「${c.name}」主表无坐标且数据未带坐标，已丢弃`);
  }
  return out;
};
