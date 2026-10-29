/**
 * 地点符号库 —— 16 个符号 × 10 个状态。
 *
 * 设计原则（见 maindata/../可复用资产清单-v1.md 第二节）：
 *   1. 符号不硬编码颜色 / 字体 —— 全部由 props 注入，否则复用会变成"一改颜色全崩"。
 *   2. 层级感靠「形状 + 尺寸 + 是否带环/框」区分，不只靠颜色（色盲与缩略图下颜色会失效）。
 *   3. 状态与符号正交 —— 同一符号可以是被围的、陷落的、改名的。
 *
 * 用法（必须放在现有 <svg> 内）：
 *   <PlaceMarker
 *     place={{ name: "洛阳", lon: 112.6183, lat: 34.7195 }}
 *     tier="capital" state="besieged" color="#8c3424"
 *     kind="core" frame={frame} progress={0.5}
 *   />
 */
import React from "react";
import { project, type BasemapKind } from "./geo";

// ---------- 类型 ----------
export type PlaceTier =
  | "capital" | "secondary_capital" | "seat" | "county" | "town"
  | "pass" | "fortress" | "fort" | "camp" | "beacon"
  | "ferry" | "port" | "bridge" | "gorge"
  | "granary" | "tomb" | "temple" | "market";

export type PlaceState =
  | "normal" | "controlled" | "contested" | "besieged" | "fallen"
  | "burned" | "abandoned" | "newly_built" | "renamed" | "upgraded";

/** 符号视觉规格：绘制时只依赖这个对象，不读全局常量 */
export type PlaceVisual = {
  tier: PlaceTier;
  state: PlaceState;
  /** 归属/主色（边线色） */
  color: string;
  /** 填充色，缺省用白色底 */
  fillColor?: string;
  font: string;
  /** 标签字号 */
  labelSize: number;
  /** 0–1，状态动画进度 */
  t: number;
  /** 是否绘制高亮外环 */
  highlight?: boolean;
};

export const DEFAULT_FONT = '"HistoryMapSerifSC", serif';
const PAPER = "#f2ede2";

export function tierOf(t?: string): PlaceTier {
  const v = (t || "").toLowerCase();
  if (v in TIER_DRAW) return v as PlaceTier;
  // 中文 / 旧 tier 名兼容
  const map: Record<string, PlaceTier> = {
    都城: "capital", 首都: "capital", 陪都: "secondary_capital",
    州治: "seat", 郡治: "seat", 治所: "seat",
    县城: "county", 县: "county", 邑: "town", 聚落: "town",
    关隘: "pass", 津关: "pass", 要塞: "fortress", 军镇: "fortress",
    戍: "fort", 堡: "fort", 坞: "fort", 营寨: "camp", 烽燧: "beacon",
    渡口: "ferry", 津: "ferry", 港口: "port", 桥梁: "bridge", 峡: "gorge", 隘口: "gorge",
    粮仓: "granary", 陵墓: "tomb", 祠庙: "temple", 寺: "temple", 市: "market",
    // 旧 ACTION_LIBRARY 的四个 tier
    stronghold: "fortress", city: "county",
  };
  return map[t || ""] ?? "county";
}

// ---------- 符号绘制（均以 0,0 为中心） ----------
type DrawFn = (v: PlaceVisual) => React.ReactNode;

