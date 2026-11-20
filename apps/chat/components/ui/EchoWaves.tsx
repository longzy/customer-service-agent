/**
 * 品牌回声：以「声源」为圆心的 6 圈同心圆，实线与虚线交替、由内向外变淡，
 * 圆心一个实心点表示声源本身。
 *
 * 动效：由内向外依次亮起（每条错开 300ms，周期 3600ms），像石子入水后
 * 一圈圈推开的涟漪；`prefers-reduced-motion` 下回到静态的 --wave-o-*。
 *
 * 纯装饰，不承载信息；定位与尺寸由调用方的容器决定
 * （ui-spec 2.7「品牌回声」、3.1 品牌栏、3.5 欢迎卡）。
 */

/** 声源位置：偏右下，波纹向左上推开，不压住左侧主标题。 */
const SOURCE = { x: 330, y: 560 } as const;

type Ring = {
  /** 半径，内圈最小。 */
  r: number;
  /** 弧线强度令牌，外圈最淡、内圈最浓。 */
  token: string;
  width: number;
  dash?: string;
  /** 由内向外扩散：内圈先亮，外圈后亮。 */
  delay: number;
};

const RINGS: Ring[] = [
  { r: 60, token: "--wave-o-6", width: 1.4, delay: 0 },
  { r: 120, token: "--wave-o-5", width: 1.3, delay: 300 },
  { r: 180, token: "--wave-o-4", width: 1.2, dash: "3 8", delay: 600 },
  { r: 240, token: "--wave-o-3", width: 1.15, delay: 900 },
  { r: 300, token: "--wave-o-2", width: 1.1, dash: "3 8", delay: 1200 },
  { r: 360, token: "--wave-o-1", width: 1.1, delay: 1500 },
];

/** 动效参数按令牌传入：Tailwind 无法从插值生成类名，只能用内联值（ui-spec 2.6 允许数值型 token）。 */
const RIPPLE = "animate-[echo-ripple_3600ms_ease-in-out_infinite] motion-reduce:animate-none";

export function EchoWaves({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      data-echo-waves=""
      className={className}
      viewBox="0 0 460 620"
      preserveAspectRatio="none"
      fill="none"
    >
      {RINGS.map((ring) => (
        <circle
          key={ring.token}
          cx={SOURCE.x}
          cy={SOURCE.y}
          r={ring.r}
          stroke="currentColor"
          strokeWidth={ring.width}
          strokeDasharray={ring.dash}
          vectorEffect="non-scaling-stroke"
          className={RIPPLE}
          style={{ strokeOpacity: `var(${ring.token})`, animationDelay: `${ring.delay}ms` }}
        />
      ))}
      <circle
        cx={SOURCE.x}
        cy={SOURCE.y}
        r="4.5"
        fill="currentColor"
        style={{ fillOpacity: "var(--wave-o-6)" }}
      />
      <circle
        cx={SOURCE.x}
        cy={SOURCE.y}
        r="12"
        stroke="currentColor"
        strokeWidth="1"
        style={{ strokeOpacity: "var(--wave-o-4)" }}
      />
    </svg>
  );
}
