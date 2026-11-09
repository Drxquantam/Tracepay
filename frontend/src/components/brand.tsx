// Brand graphics, all drawn in code (no image files):
//  - CoinMark: the logo, a coin with a reeded (ridged) edge, like a real ₹ coin.
//  - Guilloche: the fine interlaced engraving printed on banknotes and cheques as an
//    anti-forgery pattern. It's TracePay's money motif, slowly rotating where it appears.
//
// The guilloché is made of hypotrochoids (the curves a Spirograph draws):
//   x(t) = (R − r)·cos t + d·cos((R − r)/r · t)
//   y(t) = (R − r)·sin t − d·sin((R − r)/r · t)
// Layering a few with slightly different r and d gives the woven banknote look.

import { motion, useReducedMotion } from "framer-motion";
import { useMemo } from "react";
import { cn } from "./ui";

const COIN_TONES = {
  purple: { edge: "rgb(var(--primary))", from: "rgb(var(--primary))", to: "rgb(var(--deep))" },
  gold: { edge: "#d9b866", from: "#f3dc95", to: "#8f6c2a" },
};

export function CoinMark({ size = 28, className, tone = "purple" }: { size?: number; className?: string; tone?: keyof typeof COIN_TONES }) {
  const c = COIN_TONES[tone];
  const id = `coinFace-${tone}`; // gradient ids must be unique per colour
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={c.from} />
          <stop offset="100%" stopColor={c.to} />
        </linearGradient>
      </defs>
      {/* Reeded edge: a dashed ring reads as the ridges on a coin's rim. */}
      <circle cx="16" cy="16" r="14.5" fill="none" stroke={c.edge} strokeWidth="2" strokeDasharray="1.2 1.4" opacity="0.9" />
      <circle cx="16" cy="16" r="11.5" fill={`url(#${id})`} />
      {/* A "T" whose bar doubles as the path money travels along. */}
      <path d="M10.5 12.5h11M16 12.5v8.5" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="21.5" cy="12.5" r="1.6" fill="white" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5 font-semibold tracking-tight", className)}>
      <CoinMark />
      <span>TracePay</span>
    </span>
  );
}

function hypotrochoid(R: number, r: number, d: number, scale: number): string {
  const k = (R - r) / r;
  let path = "";
  // The curve closes after r / gcd(R, r) full turns; ~240 points per turn keeps it smooth.
  const turns = r / gcd(R, r);
  const steps = 240 * turns;
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2 * turns;
    const x = (R - r) * Math.cos(t) + d * Math.cos(k * t);
    const y = (R - r) * Math.sin(t) - d * Math.sin(k * t);
    path += `${i === 0 ? "M" : "L"}${(x * scale).toFixed(2)} ${(y * scale).toFixed(2)}`;
  }
  return path;
}

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

// Each layer: [R, r, d]. Ratios chosen so each curve closes in a few turns (light to
// render) while the layers still weave into each other.
const LAYERS: [number, number, number][] = [
  [96, 36, 52], // 3 turns
  [96, 40, 50], // 5 turns
  [96, 42, 46], // 7 turns
  [72, 27, 30], // 3 turns
];

export function Guilloche({ className, size = 420, speed = 140 }: { className?: string; size?: number; speed?: number }) {
  const reduce = useReducedMotion();
  const paths = useMemo(() => LAYERS.map(([R, r, d]) => hypotrochoid(R, r, d, 1.45)), []);
  const half = size / 2;
  return (
    <motion.svg
      viewBox={`${-half} ${-half} ${size} ${size}`}
      className={cn("pointer-events-none", className)}
      aria-hidden
      animate={reduce ? undefined : { rotate: 360 }}
      transition={{ duration: speed, repeat: Infinity, ease: "linear" }}
    >
      {paths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke="currentColor" strokeWidth={0.45} opacity={0.55 - i * 0.08} />
      ))}
    </motion.svg>
  );
}
