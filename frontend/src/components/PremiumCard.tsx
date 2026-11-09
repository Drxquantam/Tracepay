// TracePay Black · V12 Limited Edition: a 3D, tilt-and-flip hypercar-styled card for the
// home screen. Carbon-fibre body, gold detailing, the cardholder's name in shining gold,
// and an original line-art hypercar (no real car brand's name or logo is used).
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
  // A warm reflection that follows the pointer, plus a faint gold/purple foil band.
  const reflection = useMotionTemplate`radial-gradient(55% 75% at ${lightX} ${lightY}, rgb(255 244 210 / 0.16), transparent 60%)`;
  const foil = useMotionTemplate`linear-gradient(115deg, transparent 25%, rgb(232 204 122 / 0.14) ${lightX}, rgb(167 139 250 / 0.10), transparent 75%)`;

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
        aria-label={`TracePay Black V12 Limited Edition card for ${holder}. ${flipped ? "Showing the back." : "Showing the front."} Press to flip.`}
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
          <Honeycomb className="absolute -right-6 -top-6 h-40 w-56 [mask-image:radial-gradient(70%_70%_at_80%_20%,black,transparent)]" />
          <BodyLines />
          <Hypercar className="absolute right-[1%] top-[29%] w-[74%] drop-shadow-[0_6px_10px_rgb(0_0_0/0.6)]" />
          <motion.div className="absolute inset-0 mix-blend-screen" style={{ background: foil }} aria-hidden />
          <motion.div className="absolute inset-0" style={{ background: reflection }} aria-hidden />

          <div className="relative flex h-full flex-col justify-between p-[6.5%] text-white">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <CoinMark size={24} tone="gold" />
                <div className="leading-none">
                  <p className="text-[14px] font-semibold tracking-tight">TracePay</p>
                  <p className="mt-1 font-mono text-[8px] uppercase tracking-[0.28em]" style={{ color: GOLD }}>
                    Black · V12 Edition
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[9px] tracking-[0.2em]" style={{ color: GOLD }}>
                  Nº 007 / 100
                </span>
                <Contactless />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Chip />
              {frozen && <span className="rounded border border-amber-300/40 bg-amber-300/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-amber-200">Frozen</span>}
            </div>

            <div className="flex items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-[8px] uppercase tracking-[0.3em] text-white/40">Cardholder</p>
                <p className="gold-text truncate text-[17px] font-semibold uppercase tracking-[0.2em]">{holder}</p>
                <p className="mt-1 truncate font-mono text-[11px] tracking-wide text-white/60">{vpa}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-[8px] uppercase tracking-[0.28em]" style={{ color: GOLD }}>
                  Limited edition
                </p>
                <p className="text-[12px] font-medium tracking-wide text-white/75">{bank}</p>
              </div>
            </div>
          </div>
        </Face>

        {/* ---------- BACK ---------- */}
        <Face back>
          <CarbonFibre />
          <Honeycomb className="absolute -bottom-8 -left-8 h-44 w-64 [mask-image:radial-gradient(70%_70%_at_20%_80%,black,transparent)]" />
          <motion.div className="absolute inset-0" style={{ background: reflection }} aria-hidden />
          <div className="relative flex h-full flex-col text-white">
            <div className="mt-[9%] h-[18%] w-full bg-black/85" aria-hidden />
            <div className="flex flex-1 flex-col justify-between p-[6.5%] pt-[5%]">
              <div className="flex h-9 items-center rounded-[4px] border border-[#d9b866]/40 bg-[repeating-linear-gradient(135deg,rgb(250_244_225/0.9)_0_6px,rgb(236_226_196/0.9)_6px_12px)] px-3">
                <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-neutral-700">Simulation only · not a payment card</span>
              </div>
              <p className="text-[10px] leading-relaxed text-white/55">
                A design element of a simulated app. It has no number and cannot be used to pay. Fake money, fake banks, a mock UPI switch.
              </p>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[0.25em]" style={{ color: GOLD }}>
                  V12 Limited Edition · Nº 007 / 100
                </span>
                <CoinMark size={20} tone="gold" />
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
      className="absolute inset-0 overflow-hidden rounded-[18px] border border-[#d9b866]/30 shadow-[0_30px_70px_-25px_rgb(0_0_0/0.9),0_0_40px_-12px_rgb(217_184_102/0.25)]"
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
      {/* Clear coat: a gloss highlight from the top, deep shadow at the bottom, and a
          faint purple glow underneath like ambient lighting. */}
      <div
        className="absolute inset-0"
        aria-hidden
        style={{
          background: [
            "linear-gradient(165deg, rgb(255 255 255 / 0.13) 0%, rgb(255 255 255 / 0.02) 35%, transparent 50%)",
            "radial-gradient(90% 60% at 50% 120%, rgb(124 58 237 / 0.28), transparent 70%)",
            "linear-gradient(180deg, transparent 55%, rgb(0 0 0 / 0.55) 100%)",
          ].join(","),
        }}
      />
    </>
  );
}

