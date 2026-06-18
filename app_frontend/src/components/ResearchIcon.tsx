import type { SVGProps } from "react";

export type ResearchIconName =
  | "dashboard"
  | "evidence"
  | "scenario"
  | "history"
  | "ai"
  | "portfolio"
  | "diagnostics"
  | "close"
  | "chevron"
  | "search"
  | "copy"
  | "check"
  | "shield"
  | "database"
  | "clock"
  | "layers";

type ResearchIconProps = SVGProps<SVGSVGElement> & {
  name: ResearchIconName;
  size?: number;
};

export function ResearchIcon({
  name,
  size = 18,
  ...props
}: ResearchIconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      {iconPaths[name]}
    </svg>
  );
}

const common = {
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.7
};

const iconPaths: Record<ResearchIconName, React.ReactNode> = {
  dashboard: (
    <>
      <rect {...common} height="6" rx="1" width="6" x="3" y="3" />
      <rect {...common} height="6" rx="1" width="6" x="15" y="3" />
      <rect {...common} height="6" rx="1" width="6" x="3" y="15" />
      <rect {...common} height="6" rx="1" width="6" x="15" y="15" />
    </>
  ),
  evidence: (
    <>
      <rect {...common} height="18" rx="1.5" width="16" x="4" y="3" />
      <path {...common} d="M4 8h16M9 8v13M14 8v13" />
    </>
  ),
  scenario: (
    <>
      <path {...common} d="M12 3 3.5 7.5 12 12l8.5-4.5L12 3Z" />
      <path {...common} d="m5 11 7 3.8 7-3.8M5 15l7 3.8 7-3.8" />
    </>
  ),
  history: (
    <>
      <path {...common} d="M3.5 12a8.5 8.5 0 1 0 2.2-5.7L3.5 8.5" />
      <path {...common} d="M3.5 4.5v4h4M12 7.5V12l3 2" />
    </>
  ),
  ai: (
    <>
      <path
        {...common}
        d="M9 4.5A3.5 3.5 0 0 0 5.5 8v1A3.5 3.5 0 0 0 4 15.3 3.5 3.5 0 0 0 9 19.5"
      />
      <path
        {...common}
        d="M15 4.5A3.5 3.5 0 0 1 18.5 8v1a3.5 3.5 0 0 1 1.5 6.3 3.5 3.5 0 0 1-5 4.2"
      />
      <path {...common} d="M9 4.5V20M15 4.5V20M9 9h3M12 15h3" />
    </>
  ),
  portfolio: (
    <>
      <circle {...common} cx="12" cy="12" r="8.5" />
      <path {...common} d="M12 3.5V12h8.5M12 12l-5.8 6.2" />
    </>
  ),
  diagnostics: (
    <>
      <path {...common} d="M3 12h3l2-5 4 10 2.5-6 1.5 3H21" />
      <path {...common} d="M4 4h16v16H4z" opacity=".45" />
    </>
  ),
  close: <path {...common} d="m6 6 12 12M18 6 6 18" />,
  chevron: <path {...common} d="m9 6 6 6-6 6" />,
  search: (
    <>
      <circle {...common} cx="10.5" cy="10.5" r="6.5" />
      <path {...common} d="m15.5 15.5 5 5" />
    </>
  ),
  copy: (
    <>
      <rect {...common} height="13" rx="1.5" width="11" x="8" y="8" />
      <path {...common} d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
    </>
  ),
  check: <path {...common} d="m5 12 4 4L19 6" />,
  shield: (
    <>
      <path {...common} d="M12 3 5 6v5c0 4.7 2.8 8.2 7 10 4.2-1.8 7-5.3 7-10V6l-7-3Z" />
      <path {...common} d="m9 12 2 2 4-5" />
    </>
  ),
  database: (
    <>
      <ellipse {...common} cx="12" cy="5.5" rx="7.5" ry="3" />
      <path {...common} d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
    </>
  ),
  clock: (
    <>
      <circle {...common} cx="12" cy="12" r="9" />
      <path {...common} d="M12 7v5l3.5 2" />
    </>
  ),
  layers: (
    <>
      <path {...common} d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path {...common} d="m3 12 9 5 9-5M3 16l9 5 9-5" />
    </>
  )
};
