// TracePay · Grand Prix Edition: a 3D, tilt-and-flip racing card for the home screen.
// Carbon-fibre body, an original open-wheel race car (car 07), a purple "fastest lap"
// timing chip (purple = fastest on a race timing screen, and the app's accent colour),
// a checkered flag, and the cardholder's name in shining gold. No official racing-series
// or team names, logos or liveries are used.
//
// Purely decorative. SIMULATION ONLY: there is deliberately no card number, expiry or CVV
// anywhere, so it can never look like (or be mistaken for) real card details.
//
// How the 3D works:
//  - The outer box sets `perspective`, so rotations look 3D instead of flat.
//  - Pointer position → rotateX / rotateY (max ±12°), smoothed by springs.
//  - The same position moves a light (CSS gradient) across the card, like a reflection.
//  - Two faces share one rotating box; `backface-visibility: hidden` shows only the side
//    facing you. Flipping adds 180° to rotateY.

import { motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { CoinMark } from "./brand";

type Props = { holder: string; vpa: string; bank: string; frozen?: boolean };

const TILT = 12; // degrees
const spring = { stiffness: 180, damping: 18, mass: 0.6 };
const GOLD = "#d9b866";
const PURPLE = "#a78bfa";

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
  const reflection = useMotionTemplate`radial-gradient(55% 75% at ${lightX} ${lightY}, rgb(255 255 255 / 0.13), transparent 60%)`;

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
        aria-label={`TracePay Grand Prix Edition card for ${holder}. ${flipped ? "Showing the back." : "Showing the front."} Press to flip.`}
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
          <CarbonFibre />
          <Checkered className="absolute right-0 top-0 h-[55%] w-[55%] [mask-image:linear-gradient(225deg,black_5%,transparent_60%)]" />
          <RaceStripes />
          {/* Car number, big and italic, like the number on a race car's nose. */}
          <span
            className="absolute right-[7%] top-[16%] select-none text-[78px] font-semibold italic leading-none tracking-tighter text-transparent"
            style={{ WebkitTextStroke: `1.2px ${GOLD}`, opacity: 0.55 }}
            aria-hidden
          >
            07
          </span>
          <RaceCar className="absolute bottom-[29%] right-[0%] w-[76%] drop-shadow-[0_8px_10px_rgb(0_0_0/0.7)]" />
          <motion.div className="absolute inset-0" style={{ background: reflection }} aria-hidden />

          <div className="relative flex h-full flex-col justify-between p-[6.5%] text-white">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <CoinMark size={24} tone="gold" />
                <div className="leading-none">
                  <p className="text-[14px] font-semibold tracking-tight">TracePay</p>
                  <p className="mt-1 font-mono text-[8px] uppercase tracking-[0.28em]" style={{ color: GOLD }}>
                    Grand Prix Edition
                  </p>
                </div>
              </div>
              <Contactless />
            </div>

            <div className="flex items-center gap-3">
              <Chip />
              {frozen ? (
                <span className="rounded border border-amber-300/40 bg-amber-300/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-amber-200">Frozen</span>
              ) : (
                <FastestLap />
              )}
            </div>

            <div className="flex items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-[8px] uppercase tracking-[0.3em] text-white/40">Driver</p>
                <p className="gold-text truncate text-[17px] font-semibold uppercase italic tracking-[0.16em]">{holder}</p>
                <p className="mt-1 truncate font-mono text-[11px] tracking-wide text-white/60">{vpa}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-[8px] uppercase tracking-[0.28em]" style={{ color: GOLD }}>
                  Car Nº 07
                </p>
                <p className="text-[12px] font-medium tracking-wide text-white/75">{bank}</p>
              </div>
            </div>
          </div>
        </Face>

        {/* ---------- BACK ---------- */}
        <Face back>
          <CarbonFibre />
          <Checkered className="absolute bottom-0 left-0 h-[45%] w-[45%] [mask-image:linear-gradient(45deg,black_5%,transparent_60%)]" />
          <motion.div className="absolute inset-0" style={{ background: reflection }} aria-hidden />
          <div className="relative flex h-full flex-col text-white">
            <div className="mt-[8%] h-[16%] w-full bg-black/85" aria-hidden />
            <div className="flex flex-1 gap-3 p-[6.5%] pt-[4%]">
              <div className="flex min-w-0 flex-1 flex-col justify-between">
                <div className="flex h-8 items-center rounded-[4px] border border-[#d9b866]/40 bg-[repeating-linear-gradient(135deg,rgb(250_244_225/0.9)_0_6px,rgb(236_226_196/0.9)_6px_12px)] px-2.5">
                  <span className="truncate font-mono text-[9px] font-medium uppercase tracking-widest text-neutral-700">Not a payment card</span>
                </div>
                <p className="text-[9.5px] leading-relaxed text-white/55">
                  Simulation only. A design element of a simulated app: it has no number and cannot be used to pay. Fake money, fake banks, a mock UPI switch.
                </p>
                <div className="flex items-center gap-2">
                  <CoinMark size={18} tone="gold" />
                  <span className="font-mono text-[8.5px] uppercase tracking-[0.22em]" style={{ color: GOLD }}>
                    Grand Prix · Nº 07
                  </span>
                </div>
              </div>
              <div className="flex w-[38%] shrink-0 flex-col items-center justify-center">
                <Circuit animate={!reduce} />
                <p className="mt-1 font-mono text-[8px] uppercase tracking-[0.25em] text-white/45">Home circuit</p>
              </div>
            </div>
          </div>
        </Face>
      </motion.div>
      <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-muted">Tap the card to flip</p>
    </div>
  );
}