/** Hexagon pattern, like a supercar's air-intake mesh, in faint gold. */
function Honeycomb({ className }: { className?: string }) {
  // Pointy-top hexagons of radius 6: width 2·cos30°·6 ≈ 10.39, rows 9 apart.
  const hex = (cx: number, cy: number) => {
    const pts = [0, 60, 120, 180, 240, 300].map((deg) => {
      const a = ((deg - 90) * Math.PI) / 180;
      return `${(cx + 6 * Math.cos(a)).toFixed(2)},${(cy + 6 * Math.sin(a)).toFixed(2)}`;
    });
    return `M${pts.join("L")}Z`;
  };
  const d = [hex(5.2, 6), hex(0, 15), hex(10.39, 15)].join("");
  return (
    <svg className={className} aria-hidden>
      <defs>
        <pattern id="hexMesh" width="10.39" height="18" patternUnits="userSpaceOnUse">
          <path d={d} fill="none" stroke={GOLD} strokeWidth="0.6" opacity="0.35" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#hexMesh)" />
    </svg>
  );
}

/** Sharp angular gold pinstripes, like the creases in supercar bodywork. */
function BodyLines() {
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 252" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="pinstripe" x1="0" x2="1">
          <stop offset="0%" stopColor={GOLD} stopOpacity="0" />
          <stop offset="50%" stopColor={GOLD} stopOpacity="0.55" />
          <stop offset="100%" stopColor={GOLD} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M0 196 L150 176 L230 120 L400 104" fill="none" stroke="url(#pinstripe)" strokeWidth="0.8" />
      <path d="M0 206 L160 186 L240 130 L400 116" fill="none" stroke="url(#pinstripe)" strokeWidth="0.5" />
    </svg>
  );
}

/**
 * An original, shaded hypercar in side profile (nose to the left), in bronze-gold
 * metallic: low wedge stance, steep windscreen, long louvred engine cover, rear wing on
 * pylons, huge side intake, carbon splitter and skirts, Y-shaped LED headlight, big black
 * Y-spoke wheels that spin, speed lines behind, and a glint running along the roofline.
 * Drawn by hand in SVG; no real car brand's name, badge or logo is used.
 */
