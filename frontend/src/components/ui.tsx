// Small building blocks shared by every screen. Plain components, no UI library.

import { animate, useReducedMotion } from "framer-motion";
import { FlaskConical } from "lucide-react";
import { forwardRef, useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { formatINR, STATE_LABEL } from "../lib/format";
import type { PaymentState } from "../lib/types";

export const cn = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function Card({ className, children, glow }: { className?: string; children: ReactNode; glow?: boolean }) {
  return <div className={cn("panel rounded-2xl p-5 sm:p-6", glow && "shadow-glow-deep", className)}>{children}</div>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
  size?: "md" | "lg";
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium tracking-tight transition",
        "disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.98]",
        size === "lg" ? "h-12 px-5 text-[15px]" : "h-10 px-4 text-sm",
        // Solid purple with a 1px top highlight: reads as a physical button, not a gradient blob.
        variant === "primary" &&
          "bg-deep text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18),0_8px_24px_-12px_rgb(var(--deep)/0.8)] hover:bg-deep/90",
        variant === "ghost" && "border border-line/10 bg-raised text-ink hover:border-line/20",
        variant === "danger" && "border border-bad/30 bg-bad/10 text-bad hover:bg-bad/15",
        className,
      )}
      {...rest}
    >
      {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />}
      {children}
    </button>
  );
});

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string };

export const TextField = forwardRef<HTMLInputElement, FieldProps>(function TextField(
  { label, hint, error, id, className, ...rest },
  ref,
) {
  const inputId = id ?? rest.name ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="block text-sm font-medium text-muted">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={!!error}
        aria-describedby={hint || error ? `${inputId}-help` : undefined}
        className={cn(
          "h-12 w-full rounded-xl border border-line/10 bg-raised px-4 text-ink placeholder:text-muted/60",
          "transition focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15",
          error && "ring-2 ring-bad/60",
          className,
        )}
        {...rest}
      />
      {(hint || error) && (
        <p id={`${inputId}-help`} className={cn("text-xs", error ? "text-bad" : "text-muted")}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
});

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-line/10", className)} aria-hidden />;
}

/** "Simulation only" pill, shown on every screen. */
export function SimulationBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-warn/25 bg-warn/[0.07] px-2 py-1",
        "font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-warn",
        className,
      )}
    >
      <FlaskConical className="h-3 w-3" aria-hidden />
      Simulation only
    </span>
  );
}

// Status = a coloured dot + quiet label. Colour carries meaning; the pill stays neutral.
const STATE_TONE: Record<PaymentState, string> = {
  initiated: "bg-muted",
  held: "bg-warn",
  bank_debited: "bg-primary",
  in_switch: "bg-primary",
  credited: "bg-ok",
  failed: "bg-bad",
  reversal_pending: "bg-warn",
  reversed: "bg-primary",
};

export function StateBadge({ state, stuck }: { state: PaymentState; stuck?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-line/10 bg-raised px-2 py-0.5 text-xs font-medium text-ink/80">
      <span className={cn("h-1.5 w-1.5 rounded-full", stuck ? "bg-warn" : STATE_TONE[state])} aria-hidden />
      {stuck ? "Delayed" : STATE_LABEL[state]}
    </span>
  );
}

/** A rupee amount that counts up to its new value, in tabular figures. */
export function AnimatedAmount({ paise, className }: { paise: number; className?: string }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? paise : 0);
  const from = useRef(reduce ? paise : 0);

  useEffect(() => {
    if (reduce) {
      setShown(paise);
      return;
    }
    const controls = animate(from.current, paise, {
      duration: 0.9,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setShown(Math.round(v)),
    });
    from.current = paise;
    return () => controls.stop();
  }, [paise, reduce]);

  return (
    <span className={cn("money", className)} aria-label={formatINR(paise)}>
      {formatINR(shown)}
    </span>
  );
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center">
      <div className="grid h-11 w-11 place-items-center rounded-xl border border-line/10 bg-raised text-muted">{icon}</div>
      <p className="font-semibold">{title}</p>
      {children && <p className="max-w-xs text-sm text-muted">{children}</p>}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="label">{children}</h2>
      {action}
    </div>
  );
}
