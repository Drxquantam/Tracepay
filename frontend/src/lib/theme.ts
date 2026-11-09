// Dark-first theme with a light-mode toggle. The choice is a per-viewer convenience, kept
// in localStorage; index.html applies it before first paint to avoid a flash.

import { useCallback, useState } from "react";

const KEY = "tracepay.theme";
type Theme = "dark" | "light";

function current(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(current);
  const toggle = useCallback(() => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", next === "dark" ? "#07070a" : "#f8f8fa");
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* storage unavailable: the choice lasts until reload */
    }
    setTheme(next);
  }, []);
  return { theme, toggle };
}