export const TIER_DRAW: Record<PlaceTier, DrawFn> = {
  capital: (v) => (
    <>
      <circle r={17} fill="none" stroke={v.color} strokeWidth={0.9} strokeOpacity={0.45} />
      <circle r={13} fill={PAPER} stroke={v.color} strokeWidth={2} />
      <circle r={5.5} fill={v.color} />
    </>
  ),
  secondary_capital: (v) => (
    <>
      <rect x={-11} y={-11} width={22} height={22} fill={PAPER} stroke={v.color} strokeWidth={2} />
      <circle r={5} fill={v.color} />
    </>
  ),
  seat: (v) => (
    <>
      <circle cy={-2} r={7} fill={v.color} />
      <line x1={-11} y1={10} x2={11} y2={10} stroke={v.color} strokeWidth={2} />
    </>
  ),
  county: (v) => <circle r={5} fill={v.color} />,
  town: (v) => <circle r={3.5} fill={v.color} fillOpacity={0.85} />,

  pass: (v) => (
    <>
      <line x1={-14} y1={-5} x2={14} y2={-5} stroke={v.color} strokeWidth={2.5} />
      <line x1={-14} y1={6} x2={14} y2={6} stroke={v.color} strokeWidth={2.5} />
      <line x1={-14} y1={-10} x2={-14} y2={11} stroke={v.color} strokeWidth={1.6} />
      <line x1={14} y1={-10} x2={14} y2={11} stroke={v.color} strokeWidth={1.6} />
    </>
  ),
  fortress: (v) => (
    <>
      <rect x={-11} y={-9} width={22} height={18} fill="none" stroke={v.color} strokeWidth={2} />
      <rect x={-13} y={-15} width={5} height={6} fill={v.color} />
      <rect x={-2.5} y={-15} width={5} height={6} fill={v.color} />
      <rect x={8} y={-15} width={5} height={6} fill={v.color} />
    </>
  ),
  fort: (v) => (
    <>
      <rect x={-7} y={-7} width={14} height={14} fill="none" stroke={v.color} strokeWidth={2} />
      <circle r={2.5} fill={v.color} />
    </>
  ),
  camp: (v) => (
    <>
      <path d="M -13 9 L 0 -11 L 13 9 Z" fill="none" stroke={v.color} strokeWidth={2} />
      <line x1={0} y1={-11} x2={0} y2={-19} stroke={v.color} strokeWidth={1.6} />
      <path d="M 0 -19 L 9 -16 L 0 -13 Z" fill={v.color} />
    </>
  ),
  beacon: (v) => {
    // 火苗闪烁
    const f = 0.75 + 0.25 * Math.sin(v.t * Math.PI * 6);
    return (
      <>
        <path d="M -9 9 L 0 -6 L 9 9 Z" fill="none" stroke={v.color} strokeWidth={2} />
        <circle cy={-13} r={4.5 * f} fill={v.color} fillOpacity={0.7} />
      </>
    );
  },

  ferry: (v) => {
    const off = (v.t * 8) % 8;
    return (
      <>
        <line x1={-14} y1={-4} x2={14} y2={-4} stroke={v.color} strokeWidth={2} />
        <path d={`M ${-14 + off} 5 q 4 -7 8 0 t 8 0 t 8 0`} fill="none"
              stroke={v.color} strokeWidth={1.6} />
      </>
    );
  },
  port: (v) => (
    <>
      <circle cy={-13} r={3.5} fill="none" stroke={v.color} strokeWidth={1.8} />
      <line x1={0} y1={-9} x2={0} y2={11} stroke={v.color} strokeWidth={2} />
      <line x1={-7} y1={-4} x2={7} y2={-4} stroke={v.color} strokeWidth={1.8} />
      <path d="M -10 2 Q 0 15 10 2" fill="none" stroke={v.color} strokeWidth={1.8} />
    </>
  ),
  bridge: (v) => (
    <>
      <path d="M -14 7 Q 0 -11 14 7" fill="none" stroke={v.color} strokeWidth={2} />
      <line x1={-14} y1={7} x2={-14} y2={13} stroke={v.color} strokeWidth={1.8} />
      <line x1={14} y1={7} x2={14} y2={13} stroke={v.color} strokeWidth={1.8} />
      <line x1={0} y1={-2} x2={0} y2={9} stroke={v.color} strokeWidth={1.4} />
    </>
  ),
  gorge: (v) => (
    <>
      <path d="M -15 10 L -7 -11 L 1 10 Z" fill="none" stroke={v.color} strokeWidth={2} />
      <path d="M -1 10 L 7 -11 L 15 10 Z" fill="none" stroke={v.color} strokeWidth={2} />
    </>
  ),
  granary: (v) => (
    <>
      <circle r={8} fill="none" stroke={v.color} strokeWidth={2} />
      <path d="M -9 -5 L 0 -13 L 9 -5 Z" fill={v.color} />
      <line x1={-3} y1={-14} x2={3} y2={-14} stroke={v.color} strokeWidth={1.4} />
    </>
  ),
  tomb: (v) => (
    <>
      <path d="M -10 8 L -5 -7 L 5 -7 L 10 8 Z" fill="none" stroke={v.color} strokeWidth={2} />
      <line x1={-12} y1={8} x2={-6} y2={8} stroke={v.color} strokeWidth={1.6} />
      <line x1={12} y1={8} x2={6} y2={8} stroke={v.color} strokeWidth={1.6} />
    </>
  ),
  temple: (v) => (
    <>
      <path d="M -14 6 L 0 -11 L 14 6 Z" fill="none" stroke={v.color} strokeWidth={2} />
      <line x1={-8} y1={6} x2={-8} y2={12} stroke={v.color} strokeWidth={1.6} />
      <line x1={8} y1={6} x2={8} y2={12} stroke={v.color} strokeWidth={1.6} />
      <line x1={-17} y1={6} x2={17} y2={6} stroke={v.color} strokeWidth={1.6} />
    </>
  ),
  market: (v) => (
    <>
      <circle r={9} fill="none" stroke={v.color} strokeWidth={2} />
      <rect x={-3.5} y={-3.5} width={7} height={7} fill="none" stroke={v.color} strokeWidth={1.6} />
    </>
  ),
};

