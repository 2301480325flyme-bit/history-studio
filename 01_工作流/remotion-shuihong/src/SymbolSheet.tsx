/**
 * 符号总表（验证用）—— 把 18 个 tier 与 10 个 state 全画一遍。
 * 用于肉眼验收符号库，不参与正式成片。
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import {
  DEFAULT_FONT, PLACE_TIER_LABEL, STATE_EXTRA, TIER_DRAW,
  type PlaceTier, type PlaceState, type PlaceVisual,
} from "./Symbols";

const ALL_TIERS: PlaceTier[] = [
  "capital", "secondary_capital", "seat", "county", "town",
  "pass", "fortress", "fort", "camp", "beacon",
  "ferry", "port", "bridge", "gorge",
  "granary", "tomb", "temple", "market",
];

const ALL_STATES: PlaceState[] = [
  "normal", "controlled", "contested", "besieged", "fallen",
  "burned", "abandoned", "newly_built", "renamed", "upgraded",
];

const COLOR = "#8c3424";
const PAPER = "#f2ede2";
const INK = "#2a221b";

const StateDraw: React.FC<{ state: PlaceState; t: number }> = ({ state, t }) => {
  const v: PlaceVisual = { tier: "county", state, color: COLOR, font: DEFAULT_FONT, labelSize: 14, t };
  return <g>{TIER_DRAW.county(v)}{STATE_EXTRA[state]?.(v)}</g>;
};

export const SymbolSheet: React.FC = () => {
  const frame = useCurrentFrame();
  const t = Math.min(1, frame / 45);
  const cols = 6;
  const cellW = 300;
  const cellH = 150;
  const x0 = 60;
  const y0 = 165;

  return (
    <AbsoluteFill style={{ background: PAPER }}>
      <svg width={1920} height={1080} viewBox="0 0 1920 1080">
        <text x={60} y={54} fontSize={30} fill={INK}
              style={{ fontFamily: DEFAULT_FONT, fontWeight: 500 }}>地点符号库 · 18 个符号</text>
        <text x={60} y={84} fontSize={17} fill="#6b5a49" style={{ fontFamily: DEFAULT_FONT }}>
          第二行起为状态层（同一符号的不同状态）
        </text>

        {ALL_TIERS.map((tier, i) => {
          const c = i % cols;
          const r = Math.floor(i / cols);
          const cx = x0 + c * cellW + cellW / 2;
          const cy = y0 + r * cellH;
          const vv: PlaceVisual = { tier, state: "normal", color: COLOR, font: DEFAULT_FONT, labelSize: 14, t };
          return (
            <g key={tier}>
              <rect x={cx - cellW / 2 + 10} y={cy - 55} width={cellW - 20} height={cellH - 22} rx={8}
                    fill="#ffffff" stroke="#d3d1c7" strokeWidth={0.5} />
              <g transform={`translate(${cx} ${cy - 14})`}>{TIER_DRAW[tier](vv)}</g>
              <text x={cx} y={cy + 46} fontSize={16} fill={INK} textAnchor="middle"
                    style={{ fontFamily: DEFAULT_FONT, fontWeight: 500 }}>
                {tier}
              </text>
              <text x={cx} y={cy + 68} fontSize={14} fill="#6b5a49" textAnchor="middle"
                    style={{ fontFamily: DEFAULT_FONT }}>
                {PLACE_TIER_LABEL[tier]}
              </text>
            </g>
          );
        })}

        {/* 状态行 */}
        <text x={60} y={y0 + 3 * cellH + 22} fontSize={22} fill={INK}
              style={{ fontFamily: DEFAULT_FONT, fontWeight: 500 }}>状态层 · 10 种</text>
        {ALL_STATES.map((st, i) => {
          const c = i % 5;
          const row = Math.floor(i / 5);
          const cx = x0 + c * 360 + 180;
          const cy = y0 + 3 * cellH + 90 + row * 130;
          return (
            <g key={st}>
              <rect x={cx - 170} y={cy - 55} width={340} height={120} rx={8}
                    fill="#ffffff" stroke="#d3d1c7" strokeWidth={0.5} />
              <g transform={`translate(${cx} ${cy - 12})`}>
                <StateDraw state={st} t={t} />
              </g>
              <text x={cx} y={cy + 46} fontSize={16} fill={INK} textAnchor="middle"
                    style={{ fontFamily: DEFAULT_FONT, fontWeight: 500 }}>{st}</text>
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
