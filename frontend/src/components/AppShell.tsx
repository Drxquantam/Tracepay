// The frame around every logged-in screen: top bar, a sidebar on desktop, a bottom tab bar
// on phones (like a real payments app), and a fade/slide transition between pages.

import { motion, useReducedMotion } from "framer-motion";
import { Bell, Home, LogOut, Moon, Scale, Send, Shield, Sun, Type } from "lucide-react";
import { useEffect } from "react";
import { Link, NavLink, useLocation, useOutlet } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";
import { useApi } from "../lib/useApi";
import { useToast } from "./Toast";
import { cn, SimulationBadge } from "./ui";

const CUSTOMER_NAV = [
  { to: "/", label: "Home", icon: Home },
  { to: "/pay", label: "Pay", icon: Send },
  { to: "/guardian", label: "Guardian", icon: Shield },
  { to: "/disputes", label: "Disputes", icon: Scale },
];
const ADMIN_NAV = [{ to: "/", label: "Home", icon: Home }];

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2 font-extrabold tracking-tight", className)}>
      <span className="grid h-8 w-8 place-items-center rounded-xl bg-accent text-sm text-white shadow-glow" aria-hidden>
        ₹
      </span>
      <span>
        Trace<span className="text-gradient">Pay</span>
      </span>
    </span>
  );
}

export function AppShell() {
  const { me, logout, refreshMe } = useAuth();
  const { theme, toggle } = useTheme();
  const toast = useToast();
  const NAV = me?.role === "admin" ? ADMIN_NAV : CUSTOMER_NAV;
  const notes = useApi<{ unread: number }>("/notifications", 10000);

  // Senior mode scales the whole UI (rem-based) via a class on <html>.
  const senior = !!me?.senior_mode;
  useEffect(() => {
    document.documentElement.classList.toggle("senior", senior);
  }, [senior]);

  async function toggleSenior() {
    await api("/auth/me", { method: "PATCH", body: { senior_mode: !senior } });
    await refreshMe();
    toast(senior ? "Standard text size" : "Senior mode on: larger text", "success");
  }
  const location = useLocation();
  const outlet = useOutlet();
  const reduce = useReducedMotion();

  return (
    <div className="min-h-dvh lg:flex">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col gap-8 p-6 lg:flex">
        <Logo className="text-xl" />
        <nav aria-label="Main" className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition",
                  isActive ? "glass text-ink shadow-glow" : "text-muted hover:text-ink",
                )
              }
            >
              <Icon className="h-5 w-5" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="mt-auto text-xs leading-relaxed text-muted">
          Fake money, fake banks and a mock UPI switch. Nothing here touches a real bank or NPCI.
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line/5 bg-canvas/60 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-5xl items-center gap-3 px-4 sm:px-6">
            <Logo className="lg:hidden" />
            <SimulationBadge className="hidden sm:inline-flex lg:ml-0" />
            <div className="ml-auto flex items-center gap-2">
              <span className="hidden text-sm text-muted sm:block">{me?.full_name}</span>
              <Link
                to="/notifications"
                className="glass relative grid h-10 w-10 place-items-center rounded-xl"
                aria-label={`Notifications${notes.data?.unread ? `, ${notes.data.unread} unread` : ""}`}
              >
                <Bell className="h-5 w-5" aria-hidden />
                {!!notes.data?.unread && (
                  <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-bad px-1 text-[11px] font-bold text-white">
                    {notes.data.unread}
                  </span>
                )}
              </Link>
              <button
                onClick={toggleSenior}
                className={cn("glass grid h-10 w-10 place-items-center rounded-xl", senior && "ring-2 ring-teal/60")}
                aria-label={senior ? "Turn off senior mode (larger text)" : "Turn on senior mode (larger text)"}
                aria-pressed={senior}
              >
                <Type className="h-5 w-5" aria-hidden />
              </button>
              <button onClick={toggle} className="glass grid h-10 w-10 place-items-center rounded-xl" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
                {theme === "dark" ? <Sun className="h-5 w-5" aria-hidden /> : <Moon className="h-5 w-5" aria-hidden />}
              </button>
              <button onClick={logout} className="glass grid h-10 w-10 place-items-center rounded-xl" aria-label="Log out">
                <LogOut className="h-5 w-5" aria-hidden />
              </button>
            </div>
          </div>
          <div className="px-4 pb-2 sm:hidden">
            <SimulationBadge />
          </div>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-32 pt-6 sm:px-6 lg:pb-12">
          <motion.div
            key={location.pathname}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          >
            {outlet}
          </motion.div>
        </main>
      </div>

      {/* Phone tab bar */}
      <nav aria-label="Main" className="glass fixed inset-x-3 bottom-3 z-40 flex justify-around rounded-3xl px-2 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] lg:hidden">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn("flex min-w-16 flex-col items-center gap-1 rounded-2xl px-3 py-1.5 text-[11px] font-semibold", isActive ? "text-teal" : "text-muted")
            }
          >
            <Icon className="h-5 w-5" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
