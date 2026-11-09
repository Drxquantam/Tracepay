// The signature element: a glowing dot that travels Payer's bank → UPI switch → Payee's
// bank, pauses and turns amber when delayed, red when late or failed, and flies back along
// a lower arc when the money is being refunded.
//
// How the dot follows a curve: each leg is a quadratic Bézier curve (start, control, end).
// A progress number `t` goes 0 → 1 → 2 along the two forward legs; for each value we work
// out the (x, y) point on the curve and move the dot there. The return trip is a third
// curve with its own 0 → 1 progress.

import { animate, motion, useMotionValue, useReducedMotion } from "framer-motion";
import { ArrowLeftRight, Check, Landmark, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Health, PaymentState, Position } from "../lib/types";

type Pt = { x: number; y: number };
const P0: Pt = { x: 48, y: 72 }; // payer's bank
const P1: Pt = { x: 200, y: 72 }; // UPI switch
const P2: Pt = { x: 352, y: 72 }; // payee's bank
const C1: Pt = { x: 124, y: 22 };
const C2: Pt = { x: 276, y: 22 };
const CR: Pt = { x: 124, y: 128 }; // control point of the refund arc (below the line)

function bezier(a: Pt, c: Pt, b: Pt, u: number): Pt {
  const k = 1 - u;
  return { x: k * k * a.x + 2 * k * u * c.x + u * u * b.x, y: k * k * a.y + 2 * k * u * c.y + u * u * b.y };
}

type Mode = "forward" | "return";
function pointAt(mode: Mode, t: number): Pt {
  if (mode === "return") return bezier(P1, CR, P0, t);
  return t <= 1 ? bezier(P0, C1, P1, t) : bezier(P1, C2, P2, t - 1);
}

/** Where the dot should rest for a given payment state. */
function target(position: Position, state: PaymentState): { mode: Mode; t: number } {
  if (position === "returning") return { mode: "return", t: state === "reversed" ? 1 : 0.55 };
  if (position === "payee_bank") return { mode: "forward", t: 2 };
  if (position === "switch") return { mode: "forward", t: 1 };
  return { mode: "forward", t: state === "bank_debited" ? 0.3 : 0 };
}

const FORWARD_D = `M${P0.x} ${P0.y} Q${C1.x} ${C1.y} ${P1.x} ${P1.y} Q${C2.x} ${C2.y} ${P2.x} ${P2.y}`;
const LEG2_D = `M${P1.x} ${P1.y} Q${C2.x} ${C2.y} ${P2.x} ${P2.y}`;
const LEG1_D = `M${P0.x} ${P0.y} Q${C1.x} ${C1.y} ${P1.x} ${P1.y}`;
const RETURN_D = `M${P1.x} ${P1.y} Q${CR.x} ${CR.y} ${P0.x} ${P0.y}`;

const COLOR: Record<Health | "done", string> = {
  ok: "rgb(var(--teal))",
  done: "rgb(var(--ok))",
  delayed: "rgb(var(--warn))",
  late: "rgb(var(--bad))",
  failed: "rgb(var(--bad))",
};

type Props = {
  position: Position;
  health: Health;
  state: PaymentState;
  stages: { key: string; label: string }[];
  summary: string; // read out by screen readers in place of the drawing
};

