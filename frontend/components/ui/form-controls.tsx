import type { InputHTMLAttributes, ReactNode } from "react";

export const inputClassName =
  "mt-2 min-h-11 w-full border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] px-3 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] hover:border-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-60";

export const buttonClassName =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-[var(--color-action-border)] bg-[var(--color-action-fill)] px-5 font-semibold text-[var(--color-action-text)] shadow-[var(--shadow-button)] transition duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-action-fill-hover)] hover:shadow-[var(--shadow-button-hover)] disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:translate-y-0 disabled:hover:shadow-[var(--shadow-button)]";

export const commandButtonClassName =
  "inline-flex h-9 min-h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-transparent bg-[var(--color-action-fill)] px-3 text-sm font-medium whitespace-nowrap text-[var(--color-action-text)] transition-all outline-none hover:bg-[var(--color-action-fill-hover)] focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] active:translate-y-px disabled:pointer-events-none disabled:opacity-50";

export const commandLinkClassName = commandButtonClassName + " no-underline";

export const buttonLinkClassName = buttonClassName + " no-underline";

type FieldProps = Readonly<{
  label: string;
  name: string;
  hint?: string;
  error?: string;
  children?: ReactNode;
}> &
  Omit<InputHTMLAttributes<HTMLInputElement>, "name">;

export function Field({
  label,
  name,
  hint,
  error,
  children,
  ...inputProps
}: FieldProps) {
  const describedBy = [
    hint ? name + "-hint" : null,
    error ? name + "-error" : null,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div>
      <label className="block text-sm font-medium" htmlFor={name}>
        {label}
      </label>
      <input
        {...inputProps}
        aria-describedby={describedBy || undefined}
        aria-invalid={error ? true : undefined}
        className={inputClassName}
        id={name}
        name={name}
      />
      {children}
      {hint ? (
        <p
          className="mt-2 text-xs text-[var(--color-text-muted)]"
          id={name + "-hint"}
        >
          {hint}
        </p>
      ) : null}
      {error ? (
        <p
          className="mt-2 text-sm text-[var(--color-danger)]"
          id={name + "-error"}
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function FormMessage({
  children,
  tone = "danger",
}: Readonly<{
  children: ReactNode;
  tone?: "danger" | "success" | "info";
}>) {
  const color = {
    danger: "border-[var(--color-danger)]",
    success: "border-[var(--color-success)]",
    info: "border-[var(--color-info)]",
  }[tone];
  return (
    <p
      aria-live="polite"
      className={
        "border-l-2 " +
        color +
        " bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text-secondary)]"
      }
      role="status"
    >
      {children}
    </p>
  );
}
