/**
 * 通用镜头组件 DirectorShot —— 消费脚本 JSON 渲染单个镜头。
 *
 * 解决的根本问题：原先 7 条镜头的脚本硬编码在 Root.tsx 的 `const SHOTS: BW[]`，
 * 加一集要改代码。现在镜头完全由数据驱动，**改脚本 = 改 JSON**。
 *
 * 与旧组件的关系：
 *   - 取代 Root.tsx 内联的 BWShot（版式已抽到 Layout.tsx 的 ShotChrome）
 *   - 城池符号改用 Symbols.tsx 的 PlaceMarker（18 符号 + 10 状态）
 *   - 事件动画改用 ActionLayer.tsx（15 动词）
 *   - 坐标由 MainData.ts 按 placeId 从主表解析
 */
import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import type { FeatureCollection } from "geojson";
import { BASEMAP_FILE, H, PALETTE, W, project, type BasemapKind } from "./geo";
import { LabelLayer } from "./HistoryLayers";
import { KingMarker, KingPanel, type King, type Route } from "./KingLayer";
import { ShotChrome } from "./Layout";
import { ActionLayer, type ActionSpec } from "./ActionLayer";
import { PlaceMarker, type PlaceState } from "./Symbols";
import { Transition } from "./Camera";
import { TerritoryGrow, BorderFlow, LabelEmerge, YearTick } from "./Layers";

// ---------- 脚本 JSON 的类型 ----------
export type ShotAction = Omit<ActionSpec, "start" | "dur"> & {
  /** 秒（脚本用秒，渲染时换算成帧） */
  startSec?: number;
  durSec?: number;
  at?: { lon: number; lat: number };
  from?: { lon: number; lat: number };
  to?: { lon: number; lat: number };
};

export type EpisodeShot = {
  title?: string;
  subtitle?: string;
  year?: number;
  yearLabel?: string;
  focus: [number, number];
  zoom: number;
  durationInFrames: number;
  basemap?: BasemapKind;
  narration?: string;
  disclaimer?: string;
  highlight?: string[];
  activeKing?: string | null;
  routeOf?: string;
  /** 本镜要显示的地点符号（坐标由 placeId 从主表解析） */
  places?: {
    placeId: string;
    state?: PlaceState;
    tier?: string;
    color?: string;
    progress?: number;
    showLabel?: boolean;
  }[];
  /** 事件动画 */
  actions?: ShotAction[];
  /** 入场转场（如 ink_bleed） */
  transitionIn?: string;
  /** 出场转场 */
  transitionOut?: string;
  /** 整镜震动（攻城/决战） */
  shake?: boolean;
  /** 定格：在此时长（帧）内镜头不动，让观众读字幕 */
  holdFrames?: number;
  /** L4 疆域生长：用本镜的 zones 数据做色块扩张 */
  territoryGrow?: { color?: string; origin?: [number, number]; progress?: number };
  /** L4 边界流动（虚线沿边界游走，表示边界不稳） */
  borderFlow?: { color?: string; speed?: number };
  /** L4 地名逐个浮现 */
  emergeLabels?: { text: string; lon: number; lat: number; rank?: number; size?: number; color?: string }[];
  /** L5 年份跳变 */
  yearTick?: { from: number; to: number; spanFrames?: number; startFrame?: number };
};

export type Episode = {
  id: string;
  title: string;
  dynasty?: string;
  year: number;
  fps?: number;
  sourceNote?: string;
  shots: EpisodeShot[];
};

export type KingBundle = {
  kings: King[];
  cities: { name: string; lon: number; lat: number; role?: string; placeId?: string }[];
  routes: Route[];
};