// ---------- 状态绘制（叠加在符号之上/之外） ----------
export const STATE_EXTRA: Partial<Record<PlaceState, (v: PlaceVisual) => React.ReactNode>> = {
  besieged: (v) => (
    // 包围环缓慢旋转
    <circle r={15} fill="none" stroke={v.color} strokeWidth={1.4}
            strokeDasharray="4 3" transform={`rotate(${v.t * 360})`} strokeOpacity={0.9} />
  ),
  fallen: (v) => (
    <>
      <circle r={8} fill="#5F5E5A" fillOpacity={0.9} />
      <line x1={0} y1={0} x2={0} y2={-9} stroke={PAPER} strokeWidth={1.6} />
      <line x1={0} y1={0} x2={8} y2={5} stroke={PAPER} strokeWidth={1.6} />
      <line x1={0} y1={0} x2={-7} y2={6} stroke={PAPER} strokeWidth={1.6} />
    </>
  ),
  burned: (v) => (
    <>
      <circle r={6} fill="#444441" />
      {/* 烟柱：3 个渐隐圆上浮 */}
      {[0, 1, 2].map((i) => {
        const p = ((v.t + i / 3) % 1);
        return (
          <circle key={i} cx={p * 4 - 2} cy={-8 - p * 16} r={3 + p * 4}
                  fill="#5F5E5A" fillOpacity={(1 - p) * 0.4} />
        );
      })}
    </>
  ),
  abandoned: (v) => (
    <circle r={7} fill="none" stroke="#5F5E5A" strokeWidth={1.6} strokeDasharray="3 3" />
  ),
  newly_built: (v) => {
    // 半径 0→1 生长 + 落地涟漪
    const g = Math.min(1, v.t);
    return (
      <>
        <g transform={`scale(${g})`}>{TIER_DRAW[v.tier](v)}</g>
        {g < 1 && <circle r={6 + g * 22} fill="none" stroke={v.color} strokeWidth={2}
                          strokeOpacity={(1 - g) * 0.7} />}
      </>
    );
  },
  upgraded: (v) => {
    // 形态 morph 的近似：就位前先放大回落，暗示"升级"
    const s = 1 + Math.sin(Math.min(1, v.t) * Math.PI) * 0.28;
    return <g transform={`scale(${s})`}>{TIER_DRAW[v.tier](v)}</g>;
  },
  contested: (v) => (
    <>
      {/* 双色对角分半：表示争夺中 / 归属存疑（也用于「疆界存疑」标注） */}
      <path d="M 0 -14 A 14 14 0 0 1 0 14 Z" fill={v.color} fillOpacity={0.5} />
      <path d="M 0 -14 A 14 14 0 0 0 0 14 Z" fill="#8a7a63" fillOpacity={0.5} />
      <circle r={14} fill="none" stroke={v.color} strokeWidth={1.4} />
    </>
  ),
};

// ---------- 主组件 ----------
export type PlaceSpec = {
  name: string;
  lon: number;
  lat: number;
  tier?: PlaceTier | string;
  state?: PlaceState;
  color?: string;
  fillColor?: string;
  font?: string;
  labelSize?: number;
  highlight?: boolean;
  showLabel?: boolean;
  /** 状态动画进度 0–1（由调用方按自己的时间轴算） */
  progress?: number;
  /** renamed 状态的旧名 */
  renamedFrom?: string;
};

