/**
 * 攻取洛阳 · 单镜头演示。
 *
 * 八王之乱名义上只有一个晋朝，所以这里不画政权色块，
 * 而是用「城池易主」表达战事：
 *   洛阳城标记随控制者换色 → 旗帜换主 → 事件卡浮出 → 箭头抵达
 */
import React from "react";
import { AbsoluteFill, Img, continueRender, delayRender, interpolate, staticFile, useCurrentFrame } from "remotion";
import { FPS, H, PALETTE, W, project } from "./geo";
import { CityMarker, EventCard, controllerAt, useCapture, type City, type Event, type King } from "./CaptureLayer";
import { RouteArrow } from "./KingLayer";
import { LabelLayer } from "./HistoryLayers";

type Data = {
  kings: King[]; cities: City[]; events: Event[];
};

const CAP: React.FC<{ data: Data }> = ({ data }) => {
  const frame = useCurrentFrame();
  const DUR = 210;                    // 7 秒
  const { march, capture, card } = useCapture(frame, 20, DUR - 30);

  // 本次攻取：301年四月 齐王冏自许昌起兵讨伦
  const ev = data.events.find((e) => e.year === 301 && e.type === "攻取" && e.actor === "sima_jiong")
    ?? data.events.find((e) => e.type === "攻取");
  const actor = data.kings.find((k) => k.id === ev?.actor) ?? null;

  // 洛阳：攻取前属赵王伦，攻取后属齐王冏
  const luoyang = data.cities.find((c) => c.name === "洛阳");
  const xuchang = data.cities.find((c) => c.name === "许昌");
  const before = data.kings.find((k) => k.id === "sima_lun") ?? null;

  const zoom = interpolate(frame, [0, 70], [1, 1.25], { extrapolateRight: "clamp" });
  const [cx, cy] = project(113.3, 34.9, "core");

  const head = interpolate(frame, [4, 22], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const cap = interpolate(frame, [30, 46], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  return (
    <AbsoluteFill style={{ background: PALETTE.paper }}>
      <div style={{
        position: "absolute", width: W, height: H, left: "50%", top: "50%",
        transform: `translate(${-W / 2}px, ${-H / 2}px) scale(${zoom})`,
        transformOrigin: `${cx}px ${cy}px`,
      }}>
        <Img src={staticFile("basemap_core.png")} style={{ width: W, height: H, display: "block" }} />
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
          {/* 底图地名（降级：用空 FeatureCollection 占位，避免加载） */}
          {/* 进军箭头：许昌 → 洛阳 */}
          {xuchang && luoyang && (
            <RouteArrow
              from={[xuchang.lon, xuchang.lat]}
              to={[luoyang.lon, luoyang.lat]}
              kind="core" progress={march}
              color={actor?.color ?? PALETTE.accent} width={5}
              label={ev?.text ? "讨伦" : undefined}
            />
          )}
          {/* 各城池：颜色 = 当时控制者 */}
          {data.cities.map((c) => {
            const who = controllerAt(c, ev?.year ?? 301);
            const k = data.kings.find((x) => x.id === who) ?? null;
            const isTarget = c.name === (ev?.to ?? ev?.target);
            return (
              <CityMarker key={c.name} city={c} year={ev?.year ?? 301} king={k}
                kind="core" highlight={isTarget}
                captureProgress={isTarget ? capture : 1}
                attacker={isTarget ? actor : null} />
            );
          })}
        </svg>
      </div>

      <div style={{ position: "absolute", left: 60, top: 54, opacity: head }}>
        <div style={{ fontSize: 52, color: PALETTE.ink, fontFamily: "HistoryMapSerifSC, serif", fontWeight: 500, letterSpacing: 3 }}>
          攻取洛阳
        </div>
        <div style={{ fontSize: 24, color: PALETTE.inkSoft, marginTop: 10, fontFamily: "HistoryMapSerifSC, serif" }}>
          公元三〇一年四月 · 齐王冏自许昌
        </div>
      </div>

      <div style={{
        position: "absolute", right: 72, top: 50,
        border: `2px solid ${PALETTE.realmEdge}`, color: PALETTE.realmEdge,
        padding: "12px 26px", fontSize: 38, letterSpacing: 3,
        fontFamily: "HistoryMapSerifSC, serif", opacity: head,
      }}>公元 301 年</div>

      {ev && <EventCard ev={ev} king={actor} opacity={card} />}

      <div style={{ position: "absolute", left: 62, bottom: 150, maxWidth: 800, opacity: cap }}>
        <span style={{
          fontSize: 17, color: PALETTE.inkSoft, borderLeft: `3px solid ${PALETTE.realmEdge}`,
          paddingLeft: 12, lineHeight: 1.5, fontFamily: "HistoryMapSerifSC, serif",
        }}>
          八王之乱名义上仍是一个晋朝，故不按政权分色；城池标记颜色表示当时的控制者（诸王控制区色），
          易主时换旗并浮出事件卡。人物肖像是艺术想象，非史实复原。
        </span>
      </div>

      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 62, textAlign: "center",
        opacity: interpolate(frame, [24, 40], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
      }}>
        <span style={{
          fontSize: 32, color: "#f5efe3", background: "rgba(28,22,17,0.72)",
          padding: "12px 30px", fontFamily: "HistoryMapSerifSC, serif",
        }}>
          {capture > 0.5 ? "齐王冏攻入洛阳，赵王伦败死" : "齐王冏自许昌起兵，会师讨伦"}
        </span>
      </div>
    </AbsoluteFill>
  );
};

const useData = () => {
  const [data, setData] = React.useState<Data | null>(null);
  React.useEffect(() => {
    // 必须 delayRender：否则数据未就绪就截帧，底图与标记都不会出现
    const h = delayRender("载入八王数据与底图");
    const loadImg = (src: string) => new Promise<void>((res) => {
      const im = new window.Image();
      im.onload = () => res();
      im.onerror = () => res();
      im.src = src;
    });
    Promise.all([
      fetch(staticFile("dynasty/八王之乱-起兵/labels.json")).then((r) => r.json()),
      loadImg(staticFile("basemap_core.png")),
    ])
      .then(([l]) => {
        setData({ kings: l.kings ?? [], cities: l.cities ?? [], events: l.events ?? [] });
        continueRender(h);
      })
      .catch((e) => { console.error(e); continueRender(h); });
  }, []);
  return data;
};

export const CaptureLuoyang: React.FC = () => {
  const data = useData();
  if (!data) return <div style={{ width: W, height: H, background: PALETTE.paper }} />;
  return <CAP data={data} />;
};

export const DURATION = 210;
export const FPS_ = FPS;