function Face({ back, children }: { back?: boolean; children: ReactNode }) {
  return (
    <div
      className="absolute inset-0 overflow-hidden rounded-[18px] border border-white/10 shadow-[0_30px_70px_-25px_rgb(0_0_0/0.9),0_0_40px_-14px_rgb(124_58_237/0.45)]"
      style={{ backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden", transform: back ? "rotateY(180deg)" : undefined }}
    >
      {children}
    </div>
  );
}

/** Carbon-fibre twill: the classic layered-gradient weave, under a glossy clear coat. */
function CarbonFibre() {
  return (
    <>
      <div
        className="absolute inset-0"
        aria-hidden
        style={{
          backgroundColor: "#0e0e10",
          backgroundImage: [
            "linear-gradient(27deg, #141416 3px, transparent 3px)",
            "linear-gradient(207deg, #141416 3px, transparent 3px)",
            "linear-gradient(27deg, #1d1d21 3px, transparent 3px)",
            "linear-gradient(207deg, #1d1d21 3px, transparent 3px)",
            "linear-gradient(90deg, #17171a 6px, transparent 6px)",
            "linear-gradient(#18181b 25%, #151518 25%, #151518 50%, transparent 50%, transparent 75%, #1f1f23 75%, #1f1f23)",
          ].join(","),
          backgroundPosition: "0 3px, 6px 0, 0 6px, 6px 3px, 0 0, 0 0",
          backgroundSize: "12px 12px",
        }}
      />
      {/* Clear coat: gloss from the top, shadow at the bottom, purple light underneath. */}
      <div
        className="absolute inset-0"
        aria-hidden
        style={{
          background: [
            "linear-gradient(165deg, rgb(255 255 255 / 0.12) 0%, rgb(255 255 255 / 0.02) 35%, transparent 50%)",
            "radial-gradient(80% 55% at 60% 115%, rgb(124 58 237 / 0.4), transparent 70%)",
            "linear-gradient(180deg, transparent 55%, rgb(0 0 0 / 0.5) 100%)",
          ].join(","),
        }}
      />
    </>
  );
}

/** Checkered flag squares, faded out with a mask. */
function Checkered({ className }: { className?: string }) {
  return (
    <svg className={className} aria-hidden>
      <defs>
        <pattern id="checks" width="14" height="14" patternUnits="userSpaceOnUse">
          <rect width="7" height="7" fill="white" opacity="0.13" />
          <rect x="7" y="7" width="7" height="7" fill="white" opacity="0.13" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#checks)" />
    </svg>
  );
}

/** Two slanted livery stripes across the card: purple and a thin gold one. */
function RaceStripes() {
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 252" preserveAspectRatio="none" aria-hidden>
      <path d="M-10 210 L260 70 L292 70 L22 210 Z" fill={PURPLE} opacity="0.13" />
      <path d="M30 210 L300 70 L306 70 L36 210 Z" fill={GOLD} opacity="0.22" />
    </svg>
  );
}

/** The purple timing chip: on a race timing screen, purple marks the fastest of anyone. */
function FastestLap() {
  return (
    <span className="flex items-center gap-1.5 rounded-[5px] border border-[#a78bfa]/50 bg-[#7c3aed]/30 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-[#ddd0ff] shadow-[0_0_14px_-2px_rgb(124_58_237/0.7)]">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#a78bfa]" aria-hidden />
      Fastest lap 1:17.452
    </span>
  );
}

/**
 * An original open-wheel race car in side profile (nose to the left), car 07:
 * front wing with endplate, low nose, halo over the cockpit, helmet, sidepods with a
 * purple and gold livery stripe, airbox, shark fin, rear wing with DRS flap, diffuser,
 * and big exposed wheels with gold sidewall rings that spin. Speed lines trail behind.
 */
function RaceCar({ className }: { className?: string }) {
  // Ground is y = 90. Front wheel radius 21, rear 23 (rear tyres are wider/taller).
  const FRONT = { cx: 76, cy: 69, r: 21 };
  const REAR = { cx: 286, cy: 67, r: 23 };
  const chassis =
    "M16 76 L20 72 L62 66 L112 60 L150 58 L196 54 L206 37 L226 35 L240 41 L300 57 L318 61 L318 74 L300 78 L118 80 L62 77 Z";
  const topEdge = "M20 72 L62 66 L112 60 L150 58 L196 54 L206 37 L226 35 L240 41 L300 57";
  return (
    <svg viewBox="0 0 370 96" className={className} aria-hidden>
      <defs>
        <linearGradient id="bodyPaint" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4c4c5a" />
          <stop offset="40%" stopColor="#17171d" />
          <stop offset="100%" stopColor="#060608" />
        </linearGradient>
        <linearGradient id="helmet" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f3dc95" />
          <stop offset="100%" stopColor="#8f6c2a" />
        </linearGradient>
        <radialGradient id="raceRim" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="#2e2e35" />
          <stop offset="100%" stopColor="#0b0b0d" />
        </radialGradient>
      </defs>

      {/* Speed lines trailing behind. */}
      {[48, 60, 72, 82].map((y, i) => (
        <line key={y} x1="322" y1={y} x2="368" y2={y} stroke={i % 2 ? PURPLE : GOLD} strokeWidth="0.9" strokeLinecap="round" opacity={0.6 - i * 0.1} className="speed-line" style={{ animationDelay: `${i * 0.18}s` }} />
      ))}

      {/* Ground shadow. */}
      <ellipse cx="170" cy="91.5" rx="165" ry="3.5" fill="black" opacity="0.8" />

      {/* Rear wing pillar (behind the body). */}
      <path d="M322 36 L324 62" stroke="#0b0b0e" strokeWidth="3" />

      {/* Chassis, nose and engine cover. */}
      <path d={chassis} fill="url(#bodyPaint)" />
      {/* Livery: a purple band with a gold pinstripe along the car. */}
      <path d="M58 70 L150 63 L262 61 L306 64 L306 68 L262 65.5 L150 67.5 L58 74 Z" fill={PURPLE} opacity="0.9" />
      <path d="M58 68.5 L150 61.5 L262 59.5 L306 62.5" stroke={GOLD} strokeWidth="0.8" fill="none" />
      {/* Sidepod with its dark inlet, and the floor. */}
      <path d="M150 66 L166 61 L252 61 L280 68 L282 79 L150 80 Z" fill="#101015" opacity="0.85" />
      <path d="M150 66 L162 62.5 L162 76 L150 77 Z" fill="#020203" />
      <path d="M112 81 L300 79" stroke="#000" strokeWidth="2" />
      {/* Shark fin with the car number. */}
      <path d="M226 35 L300 56 L300 50 L236 34 Z" fill="#202027" />
      <text x="258" y="52" fill={GOLD} fontSize="9" fontStyle="italic" fontWeight="700" fontFamily="Geist, sans-serif">
        07
      </text>
      {/* Top edge catching the light. */}
      <path d={topEdge} stroke="white" strokeWidth="0.8" fill="none" opacity="0.35" />

      {/* Helmet, then the halo over it. */}
      <circle cx="178" cy="50" r="7.5" fill="url(#helmet)" />
      <path d="M172 49.5 L184 48" stroke="#08080a" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M146 58 C158 41, 188 39, 202 48" stroke="#0a0a0d" strokeWidth="3.4" fill="none" strokeLinecap="round" />
      <path d="M146 58 C158 41, 188 39, 202 48" stroke="white" strokeWidth="0.6" fill="none" opacity="0.3" />
      <path d="M152 57 L157 46" stroke="#0a0a0d" strokeWidth="2.6" strokeLinecap="round" />
      {/* Wing mirror. */}
      <path d="M136 55 L146 53.5 L146 57 L138 57.5 Z" fill="#0a0a0d" stroke={GOLD} strokeWidth="0.4" />

      {/* Front wing: two elements and an endplate. */}
      <path d="M4 82 L72 82 L74 86 L6 87 Z" fill="#0b0b0e" stroke={GOLD} strokeWidth="0.5" />
      <path d="M8 77.5 L66 76.5 L66 79.5 L10 80.5 Z" fill={PURPLE} opacity="0.85" />
      <path d="M2 71 L9 71 L9 88 L2 88 Z" fill="#0b0b0e" stroke={GOLD} strokeWidth="0.5" />

      {/* Rear wing: mainplane, DRS flap and endplate. Diffuser below. */}
      <path d="M302 33 L356 30 L356 37 L304 39 Z" fill="#0b0b0e" stroke={GOLD} strokeWidth="0.5" />
      <path d="M306 24 L356 21 L356 27 L308 28.5 Z" fill={PURPLE} opacity="0.9" />
      <path d="M350 14 L358 14 L358 64 L350 64 Z" fill="#0b0b0e" stroke={GOLD} strokeWidth="0.5" />
      <path d="M300 78 L338 73 L342 80 L304 84 Z" fill="#0b0b0e" />

      {/* Exposed wheels with gold sidewall rings, spinning. */}
      {[FRONT, REAR].map(({ cx, cy, r }) => (
        <g key={cx}>
          <circle cx={cx} cy={cy} r={r} fill="#050506" />
          <circle cx={cx} cy={cy} r={r - 3} fill="none" stroke={GOLD} strokeWidth="1.4" opacity="0.9" />
          <circle cx={cx} cy={cy} r={r - 7} fill="url(#raceRim)" />
          <g className="wheel-spin" style={{ transformOrigin: `${cx}px ${cy}px` }}>
            {Array.from({ length: 10 }, (_, i) => {
              const a = (i * 36 * Math.PI) / 180;
              return (
                <line
                  key={i}
                  x1={cx + 3.5 * Math.cos(a)}
                  y1={cy + 3.5 * Math.sin(a)}
                  x2={cx + (r - 8) * Math.cos(a + 0.25)}
                  y2={cy + (r - 8) * Math.sin(a + 0.25)}
                  stroke="#55555f"
                  strokeWidth="0.9"
                />
              );
            })}
            {/* A gold mark on the sidewall makes the spin visible. */}
            <path d={`M${cx - (r - 3)} ${cy} A${r - 3} ${r - 3} 0 0 1 ${cx - (r - 3) * 0.5} ${cy - (r - 3) * 0.87}`} stroke="#fff4c9" strokeWidth="1.6" fill="none" />
            <circle cx={cx} cy={cy} r="3.2" fill="#f3dc95" />
          </g>
        </g>
      ))}
    </svg>
  );
}

/** An original race circuit with a glowing car lapping it (the back of the card). */
function Circuit({ animate }: { animate: boolean }) {
  const track =
    "M30 92 L84 96 Q102 98 112 86 L130 62 Q138 51 150 53 L172 57 Q188 60 186 44 Q184 29 167 27 L92 21 Q70 19 62 32 L50 52 Q44 62 32 64 Q17 66 17 79 Q17 91 30 92 Z";
  return (
    <svg viewBox="0 0 200 116" className="w-full" aria-hidden>
      <path d={track} fill="none" stroke="black" strokeWidth="7" strokeLinejoin="round" opacity="0.6" />
      <path d={track} fill="none" stroke={GOLD} strokeWidth="2.2" strokeLinejoin="round" opacity="0.85" />
      {/* Start/finish line. */}
      <path d="M58 90 L58 98" stroke="white" strokeWidth="2.4" />
      {animate ? (
        <circle r="4" fill={PURPLE} style={{ filter: "drop-shadow(0 0 4px #a78bfa)" }}>
          <animateMotion dur="6s" repeatCount="indefinite" path={track} rotate="auto" />
        </circle>
      ) : (
        <circle cx="58" cy="94" r="4" fill={PURPLE} />
      )}
    </svg>
  );
}

/** EMV chip in champagne gold, drawn with SVG. */
function Chip() {
  return (
    <svg width="44" height="33" viewBox="0 0 46 34" aria-hidden>
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

/** Contactless symbol: three widening arcs, in gold. */
function Contactless() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={GOLD} strokeWidth="1.8" strokeLinecap="round" opacity="0.85" aria-hidden>
      <path d="M8.5 9a5 5 0 0 1 0 6" />
      <path d="M12 6.5a9 9 0 0 1 0 11" />
      <path d="M15.5 4a13 13 0 0 1 0 16" />
    </svg>
  );
}
