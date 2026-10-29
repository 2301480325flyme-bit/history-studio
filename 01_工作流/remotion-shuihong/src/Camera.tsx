/**
 * 镜头运动与转场。
 *
 * 补齐 视觉符号与动画库-v1.md 的 L2（镜头运动）与 L3（转场）：
 *   L2: dolly_in / dolly_out / hold / shake / track
 *   L3: ink_bleed 墨迹扩散（契合水墨风，优先）
 *
 * 设计：镜头运动用「关键帧数组」描述，与 director.json 的 camera[] 字段同构。
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export type CameraKeyframe = {
  /** 秒 */
  t: number;
  zoom?: number;
  x?: number;
  y?: number;
  /** 该段的运动类型，仅作标注；几何效果由 zoom/x/y 决定 */
  camera?: string;
  /** 段落内是否震动 */
  shake?: boolean;
  /** 段落结束时触发的转场 */
  transition?: string;
};

export type CameraState = {
  zoom: number;
  x: number;
  y: number;
  shaking: boolean;
};

const IDENTITY: CameraState = { zoom: 1, x: 0, y: 0, shaking: false };

/**
 * 按关键帧插值镜头状态。缓动用 Remotion 的 Easing（默认 ease-in-out）。
 * 未提供关键帧时返回恒等变换。
 */
export function useCameraAt(
  keyframes: CameraKeyframe[] | undefined,
  fallbackZoom = 1,
): CameraState {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sec = frame / fps;

  if (!keyframes || keyframes.length === 0) {
    return { ...IDENTITY, zoom: fallbackZoom };
  }

  const ks = [...keyframes].sort((a, b) => a.t - b.t);
  // 定位当前所在段
  let i = 0;
  for (let k = 0; k < ks.length - 1; k++) {
    if (sec >= ks[k].t && sec <= ks[k + 1].t) { i = k; break; }
    if (sec > ks[ks.length - 1].t) i = ks.length - 1;
  }
  const a = ks[i];
  const b = ks[Math.min(i + 1, ks.length - 1)];
  const span = Math.max(1e-6, b.t - a.t);
  const p = Math.max(0, Math.min(1, (sec - a.t) / span));

  const zoom = interpolate(p, [0, 1], [a.zoom ?? fallbackZoom, b.zoom ?? a.zoom ?? fallbackZoom]);
  const x = interpolate(p, [0, 1], [a.x ?? 0, b.x ?? a.x ?? 0]);
  const y = interpolate(p, [0, 1], [a.y ?? 0, b.y ?? a.y ?? 0]);

  // shake：在标注了 shake 的段内叠加高频位移
  const shaking = !!a.shake;
  const shX = shaking ? Math.sin(frame * 2.7) * 4 + Math.sin(frame * 5.3) * 2 : 0;
  const shY = shaking ? Math.cos(frame * 3.1) * 3 + Math.cos(frame * 6.1) * 1.6 : 0;

  return { zoom, x: x + shX, y: y + shY, shaking };
}

/** 把镜头变换套到子元素上（origin 为屏幕中心） */
export const CameraRig: React.FC<{
  keyframes?: CameraKeyframe[];
  fallbackZoom?: number;
  origin?: [number, number];
  children: React.ReactNode;
}> = ({ keyframes, fallbackZoom = 1, origin = [960, 540], children }) => {
  const c = useCameraAt(keyframes, fallbackZoom);
  return (
    <div style={{
      position: "absolute", inset: 0,
      transform: `translate(${c.x}px, ${c.y}px) scale(${c.zoom})`,
      transformOrigin: `${origin[0]}px ${origin[1]}px`,
    }}>
      {children}
    </div>
  );
};

// ---------- L3 转场 ----------

/**
 * 墨迹扩散转场（ink_bleed）。
 * 一团墨自中心化开铺满画面，再退去 —— 契合水墨风格。
 * progress: 0→1
 */
export const InkBleed: React.FC<{
  progress: number;
  color?: string;
  paper?: string;
  /** 0–1，墨迹边缘的不规则度 */
  irregularity?: number;
}> = ({ progress, color = "#2a221b", paper = "#f2ede2", irregularity = 0.18 }) => {
  if (progress <= 0 || progress >= 1) return null;

  // 前半程铺开，后半程退去
  const open = Math.min(1, progress / 0.5);
  const close = Math.max(0, (progress - 0.5) / 0.5);
  // ⚠️ 半径必须覆盖画面对角线：sqrt(960² + 540²) ≈ 1101，故取 1400 留余量
  const r = open * 1400 + close * 500;

  // 不规则边缘：用极坐标生成一圈起伏点
  const N = 72;
  const pts: string[] = [];
  for (let k = 0; k < N; k++) {
    const a = (k / N) * Math.PI * 2;
    const wob = 1 + irregularity * (
      Math.sin(a * 3 + progress * 9) * 0.55 +
      Math.sin(a * 7 - progress * 5) * 0.3 +
      Math.sin(a * 11 + progress * 13) * 0.15
    );
    pts.push(`${960 + Math.cos(a) * r * wob},${540 + Math.sin(a) * r * wob}`);
  }
  const opacity = progress < 0.5
    ? interpolate(progress, [0, 0.5], [1, 1])
    : interpolate(progress, [0.5, 1], [1, 0]);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <svg width={1920} height={1080} viewBox="0 0 1920 1080">
        <rect width={1920} height={1080} fill={paper} opacity={0.5} />
        <polygon points={pts.join(" ")} fill={color} opacity={opacity * 0.94} />
      </svg>
    </AbsoluteFill>
  );
};

/** 卷轴展开（scroll_unfurl）：上下两轴向外撑开 */
export const ScrollUnfurl: React.FC<{ progress: number; color?: string }> = ({
  progress, color = "#8c3424",
}) => {
  if (progress <= 0 || progress >= 1) return null;
  const h = interpolate(progress, [0, 0.5, 1], [540, 540, 0]);
  void color;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: h, background: "#2a221b" }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: h, background: "#2a221b" }} />
    </AbsoluteFill>
  );
};

/** 转场总入口：按 id 派发 */
export const Transition: React.FC<{
  type?: string;
  progress: number;
}> = ({ type, progress }) => {
  switch (type) {
    case "ink_bleed": return <InkBleed progress={progress} />;
    case "scroll_unfurl": return <ScrollUnfurl progress={progress} />;
    default: return null;
  }
};