export function FlightPath({ position, health, state, stages, summary }: Props) {
  const reduce = useReducedMotion();
  const cx = useMotionValue(P0.x);
  const cy = useMotionValue(P0.y);
  const progress = useRef<{ mode: Mode; t: number }>({ mode: "forward", t: 0 });
  const [mode, setMode] = useState<Mode>("forward");
  const [t, setT] = useState(0); // mirrored into state to draw the "completed" part of the track

  const goal = target(position, state);
  const finished = state === "credited" || state === "reversed";
  const color = finished ? COLOR.done : COLOR[health];
  const pulsing = health === "delayed" || health === "late";
  const moving = health === "ok" && (state === "bank_debited" || state === "in_switch");

  useEffect(() => {
    const from = progress.current;
    // Switching from the forward track to the refund arc: both start at the switch, so we
    // can jump the progress to 0 on the new curve without the dot visibly moving.
    let start = from.t;
    if (from.mode !== goal.mode) start = 0;
    setMode(goal.mode);

    const place = (v: number) => {
      const p = pointAt(goal.mode, v);
      cx.set(p.x);
      cy.set(p.y);
      setT(v);
    };
    progress.current = { mode: goal.mode, t: goal.t };
    if (reduce) {
      place(goal.t);
      return;
    }
    const controls = animate(start, goal.t, {
      duration: Math.min(2.2, 0.6 + Math.abs(goal.t - start) * 0.9),
      ease: [0.45, 0, 0.2, 1],
      onUpdate: place,
    });
    return () => controls.stop();
  }, [goal.mode, goal.t, reduce, cx, cy]);

  // Which stages the money has reached. On a refund it got as far as the switch (never
  // the payee) and is coming back to the payer's bank.
  const reached = (i: number) => {
    if (mode === "forward") return t >= i - 0.001;
    return i === 1 || (i === 0 && t >= 0.999);
  };
  const caption = ["Your bank", "Simulated", "Payee's bank"];

  return (
    <figure className="w-full">
      <svg viewBox="0 0 400 160" className="w-full overflow-visible" role="img" aria-label={summary}>
        <defs>
          <linearGradient id="trackGrad" x1="0" x2="1">
            <stop offset="0%" stopColor="rgb(var(--teal))" />
            <stop offset="100%" stopColor="rgb(var(--violet))" />
          </linearGradient>
          <filter id="glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="6" />
          </filter>
        </defs>

        {/* Base tracks */}
        <path d={FORWARD_D} fill="none" stroke="rgb(var(--line) / 0.12)" strokeWidth={3} strokeLinecap="round" />
        {mode === "return" && <path d={RETURN_D} fill="none" stroke="rgb(var(--line) / 0.12)" strokeWidth={3} strokeDasharray="2 7" strokeLinecap="round" />}

        {/* Completed part of the journey */}
        {mode === "forward" ? (
          <path d={FORWARD_D} fill="none" stroke="url(#trackGrad)" strokeWidth={3} strokeLinecap="round" pathLength={1} strokeDasharray={`${t / 2} 1`} />
        ) : (
          <>
            <path d={LEG1_D} fill="none" stroke="url(#trackGrad)" strokeWidth={3} strokeLinecap="round" />
            <path d={RETURN_D} fill="none" stroke={color} strokeWidth={3} strokeLinecap="round" pathLength={1} strokeDasharray={`${t} 1`} />
          </>
        )}

        {/* "Data flowing" dashes along the next leg while things are moving normally */}
        {moving && !reduce && (
          <motion.path
            d={position === "switch" ? LEG2_D : LEG1_D}
            fill="none"
            stroke="rgb(var(--teal) / 0.7)"
            strokeWidth={3}
            strokeLinecap="round"
            strokeDasharray="1 11"
            animate={{ strokeDashoffset: [0, -24] }}
            transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
          />
        )}

        {/* Stage nodes */}
        {[P0, P1, P2].map((p, i) => {
          const isLast = i === 2;
          const done = reached(i);
          const Icon = i === 1 ? ArrowLeftRight : Landmark;
          return (
            <g key={i}>
              <circle cx={p.x} cy={p.y} r={17} fill="rgb(var(--canvas))" stroke={done ? "url(#trackGrad)" : "rgb(var(--line) / 0.18)"} strokeWidth={2} />
              {isLast && state === "credited" ? (
                <Check x={p.x - 8} y={p.y - 8} width={16} height={16} stroke="rgb(var(--ok))" strokeWidth={3} />
              ) : i === 0 && state === "failed" ? (
                <X x={p.x - 8} y={p.y - 8} width={16} height={16} stroke="rgb(var(--bad))" strokeWidth={3} />
              ) : (
                <Icon x={p.x - 8} y={p.y - 8} width={16} height={16} stroke={done ? "rgb(var(--ink))" : "rgb(var(--muted))"} strokeWidth={2} />
              )}
              <text x={p.x} y={p.y + 36} textAnchor="middle" fontSize={11.5} fontWeight={700} fill="rgb(var(--ink))">
                {stages[i]?.label.replace(" (simulated)", "")}
              </text>
              <text x={p.x} y={p.y + 51} textAnchor="middle" fontSize={10} fill="rgb(var(--muted))">
                {caption[i]}
              </text>
            </g>
          );
        })}

        {/* The money */}
        <motion.circle cx={cx} cy={cy} r={13} fill={color} opacity={0.55} filter="url(#glow)" />
        {pulsing && !reduce && (
          <motion.circle cx={cx} cy={cy} fill="none" stroke={color} strokeWidth={2} initial={{ r: 8, opacity: 0.9 }} animate={{ r: 22, opacity: 0 }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }} />
        )}
        <motion.circle cx={cx} cy={cy} r={7} fill={color} stroke="white" strokeWidth={2} />
      </svg>
    </figure>
  );
}
