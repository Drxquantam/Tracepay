/** Tailwind config. Colours point at CSS variables (src/index.css), so one class like
 *  `text-ink` works in both dark and light mode: the theme only swaps the variables. */

/** @param {string} name */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"), // page background
        surface: token("surface"), // cards
        raised: token("raised"), // inputs, hover, nested panels
        ink: token("ink"), // main text
        muted: token("muted"), // secondary text
        line: token("line"), // borders (used with low opacity)
        primary: token("primary"), // purple accent: links, icons, active states
        deep: token("deep"), // deeper purple: buttons, fills
        ok: token("ok"),
        warn: token("warn"),
        bad: token("bad"),
      },
      fontFamily: {
        sans: ['"Geist"', "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        // Restrained: a hairline purple ring plus a soft drop, not a neon blob.
        glow: "0 0 0 1px rgb(var(--primary) / 0.22), 0 10px 30px -12px rgb(var(--deep) / 0.55)",
        "glow-deep": "0 0 0 1px rgb(var(--primary) / 0.16), 0 24px 60px -24px rgb(var(--deep) / 0.6)",
      },
      backgroundImage: {
        accent: "linear-gradient(135deg, rgb(var(--primary)), rgb(var(--deep)))",
      },
      keyframes: {
        // A slow light sweep across the balance card, like light on a metal card.
        sheen: {
          "0%": { transform: "translateX(-120%) skewX(-18deg)" },
          "60%, 100%": { transform: "translateX(260%) skewX(-18deg)" },
        },
      },
      animation: {
        sheen: "sheen 7s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
