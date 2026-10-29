/**
 * 事件动作层 —— 15 个事件动词的通用实现。
 *
 * 与 CaptureLayer 的关系：
 *   CaptureLayer 是「攻取」这一个动词的早期实现（八王之乱专用）。
 *   本文件是它的通用化：动词与具体朝代解耦，颜色 / 字体 / 底图全部由 props 注入。
 *   保留 CaptureLayer 不动（避免破坏现有成片），新逻辑一律走这里。
 *
 * 三层设计（见 Remotion-Studio-管线设计-v1.md 第三节）：
 *   ① 语义层 —— ActionVerb 枚举
 *   ② 参数层 —— ActionSpec（编译器 / 校验器负责检查必需字段）
 *   ③ 实现层 —— 每个 verb 一个组件，共用 useVerbTiming 的时序曲线
 *
 * 一句铁律：复用的是「行为 + 时序曲线」，不是素材。
 * 所以这里 **没有任何硬编码的颜色 / 字体 / 底图**。
 */
import React from "react";
import { PALETTE, project, type BasemapKind } from "./geo";

export type Pt = { lon: number; lat: number };

export type ActionVerb =
  | "march" | "capture" | "defeat" | "kill" | "siege" | "fall"
  | "ascend" | "depose" | "usurp" | "raise" | "defect" | "flee"
  | "enfeoff" | "ally" | "move_capital"
  /** 收束段：无地图动作，只用于承载结语字幕与拉镜 */
  | "aftermath";

export type ActionSpec = {
  verb: ActionVerb;
  /** 起始帧（相对本合成） */
  start: number;
  /** 持续帧数 */
  dur: number;
  from?: Pt;
  to?: Pt;
  at?: Pt;
  /** 主色；缺省用 PALETTE.realmEdge */
  color?: string;
  /** 次色（被击败 / 被废一方） */
  colorB?: string;
  label?: string;
  /** kill 用：印章字（诛 / 卒 / 赐死） */
  stamp?: string;
  name?: string;
  font?: string;
};

export const DEFAULT_FONT = '"HistoryMapSerifSC", serif';

const clamp = (v: number) => Math.max(0, Math.min(1, v));
const seg = (p: number, a: number, b: number) => clamp((p - a) / (b - a));

export type VerbTiming = {
  /** 总进度 0–1 */
  p: number;
  /** ① 接近 / 推进 */
  approach: number;
  /** ② 接触 / 撞击 */
  impact: number;
  /** ③ 结果 / 易主 */
  resolve: number;
  /** ④ 标注浮出 */
  card: number;
  /** 是否已开始 */
  active: boolean;
};

/**
 * 四段式标准时序 —— 所有动词共用。
 * 让不同动词的节奏一致，观众才会觉得「是同一部片子」。
 */
export function useVerbTiming(frame: number, start: number, dur: number): VerbTiming {
  const raw = (frame - start) / Math.max(1, dur);
  const p = clamp(raw);
  return {
    p,
    approach: seg(p, 0.0, 0.5),
    impact: seg(p, 0.42, 0.68),
    resolve: seg(p, 0.6, 0.88),
    card: seg(p, 0.7, 1.0),
    active: raw >= 0,
  };
}

