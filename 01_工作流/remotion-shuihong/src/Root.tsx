/**
 * 八王之乱 · 完整时间线。参照「秋水制图」视觉风格：
 * 多政权色块 + 都城大字 + 小地名白描边 + 人物旗标 + 进军路线。
 *
 * 数据：public/dynasty/八王之乱-{起兵,洛阳易手,诸王尽死,永嘉之乱}/
 * 人物：public/dynasty/八王之乱-301/kings.json
 * 肖像：public/portraits/{king_id}_sq.png
 */
import React from "react";
import { Composition, continueRender, delayRender, staticFile } from "remotion";
import type { FeatureCollection } from "geojson";
import { BASEMAP_FILE, FPS, H, PALETTE, W, project, type BasemapKind } from "./geo";
import { HistoryShot } from "./HistoryShot";
import { KingMarker, KingPanel, RouteArrow, type King, type Route } from "./KingLayer";
import { CaptureLuoyang } from "./CaptureLuoyang";
import { Img, interpolate, useCurrentFrame } from "remotion";

// ---------- 人物与路线（由 studio/bawang_data.py 生成） ----------
type Kings = {
  kings: King[];
  cities: { name: string; lon: number; lat: number; role?: string; placeId?: string; tier?: string }[];
  routes: Route[];
};

// ---------- 镜头脚本 ----------
type BW = {
  id: string;               // 数据目录
  title: string;
  subtitle: string;
  year: number;
  yearLabel: string;
  focus: [number, number];
  zoom: number;
  basemap: BasemapKind;
  durationInFrames: number;
  narration: string;
  activeKing?: string;      // 本镜聚焦人物
  routeOf?: string;         // 本镜推进的路线 label
  highlights?: string[];
};

const SHOTS: BW[] = [
  {
    id: "八王之乱-起兵",
    title: "八王之乱",
    subtitle: "公元三〇一年 · 中原",
    year: 301, yearLabel: "公元 301 年",
    focus: [113.8, 35.0], zoom: 1.05, basemap: "wide",
    durationInFrames: 165,
    narration: "公元三〇一年，洛阳。宗王拥兵于州郡，天下已在失控边缘。",
  },
  {
    id: "八王之乱-起兵",
    title: "司马伦",
    subtitle: "赵王 · 洛阳",
    year: 301, yearLabel: "公元 301 年",
    focus: [114.46, 36.58], zoom: 1.3, basemap: "wide",
    durationInFrames: 150,
    narration: "赵王司马伦入洛阳，旋以皇太孙之姿践阼。",
    activeKing: "sima_lun", routeOf: "sima_jiong",
    highlights: ["洛阳", "邺", "许昌", "阳翟"],
  },
  {
    id: "八王之乱-起兵",
    title: "齐王冏起兵",
    subtitle: "许昌 → 洛阳",
    year: 301, yearLabel: "公元 301 年",
    focus: [113.6, 34.3], zoom: 1.25, basemap: "core",
    durationInFrames: 165,
    narration: "许昌、阳翟，齐王司马冏举兵，讨伐司马伦。",
    activeKing: "sima_jiong", routeOf: "sima_jiong",
    highlights: ["许昌", "阳翟", "洛阳", "颍川", "汝南"],
  },
  {
    id: "八王之乱-洛阳易手",
    title: "洛阳易手",
    subtitle: "公元三〇四年 · 三月",
    year: 304, yearLabel: "公元 304 年",
    focus: [113.4, 34.6], zoom: 1.15, basemap: "core",
    durationInFrames: 165,
    narration: "三〇四年，邺城与河内的兵马同时压向洛阳。",
    activeKing: "sima_ying", routeOf: "sima_ying",
    highlights: ["洛阳", "邺", "河内", "温县", "成皋"],
  },
  {
    id: "八王之乱-洛阳易手",
    title: "成都王颖",
    subtitle: "邺城 · 皇太弟",
    year: 304, yearLabel: "公元 304 年",
    focus: [114.41, 36.27], zoom: 1.4, basemap: "core",
    durationInFrames: 150,
    narration: "邺城，司马颖被立为皇太弟，天下尽归其手。",
    activeKing: "sima_ying",
    highlights: ["邺", "邺城", "邯郸", "巨鹿", "平原"],
  },
  {
    id: "八王之乱-诸王尽死",
    title: "诸王尽死",
    subtitle: "公元三〇六年",
    year: 306, yearLabel: "公元 306 年",
    focus: [114.0, 35.0], zoom: 1.0, basemap: "wide",
    durationInFrames: 165,
    narration: "三〇六年，颖、颙、乂相继被杀，司马越独自握权。",
    activeKing: "sima_yue",
    highlights: ["洛阳", "邺", "河内", "长安", "东海"],
  },
  {
    id: "八王之乱-永嘉之乱",
    title: "永嘉之乱",
    subtitle: "公元三一一年",
    year: 311, yearLabel: "公元 311 年",
    focus: [113.5, 34.7], zoom: 1.2, basemap: "core",
    durationInFrames: 175,
    narration: "三一一年，洛阳陷落。衣冠南渡，晋室移于建康。",
    highlights: ["洛阳", "长安", "建康", "汝南", "颍川"],
  },
];

