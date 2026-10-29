/**
 * 人物图层：旗标式人物标记 + 进军路线箭头。
 * 肖像图为可选插槽（portraitUrl 存在时叠加），无图也能用纯排版标记。
 */
import React from "react";
import { Img, interpolate, staticFile } from "remotion";
import { PALETTE, project, shortName, type BasemapKind } from "./geo";

export type King = {
  id: string; name: string; title: string; realm: string;
  lon: number; lat: number; note: string;
  realm_note?: string; realm_valid?: string;
};

export type Route = { from: string; to: string; who: string; label: string; year: number };

/** 旗标：竖杆 + 燕尾旗面 + 姓名，锚定在真实坐标上 */
export const KingMarker: React.FC<{
  king: King;
  kind: BasemapKind;
  W: number; H: number;
  active: boolean;
  portraitUrl?: string;
  showAll?: boolean;
}> = ({ king, kind, W, H, active, portraitUrl, showAll = true }) => {
  const [x, y] = project(king.lon, king.lat, kind);
  if (!isFinite(x) || x < -80 || x > W + 80 || y < -80 || y > H + 80) return null;
  if (!showAll && !active) return null;

  const flag = active ? "#c65c4a" : "#8a7a63";
  const edge = active ? "#8c3424" : "#6b5a49";
  const h = active ? 74 : 58;
  const w = active ? 96 : 78;
  const nameSize = active ? 25 : 20;

  return (
    <g opacity={active ? 1 : 0.88}>
      {/* 锚点 */}
      <circle cx={x} cy={y} r={active ? 7 : 5} fill="#fffdf7" stroke={edge} strokeWidth={2.5} />
      {/* 旗杆 */}
      <line x1={x} y1={y} x2={x} y2={y - h} stroke={edge} strokeWidth={active ? 3.5 : 2.5} />
      {/* 燕尾旗面 */}
      <path
        d={`M ${x} ${y - h} L ${x + w} ${y - h + 10} L ${x + w} ${y - h + 30}
            L ${x + w - 14} ${y - h + 20} L ${x + w} ${y - h + 40} L ${x} ${y - h + 34} Z`}
        fill={flag} stroke={edge} strokeWidth={1.6}
      />
      {/* 封号 */}
      <text
        x={x + 8} y={y - h + 27} fontSize={nameSize - 5} fill="#fdf6ea"
        style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500 }}
      >
        {king.title}
      </text>
      {/* 姓名 */}
      <text
        x={x} y={y - h - 8} fontSize={nameSize} fill={active ? PALETTE.accent : PALETTE.ink}
        textAnchor="middle" stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
        style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500 }}
      >
        {king.name}
      </text>
      {/* 肖像圈位（图片由外层 HTML 叠加，SVG 内不用 Img） */}
      {portraitUrl && active && (
        <circle cx={x + w + 34} cy={y - h + 20} r={28} fill="#f2ede2" stroke={edge} strokeWidth={2} />
      )}
    </g>
  );
};

/** 进军路线：起兵地 → 目标，带推进感的箭头 */
export const RouteArrow: React.FC<{
  from: [number, number];
  to: [number, number];
  kind: BasemapKind;
  progress: number;   // 0–1，控制绘制长度
  color?: string;
  width?: number;
  label?: string;
}> = ({ from, to, kind, progress, color = "#9a2824", width = 4, label }) => {
  const [x1, y1] = project(from[0], from[1], kind);
  const [x2, y2] = project(to[0], to[1], kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;

  // 轻微弧线，避免直线呆板
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const cx = mx - (dy / len) * len * 0.12;
  const cy = my + (dx / len) * len * 0.12;

  const p = Math.max(0, Math.min(1, progress));
  const ex = (1 - p) * (1 - p) * x1 + 2 * (1 - p) * p * cx + p * p * x2;
  const ey = (1 - p) * (1 - p) * y1 + 2 * (1 - p) * p * cy + p * p * y2;
  const d = `M ${x1} ${y1} Q ${cx} ${cy} ${ex} ${ey}`;
  const head = p > 0.97;

  return (
    <g>
      <path d={d} fill="none" stroke="#fdfaf2" strokeWidth={width + 3} strokeOpacity={0.55} />
      <path
        d={d} fill="none" stroke={color} strokeWidth={width}
        strokeDasharray="10 7" strokeDashoffset={-p * 60}
        strokeLinecap="round"
      />
      {head && (
        <circle cx={ex} cy={ey} r={5} fill={color} />
      )}
      {label && p > 0.55 && (
        <text
          x={ex} y={ey - 16} fontSize={21} fill={color} textAnchor="middle"
          stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
          style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500 }}
        >
          {label}
        </text>
      )}
    </g>
  );
};

/** 叙事侧栏：列出当前镜头涉及的人物 */
export const KingPanel: React.FC<{
  kings: King[];
  activeId: string | null;
  opacity: number;
}> = ({ kings, activeId, opacity }) => {
  if (opacity <= 0.01) return null;
  return (
    <div style={{
      position: "absolute", left: 60, bottom: 190, width: 268,
      background: "rgba(250,246,238,0.94)", border: `1px solid ${PALETTE.realmEdge}aa`,
      borderRadius: 10, padding: "14px 16px", opacity,
      fontFamily: "HistoryMapSerifSC, serif",
    }}>
      <div style={{ fontSize: 20, color: PALETTE.realmEdge, letterSpacing: 2, marginBottom: 8 }}>
        八王
      </div>
      {kings.map((k) => (
        <div key={k.id} style={{
          display: "flex", justifyContent: "space-between", alignItems: "baseline",
          fontSize: 18, padding: "3px 0",
          color: activeId === k.id ? PALETTE.accent : PALETTE.ink,
          fontWeight: activeId === k.id ? 500 : 400,
        }}>
          <span>{k.name}</span>
          <span style={{ fontSize: 15, color: PALETTE.inkSoft }}>{k.title}</span>
        </div>
      ))}
    </div>
  );
};
