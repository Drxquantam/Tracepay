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
        canvas: token("canvas"),
        ink: token("ink"),
        muted: token("muted"),
        line: token("line"),
        teal: token("teal"),
        violet: token("violet"),
        ok: token("ok"),
        warn: token("warn"),
        bad: token("bad"),
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 24px -4px rgb(var(--teal) / 0.55)",
        "glow-violet": "0 0 32px -6px rgb(var(--violet) / 0.6)",
      },
      backgroundImage: {
        accent: "linear-gradient(135deg, rgb(var(--teal)), rgb(var(--violet)))",
      },
    },
  },
  plugins: [],
};