// ---------- 镜头组件 ----------
export const DirectorShot: React.FC<{
  shot: EpisodeShot;
  episode: Episode;
  data: { labels: FeatureCollection; zones: FeatureCollection };
  kings: KingBundle | null;
  font?: string;
  /** placeId → 坐标（由 MainData 主表解析后注入） */
  coords: Record<string, { lon: number; lat: number; name: string }>;
}> = ({ shot, episode, data, kings, font, coords }) => {
  void episode;
  const frame = useCurrentFrame();
  const kind: BasemapKind = shot.basemap ?? "wide";
  const total = shot.durationInFrames;
  const fps = 30;

  const holdEnd = shot.holdFrames ?? 0;
  const mf = frame < holdEnd ? 0 : frame - holdEnd;   // 定格后的有效运动帧
  const zoom = interpolate(mf, [0, Math.min(total, 60)], [1, shot.zoom], {
    extrapolateRight: "clamp",
  });
  const drift = interpolate(mf, [0, total], [0, -26], { extrapolateRight: "clamp" });
  const [fx, fy] = project(shot.focus[0], shot.focus[1], kind);
  const [wx, wy] = project(113.5, 35.2, kind);
  const cx = interpolate(mf, [0, 60], [wx, fx], { extrapolateRight: "clamp" });
  const cy = interpolate(mf, [0, 60], [wy, fy], { extrapolateRight: "clamp" });

  // 震动：高频小幅位移（攻城 / 决战瞬间）
  const shX = shot.shake ? Math.sin(frame * 2.7) * 4 + Math.sin(frame * 5.3) * 2 : 0;
  const shY = shot.shake ? Math.cos(frame * 3.1) * 3 + Math.cos(frame * 6.1) * 1.6 : 0;

  const fade = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const head = interpolate(frame, [4, 22], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const cap = interpolate(frame, [26, 42], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const panel = interpolate(frame, [18, 34], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const portraitOp = interpolate(frame, [16, 34], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  // 路线推进（兼容旧的 routeOf 机制）
  const route = kings?.routes.find((r) => r.who === shot.routeOf);
  const rp = route
    ? interpolate(frame, [30, Math.max(31, total - 20)], [0, 1], { extrapolateRight: "clamp" })
    : 0;
  const coordOf = (name: string): [number, number] => {
    const c = kings?.cities.find((x) => x.name === name);
    return c ? [c.lon, c.lat] : [0, 0];
  };

  // actions：秒 → 帧
  const actions: ActionSpec[] = (shot.actions ?? []).map((a) => ({
    ...a,
    start: Math.round((a.startSec ?? 0) * fps),
    dur: Math.round((a.durSec ?? 2) * fps),
  })) as ActionSpec[];

  const activeKing = shot.activeKing
    ? kings?.kings.find((k) => k.id === shot.activeKing)
    : undefined;

  return (
    <div style={{ position: "absolute", inset: 0, background: PALETTE.paper, opacity: fade }}>
      {/* 地图层 */}
      <div style={{
        position: "absolute", width: W, height: H, left: "50%", top: "50%",
        transform: `translate(${-W / 2 + drift + shX}px, ${-H / 2 + shY}px) scale(${zoom})`,
        transformOrigin: `${cx}px ${cy}px`,
      }}>
        <Img src={staticFile(BASEMAP_FILE[kind] ?? "basemap_wide.png")}
             style={{ width: W, height: H, display: "block" }} />
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}
             style={{ position: "absolute", inset: 0 }}>
          {/* 地名标签（旧层，保留） */}
          <LabelLayer labels={data.labels} kind={kind} zoom={zoom}
                      highlight={shot.highlight ?? []} W={W} H={H} />

          {/* 地点符号（新：18 符号 + 10 状态，坐标由主表解析） */}
          {(shot.places ?? []).map((p) => {
            const c = coords[p.placeId];
            if (!c) return null;
            return (
              <PlaceMarker
                key={p.placeId}
                place={{
                  name: c.name, lon: c.lon, lat: c.lat,
                  tier: p.tier, state: p.state,
                  color: p.color, progress: p.progress, showLabel: p.showLabel,
                }}
                kind={kind}
                frame={frame}
                W={W} H={H}
              />
            );
          })}

          {/* 人物旗标 */}
          {kings?.kings.map((k) => (
            <KingMarker key={k.id} king={k} kind={kind} W={W} H={H}
                        active={shot.activeKing === k.id} showAll={!shot.activeKing} />
          ))}

          {/* L4 疆域生长 / 边界流动 */}
          {shot.territoryGrow && (
            <TerritoryGrow data={data.zones} kind={kind}
                           progress={shot.territoryGrow.progress
                             ?? interpolate(frame, [0, Math.round(total * 0.6)], [0, 1],
                                { extrapolateRight: "clamp" })}
                           color={shot.territoryGrow.color}
                           origin={shot.territoryGrow.origin} />
          )}
          {shot.borderFlow && (
            <BorderFlow data={data.zones} kind={kind}
                        color={shot.borderFlow.color} speed={shot.borderFlow.speed} />
          )}

          {/* L4 地名逐个浮现 */}
          {shot.emergeLabels && (
            <LabelEmerge labels={shot.emergeLabels} kind={kind}
                         spanFrames={Math.round(total * 0.5)} font={font} />
          )}

          {/* L5 年份跳变 */}
          {shot.yearTick && (
            <YearTick from={shot.yearTick.from} to={shot.yearTick.to}
                      spanFrames={shot.yearTick.spanFrames ?? Math.round(total * 0.6)}
                      startFrame={shot.yearTick.startFrame ?? 0} font={font} />
          )}

          {/* 事件动画（15 动词） */}
          <ActionLayer actions={actions} kind={kind} frame={frame} font={font} />
        </svg>
      </div>

      {/* 旧路线箭头（兼容 routeOf） */}
      {route && (
        <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
          <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
            <RouteArrowCompat from={coordOf(route.from)} to={coordOf(route.to)}
                              kind={kind} progress={rp} label={route.label} />
          </svg>
        </div>
      )}

      {/* 版式层（与 HistoryShot 共用 ShotChrome） */}
      <ShotChrome
        title={shot.title}
        subtitle={shot.subtitle}
        yearLabel={shot.yearLabel ?? (shot.year ? `公元 ${shot.year} 年` : undefined)}
        disclaimer={shot.disclaimer}
        narration={shot.narration}
        opacity={{ head, badge: head, disclaimer: cap, narration: interpolate(frame, [20, 36], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }) }}
        sideSlot={
          activeKing && portraitOp > 0.01 ? (
            <PortraitCardCompat king={activeKing} opacity={portraitOp} />
          ) : null
        }
        leftSlot={
          kings ? <KingPanel kings={kings.kings} activeId={shot.activeKing ?? null} opacity={panel} /> : null
        }
      />

      {/* 转场层（L3）：墨迹扩散 / 卷轴展开 */}
      {shot.transitionIn && (
        <Transition type={shot.transitionIn}
          progress={interpolate(frame, [0, Math.round(fps * 0.7)], [0, 1],
            { extrapolateRight: "clamp", extrapolateLeft: "clamp" })} />
      )}
      {shot.transitionOut && (
        <Transition type={shot.transitionOut}
          progress={interpolate(frame, [total - Math.round(fps * 0.7), total], [0, 1],
            { extrapolateRight: "clamp", extrapolateLeft: "clamp" })} />
      )}
    </div>
  );
};

// ---------- 内部小部件（避免循环依赖，就地实现） ----------
const RouteArrowCompat: React.FC<{
  from: [number, number]; to: [number, number];
  kind: BasemapKind; progress: number; label?: string;
}> = ({ from, to, kind, progress, label }) => {
  const [x1, y1] = project(from[0], from[1], kind);
  const [x2, y2] = project(to[0], to[1], kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;
  const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
  const cx = (x1 + x2) / 2 - (dy / len) * len * 0.12;
  const cy = (y1 + y2) / 2 + (dx / len) * len * 0.12;
  const p = Math.max(0, Math.min(1, progress));
  const ex = (1 - p) * (1 - p) * x1 + 2 * (1 - p) * p * cx + p * p * x2;
  const ey = (1 - p) * (1 - p) * y1 + 2 * (1 - p) * p * cy + p * p * y2;
  const d = `M ${x1} ${y1} Q ${cx} ${cy} ${ex} ${ey}`;
  return (
    <g>
      <path d={d} fill="none" stroke="#fdfaf2" strokeWidth={7} strokeOpacity={0.55} />
      <path d={d} fill="none" stroke={PALETTE.accent} strokeWidth={4}
            strokeDasharray="10 7" strokeDashoffset={-p * 60} strokeLinecap="round" />
      {p > 0.97 && <circle cx={ex} cy={ey} r={5.5} fill={PALETTE.accent} />}
      {label && p > 0.55 && (
        <text x={ex} y={ey - 16} fontSize={21} fill={PALETTE.accent} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: '"HistoryMapSerifSC", serif', fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

const PortraitCardCompat: React.FC<{ king: King; opacity: number }> = ({ king, opacity }) => (
  <div style={{
    position: "absolute", right: 72, top: 150, width: 250,
    background: "rgba(250,246,238,0.96)", border: `2px solid ${PALETTE.realmEdge}`,
    borderRadius: 12, padding: 16, opacity, fontFamily: '"HistoryMapSerifSC", serif',
  }}>
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <Img src={staticFile(`portraits/${king.id}_sq.png`)}
           style={{ width: 72, height: 72, borderRadius: 6 }} />
      <div>
        <div style={{ fontSize: 28, color: PALETTE.ink, fontWeight: 500 }}>{king.name}</div>
        <div style={{ fontSize: 19, color: PALETTE.realmEdge, marginTop: 2 }}>{king.title}</div>
      </div>
    </div>
    {king.note && (
      <div style={{ fontSize: 16, color: PALETTE.inkSoft, marginTop: 10, lineHeight: 1.5 }}>
        {king.note}
      </div>
    )}
  </div>
);
