// The TracePay Black card: a 3D, tilt-and-flip metal card for the home screen.
//
// It is purely decorative. SIMULATION ONLY: there is deliberately no card number, expiry
// or CVV anywhere, so it can never look like (or be mistaken for) real card details.
// The front shows the member's name and UPI ID; the back says it isn't a payment card.
//
// How the 3D works:
//  - The outer box sets `perspective`, so rotations look 3D instead of flat.
//  - Pointer position → rotateX / rotateY (max ±12°), smoothed by springs.
//  - The same position drives CSS variables (--mx, --my) that move a holographic light
//    across the metal, so the sheen tracks your finger like light on a real card.
//  - Two faces share one rotating box; `backface-visibility: hidden` shows only the side
//    facing you. Flipping adds 180° to rotateY.

import { motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { useState, type KeyboardEvent, type PointerEvent } from "react";
import { CoinMark, Guilloche } from "./brand";

type Props = { holder: string; vpa: string; bank: string; frozen?: boolean };

const TILT = 12; // degrees
const spring = { stiffness: 180, damping: 18, mass: 0.6 };

export function PremiumCard({ holder, vpa, bank, frozen }: Props) {
  const reduce = useReducedMotion();
  const [flipped, setFlipped] = useState(false);

  // Pointer position over the card, 0..1 on each axis (0.5 = centre).
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const rotateX = useSpring(useTransform(py, [0, 1], [TILT, -TILT]), spring);
  const tiltY = useSpring(useTransform(px, [0, 1], [-TILT, TILT]), spring);
  const flipY = useSpring(0, { stiffness: 120, damping: 16 });
  const rotateY = useTransform([tiltY, flipY], ([t, f]: number[]) => t + f);
  const lightX = useTransform(px, (v) => `${v * 100}%`);
  const lightY = useTransform(py, (v) => `${v * 100}%`);
  const holo = useMotionTemplate`radial-gradient(60% 80% at ${lightX} ${lightY}, rgb(255 255 255 / 0.16), transparent 60%)`;
  const foil = useMotionTemplate`linear-gradient(115deg, transparent 20%, rgb(167 139 250 / 0.22) ${lightX}, rgb(236 72 153 / 0.12), rgb(56 189 248 / 0.10), transparent 80%)`;

  function onMove(e: PointerEvent<HTMLDivElement>) {
    if (reduce) return;
    const box = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - box.left) / box.width);
    py.set((e.clientY - box.top) / box.height);
  }
  function reset() {
    px.set(0.5);
    py.set(0.5);
  }
  function flip() {
    const next = !flipped;
    setFlipped(next);
    flipY.set(next ? 180 : 0);
  }
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      flip();
    }
  }

  return (
    <div className="w-full max-w-[400px]" style={{ perspective: 1200 }}>
      <motion.div
        role="button"
        tabIndex={0}
        aria-label={`TracePay Black card for ${holder}. ${flipped ? "Showing the back." : "Showing the front."} Press to flip.`}
        aria-pressed={flipped}
        onPointerMove={onMove}
        onPointerLeave={reset}
        onClick={flip}
        onKeyDown={onKey}
        // Idle float: a slow bob when nobody is touching it.
        animate={reduce ? undefined : { y: [0, -6, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
        className="relative aspect-[1.586] w-full cursor-pointer select-none rounded-[18px] outline-offset-4"
        style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
      >
        {/* ---------- FRONT ---------- */}
        <Face>
          <Metal />
          <Guilloche className="absolute -right-24 -top-28 h-[420px] w-[420px] text-primary/60" speed={160} />
          <motion.div className="absolute inset-0 mix-blend-screen" style={{ background: foil }} aria-hidden />
          <motion.div className="absolute inset-0" style={{ background: holo }} aria-hidden />

          <div className="relative flex h-full flex-col justify-between p-[7%] text-white">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <CoinMark size={26} />
                <div className="leading-none">
                  <p className="text-[15px] font-semibold tracking-tight">TracePay</p>
                  <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.3em] text-white/50">Black</p>
                </div>
              </div>
              <Contactless />
            </div>

            <div className="flex items-center gap-4">
              <Chip />
              {frozen && <span className="rounded border border-amber-300/40 bg-amber-300/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-amber-200">Frozen</span>}
            </div>

            <div className="flex items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-[9px] uppercase tracking-[0.25em] text-white/45">UPI ID</p>
                <p className="truncate font-mono text-[13px] tracking-wide text-white/90">{vpa}</p>
                <p className="mt-2 truncate text-[13px] font-medium uppercase tracking-[0.18em] text-white/85">{holder}</p>
              </div>
              <div className="text-right">
                <p className="font-mono text-[8px] uppercase tracking-[0.25em] text-white/40">Simulation</p>
                <p className="text-[11px] font-medium text-white/60">{bank}</p>
              </div>
            </div>
          </div>
        </Face>

        {/* ---------- BACK ---------- */}
        <Face back>
          <Metal />
          <Guilloche className="absolute -bottom-40 -left-24 h-[420px] w-[420px] text-primary/40" speed={200} />
          <motion.div className="absolute inset-0" style={{ background: holo }} aria-hidden />
          <div className="relative flex h-full flex-col text-white">
            <div className="mt-[9%] h-[18%] w-full bg-black/80" aria-hidden />
            <div className="flex flex-1 flex-col justify-between p-[7%] pt-[5%]">
              <div className="flex h-9 items-center rounded-[4px] bg-[repeating-linear-gradient(135deg,rgb(255_255_255/0.85)_0_6px,rgb(235_232_245/0.85)_6px_12px)] px-3">
                <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-neutral-700">Simulation only · not a payment card</span>
              </div>
              <p className="text-[10px] leading-relaxed text-white/55">
                A design element of a simulated app. It has no number and cannot be used to pay. Fake money, fake banks, a mock UPI switch.
              </p>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-white/40">Invite only · Member</span>
                <CoinMark size={20} />
              </div>
            </div>
          </div>
        </Face>
      </motion.div>
      <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-muted">Tap the card to flip</p>
    </div>
  );
}

function Face({ back, children }: { back?: boolean; children: React.ReactNode }) {
  return (
    <div
      className="absolute inset-0 overflow-hidden rounded-[18px] border border-white/10 shadow-[0_30px_70px_-25px_rgb(124_58_237/0.55),0_12px_30px_-10px_rgb(0_0_0/0.7)]"
      style={{ backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden", transform: back ? "rotateY(180deg)" : undefined }}
    >
      {children}
    </div>
  );
}

/** Black metal: a dark gradient plus fine brushed lines. */
function Metal() {
  return (
    <div
      className="absolute inset-0"
      aria-hidden
      style={{
        background: [
          "repeating-linear-gradient(90deg, rgb(255 255 255 / 0.018) 0 1px, transparent 1px 3px)",
          "radial-gradient(120% 90% at 100% 0%, rgb(124 58 237 / 0.35), transparent 55%)",
          "linear-gradient(135deg, #1a1822 0%, #0c0b10 45%, #121019 70%, #1d1530 100%)",
        ].join(","),
      }}
    />
  );
}

/** EMV chip in champagne gold, drawn with SVG. */
function Chip() {
  return (
    <svg width="46" height="34" viewBox="0 0 46 34" aria-hidden>
      <defs>
        <linearGradient id="chipGold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f3e3b5" />
          <stop offset="45%" stopColor="#c9a65a" />
          <stop offset="100%" stopColor="#efdba4" />
        </linearGradient>
      </defs>
      <rect x="0.5" y="0.5" width="45" height="33" rx="6" fill="url(#chipGold)" stroke="#a88a45" strokeWidth="0.8" />
      <path d="M0 11h14M0 23h14M32 11h14M32 23h14M14 0v34M32 0v34M14 17h18" stroke="#9c7f3f" strokeWidth="0.9" fill="none" opacity="0.8" />
      <rect x="18" y="8" width="10" height="18" rx="3" fill="none" stroke="#9c7f3f" strokeWidth="0.9" />
    </svg>
  );
}

/** Contactless symbol: three widening arcs. */
function Contactless() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" opacity="0.75" aria-hidden>
      <path d="M8.5 9a5 5 0 0 1 0 6" />
      <path d="M12 6.5a9 9 0 0 1 0 11" />
      <path d="M15.5 4a13 13 0 0 1 0 16" />
    </svg>
  );
}
