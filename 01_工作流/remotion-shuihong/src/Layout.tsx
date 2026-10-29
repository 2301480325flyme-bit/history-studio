/**
 * 镜头版式层（ShotChrome）—— 全项目共用的画面版式。
 *
 * 抽出来的原因：这套版式原先在 HistoryShot.tsx 和 Root.tsx 的 BWShot 里各写了一遍，
 * 改一次要改两处。现在只此一份，两个镜头组件都复用它。
 *
 * 版式只描述「区块在哪、长什么样」，不参与动画时序 ——
 * 各区块的透明度由调用方按自己的时间轴算好传入（opacity 参数）。
 */
import React from "react";
import { PALETTE } from "./geo";

const SERIF = '"HistoryMapSerifSC", serif';

export type ChromeOpacity = {
  /** 标题区（标题 + 副标题） */
  head?: number;
  /** 年份徽标 */
  badge?: number;
  /** 精度声明 */
  disclaimer?: number;
  /** 旁白字幕 */
  narration?: number;
};

export type ShotChromeProps = {
  title?: string;
  subtitle?: string;
  /** 年份文字，如「公元 301 年」；不传则不显示徽标 */
  yearLabel?: string;
  /** 精度/免责声明；不传则用默认文案 */
  disclaimer?: string;
  /** 旁白字幕；不传则不显示 */
  narration?: string;
  opacity?: ChromeOpacity;
  /** 右侧插槽（如人物肖像卡、事件卡），由调用方自行定位 */
  sideSlot?: React.ReactNode;
  /** 左侧插槽（如人物列表 KingPanel） */
  leftSlot?: React.ReactNode;
};

const DEFAULT_DISCLAIMER = "地名点位为群体点，用于定位示意；疆界为范围参考，非考证结论。";

export const ShotChrome: React.FC<ShotChromeProps> = ({
  title,
  subtitle,
  yearLabel,
  disclaimer,
  narration,
  opacity = {},
  sideSlot,
  leftSlot,
}) => {
  const o = { head: 1, badge: 1, disclaimer: 1, narration: 1, ...opacity };
  return (
    <>
      {/* 右侧插槽（肖像卡 / 事件卡）—— 置于最底层，与原图层叠放一致 */}
      {sideSlot}

      {/* 标题区 */}
      {(title || subtitle) && (
        <div style={{ position: "absolute", left: 60, top: 54, opacity: o.head }}>
          {title && (
            <div style={{
              fontSize: 52, color: PALETTE.ink, fontFamily: SERIF,
              fontWeight: 500, letterSpacing: 3,
            }}>
              {title}
            </div>
          )}
          {subtitle && (
            <div style={{
              fontSize: 24, color: PALETTE.inkSoft, marginTop: 10,
              fontFamily: SERIF, letterSpacing: 1,
            }}>
              {subtitle}
            </div>
          )}
        </div>
      )}

      {/* 年份徽标 */}
      {yearLabel && (
        <div style={{
          position: "absolute", right: 72, top: 50,
          border: `2px solid ${PALETTE.realmEdge}`, color: PALETTE.realmEdge,
          padding: "12px 26px", fontSize: 38, letterSpacing: 3,
          fontFamily: SERIF, opacity: o.badge,
        }}>
          {yearLabel}
        </div>
      )}

      {/* 左侧插槽（人物列表 KingPanel）—— 置于精度声明之下 */}
      {leftSlot}

      {/* 精度声明 */}
      <div style={{ position: "absolute", left: 62, bottom: 150, maxWidth: 780, opacity: o.disclaimer }}>
        <span style={{
          fontSize: 17, color: PALETTE.inkSoft, borderLeft: `3px solid ${PALETTE.realmEdge}`,
          paddingLeft: 12, lineHeight: 1.5, fontFamily: SERIF,
        }}>
          {disclaimer ?? DEFAULT_DISCLAIMER}
        </span>
      </div>

      {/* 旁白字幕（适配静音观看） */}
      {narration && (
        <div style={{
          position: "absolute", left: 0, right: 0, bottom: 62, textAlign: "center",
          opacity: o.narration,
        }}>
          <span style={{
            fontSize: 32, color: "#f5efe3", background: "rgba(28,22,17,0.72)",
            padding: "12px 30px", fontFamily: SERIF, letterSpacing: 1,
          }}>
            {narration}
          </span>
        </div>
      )}
    </>
  );
};
