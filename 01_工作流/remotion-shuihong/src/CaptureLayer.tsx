/**
 * 攻取事件动画。八王之乱只有一个晋朝，不按政权分色；
 * 这里表达的是「城池易主」—— 诸王控制区色 + 归属时间线 + 事件驱动。
 *
 * 一次攻取 = 四步：
 *   ① 进军   箭头自起点推进到目标（RouteArrow progress 0→1）
 *   ② 抵达   箭头脉冲 + 目标城池高亮
 *   ③ 易主   城池标记从旧主色过渡到新主色，同�出现扩散光晕
 *   ④ 标注   事件文字浮出（年/月 + 事件类型 + 说明）
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { PALETTE, project, type BasemapKind } from "./geo";

export type King = {
  id: string; name: string; title: string; color: string;
  lon?: number; lat?: number; note?: string; realm?: string;
  realm_valid?: string; realm_note?: string;
};

export type City = {
  name: string; lon: number; lat: number; role?: string;
  /** [[起年, 止年, 控制者id], ...] 9999 表示延续 */
  control: [number, number, string | null][];
};

export type Event = {
  year: number; month?: number;
  type: "篡位" | "起兵" | "攻取" | "杀" | "陷落";
  actor: string | null;
  from?: string; to?: string; target?: string;
  text: string;
};

/** 取某年某城的控制者 */
export function controllerAt(city: City, year: number): string | null {
  for (const [a, b, who] of city.control) {
    if (a <= year && year <= b) return who;
  }
  return null;
}

/** 城池标记：颜色随控制者变化，易主时带过渡动画 */
export const CityMarker: React.FC<{
  city: City;
  year: number;
  prevYear?: number;        // 上一帧年份，用于易主过渡
  king: King | null;
  kind: BasemapKind;
  highlight?: boolean;
  captureProgress?: number; // 0–1，攻取进度
  /** 攻取瞬间覆盖控制者：captureProgress<0.5 用旧主，>0.5 用新主 */
  attacker?: King | null;
}> = ({ city, year, king, kind, highlight, captureProgress = 1, attacker = null }) => {
  const frame = useCurrentFrame();
  const [x, y] = project(city.lon, city.lat, kind);
  if (!isFinite(x) || x < -60 || x > 1980 || y < -60 || y > 1140) return null;

  // 攻取瞬间换主：进度过半即改旗易帜
  const displayKing = attacker
    ? (captureProgress > 0.5 ? attacker : king)
    : king;
  const color = displayKing ? displayKing.color : PALETTE.ink;
  const isCapital = city.name === "洛阳" || city.name === "长安";
  const r = isCapital ? 9 : 6;

  // 易主光晕：攻取瞬间扩散后收敛
  const ripple = captureProgress < 1 ? 1 - captureProgress : 0;
  const halo = 12 + ripple * 26;

  // 事件浮标：攻取完成后短暂显示
  const showFlag = captureProgress > 0.55;

  return (
    <g>
      {/* 攻取光晕 */}
      {ripple > 0 && (
        <circle cx={x} cy={y} r={halo} fill="none" stroke={color}
                strokeWidth={3} strokeOpacity={ripple * 0.8} />
      )}
      {/* 城池点 */}
      <circle cx={x} cy={y} r={r} fill="#fffdf7" stroke={color}
              strokeWidth={highlight ? 4 : 2.5} />
      {isCapital && (
        <circle cx={x} cy={y} r={r + 5} fill="none" stroke={color}
                strokeWidth={1.5} strokeOpacity={0.55} />
      )}
      {/* 城名 */}
      <text x={x + r + 7} y={y + 5} fontSize={isCapital ? 27 : 21}
            fill={PALETTE.ink} stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
            style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: isCapital ? 500 : 400 }}>
        {city.name}
      </text>
      {/* 控制者小旗（易主后） */}
      {showFlag && displayKing && (
        <g>
          <rect x={x - 6} y={y - r - 30} width={52} height={22} rx={3}
                fill={color} fillOpacity={0.92} />
          <text x={x - 2} y={y - r - 14} fontSize={15} fill="#fdf6ea"
                style={{ fontFamily: "HistoryMapSerifSC, serif" }}>
            {displayKing.title}
          </text>
        </g>
      )}
    </g>
  );
};

/** 事件卡：年/月 + 类型 + 说明，攻取时浮出 */
export const EventCard: React.FC<{
  ev: Event; king: King | null; opacity: number;
}> = ({ ev, king, opacity }) => {
  if (opacity <= 0.01) return null;
  const TYPE_COLOR: Record<string, string> = {
    "篡位": "#8e24aa", "起兵": "#c62828", "攻取": "#c62828",
    "杀": "#6d4c41", "陷落": "#37474f",
  };
  const c = TYPE_COLOR[ev.type] ?? PALETTE.accent;
  return (
    <div style={{
      position: "absolute", right: 72, top: 330, width: 300, opacity,
      background: "rgba(250,246,238,0.96)", borderLeft: `5px solid ${c}`,
      borderRadius: 8, padding: "14px 16px",
      fontFamily: "HistoryMapSerifSC, serif",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span style={{ fontSize: 15, color: c, letterSpacing: 1 }}>
          {ev.year}年{ev.month ? `${ev.month}月` : ""}
        </span>
        <span style={{
          fontSize: 15, color: "#fdf6ea", background: c,
          padding: "1px 9px", borderRadius: 3,
        }}>{ev.type}</span>
      </div>
      <div style={{ fontSize: 19, color: PALETTE.ink, marginTop: 8, lineHeight: 1.5 }}>
        {ev.text}
      </div>
      {king && (
        <div style={{ fontSize: 15, color: PALETTE.inkSoft, marginTop: 6 }}>
          主事：{king.name}（{king.title}）
        </div>
      )}
    </div>
  );
};

/**
 * 攻取序列：把一次「攻取」事件的四步串起来。
 * 返回箭头进度、城池易主进度、事件卡透明度。
 */
export function useCapture(frame: number, startFrame: number, dur: number) {
  const march = interpolate(frame, [startFrame, startFrame + dur * 0.55], [0, 1],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const capture = interpolate(frame, [startFrame + dur * 0.5, startFrame + dur * 0.75], [0, 1],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const card = interpolate(frame, [startFrame + dur * 0.6, startFrame + dur * 0.8], [0, 1],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  return { march, capture, card };
}