// ---------- ① march 行军 ----------
export const MarchArrow: React.FC<{
  from: Pt; to: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; width?: number; label?: string; font?: string;
}> = ({ from, to, kind, timing, color = PALETTE.realmEdge, width = 4, label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x1, y1] = project(from.lon, from.lat, kind);
  const [x2, y2] = project(to.lon, to.lat, kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;

  // 轻微弧线，避免直线呆板
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const cx = (x1 + x2) / 2 - (dy / len) * len * 0.12;
  const cy = (y1 + y2) / 2 + (dx / len) * len * 0.12;

  const p = timing.approach;
  const ex = (1 - p) * (1 - p) * x1 + 2 * (1 - p) * p * cx + p * p * x2;
  const ey = (1 - p) * (1 - p) * y1 + 2 * (1 - p) * p * cy + p * p * y2;
  const d = `M ${x1} ${y1} Q ${cx} ${cy} ${ex} ${ey}`;

  return (
    <g>
      <path d={d} fill="none" stroke="#fdfaf2" strokeWidth={width + 3} strokeOpacity={0.55} />
      <path d={d} fill="none" stroke={color} strokeWidth={width}
            strokeDasharray="10 7" strokeDashoffset={-p * 60} strokeLinecap="round" />
      {p > 0.97 && <circle cx={ex} cy={ey} r={5.5} fill={color} />}
      {label && timing.card > 0.3 && (
        <text x={ex} y={ey - 16} fontSize={21} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ② defeat 击败 ----------
/**
 * 胜方箭头推进 → 相撞爆点 → 败方箭头倒退碎裂。
 * from = 胜方出发地，to = 败方位置。
 */
export const DefeatMark: React.FC<{
  from: Pt; to: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; colorB?: string; label?: string; font?: string;
}> = ({ from, to, kind, timing, color = PALETTE.realmEdge, colorB = "#6b5a49",
        label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [ax, ay] = project(from.lon, from.lat, kind);
  const [bx, by] = project(to.lon, to.lat, kind);
  if (!isFinite(ax) || !isFinite(bx)) return null;

  const t = timing.approach;
  // 胜方推进到接触点（留 12px 间距）
  const gx = bx + (ax - bx) * 0.12, gy = by + (ay - by) * 0.12;
  const hx = ax + (gx - ax) * t, hy = ay + (gy - ay) * t;

  // 败方后退：impact 后沿反方向退 34px 并碎裂
  const rec = timing.impact;
  const ux = (bx - ax) / (Math.hypot(bx - ax, by - ay) || 1);
  const uy = (by - ay) / (Math.hypot(bx - ax, by - ay) || 1);
  const rx = bx + ux * rec * 34, ry = by + uy * rec * 34;
  const fadeB = 1 - seg(timing.p, 0.55, 0.95) * 0.85;

  // 撞击爆点
  const burst = timing.impact > 0 && timing.impact < 1 ? Math.sin(timing.impact * Math.PI) : 0;

  return (
    <g>
      {/* 胜方箭头 */}
      <line x1={ax} y1={ay} x2={hx} y2={hy} stroke={color} strokeWidth={4.5} strokeLinecap="round" />
      <path d={`M ${hx} ${hy} l -13 -6 l 0 12 Z`} fill={color} />
      {/* 败方队列：三段，逐段碎裂后退 */}
      {[0, 1, 2].map((i) => {
        const off = i * 11;
        const breakT = seg(timing.impact, i * 0.18, i * 0.18 + 0.4);
        const px = rx + ux * off, py = ry + uy * off;
        return (
          <g key={i} opacity={fadeB * (1 - breakT * 0.6)}>
            <line x1={px} y1={py} x2={px + ux * 16} y2={py + uy * 16}
                  stroke={colorB} strokeWidth={4} strokeLinecap="round" />
            {breakT > 0 && (
              <circle cx={px} cy={py} r={2.5 + breakT * 4} fill={colorB}
                      fillOpacity={(1 - breakT) * 0.6} />
            )}
          </g>
        );
      })}
      {/* 撞击爆点 */}
      {burst > 0 && (
        <>
          <circle cx={gx} cy={gy} r={6 + burst * 26} fill="none" stroke={color}
                  strokeWidth={3} strokeOpacity={(1 - burst) * 0.9} />
          {Array.from({ length: 8 }).map((_, k) => {
            const a = (k / 8) * Math.PI * 2;
            const r0 = 8 + burst * 14, r1 = 8 + burst * 34;
            return <line key={k} x1={gx + Math.cos(a) * r0} y1={gy + Math.sin(a) * r0}
                         x2={gx + Math.cos(a) * r1} y2={gy + Math.sin(a) * r1}
                         stroke={color} strokeWidth={2} strokeOpacity={(1 - burst) * 0.8} />;
          })}
        </>
      )}
      {label && timing.card > 0.2 && (
        <text x={gx} y={gy - 30} fontSize={22} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ③ kill 斩杀 ----------
/** 印章落下 + 灰色扩散环；severity 由 stamp 字体现（诛 / 卒 / 赐死） */
export const KillStamp: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming;
  stamp?: string; color?: string; font?: string;
}> = ({ at, kind, timing, stamp = "诛", color = "#4a3a34", font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;

  const drop = timing.approach;             // 印章下落
  const scale = 2.2 - 1.2 * drop;           // 由大缩小砸下
  const ring = timing.resolve;              // 灰色扩散
  const op = seg(timing.p, 0.05, 0.2);

  return (
    <g opacity={op}>
      {ring > 0 && (
        <circle cx={x} cy={y} r={10 + ring * 30} fill="none" stroke="#5F5E5A"
                strokeWidth={2.5} strokeOpacity={(1 - ring) * 0.7} />
      )}
      <g transform={`translate(${x} ${y}) scale(${scale})`}>
        <circle r={15} fill="none" stroke={color} strokeWidth={2} />
        <text y={7} fontSize={20} fill={color} textAnchor="middle"
              style={{ fontFamily: font, fontWeight: 500 }}>{stamp}</text>
      </g>
    </g>
  );
};

// ---------- ④ siege 围城 ----------
/** 虚线包围环由外向内收拢，收拢后开始旋转 */
export const SiegeRing: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming; color?: string; label?: string; font?: string;
}> = ({ at, kind, timing, color = PALETTE.realmEdge, label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;

  const r = 66 - 48 * timing.approach;                 // 收拢
  const spin = timing.impact * 360 + timing.resolve * 180;
  const op = seg(timing.p, 0.02, 0.12);

  return (
    <g opacity={op}>
      <circle cx={x} cy={y} r={r} fill="none" stroke={color} strokeWidth={2}
              strokeDasharray="6 5" strokeOpacity={0.85}
              transform={`rotate(${spin} ${x} ${y})`} />
      <circle cx={x} cy={y} r={r - 6} fill="none" stroke={color} strokeWidth={1}
              strokeDasharray="3 6" strokeOpacity={0.45}
              transform={`rotate(${-spin * 0.7} ${x} ${y})`} />
      {/* 围城的兵力点，均布在环上 */}
      {timing.resolve > 0 && Array.from({ length: 6 }).map((_, k) => {
        const a = (k / 6) * Math.PI * 2 + timing.resolve * 0.8;
        return <circle key={k} cx={x + Math.cos(a) * r} cy={y + Math.sin(a) * r}
                       r={3} fill={color} fillOpacity={0.8} />;
      })}
      {label && timing.card > 0.2 && (
        <text x={x} y={y - r - 12} fontSize={20} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑤ fall 陷落 ----------
/** 暗化 + 裂纹自中心扩散 */
export const FallMark: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming; color?: string; label?: string; font?: string;
}> = ({ at, kind, timing, color = "#4a3a34", label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;

  const dk = timing.impact;      // 暗化程度
  const cr = timing.resolve;     // 裂纹扩张
  const N = 5;
  return (
    <g>
      {dk > 0 && <circle cx={x} cy={y} r={13} fill="#3a3330" fillOpacity={dk * 0.55} />}
      {Array.from({ length: N }).map((_, k) => {
        const a = (k / N) * Math.PI * 2 + 0.4;
        const r0 = 3, r1 = 3 + cr * (16 + (k % 3) * 6);
        return <line key={k} x1={x + Math.cos(a) * r0} y1={y + Math.sin(a) * r0}
                     x2={x + Math.cos(a) * r1} y2={y + Math.sin(a) * r1}
                     stroke="#2a221b" strokeWidth={1.8} strokeOpacity={0.75 * cr}
                     strokeLinecap="round" />;
      })}
      {label && timing.card > 0.2 && (
        <text x={x + 18} y={y + 6} fontSize={22} fill={color}
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑥ capture 攻取（沿用四段式，与 CaptureLayer 同源） ----------
/** 易主：填充色由旧主过渡到新主 + 扩散光晕 */
export const CaptureMark: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming;
  colorFrom?: string; colorTo?: string; label?: string; font?: string;
}> = ({ at, kind, timing, colorFrom = "#8a7a63", colorTo = PALETTE.realmEdge,
        label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;

  const flip = timing.impact;                 // 过半点即改旗
  const cur = flip > 0.5 ? colorTo : colorFrom;
  const ripple = timing.resolve < 1 ? 1 - timing.resolve : 0;

  return (
    <g>
      {ripple > 0 && (
        <circle cx={x} cy={y} r={12 + ripple * 28} fill="none" stroke={colorTo}
                strokeWidth={3} strokeOpacity={ripple * 0.8} />
      )}
      <circle cx={x} cy={y} r={7} fill={cur} />
      {label && timing.card > 0.3 && (
        <text x={x + 14} y={y + 5} fontSize={21} fill={colorTo}
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑦ raise / showFlag 起兵 ----------
/** 旗标升起（竖杆生长 + 旗面展开） */
export const FlagRise: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; label?: string; glyph?: string; font?: string;
}> = ({ at, kind, timing, color = PALETTE.realmEdge, label, glyph, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;

  const h = timing.approach * 62;              // 旗杆生长
  const w = timing.impact * 44;                // 旗面展开
  const op = seg(timing.p, 0.02, 0.15);
  return (
    <g opacity={op}>
      <circle cx={x} cy={y} r={6} fill="#fffdf7" stroke={color} strokeWidth={2.5} />
      <line x1={x} y1={y} x2={x} y2={y - h} stroke={color} strokeWidth={3} strokeLinecap="round" />
      {w > 0 && (
        <>
          <path d={`M ${x} ${y - h} L ${x + w} ${y - h + 8} L ${x + w} ${y - h + 26}
                    L ${x} ${y - h + 32} Z`} fill={color} fillOpacity={0.92} />
          {glyph && (
            <text x={x + 7} y={y - h + 22} fontSize={17} fill="#fdf6ea"
                  style={{ fontFamily: font, fontWeight: 500 }}>{glyph}</text>
          )}
        </>
      )}
      {label && timing.card > 0.3 && (
        <text x={x} y={y - h - 10} fontSize={21} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑧ flee 出奔 ----------
/** 快速短箭头 + 残影 */
export const FleeArrow: React.FC<{
  from: Pt; to: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; label?: string; font?: string;
}> = ({ from, to, kind, timing, color = "#6b5a49", label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x1, y1] = project(from.lon, from.lat, kind);
  const [x2, y2] = project(to.lon, to.lat, kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;

  const p = timing.approach;
  const ex = x1 + (x2 - x1) * p, ey = y1 + (y2 - y1) * p;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  return (
    <g>
      {/* 残影：三段递减透明度 */}
      {[0, 1, 2].map((i) => {
        const q = Math.max(0, p - (i + 1) * 0.08);
        const px = x1 + (x2 - x1) * q, py = y1 + (y2 - y1) * q;
        return <circle key={i} cx={px} cy={py} r={5 - i} fill={color}
                       fillOpacity={0.42 - i * 0.12} />;
      })}
      <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={color} strokeWidth={3}
            strokeDasharray="7 6" strokeLinecap="round" strokeOpacity={0.85} />
      <g transform={`translate(${ex} ${ey}) rotate(${(ang * 180) / Math.PI})`}>
        <path d="M 0 0 L -12 -5 L -12 5 Z" fill={color} />
      </g>
      {label && timing.card > 0.3 && (
        <text x={ex} y={ey - 14} fontSize={20} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑨ ally 会盟 ----------
/** 双色连线 + 中点盟标记 */
export const AllyLink: React.FC<{
  a: Pt; b: Pt; kind: BasemapKind; timing: VerbTiming;
  colorA?: string; colorB?: string; label?: string; font?: string;
}> = ({ a, b, kind, timing, colorA = "#8c3424", colorB = "#2f5d7c",
        label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x1, y1] = project(a.lon, a.lat, kind);
  const [x2, y2] = project(b.lon, b.lat, kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;

  const p = timing.approach;
  const ex = x1 + (x2 - x1) * p, ey = y1 + (y2 - y1) * p;
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const merge = timing.impact;
  return (
    <g>
      <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={colorA} strokeWidth={4} strokeLinecap="round" />
      <line x1={x2} y1={y2} x2={x1 + (x2 - x1) * (1 - p)} y2={y1 + (y2 - y1) * (1 - p)}
            stroke={colorB} strokeWidth={4} strokeLinecap="round" />
      {merge > 0 && (
        <g transform={`translate(${mx} ${my}) scale(${merge})`}>
          <circle r={13} fill="#fffdf7" stroke={colorA} strokeWidth={2} />
          <path d="M -6 0 L 0 -7 L 6 0" fill="none" stroke={colorA} strokeWidth={2.2} />
          <path d="M -6 6 L 0 -1 L 6 6" fill="none" stroke={colorB} strokeWidth={2.2} />
        </g>
      )}
      {label && timing.card > 0.3 && (
        <text x={mx} y={my - 22} fontSize={20} fill={colorA} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑩-⑮ 未单独实现者的占位说明 ----------
/**
 * ascend / depose / usurp / enfeoff / move_capital 属「人物层」或「版式层」动作：
 *   - ascend（即位） / usurp（篡位） / depose（废黜）→ 作用于人物牌，见 KingLayer.PortraitCard
 *   - enfeoff（册封）→ 色块分配，走 TerritoryShift（待补）
 *   - move_capital（迁都）→ 都城标记平移，可用 PlaceMarker + 位移插值组合
 * 这些动词的数据结构已定义（ActionVerb），实现按需补。
 */

// ---------- ⑩ ascend 即位 / usurp 篡位 ----------
/** 光晕自内向外扩散 + 旗帜升起。usurp 用暗红，ascend 用金色。 */
export const EnthroneMark: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; label?: string; glyph?: string; font?: string;
}> = ({ at, kind, timing, color = "#b8860b", label, glyph, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;
  const crown = timing.approach;                 // 光环扩张
  const rise = timing.impact;                    // 旗帜升起
  const op = seg(timing.p, 0.02, 0.12);
  return (
    <g opacity={op}>
      {crown > 0 && (
        <>
          <circle cx={x} cy={y} r={10 + crown * 34} fill="none" stroke={color}
                  strokeWidth={3} strokeOpacity={(1 - crown) * 0.85} />
          <circle cx={x} cy={y} r={6 + crown * 20} fill="none" stroke={color}
                  strokeWidth={1.5} strokeOpacity={(1 - crown) * 0.5} />
        </>
      )}
      <line x1={x} y1={y} x2={x} y2={y - rise * 54} stroke={color} strokeWidth={3} strokeLinecap="round" />
      {rise > 0.3 && (
        <path d={`M ${x} ${y - rise * 54} l 13 -7 l 0 14 Z`} fill={color} />
      )}
      {/* 冠饰：即位/篡位用不同形状区分 */}
      {rise > 0.6 && (
        <path d={`M ${x - 9} ${y - rise * 54 - 4} L ${x} ${y - rise * 54 - 14}
                  L ${x + 9} ${y - rise * 54 - 4} Z`} fill={color} />
      )}
      {label && timing.card > 0.25 && (
        <text x={x} y={y - 70} fontSize={21} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
      {glyph && rise > 0.5 && (
        <text x={x + 16} y={y - 46} fontSize={18} fill={color}
              style={{ fontFamily: font, fontWeight: 500 }}>{glyph}</text>
      )}
    </g>
  );
};

// ---------- ⑪ depose 废黜 ----------
/** 旗帜降下并灰化 —— 与 ascend 互为反向 */
export const DeposeMark: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; label?: string; font?: string;
}> = ({ at, kind, timing, color = "#6b5a49", label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;
  const h = 46 * (1 - timing.approach);          // 旗杆缩短
  const gray = timing.resolve;                   // 灰化
  const op = seg(timing.p, 0.02, 0.12);
  const c = gray > 0.5 ? "#8a8a86" : color;
  return (
    <g opacity={op}>
      <line x1={x} y1={y} x2={x} y2={y - h} stroke={c} strokeWidth={3} strokeLinecap="round"
            strokeOpacity={1 - gray * 0.5} />
      {h > 6 && (
        <path d={`M ${x} ${y - h} l -13 -7 l 0 14 Z`} fill={c} fillOpacity={1 - gray * 0.6} />
      )}
      {gray > 0 && (
        <circle cx={x} cy={y} r={8 + gray * 20} fill="none" stroke="#8a8a86"
                strokeWidth={2} strokeOpacity={(1 - gray) * 0.6} strokeDasharray="3 4" />
      )}
      {label && timing.card > 0.25 && (
        <text x={x + 14} y={y + 5} fontSize={21} fill="#6b5a49"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑫ enfeoff 册封 ----------
/** 从授予者向受封地投射色块 —— 表示土地分封 */
export const EnfeoffMark: React.FC<{
  from: Pt; to: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; label?: string; font?: string;
}> = ({ from, to, kind, timing, color = "#8c3424", label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x1, y1] = project(from.lon, from.lat, kind);
  const [x2, y2] = project(to.lon, to.lat, kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;
  const p = timing.approach;
  const ex = x1 + (x2 - x1) * p, ey = y1 + (y2 - y1) * p;
  const fill = timing.resolve;                   // 落地区块扩张
  return (
    <g>
      <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={color} strokeWidth={4}
            strokeDasharray="9 6" strokeLinecap="round" strokeOpacity={0.85} />
      {fill > 0 && (
        <rect x={x2 - 16 * fill} y={y2 - 16 * fill} width={32 * fill} height={32 * fill}
              rx={4} fill={color} fillOpacity={0.22} stroke={color}
              strokeWidth={1.6} strokeOpacity={0.7} />
      )}
      {label && timing.card > 0.25 && (
        <text x={x2} y={y2 - 26} fontSize={20} fill={color} textAnchor="middle"
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑬ move_capital 迁都 ----------
/** 都城标记沿轨迹平移，旧都留虚影 */
export const MoveCapital: React.FC<{
  from: Pt; to: Pt; kind: BasemapKind; timing: VerbTiming;
  color?: string; label?: string; font?: string;
}> = ({ from, to, kind, timing, color = "#8c3424", label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x1, y1] = project(from.lon, from.lat, kind);
  const [x2, y2] = project(to.lon, to.lat, kind);
  if (!isFinite(x1) || !isFinite(x2)) return null;
  const p = timing.approach;
  const cx = x1 + (x2 - x1) * p, cy = y1 + (y2 - y1) * p;
  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={2}
            strokeDasharray="5 6" strokeOpacity={0.5} />
      {/* 旧都虚影 */}
      <circle cx={x1} cy={y1} r={11} fill="none" stroke={color} strokeWidth={1.6}
              strokeDasharray="3 3" strokeOpacity={0.5} />
      {/* 迁动中的都城 */}
      <circle cx={cx} cy={cy} r={9} fill="none" stroke={color} strokeWidth={2.4} />
      <circle cx={cx} cy={cy} r={4} fill={color} />
      {timing.resolve > 0.6 && (
        <circle cx={x2} cy={y2} r={15} fill="none" stroke={color} strokeWidth={1.2}
                strokeOpacity={(1 - timing.resolve) * 0.8} />
      )}
      {label && timing.card > 0.25 && (
        <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 16} fontSize={20} fill={color}
              textAnchor="middle" stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- ⑭ defect 叛 / 降 ----------
/** 旗帜颜色由旧主翻转为新主 */
export const DefectMark: React.FC<{
  at: Pt; kind: BasemapKind; timing: VerbTiming;
  colorFrom?: string; colorTo?: string; label?: string; font?: string;
}> = ({ at, kind, timing, colorFrom = "#8a7a63", colorTo = "#c62828",
        label, font = DEFAULT_FONT }) => {
  if (!timing.active) return null;
  const [x, y] = project(at.lon, at.lat, kind);
  if (!isFinite(x)) return null;
  const t = timing.impact;
  const cur = t > 0.5 ? colorTo : colorFrom;
  const h = 40;
  return (
    <g>
      <line x1={x} y1={y} x2={x} y2={y - h} stroke={cur} strokeWidth={3} strokeLinecap="round" />
      <path d={`M ${x} ${y - h} l 16 -8 l 0 16 Z`} fill={cur} />
      {/* 翻转瞬间的爆点 */}
      {t > 0 && t < 1 && (
        <circle cx={x} cy={y - h / 2} r={8 + t * 18} fill="none" stroke={colorTo}
                strokeWidth={2.5} strokeOpacity={(1 - t) * 0.9} />
      )}
      {label && timing.card > 0.25 && (
        <text x={x + 20} y={y - h / 2} fontSize={20} fill={colorTo}
              stroke="#fdfaf2" strokeWidth={3.5} paintOrder="stroke"
              style={{ fontFamily: font, fontWeight: 500 }}>{label}</text>
      )}
    </g>
  );
};

// ---------- 统一分发 ----------
/** 单个动作。抽成组件是因为要在组件体内调用 hook（不能在 .map 里直接调） */
const ActionItem: React.FC<{
  a: ActionSpec; kind: BasemapKind; frame: number; font: string;
}> = ({ a, kind, frame, font }) => {
  const t = useVerbTiming(frame, a.start, a.dur);
  if (!t.active) return null;
  switch (a.verb) {
    case "march":
      return a.from && a.to
        ? <MarchArrow from={a.from} to={a.to} kind={kind} timing={t}
                      color={a.color} label={a.label} font={font} />
        : null;
    case "defeat":
      return a.from && a.to
        ? <DefeatMark from={a.from} to={a.to} kind={kind} timing={t}
                      color={a.color} colorB={a.colorB} label={a.label} font={font} />
        : null;
    case "kill":
      return a.at
        ? <KillStamp at={a.at} kind={kind} timing={t}
                     stamp={a.stamp} color={a.color} font={font} />
        : null;
    case "siege":
      return a.at
        ? <SiegeRing at={a.at} kind={kind} timing={t}
                     color={a.color} label={a.label} font={font} />
        : null;
    case "fall":
      return a.at
        ? <FallMark at={a.at} kind={kind} timing={t}
                    color={a.color} label={a.label} font={font} />
        : null;
    case "capture":
      return a.at
        ? <CaptureMark at={a.at} kind={kind} timing={t}
                       colorFrom={a.colorB} colorTo={a.color} label={a.label} font={font} />
        : null;
    case "raise":
      return a.at
        ? <FlagRise at={a.at} kind={kind} timing={t}
                    color={a.color} label={a.label} glyph={a.name} font={font} />
        : null;
    case "flee":
      return a.from && a.to
        ? <FleeArrow from={a.from} to={a.to} kind={kind} timing={t}
                     color={a.color} label={a.label} font={font} />
        : null;
    case "ally":
      return a.from && a.to
        ? <AllyLink a={a.from} b={a.to} kind={kind} timing={t}
                    colorA={a.color} colorB={a.colorB} label={a.label} font={font} />
        : null;
    case "ascend":
      return a.at
        ? <EnthroneMark at={a.at} kind={kind} timing={t} color={a.color ?? "#b8860b"}
                        label={a.label} glyph={a.name} font={font} />
        : null;
    case "usurp":
      return a.at
        ? <EnthroneMark at={a.at} kind={kind} timing={t} color={a.color ?? "#8e24aa"}
                        label={a.label} glyph={a.name} font={font} />
        : null;
    case "depose":
      return a.at
        ? <DeposeMark at={a.at} kind={kind} timing={t} color={a.color} label={a.label} font={font} />
        : null;
    case "enfeoff":
      return a.from && a.to
        ? <EnfeoffMark from={a.from} to={a.to} kind={kind} timing={t}
                       color={a.color} label={a.label} font={font} />
        : null;
    case "move_capital":
      return a.from && a.to
        ? <MoveCapital from={a.from} to={a.to} kind={kind} timing={t}
                       color={a.color} label={a.label} font={font} />
        : null;
    case "defect":
      return a.at
        ? <DefectMark at={a.at} kind={kind} timing={t} colorFrom={a.colorB}
                      colorTo={a.color} label={a.label} font={font} />
        : null;
    default:
      return null;   // aftermath：无地图动作，仅承载字幕
  }
};

export const ActionLayer: React.FC<{
  actions: ActionSpec[];
  kind?: BasemapKind;
  frame: number;
  font?: string;
}> = ({ actions, kind = "wide", frame, font = DEFAULT_FONT }) => (
  <>
    {actions.map((a, i) => (
      <ActionItem key={i} a={a} kind={kind} frame={frame} font={font} />
    ))}
  </>
);
