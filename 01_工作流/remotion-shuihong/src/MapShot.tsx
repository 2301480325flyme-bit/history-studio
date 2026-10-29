import React, { useMemo } from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { FeatureCollection, Feature, Point } from "geojson";
import { BASEMAP_FILE, FONT_SCALE, H, PALETTE, W, colorFor, pathGen, project, shortName, tierOf, type Shot, type Tier } from "./geo";

type Props = {
  data: FeatureCollection;
  shot: Shot;
  showRealm?: boolean | "hard";
  realmData?: FeatureCollection | null;
  regionData?: FeatureCollection | null;
};

const PlaceLabel: React.FC<{
  f: Feature<Point>;
  tier: string;
  highlighted: boolean;
  occupied: { x: number; y: number; w: number; h: number }[];
  fontSize: number;
  kind: "wide" | "core";
}> = ({ f, tier, highlighted, occupied, fontSize, kind }) => {
  const [lon, lat] = f.geometry.coordinates;
  const [x, y] = project(lon, lat, kind);
  const name = shortName(f.properties!.name as string);
  if (!isFinite(x) || !isFinite(y)) return null;

  const pad = 200;
  if (x < -pad || x > W + pad || y < -pad || y > H + pad) return null;

  const ftype = (f.properties as any).ftype as string;
  const tierColor = colorFor(ftype);
  const size = highlighted
    ? FONT_SCALE.capital
    : tier === "capital"
    ? FONT_SCALE.capital
    : tier === "jun"
    ? FONT_SCALE.jun
    : FONT_SCALE.xian;
  // 秋水制图用白字压高饱和色块；本项目底图是浅色地形，白字不可读，
  // 故改为「深字 + 浅描边」—— 同样保证任意底色下的可读性。
  const color = highlighted ? PALETTE.accent : tier === "capital" ? PALETTE.ink : PALETTE.inkSoft;
  const r = highlighted ? 7 : tier === "capital" ? 5 : 3;
  const w = name.length * size * 1.02 + 12;
  const h = size + 8;

  // 网格化避让：与已放置标签相交则尝试下移/右移，仍冲突则不画
  const cand: { x: number; y: number; w: number; h: number }[] = [
    { x: x + 12, y: y - h / 2, w, h },
    { x: x + 12, y: y - h / 2 - h, w, h },
    { x: x + 12, y: y - h / 2 + h, w, h },
    { x: x - 12 - w, y: y - h / 2, w, h },
    { x: x - 12 - w, y: y - h / 2 - h, w, h },
  ];
  let slot = null as null | { x: number; y: number; w: number; h: number };
  for (const c of cand) {
    const hit = occupied.some(
      (o) => c.x < o.x + o.w && c.x + c.w > o.x && c.y < o.y + o.h && c.y + c.h > o.y
    );
    if (!hit) {
      slot = c;
      break;
    }
  }
  if (!slot) return null;
  occupied.push(slot);

  return (
    <g>
      {highlighted && (
        <circle cx={x} cy={y} r={16} fill="none" stroke={PALETTE.accent} strokeWidth={2} opacity={0.5} />
      )}
      <circle cx={x} cy={y} r={r} fill="#fffdf7" stroke={color} strokeWidth={highlighted ? 3 : 2} />
      <text
        x={slot.x + 6}
        y={slot.y + h / 2}
        fontSize={size}
        fill={color}
        stroke="#fdfaf2"
        strokeWidth={highlighted ? 4.5 : 3.5}
        paintOrder="stroke"
        style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: highlighted ? 500 : 400 }}
      >
        {name}
      </text>
    </g>
  );
};

