/**
 * 事件动作总表（验证用）—— 把已实现的 9 个动词画在真实地理坐标上。
 * 用于肉眼验收动作库，不参与正式成片。
 */
import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { H, PALETTE, W, type BasemapKind } from "./geo";
import { ActionLayer, DEFAULT_FONT, type ActionSpec } from "./ActionLayer";

const KIND: BasemapKind = "wide";

const P = {
  许昌: { lon: 113.85, lat: 34.03 },
  洛阳: { lon: 112.6183, lat: 34.7195 },
  邺: { lon: 114.4002, lat: 36.2748 },
  河内: { lon: 113.25908, lat: 35.03151 },
  长安: { lon: 108.8931, lat: 34.2941 },
  建康: { lon: 118.796389, lat: 32.058333 },
  濮阳: { lon: 115.07806, lat: 35.65018 },
  阳翟: { lon: 113.46706, lat: 34.16249 },
  温县: { lon: 112.95068, lat: 34.91056 },
  成皋: { lon: 113.19, lat: 34.85 },
};

const DUR = 120;
const ACTIONS: ActionSpec[] = [
  { verb: "march",   start: 0, dur: DUR, from: P.许昌, to: P.洛阳, label: "march 行军", color: "#8c3424" },
  { verb: "defeat",  start: 0, dur: DUR, from: P.邺,   to: P.河内, label: "defeat 击败", color: "#8c3424", colorB: "#c2185b" },
  { verb: "kill",    start: 0, dur: DUR, at: P.洛阳, stamp: "诛", color: "#4a3a34" },
  { verb: "siege",   start: 0, dur: DUR, at: P.长安, label: "siege 围城", color: "#6a1b9a" },
  { verb: "fall",    start: 0, dur: DUR, at: P.建康, label: "fall 陷落", color: "#37474f" },
  { verb: "capture", start: 0, dur: DUR, at: P.濮阳, label: "capture 攻取", color: "#c62828", colorB: "#8a7a63" },
  { verb: "raise",   start: 0, dur: DUR, at: P.阳翟, label: "raise 起兵", color: "#1565c0", name: "冏" },
  { verb: "flee",    start: 0, dur: DUR, from: P.温县, to: P.成皋, label: "flee 出奔", color: "#6b5a49" },
  { verb: "ally",    start: 0, dur: DUR, from: P.邺,  to: P.建康, label: "ally 会盟", color: "#8c3424", colorB: "#2f5d7c" },
];

export const ActionSheet: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: PALETTE.paper }}>
      <Img src={staticFile("basemap_wide.png")} style={{ width: W, height: H }} />
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        <ActionLayer actions={ACTIONS} kind={KIND} frame={frame} font={DEFAULT_FONT} />
      </svg>
      <div style={{
        position: "absolute", left: 40, top: 30, background: "rgba(250,246,238,0.92)",
        border: `1px solid ${PALETTE.realmEdge}66`, borderRadius: 8, padding: "10px 18px",
        fontFamily: DEFAULT_FONT, fontSize: 20, color: PALETTE.ink,
      }}>
        事件动作库 · 9 个已实现动词（frame {frame}）
      </div>
    </AbsoluteFill>
  );
};