export const PlaceMarker: React.FC<{
  place: PlaceSpec;
  kind?: BasemapKind;
  frame?: number;
  W?: number;
  H?: number;
}> = ({ place, kind = "wide", frame = 0, W = 1920, H = 1080 }) => {
  const [x, y] = project(place.lon, place.lat, kind);
  if (!isFinite(x) || x < -60 || x > W + 60 || y < -60 || y > H + 60) return null;

  const tier = place.tier && (place.tier as PlaceTier) in TIER_DRAW
    ? (place.tier as PlaceTier) : tierOf(place.tier);
  const state: PlaceState = place.state ?? "normal";
  const v: PlaceVisual = {
    tier, state,
    color: place.color ?? "#8c3424",
    fillColor: place.fillColor,
    font: place.font ?? DEFAULT_FONT,
    labelSize: place.labelSize ?? (tier === "capital" ? 27 : tier === "seat" ? 23 : 20),
    t: place.progress ?? Math.min(1, frame / 30),
    highlight: place.highlight,
  };

  const isBig = tier === "capital" || tier === "secondary_capital";
  const dim = state === "fallen" || state === "abandoned";
  const labelOffset = isBig ? 20 : 13;

  return (
    <g opacity={dim ? 0.72 : 1}>
      {v.highlight && (
        <circle cx={x} cy={y} r={20} fill="none" stroke={v.color} strokeWidth={2} strokeOpacity={0.5} />
      )}
      <g transform={`translate(${x} ${y})`}>
        {TIER_DRAW[tier](v)}
        {STATE_EXTRA[state]?.(v)}
      </g>

      {/* 城名：白描边保证任何底色下可读（字体与字号均由 props 注入） */}
      {place.showLabel !== false && (
        <text x={x + labelOffset} y={y + 5} fontSize={v.labelSize}
              fill={dim ? "#6b5a49" : "#2a221b"}
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: v.font, fontWeight: isBig ? 500 : 400 }}>
          {place.renamedFrom && state === "renamed" && v.t < 0.5
            ? place.renamedFrom
            : place.name}
        </text>
      )}
    </g>
  );
};

/**
 * 图例：从符号定义自动生成。
 * 历史地图必须给图例 —— 观众不懂制图惯例，不标等于看不懂。
 */
export const PLACE_TIER_LABEL: Record<PlaceTier, string> = {
  capital: "都城", secondary_capital: "陪都", seat: "州治/郡治", county: "县城", town: "邑",
  pass: "关隘", fortress: "要塞", fort: "戍/堡", camp: "营寨", beacon: "烽燧",
  ferry: "渡口", port: "港口", bridge: "桥梁", gorge: "峡/隘口",
  granary: "粮仓", tomb: "陵墓", temple: "祠庙", market: "市",
};

export const PlaceLegend: React.FC<{
  tiers: PlaceTier[];
  x: number; y: number;
  width?: number;
  color?: string;
  font?: string;
  title?: string;
}> = ({ tiers, x, y, width = 132, color = "#8c3424", font = DEFAULT_FONT, title = "图例" }) => {
  const rowH = 30;
  const headH = 26;
  const rowPerCol = Math.max(1, Math.ceil(tiers.length / 2));
  const h = headH + rowPerCol * rowH + 12;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={0} y={0} width={width} height={h} rx={6}
            fill={PAPER} fillOpacity={0.92} stroke={color} strokeWidth={0.5} strokeOpacity={0.4} />
      <text x={10} y={18} fontSize={13} fill={color}
            style={{ fontFamily: font, fontWeight: 500 }}>{title}</text>
      {tiers.map((t, i) => {
        const col = Math.floor(i / rowPerCol);
        const row = i % rowPerCol;
        const cx = 22 + col * (width / 2 - 4);
        const cy = headH + row * rowH + 12;
        const v: PlaceVisual = { tier: t, state: "normal", color, font, labelSize: 12, t: 0.6 };
        return (
          <g key={t}>
            <g transform={`translate(${cx} ${cy}) scale(0.72)`}>{TIER_DRAW[t](v)}</g>
            <text x={cx + 16} y={cy + 5} fontSize={12} fill="#2a221b"
                  style={{ fontFamily: font }}>{PLACE_TIER_LABEL[t]}</text>
          </g>
        );
      })}
    </g>
  );
};
