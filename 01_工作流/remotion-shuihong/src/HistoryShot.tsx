/**
 * 通用镜头组件：与具体朝代无关。数据与视觉都从 dynasty/{朝代}-{年份}/ 读取。
 * 换朝代只需替换 Root.tsx 顶部的 episode 常量。
 */
import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { FeatureCollection } from "geojson";
import { BASEMAP_FILE, H, PALETTE, W, project, type BasemapKind, type Episode } from "./geo";
import { geoMercator, geoPath } from "d3-geo";
import { LabelLayer, ZoneLayer, ZoneNameLayer } from "./HistoryLayers";
import { ShotChrome } from "./Layout";

export const HistoryShot: React.FC<{
  data: { labels: FeatureCollection; zones: FeatureCollection };
  shot: Episode["shots"][number];
  realmData?: FeatureCollection | null;
}> = ({ data, shot, realmData = null }) => {
  const frame = useCurrentFrame();
  const total = shot.durationInFrames;
  const kind: BasemapKind = shot.basemap ?? "wide";

  const zoom = interpolate(frame, [0, Math.min(total, 60)], [1, shot.zoom], {
    extrapolateRight: "clamp",
  });
  const drift = interpolate(frame, [0, total], [0, -34], { extrapolateRight: "clamp" });
  const [cx, cy] = project(shot.focus[0], shot.focus[1], kind);
  // geoPath 用的投影，需与 geo.ts 的 VIEW 保持一致
  const realmProj = React.useMemo(() => {
    const v = kind === "core" ? { center: [115.5, 31.8] as [number, number], scale: 13318 }
                              : { center: [115.5, 31.8] as [number, number], scale: 7334 };
    return geoMercator().center(v.center).scale(v.scale).translate([960, 540]);
  }, [kind]);
  const realmPathGen = React.useMemo(() => geoPath(realmProj), [realmProj]);

  const fade = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const head = interpolate(frame, [4, 22], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const sub = interpolate(frame, [20, 38], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const cap = interpolate(frame, [30, 46], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  return (
    <AbsoluteFill style={{ background: PALETTE.paper, opacity: fade }}>
      <div
        style={{
          position: "absolute", width: W, height: H, left: "50%", top: "50%",
          transform: `translate(${-W / 2 + drift}px, ${-H / 2}px) scale(${zoom})`,
          transformOrigin: `${cx}px ${cy}px`,
        }}
      >
        <Img
          src={staticFile(BASEMAP_FILE[kind] ?? "basemap_wide.png")}
          style={{ width: W, height: H, display: "block" }}
        />
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
          {/* 参考疆域层（可选，最低精度，仅作范围参考） */}
          {realmData && (
            <g>
              {realmData.features.map((f: any, i: number) => {
                const d = realmPathGen(f);
                if (!d) return null;
                return (
                  <path key={i} d={d} fill="none" stroke={PALETTE.realmEdge}
                        strokeWidth={1.6} strokeDasharray="12 8" strokeOpacity={0.45} />
                );
              })}
            </g>
          )}
          <ZoneLayer zones={data.zones} kind={kind} zoom={zoom} W={W} H={H} />
          <ZoneNameLayer zones={data.zones} kind={kind} W={W} H={H} />
          <LabelLayer labels={data.labels} kind={kind} zoom={zoom}
                      highlight={shot.highlight ?? []} W={W} H={H} />
        </svg>
      </div>

      {/* 版式层：标题 / 年份徽标 / 精度声明 / 字幕 —— 与 BWShot 共用同一份实现 */}
      <ShotChrome
        title={shot.title}
        subtitle={shot.subtitle}
        yearLabel={shot.yearLabel ?? `${shot.year}`}
        disclaimer={shot.disclaimer}
        narration={shot.narration}
        opacity={{
          head,
          badge: sub,
          disclaimer: cap,
          narration: interpolate(frame, [20, 36], [0, 1],
            { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
        }}
      />
    </AbsoluteFill>
  );
};
