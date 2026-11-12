import type { ReactElement } from "react";

type IconProps = { className?: string };

function Svg({ className, children }: IconProps & { children: ReactElement | ReactElement[] }) {
  return (
    <svg
      className={className}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function OverviewIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4 6h16" />
      <path d="M4 12h10" />
      <path d="M4 18h6" />
      <path d="M18 14v6" />
    </Svg>
  );
}

export function LabIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M9 3h6" />
      <path d="M10 3v6l-5.2 9a2 2 0 0 0 1.7 3h11a2 2 0 0 0 1.7-3L14 9V3" />
      <path d="M7.5 15h9" />
    </Svg>
  );
}

export function OrdersIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z" />
      <path d="M4 7.5 12 12l8-4.5" />
      <path d="M12 12v9" />
    </Svg>
  );
}

export function AnalyticsIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M5 20V11" />
      <path d="M12 20V4" />
      <path d="M19 20v-6" />
    </Svg>
  );
}

export function AskIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4.5 4v-4H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" />
      <path d="M8.5 10h7" />
    </Svg>
  );
}