export const MapShot: React.FC<Props> = ({ data, shot, showRealm = true, realmData = null, regionData = null }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = shot.durationInFrames;

  // 镜头：入场推近 + 轻微漂移
  const zoom = interpolate(frame, [0, Math.min(total, 90)], [1, shot.zoom], {
    extrapolateRight: "clamp",
  });
  const driftX = interpolate(frame, [0, total], [0, -40], { extrapolateRight: "clamp" });

  const kind = shot.basemap ?? "wide";
  const [cx, cy] = project(shot.focus[0], shot.focus[1], kind);

  const realmPaths = useMemo(() => {
    if (!showRealm || !realmData) return [];
    return realmData.features
      .map((f) => ({ d: pathGen(f), name: (f.properties as any)?.name ?? (f.properties as any)?.LABEL_CHN ?? "" }))
      .filter((x) => x.d);
  }, [realmData, showRealm]);

  const highlightSet = useMemo(
    () => new Set((shot.highlight ?? []).map((s) => s.replace(/(縣|县|郡|國|国|城|邑)$/, ""))),
    [shot.highlight]
  );

  /**
   * 按缩放分级 + 屏幕间距抽稀。
   * 该年核心区有 897 个地名挤在约 20°×8° 内，宽视野下必糊；
   * 故先按重要度排序，再用屏幕像素间距做贪心抽稀。
   */
  const minRank = zoom >= 2.2 ? 2 : zoom >= 1.5 ? 1 : 0;
  const minGapPx = zoom >= 2.2 ? 40 : zoom >= 1.5 ? 52 : 62;
  const maxLabels = zoom >= 2.2 ? 150 : zoom >= 1.5 ? 70 : 48;
  const RANK: Record<Tier, number> = { capital: 0, jun: 1, xian: 2, other: 3 };

  const visible = useMemo(() => {
    const hl = data.features.filter((f) =>
      highlightSet.has(shortName((f.properties as any).name as string))
    );
    const rest = data.features
      .filter((f) => !highlightSet.has(shortName((f.properties as any).name as string)))
      .filter((f) => RANK[tierOf((f.properties as any).ftype, (f.properties as any).name)] >= minRank);
    return [...hl, ...rest];
  }, [data, minRank, highlightSet]);

  /** 州级政区色块（半透明色饼），仅在缩放较小时显示，避免特写时糊成一片 */
  const regionTint = useMemo(() => {
    if (!regionData || zoom < 1.15) return null;
    const blobs: React.ReactNode[] = [];
    const occupied: { x: number; y: number; r: number }[] = [];
    const items = regionData.features
      .filter((f) => (f.properties as any).ftype === "州")
      .map((f) => {
        const p = f.properties as any;
        const [lon, lat] = (f as any).geometry.coordinates as [number, number];
        return { lon, lat, name: p.name as string };
      });
    for (const it of items) {
      const [x, y] = project(it.lon, it.lat, kind);
      const r = 118;
      if (x < -r || x > W + r || y < -r || y > H + r) continue;
      if (occupied.some((o) => (x - o.x) ** 2 + (y - o.y) ** 2 < (r + o.r) ** 2 * 0.34)) continue;
      occupied.push({ x, y, r });
      const c = colorFor("州");
      blobs.push(
        <g key={it.name}>
          <circle cx={x} cy={y} r={r} fill={c.fill} fillOpacity={0.28} />
          <circle cx={x} cy={y} r={r} fill="none" stroke={c.edge} strokeWidth={2} strokeOpacity={0.5} strokeDasharray="8 6" />
          <text x={x} y={y - r + 34} fontSize={38} fill={c.label} fillOpacity={0.7} textAnchor="middle"
                stroke="#fdfaf2" strokeWidth={3} paintOrder="stroke"
                style={{ fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500 }}>{shortName(it.name)}</text>
        </g>
      );
    }
    return <g>{blobs}</g>;
  }, [regionData, zoom, kind]);

  const opacity = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: PALETTE.paper, opacity }}>
      <div
        style={{
          position: "absolute",
          width: W,
          height: H,
          left: "50%",
          top: "50%",
          transform: `translate(${-W / 2 + driftX}px, ${-H / 2}px) scale(${zoom})`,
          transformOrigin: `${cx}px ${cy}px`,
        }}
      >
        <Img
          src={staticFile(BASEMAP_FILE[kind] ?? "basemap_wide.png")}
          style={{ width: W, height: H, display: "block" }}
        />

        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
          {/* 政权色块：仅作范围参考。
              该数据 borderPrecision=1（最低档）、345 顶点画完整境、北界为 581km 直线封口，
              故低透明度 + 虚线边 + 画面注明「疆界待考」，不当作考证结论呈现。 */}
          {realmPaths.map((p, i) => (
            <g key={i}>
              <path
                d={p.d}
                fill={PALETTE.realm}
                fillOpacity={showRealm === "hard" ? 0.22 : 0.07}
                stroke={PALETTE.realmEdge}
                strokeWidth={1.8}
                strokeDasharray="12 8"
                strokeOpacity={0.6}
              />
            </g>
          ))}

          {/* 州级政区色块：参考秋水制图的政权分色思路。
              注意语义差别：他画的是多政权并立，本项目 301 年西晋境内只有晋，
              故用同色系深浅表达「行政层级」而非「不同政权」，避免误示为并立政权。 */}
          {regionTint}

          {/* 地名：重要度排序后逐个避让放置 */}
          {(() => {
            const TIER_RANK: Record<Tier, number> = { capital: 0, jun: 1, xian: 2, other: 3 };
            const base = zoom >= 2.2 ? 20 : zoom >= 1.5 ? 17 : 15;
            const ordered = visible
              .map((f) => {
                const p = f.properties as any;
                const nm = shortName(p.name as string);
                return {
                  f,
                  tier: tierOf(p.ftype, p.name),
                  hl: highlightSet.has(nm),
                };
              })
              .sort((a, b) => Number(b.hl) - Number(a.hl) || TIER_RANK[a.tier] - TIER_RANK[b.tier]);

            // 屏幕像素间距抽稀：重要度高的先占位
            const gap2 = minGapPx * minGapPx;
            const kept: typeof ordered = [];
            for (const it of ordered) {
              if (kept.length >= maxLabels) break;
              const p = it.f.geometry.coordinates;
              const [sx, sy] = project(p[0], p[1], kind);
              const nm = shortName((it.f.properties as any).name as string);
              const w = nm.length * base * 1.1;
              let clash = false;
              for (const k of kept) {
                const q = k.f.geometry.coordinates;
                const [kx, ky] = project(q[0], q[1], kind);
                if ((sx - kx) * (sx - kx) + (sy - ky) * (sy - ky) < gap2) {
                  clash = true;
                  break;
                }
              }
              if (!clash) kept.push(it);
            }

            const occupied: { x: number; y: number; w: number; h: number }[] = [
              // 标题区
              { x: 0, y: 0, w: 760, h: 150 },
              // 年份徽标
              { x: W - 360, y: 0, w: 360, h: 165 },
              // 字幕条
              { x: 0, y: H - 140, w: W, h: 140 },
              // 精度声明条
              { x: 0, y: H - 340, w: 880, h: 210 },
            ];
            // 州级色块圆心区域预留，地名绕行
            if (regionData) {
              for (const f of regionData.features) {
                if ((f.properties as any).ftype !== "州") continue;
                const [lon, lat] = (f as any).geometry.coordinates as [number, number];
                const [rx, ry] = project(lon, lat, kind);
                occupied.push({ x: rx - 46, y: ry - 46, w: 92, h: 92 });
              }
            }
            return kept.map((it, i) => (
              <PlaceLabel
                key={(it.f.properties as any).place_id ?? i}
                f={it.f as Feature<Point>}
                tier={it.tier}
                highlighted={it.hl}
                occupied={occupied}
                fontSize={base}
                kind={kind}
              />
            ));
          })()}
        </svg>
      </div>

      {/* 标题条 */}
      <div style={{ position: "absolute", left: 60, top: 56, opacity: interpolate(frame, [4, 20], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }) }}>
        <div style={{ fontSize: 54, color: PALETTE.ink, fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500, letterSpacing: 2 }}>
          {shot.title}
        </div>
        <div style={{ fontSize: 24, color: PALETTE.inkSoft, marginTop: 10, fontFamily: "HistoryMapSerifSC, serif" }}>
          {shot.subtitle}
        </div>
      </div>

      {/* 年份徽标 */}
      <div
        style={{
          position: "absolute",
          right: 72,
          top: 52,
          border: `2px solid ${PALETTE.realmEdge}`,
          color: PALETTE.realmEdge,
          padding: "12px 26px",
          fontSize: 38,
          fontFamily: "HistoryMapSerifSC, serif",
          letterSpacing: 3,
          opacity: interpolate(frame, [8, 26], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
        }}
      >
        公元 {shot.year} 年
      </div>

      {/* 疆界精度声明：数据自述最低精度档，不作考证结论 */}
      {showRealm && (
        <div
          style={{
            position: "absolute",
            left: 62,
            bottom: 150,
            maxWidth: 760,
            opacity: interpolate(frame, [30, 46], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
          }}
        >
          <span
            style={{
              fontSize: 17,
              color: PALETTE.inkSoft,
              borderLeft: `3px solid ${PALETTE.realmEdge}`,
              paddingLeft: 12,
              lineHeight: 1.5,
              fontFamily: "HistoryMapSerifSC, serif",
            }}
          >
            疆界为范围参考：底图精度为最低档，北界为资料缺口封口，非考证结论。
            <br />
            地名点位为群体点，用于定位示意。
          </span>
        </div>
      )}

      {/* 旁白字幕 */}
      {shot.narration && (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 64,
            textAlign: "center",
            opacity: interpolate(frame, [20, 34], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
          }}
        >
          <span
            style={{
              fontSize: 32,
              color: "#f5efe3",
              background: "rgba(28, 22, 17, 0.72)",
              padding: "12px 30px",
              fontFamily: "HistoryMapSerifSC, serif",
              letterSpacing: 1,
            }}
          >
            {shot.narration}
          </span>
        </div>
      )}
    </AbsoluteFill>
  );
};
