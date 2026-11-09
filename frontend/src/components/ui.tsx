// Small building blocks shared by every screen. Plain components, no UI library.

import { animate, useReducedMotion } from "framer-motion";
import { FlaskConical } from "lucide-react";
import { forwardRef, useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { formatINR, STATE_LABEL } from "../lib/format";
import type { PaymentState } from "../lib/types";

export const cn = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function Card({ className, children, glow }: { className?: string; children: ReactNode; glow?: boolean }) {
  return <div className={cn("glass rounded-3xl p-5 sm:p-6", glow && "shadow-glow-violet", className)}>{children}</div>;
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
        "inline-flex items-center justify-center gap-2 rounded-2xl font-semibold transition",
        "disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.98]",
        size === "lg" ? "h-14 px-6 text-base" : "h-11 px-4 text-sm",
        variant === "primary" && "bg-accent text-white shadow-glow hover:brightness-110",
        variant === "ghost" && "glass text-ink hover:bg-line/10",
        variant === "danger" && "bg-bad/90 text-white hover:bg-bad",
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
          "glass h-12 w-full rounded-2xl px-4 text-ink placeholder:text-muted/60",
          "focus:outline-none focus:ring-2 focus:ring-teal/60",
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
  return <div className={cn("animate-pulse rounded-2xl bg-line/10", className)} aria-hidden />;
}

/** "Simulation only" pill, shown on every screen. */
export function SimulationBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-warn/30 bg-warn/10 px-2.5 py-1",
        "text-[11px] font-semibold uppercase tracking-wide text-warn",
        className,
      )}
    >
      <FlaskConical className="h-3.5 w-3.5" aria-hidden />
      Simulation only
    </span>
  );
}

const STATE_TONE: Record<PaymentState, string> = {
  initiated: "bg-line/10 text-muted",
  bank_debited: "bg-teal/15 text-teal",
  in_switch: "bg-teal/15 text-teal",
  credited: "bg-ok/15 text-ok",
  failed: "bg-bad/15 text-bad",
  reversal_pending: "bg-warn/15 text-warn",
  reversed: "bg-violet/15 text-violet",
};

export function StateBadge({ state, stuck }: { state: PaymentState; stuck?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        stuck ? "bg-warn/15 text-warn" : STATE_TONE[state],
      )}
    >
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
      <div className="grid h-12 w-12 place-items-center rounded-2xl bg-line/10 text-muted">{icon}</div>
      <p className="font-semibold">{title}</p>
      {children && <p className="max-w-xs text-sm text-muted">{children}</p>}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">{children}</h2>
      {action}
    </div>
  );
}
