import type { ReactNode, SVGProps } from "react";

export type AppIconName =
  | "announcement"
  | "assignment"
  | "atom"
  | "audit"
  | "book"
  | "categories"
  | "chevron-left"
  | "chevron-right"
  | "close"
  | "competition"
  | "dashboard"
  | "eye"
  | "layers"
  | "log-out"
  | "mail"
  | "menu"
  | "monitor"
  | "profile"
  | "users"
  | "x";

type AppIconProps = Omit<SVGProps<SVGSVGElement>, "children"> & {
  name: AppIconName;
  size?: number;
};

function IconShape({ name }: Pick<AppIconProps, "name">): ReactNode {
  switch (name) {
    case "atom":
      return (
        <>
          <circle cx="12" cy="12" r="1.8" fill="currentColor" stroke="none" />
          <ellipse cx="12" cy="12" rx="9" ry="3.7" transform="rotate(30 12 12)" />
          <ellipse cx="12" cy="12" rx="9" ry="3.7" transform="rotate(-30 12 12)" />
          <ellipse cx="12" cy="12" rx="9" ry="3.7" transform="rotate(90 12 12)" />
        </>
      );
    case "dashboard":
      return (
        <>
          <rect x="3.5" y="3.5" width="7" height="7" rx="1.3" />
          <rect x="13.5" y="3.5" width="7" height="7" rx="1.3" />
          <rect x="3.5" y="13.5" width="7" height="7" rx="1.3" />
          <rect x="13.5" y="13.5" width="7" height="7" rx="1.3" />
        </>
      );
    case "announcement":
      return (
        <>
          <path d="M4 13.5V10a1.5 1.5 0 0 1 1.5-1.5h2.1L18.5 5v13l-10.9-3.5H5.5A1.5 1.5 0 0 1 4 13.5Z" />
          <path d="M8 14.5 9.8 20h2.7l-1.8-4.7M18.5 9a3.5 3.5 0 0 1 0 5" />
        </>
      );
    case "assignment":
      return (
        <>
          <path d="M7 3.5h7l3 3V20.5H7A1.5 1.5 0 0 1 5.5 19V5A1.5 1.5 0 0 1 7 3.5Z" />
          <path d="M14 3.5V7h3M8.5 11h5M8.5 14.5h5M8.5 18h3" />
        </>
      );
    case "book":
      return (
        <>
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" />
          <path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5v-16Z" />
        </>
      );
    case "competition":
      return (
        <>
          <path d="M8 4h8v4.5a4 4 0 0 1-8 0V4Z" />
          <path d="M8 6H4.5v1.5A3.5 3.5 0 0 0 8 11M16 6h3.5v1.5A3.5 3.5 0 0 1 16 11M12 13v4M8.5 20h7M9.5 17h5" />
        </>
      );
    case "users":
      return (
        <>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 19.5a5.5 5.5 0 0 1 11 0M16 5.5a2.6 2.6 0 0 1 0 5M16.5 14.5a4.5 4.5 0 0 1 4 5" />
        </>
      );
    case "categories":
      return (
        <>
          <path d="m12 3 8.5 4.5L12 12 3.5 7.5 12 3Z" />
          <path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5" />
        </>
      );
    case "monitor":
      return (
        <>
          <rect x="3.5" y="4" width="17" height="12" rx="1.7" />
          <path d="M8.5 20h7M12 16v4" />
        </>
      );
    case "mail":
      return (
        <>
          <rect x="3.5" y="5" width="17" height="14" rx="1.8" />
          <path d="m4.5 7 7.5 6 7.5-6" />
        </>
      );
    case "audit":
      return (
        <>
          <path d="M12 3.5 19 6v5.7c0 4.1-2.5 7.2-7 8.8-4.5-1.6-7-4.7-7-8.8V6l7-2.5Z" />
          <path d="m8.5 12 2.2 2.2 4.8-4.8" />
        </>
      );
    case "profile":
      return (
        <>
          <circle cx="12" cy="8" r="3.2" />
          <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
        </>
      );
    case "eye":
      return (
        <>
          <path d="M3.5 12s3.1-5 8.5-5 8.5 5 8.5 5-3.1 5-8.5 5-8.5-5-8.5-5Z" />
          <circle cx="12" cy="12" r="2.2" />
        </>
      );
    case "layers":
      return (
        <>
          <path d="m12 3.5 8 4-8 4-8-4 8-4Z" />
          <path d="m4 12 8 4 8-4M4 16.5l8 4 8-4" />
        </>
      );
    case "log-out":
      return (
        <>
          <path d="M14 5h4.5A1.5 1.5 0 0 1 20 6.5v11a1.5 1.5 0 0 1-1.5 1.5H14" />
          <path d="M10 8.5 13.5 12 10 15.5M4 12h9.5" />
        </>
      );
    case "chevron-left":
      return <path d="m14.5 5-7 7 7 7" />;
    case "chevron-right":
      return <path d="m9.5 5 7 7-7 7" />;
    case "menu":
      return <path d="M4 7h16M4 12h16M4 17h16" />;
    case "close":
    case "x":
      return <path d="m6 6 12 12M18 6 6 18" />;
  }
}

export function AppIcon({ name, size = 18, ...props }: AppIconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      <IconShape name={name} />
    </svg>
  );
}