function Hypercar({ className }: { className?: string }) {
  // Ground is y = 86; wheels have radius 22 (centres at y = 64), arches radius 26.
  const body =
    "M12 70 L28 64 L68 56 L112 43 L148 23 L176 18 L206 21 L238 30 L274 38 L301 41 L307 48 L309 60 L305 70 L300 76 L270 76 L270 72 A26 26 0 0 0 222 72 L222 77 L103 77 L103 72 A26 26 0 0 0 53 72 L53 77 L18 77 Z";
  const roofline = "M28 64 L68 56 L112 43 L148 23 L176 18 L206 21 L238 30 L274 38 L301 41";
  const wheels = [78, 246];
  return (
    <svg viewBox="0 0 350 96" className={className} aria-hidden>
      <defs>
        {/* Bronze-gold paint: bright where light hits the top, dark down the flanks. */}
        <linearGradient id="paint" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f6dfa8" />
          <stop offset="28%" stopColor="#c99a5b" />
          <stop offset="62%" stopColor="#8a6233" />
          <stop offset="100%" stopColor="#3b2a16" />
        </linearGradient>
        {/* A soft horizontal sheen across the paint. */}
        <linearGradient id="paintSheen" x1="0" x2="1">
          <stop offset="0%" stopColor="white" stopOpacity="0" />
          <stop offset="55%" stopColor="white" stopOpacity="0.22" />
          <stop offset="70%" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2a2a33" />
          <stop offset="60%" stopColor="#07070a" />
        </linearGradient>
        <radialGradient id="rim" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="#2b2b31" />
          <stop offset="100%" stopColor="#0c0c0f" />
        </radialGradient>
        <clipPath id="bodyClip">
          <path d={body} />
        </clipPath>
      </defs>

      {/* Speed lines streaming behind the car. */}
      {[30, 44, 58, 70].map((y, i) => (
        <line key={y} x1="312" y1={y} x2="348" y2={y} stroke={GOLD} strokeWidth="0.8" strokeLinecap="round" opacity={0.55 - i * 0.1} className="speed-line" style={{ animationDelay: `${i * 0.2}s` }} />
      ))}

      {/* Ground shadow. */}
      <ellipse cx="160" cy="88" rx="150" ry="4.5" fill="black" opacity="0.75" />

      {/* Paint. */}
      <path d={body} fill="url(#paint)" />
      <g clipPath="url(#bodyClip)">
        <rect x="0" y="0" width="350" height="96" fill="url(#paintSheen)" />
        {/* Shoulder crease catching the light, and the darker lower flank below it. */}
        <path d="M60 60 L182 46 L276 44 L306 50" stroke="#fff1c8" strokeWidth="1" fill="none" opacity="0.55" />
        <path d="M40 72 L182 60 L300 58 L310 96 L0 96 Z" fill="black" opacity="0.28" />
        {/* Carbon side skirt and front splitter. */}
        <path d="M100 77 L224 77 L218 69 L112 70 Z" fill="#0d0d10" />
        {/* Huge side air intake behind the door, with fins. */}
        <path d="M194 45 L240 38 L228 62 L198 63 Z" fill="#050507" />
        <path d="M203 47 L226 43 M201 53 L230 49 M200 59 L229 55" stroke="#2c2c33" strokeWidth="1" />
        {/* Engine-cover louvres. */}
        <path d="M214 26 L222 28 M224 28.5 L232 30.5 M234 31 L242 33 M244 33.5 L252 35.5" stroke="#2a1d0e" strokeWidth="1.4" />
        {/* Front intake and the Y-shaped LED headlight. */}
        <path d="M13 70 L44 66 L34 76 L16 77 Z" fill="#060608" />
        <path d="M26 63 L46 58.5" stroke="#fffaf0" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M36 61 L33 66 M40 60 L45 63" stroke="#fffaf0" strokeWidth="1" strokeLinecap="round" />
        {/* Tail light. */}
        <path d="M302 44 L308 50" stroke="#ff4d4d" strokeWidth="2" strokeLinecap="round" />
        {/* Door line. */}
        <path d="M118 46 L120 70" stroke="#2a1d0e" strokeWidth="0.8" opacity="0.7" />
      </g>

      {/* Glass, with a reflection streak, and the wing mirror. */}
      <path d="M116 43 L150 25 L176 21 L198 23 L213 31 L194 38 Z" fill="url(#glass)" />
      <path d="M128 39 L158 26" stroke="white" strokeWidth="1.2" opacity="0.25" strokeLinecap="round" />
      <path d="M168 39 L182 36.5 L183 41 L171 42.5 Z" fill="#0b0b0e" stroke="#c99a5b" strokeWidth="0.5" />

      {/* Front splitter and rear diffuser, in carbon. */}
      <path d="M9 77 L56 77 L56 79.5 L12 80.5 Z" fill="#0d0d10" />
      <path d="M270 76 L306 76 L303 80 L276 80 Z" fill="#0d0d10" />

      {/* Rear wing on pylons. */}
      <path d="M266 34 L268 41 M292 29 L294 42" stroke="#111114" strokeWidth="2.2" />
      <path d="M248 27 L312 22.5 L312 27 L256 31.5 Z" fill="#0d0d10" stroke={GOLD} strokeWidth="0.5" />

      {/* A glint of light running along the roofline. */}
      <path d={roofline} fill="none" stroke="#fff6d8" strokeWidth="1.6" strokeLinecap="round" pathLength={1} strokeDasharray="0.08 0.92" className="car-glint" />

      {/* Big black wheels with gold Y-spokes and hubs, spinning. */}
      {wheels.map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy="64" r="22" fill="#060607" />
          <circle cx={cx} cy="64" r="15.5" fill="url(#rim)" stroke="#3a3a42" strokeWidth="0.6" />
          {/* Brake caliper, in the app's purple, peeking through the spokes. */}
          <path d={`M${cx - 11} 56 A13 13 0 0 1 ${cx + 1} 51.2`} stroke="rgb(167 139 250)" strokeWidth="3" fill="none" strokeLinecap="round" />
          <g className="wheel-spin" style={{ transformOrigin: `${cx}px 64px` }}>
            {[0, 72, 144, 216, 288].map((deg) => {
              const a = ((deg - 90) * Math.PI) / 180;
              const p = (r: number, off = 0) => `${(cx + r * Math.cos(a + off)).toFixed(2)} ${(64 + r * Math.sin(a + off)).toFixed(2)}`;
              return <path key={deg} d={`M${p(3)} L${p(8)} L${p(14.5, 0.22)} M${p(8)} L${p(14.5, -0.22)}`} stroke={GOLD} strokeWidth="1.3" fill="none" strokeLinejoin="round" />;
            })}
            <circle cx={cx} cy="64" r="3.2" fill="#f3dc95" />
          </g>
          <circle cx={cx} cy="64" r="22" fill="none" stroke="#1d1d22" strokeWidth="1.5" />
        </g>
      ))}
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
