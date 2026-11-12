import type { ReactNode } from "react";

/**
 * Single icon registry, as in the design farm: components name an icon, the set lives in one place.
 * Hand-drawn here on a 24 grid (round caps, 1.75 stroke) so the window carries no icon package.
 */
const paths = {
  campaign: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 8v8M8 12h8" />
    </>
  ),
  run: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M10.25 8.75v6.5L15.5 12z" />
    </>
  ),
  results: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10" />
    </>
  ),
  people: (
    <>
      <circle cx="9" cy="8.5" r="3.25" />
      <path d="M2.75 19.5c.5-3.4 3-5.25 6.25-5.25s5.75 1.85 6.25 5.25" />
      <path d="M15.75 5.6a3.25 3.25 0 0 1 0 5.8M18.25 14.9c1.7.8 2.7 2.4 3 4.6" />
    </>
  ),
  data: (
    <>
      <path d="M12 3.25 19.5 6v5.5c0 4.4-3 7.9-7.5 9.25C7.5 19.4 4.5 15.9 4.5 11.5V6z" />
      <path d="M12 8.5v4l2.5 1.5" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="15.5" r="4.25" />
      <path d="m11 12.5 8.75-8.75M16.5 7l2.75 2.75M13.75 9.75l2 2" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7.5h9M17.5 7.5H20M4 16.5h2.5M11 16.5h9" />
      <circle cx="15.25" cy="7.5" r="2.25" />
      <circle cx="8.75" cy="16.5" r="2.25" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.25 4.25" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  alert: (
    <>
      <path d="M12 4 21 19.5H3z" />
      <path d="M12 10v4.5M12 17.2v.05" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.8v.05" />
    </>
  ),
  stop: <rect x="6.5" y="6.5" width="11" height="11" rx="2" />,
  play: <path d="M8 5.5v13l10.5-6.5z" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  forget: (
    <>
      <path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.9 12.5h9.2L17.500 7" />
      <path d="M10 11v5M14 11v5" />
    </>
  ),
  suppress: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m6 6 12 12" />
    </>
  ),
  sheet: (
    <>
      <path d="M6.5 3.5H14l4.500 4.500v12.500h-12z" />
      <path d="M13.500 3.500v5h5M9 12.500h6M9 16h6" />
    </>
  ),
  refresh: (
    <>
      <path d="M19.500 12a7.500 7.500 0 1 1-2.200-5.300" />
      <path d="M19.750 4.500v4.250H15.500" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="3.750" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.640 5.640l1.410 1.410M16.950 16.950l1.410 1.410M5.640 18.360l1.410-1.410M16.950 7.050l1.410-1.410" />
    </>
  ),
  moon: <path d="M19.500 14.250A8 8 0 0 1 9.750 4.500a8 8 0 1 0 9.750 9.750z" />,
  minus: <path d="M6 12h12" />,
  plus: <path d="M12 6v12M6 12h12" />,
  source: (
    <>
      <path d="M10.250 13.750a3.750 3.750 0 0 0 5.300 0l3.200-3.200a3.750 3.750 0 0 0-5.300-5.300l-1.200 1.200" />
      <path d="M13.750 10.250a3.750 3.750 0 0 0-5.300 0l-3.200 3.200a3.750 3.750 0 0 0 5.300 5.300l1.200-1.200" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof paths;

export interface IconProps {
  name: IconName;
  size?: number;
  /** Give a label only when the icon stands alone and carries meaning. */
  label?: string;
  className?: string;
}

export function Icon({ name, size = 18, label, className }: IconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}
