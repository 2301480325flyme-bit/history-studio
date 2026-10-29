/**
 * 图层与数据动画（L4 / L5）。
 *
 * 补齐 视觉符号与动画库-v1.md 中最高频的 4 项：
 *   L4 territory_grow  疆域从中心向外生长
 *   L4 border_flow     边界虚线流动（表示动态/不稳定边界）
 *   L4 label_emerge    地名逐个浮现（按重要性排序）
 *   L5 year_tick       年份数字跳变
 *
 * 同样遵守：不硬编码颜色/字体，全部 props 注入。
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { FeatureCollection } from "geojson";
import { geoMercator, geoPath } from "d3-geo";
import { project, type BasemapKind } from "./geo";

const DEFAULT_FONT = '"HistoryMapSerifSC", serif';

// ---------- L4 territory_grow 疆域生长 ----------
/**
 * 色块自中心向外生长。实现方式：用 clipPath 的圆形遮罩从 0 放大到覆盖全屏。
 * 不是真的做拓扑生长（那需要复杂几何），而是可控的视觉近似 —— 如实说明。
 */
export const TerritoryGrow: React.FC<{
  data: FeatureCollection;
  kind: BasemapKind;
  progress: number;
  color?: string;
  origin?: [number, number];
  opacity?: number;
  strokeWidth?: number;
}> = ({ data, kind, progress, color = "#bc8f7d", origin = [113.5, 35.2], opacity = 0.55, strokeWidth = 2 }) => {
  const [cx, cy] = project(origin[0], origin[1], kind);
  const proj = React.useMemo(() => {
    const v = kind === "core"
      ? { center: [113.5, 35.2] as [number, number], scale: 13500 }
      : { center: [113.5, 35.2] as [number, number], scale: 6000 };
    return geoMercator().center(v.center).scale(v.scale).translate([960, 540]);
  }, [kind]);
  const pathGen = React.useMemo(() => geoPath(proj), [proj]);
  const r = Math.max(0, Math.min(1, progress)) * 2200;
  const clipId = `tg-${Math.round(cx)}-${Math.round(cy)}`;

  if (r <= 0) return null;
  return (
    <>
      <defs>
        <clipPath id={clipId}>
          <circle cx={cx} cy={cy} r={r} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        {data.features.map((f, i) => {
          const d = pathGen(f as any);
          if (!d) return null;
          return (
            <path key={i} d={d} fill={color} fillOpacity={opacity}
                  stroke={color} strokeWidth={strokeWidth} strokeOpacity={0.8} />
          );
        })}
      </g>
      {/* 生长前沿的涟漪 */}
      {r < 2200 && (
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color}
                strokeWidth={1.5} strokeOpacity={0.5} />
      )}
    </>
  );
};

// ---------- L4 border_flow 边界流动 ----------
/** 边界虚线沿路径流动，表示「边界不稳定 / 正在变化」 */
export const BorderFlow: React.FC<{
  data: FeatureCollection;
  kind: BasemapKind;
  color?: string;
  speed?: number;
  dash?: string;
  width?: number;
}> = ({ data, kind, color = "#8c3424", speed = 40, dash = "10 8", width = 2.5 }) => {
  const frame = useCurrentFrame();
  const proj = React.useMemo(() => {
    const v = kind === "core"
      ? { center: [113.5, 35.2] as [number, number], scale: 13500 }
      : { center: [113.5, 35.2] as [number, number], scale: 6000 };
    return geoMercator().center(v.center).scale(v.scale).translate([960, 540]);
  }, [kind]);
  const pathGen = React.useMemo(() => geoPath(proj), [proj]);
  const offset = -(frame * speed) / 30;

  return (
    <g>
      {data.features.map((f, i) => {
        const d = pathGen(f as any);
        if (!d) return null;
        return (
          <path key={i} d={d} fill="none" stroke={color} strokeWidth={width}
                strokeDasharray={dash} strokeDashoffset={offset}
                strokeLinecap="round" strokeOpacity={0.9} />
        );
      })}
    </g>
  );
};

// ---------- L4 label_emerge 地名逐个浮现 ----------
export type EmergeLabel = {
  text: string;
  lon: number;
  lat: number;
  /** 重要性：0 最先出现，数字越大越晚 */
  rank?: number;
  size?: number;
  color?: string;
};

/** 地名按重要度排序逐个浮现（先都城、后郡县）—— 避免一次性砸满屏幕 */
export const LabelEmerge: React.FC<{
  labels: EmergeLabel[];
  kind: BasemapKind;
  /** 全部浮现完所需帧数 */
  spanFrames?: number;
  startFrame?: number;
  font?: string;
}> = ({ labels, kind, spanFrames = 60, startFrame = 0, font = DEFAULT_FONT }) => {
  const frame = useCurrentFrame();
  const sorted = [...labels].sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  const n = Math.max(1, sorted.length);
  const step = spanFrames / n;

  return (
    <g>
      {sorted.map((l, i) => {
        const t0 = startFrame + i * step;
        const op = interpolate(frame, [t0, t0 + step * 0.9], [0, 1],
          { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
        if (op <= 0) return null;
        const [x, y] = project(l.lon, l.lat, kind);
        if (!isFinite(x)) return null;
        return (
          <g key={l.text} opacity={op}>
            <circle cx={x} cy={y} r={3.5} fill={l.color ?? "#8c3424"} />
            <text x={x + 9} y={y + 5} fontSize={l.size ?? 20} fill="#2a221b"
                  stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
                  style={{ fontFamily: font, fontWeight: 500 }}>{l.text}</text>
          </g>
        );
      })}
    </g>
  );
};

// ---------- L5 year_tick 年份跳变 ----------
/** 年份数字滚动。用于「长时段压缩」叙述。
 *  ⚠️ 默认位置避开右上角的年份徽标（ShotChrome 在 right:72 / top:50），
 *     否则两者会叠在一起。 */
export const YearTick: React.FC<{
  from: number;
  to: number;
  startFrame?: number;
  spanFrames?: number;
  x?: number;
  y?: number;
  size?: number;
  color?: string;
  font?: string;
  suffix?: string;
}> = ({ from, to, startFrame = 0, spanFrames = 40, x = 1700, y = 235,
        size = 40, color = "#8c3424", font = DEFAULT_FONT, suffix = "年" }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [startFrame, startFrame + spanFrames], [0, 1],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const year = Math.round(from + (to - from) * p);
  return (
    <g>
      <text x={x} y={y} fontSize={size} fill={color} textAnchor="end"
            style={{ fontFamily: font, fontWeight: 500, letterSpacing: 2 }}>
        {year}{suffix}
      </text>
      {/* 跳变时的闪烁提示 */}
      {p < 1 && (
        <rect x={x - 130} y={y - size} width={140} height={size * 1.3} rx={4}
              fill={color} fillOpacity={0.06} />
      )}
    </g>
  );
};