// ---------- 组件 ----------
const BWShot: React.FC<{ shot: BW; data: { labels: FeatureCollection; zones: FeatureCollection }; kings: Kings | null }> =
  ({ shot, data, kings }) => {
    const frame = useCurrentFrame();
    const kind = shot.basemap;
    const fade = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
    const zoom = interpolate(frame, [0, 60], [1, shot.zoom], { extrapolateRight: "clamp" });
    const drift = interpolate(frame, [0, shot.durationInFrames], [0, -26], { extrapolateRight: "clamp" });
    // 镜头中心：从 wide 视野中心推进到 shot.focus
    const [fx, fy] = project(shot.focus[0], shot.focus[1], kind);
    const [wx, wy] = kind === "core" ? project(113.5, 35.2, kind) : project(113.5, 35.2, kind);
    const cx = interpolate(frame, [0, 60], [wx, fx], { extrapolateRight: "clamp" });
    const cy = interpolate(frame, [0, 60], [wy, fy], { extrapolateRight: "clamp" });
    // 镜头：以画面中心为锚推进，focus 决定最终中心
    const head = interpolate(frame, [4, 22], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
    const cap = interpolate(frame, [26, 42], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
    const panel = interpolate(frame, [18, 34], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

    // 路线推进
    const route = kings?.routes.find((r) => r.who === shot.routeOf);
    const rp = route
      ? interpolate(frame, [30, shot.durationInFrames - 20], [0, 1], { extrapolateRight: "clamp" })
      : 0;

    // 肖像淡入
    const portraitOp = interpolate(frame, [16, 34], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

    return (
      <div style={{ position: "absolute", inset: 0, background: PALETTE.paper, opacity: fade }}>
        <div style={{
          position: "absolute", width: W, height: H, left: "50%", top: "50%",
          transform: `translate(${-W / 2 + drift}px, ${-H / 2}px) scale(${zoom})`,
          transformOrigin: `${cx}px ${cy}px`,
        }}>
          <Img src={staticFile(BASEMAP_FILE[kind] ?? "basemap_wide.png")}
               style={{ width: W, height: H, display: "block" }} />
          <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
            {/* 地名 */}
            <ZoneAndLabels labels={data.labels} kind={kind} zoom={zoom} hl={shot.highlights ?? []} />
            {/* 路线 */}
            {route && kings && (
              <RouteArrow
                from={coordOf(kings, route.from)}
                to={coordOf(kings, route.to)}
                kind={kind} progress={rp} label={route.label}
              />
            )}
            {/* 人物旗标 */}
            {kings?.kings.map((k) => (
              <KingMarker key={k.id} king={k} kind={kind} W={W} H={H}
                active={shot.activeKing === k.id}
                showAll={!shot.activeKing} />
            ))}
          </svg>
        </div>

        {/* 版式层：与 HistoryShot 共用同一份实现（原先此处与 HistoryShot 各写一遍） */}
        <ShotChrome
          title={shot.title}
          subtitle={shot.subtitle}
          yearLabel={shot.yearLabel}
          disclaimer="人物肖像是艺术想象，非史实复原；地名点位为群体点，用于定位示意。"
          narration={shot.narration}
          opacity={{
            head,
            badge: head,
            disclaimer: cap,
            narration: interpolate(frame, [20, 36], [0, 1],
              { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
          }}
          sideSlot={
            shot.activeKing && kings && portraitOp > 0.01 ? (
              <PortraitCard
                king={kings.kings.find((k) => k.id === shot.activeKing)!}
                opacity={portraitOp}
              />
            ) : null
          }
          leftSlot={
            kings ? (
              <KingPanel kings={kings.kings} activeId={shot.activeKing ?? null} opacity={panel} />
            ) : null
          }
        />
      </div>
    );
  };

const PortraitCard: React.FC<{ king: King; opacity: number }> = ({ king, opacity }) => (
  <div style={{
    position: "absolute", right: 72, top: 150, width: 250,
    background: "rgba(250,246,238,0.96)", border: `2px solid ${PALETTE.realmEdge}`,
    borderRadius: 12, padding: 16, opacity, fontFamily: "HistoryMapSerifSC, serif",
  }}>
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <Img src={staticFile(`portraits/${king.id}_sq.png`)} style={{ width: 72, height: 72, borderRadius: 6 }} />
      <div>
        <div style={{ fontSize: 28, color: PALETTE.ink, fontWeight: 500 }}>{king.name}</div>
        <div style={{ fontSize: 19, color: PALETTE.realmEdge, marginTop: 2 }}>{king.title}</div>
      </div>
    </div>
    <div style={{ fontSize: 16, color: PALETTE.inkSoft, marginTop: 10, lineHeight: 1.5 }}>
      {king.note}
    </div>
    <div style={{ fontSize: 14, color: PALETTE.inkSoft, marginTop: 6, opacity: 0.85 }}>
      封地 {king.realm}（{king.realm_valid ?? ""}）
    </div>
  </div>
);

// 复用通用层
import { ZoneLayer, LabelLayer, ZoneNameLayer } from "./HistoryLayers";
import { ShotChrome } from "./Layout";
import { SymbolSheet } from "./SymbolSheet";
import { ActionSheet } from "./ActionSheet";
import { hydrateCities, loadMainData } from "./MainData";
import { DirectorComposition } from "./DirectorComposition";
import SCRIPT_MANIFEST from "../public/scripts/manifest.json";

/**
 * 从脚本 JSON 动态计算时长 —— 让「改脚本 = 改 JSON」成立，
 * 新增一集只需把 JSON 放进 public/scripts/，不必改代码。
 */
const episodeMeta = async ({ props }: { props: { episodeId: string } }) => {
  try {
    const r = await fetch(staticFile(`scripts/${props.episodeId}.json`));
    const ep = await r.json();
    const dur = (ep.shots ?? []).reduce(
      (a: number, s: { durationInFrames?: number }) => a + (s.durationInFrames ?? 0), 0);
    return { durationInFrames: Math.max(1, dur), fps: ep.fps ?? FPS };
  } catch (e) {
    console.error("[Root] 脚本载入失败", props.episodeId, e);
    return { durationInFrames: 300, fps: FPS };
  }
};

const ZoneAndLabels: React.FC<{
  labels: FeatureCollection; kind: BasemapKind; zoom: number; hl: string[];
}> = ({ labels, kind, zoom, hl }) => (
  <>
    <LabelLayer labels={labels} kind={kind} zoom={zoom} highlight={hl} W={W} H={H} />
  </>
);

const coordOf = (kings: Kings, name: string): [number, number] => {
  const c = kings.cities.find((x) => x.name === name);
  return c ? [c.lon, c.lat] : [0, 0];
};

// ---------- 数据加载 ----------
/**
 * 依次尝试多个候选路径，返回第一个成功加载的。
 * 顺序体现「目标形态 → 兼容形态」：id 引用版优先，逐步回退到原始文件。
 */
const fetchFirstOk = async (paths: string[]): Promise<{ data: any; path: string | null }> => {
  for (const p of paths) {
    try {
      const r = await fetch(staticFile(p));
      if (r.ok) return { data: await r.json(), path: p };
    } catch { /* 试下一个 */ }
  }
  return { data: null, path: null };
};

const useData = (id: string, withKings: boolean) => {
  const [labels, setLabels] = React.useState<FeatureCollection | null>(null);
  const [zones, setZones] = React.useState<FeatureCollection | null>(null);
  const [kings, setKings] = React.useState<Kings | null>(null);

  React.useEffect(() => {
    const h = delayRender("载入 " + id);
    Promise.all([
      // labels 内嵌 cities/kings/routes。优先纯 id 引用版（坐标由主表解析），
      // 回退到坐标统一版，最后回退原始文件。
      fetchFirstOk([
        `dynasty/${id}/labels.byid.json`,
        `dynasty/${id}/labels.resolved.json`,
        `dynasty/${id}/labels.json`,
      ]),
      // zones 只有面数据，不含地点坐标
      fetch(staticFile(`dynasty/${id}/zones.json`)).then((r) => r.json()),
      loadMainData(),
    ])
      .then(([lr, z, md]) => {
        const l = lr.data;
        setLabels(l);
        setZones(z);
        if (l && l.kings) {
          setKings({
            kings: l.kings,
            cities: hydrateCities(l.cities ?? [], md.places, l.year ?? 300),
            routes: l.routes ?? [],
          });
        }
        continueRender(h);
      })
      .catch((e) => { console.error(e); continueRender(h); });
  }, [id, withKings]);

  return { labels, zones, kings };
};

const makeComp = (shot: BW, idx: number) => {
  const C: React.FC = () => {
    const { labels, zones, kings } = useData(shot.id, true);
    if (!labels || !zones) return <div style={{ width: W, height: H, background: PALETTE.paper }} />;
    return <BWShot shot={shot} data={{ labels, zones }} kings={kings} />;
  };
  C.displayName = `BW${idx + 1}`;
  return C;
};

export const RemotionRoot: React.FC = () => (
  <>
    {SHOTS.map((s, i) => (
      <Composition key={i} id={`shot${i + 1}`} component={makeComp(s, i) as any}
        durationInFrames={s.durationInFrames} fps={FPS} width={W} height={H} />
    ))}
      <Composition id="capture-luoyang" component={CaptureLuoyang as any}
        durationInFrames={210} fps={FPS} width={W} height={H} />
      {/* 符号总表：验收用，不参与正式成片 */}
      <Composition id="symbol-sheet" component={SymbolSheet}
        durationInFrames={60} fps={FPS} width={W} height={H} />
      <Composition id="action-sheet" component={ActionSheet}
        durationInFrames={130} fps={FPS} width={W} height={H} />
      {/* ★ 脚本驱动合成：清单在 public/scripts/manifest.json，
             新增一集只需改清单（数据），不必改本文件（代码） */}
      {SCRIPT_MANIFEST.episodes.map((ep) => (
        <Composition
          key={ep.id}
          id={ep.id}
          component={DirectorComposition as any}
          defaultProps={{ episodeId: ep.episodeId }}
          durationInFrames={1200}
          fps={FPS} width={W} height={H}
          calculateMetadata={episodeMeta as any}
        />
      ))}
  </>
);
