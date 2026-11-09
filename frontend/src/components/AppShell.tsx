// The frame around every logged-in screen: a quiet sidebar on desktop, a top bar, a
// bottom tab bar on phones (like a real payments app), and a soft page transition.
// The active-page marker is one shared element (layoutId) that slides between items.

import { motion, useReducedMotion } from "framer-motion";
import { Bell, CalendarClock, Gauge, Home, LogOut, Moon, Scale, Send, Shield, Sun, Type } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link, NavLink, useLocation, useOutlet } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";
import { useApi } from "../lib/useApi";
import { Logo } from "./brand";
import { useToast } from "./Toast";
import { cn, SimulationBadge } from "./ui";

export { Logo };

const CUSTOMER_NAV = [
  { to: "/", label: "Home", icon: Home },
  { to: "/pay", label: "Pay", icon: Send },
  { to: "/mandates", label: "Mandates", icon: CalendarClock },
  { to: "/guardian", label: "Guardian", icon: Shield },
  { to: "/disputes", label: "Disputes", icon: Scale },
];
const ADMIN_NAV = [{ to: "/", label: "Admin", icon: Gauge }];

function IconButton({ label, onClick, active, children }: { label: string; onClick?: () => void; active?: boolean; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        "grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-raised hover:text-ink",
        active && "bg-raised text-primary",
      )}
    >
      {children}
    </button>
  );
}

export function AppShell() {
  const { me, logout, refreshMe } = useAuth();
  const { theme, toggle } = useTheme();
  const toast = useToast();
  const NAV = me?.role === "admin" ? ADMIN_NAV : CUSTOMER_NAV;
  const notes = useApi<{ unread: number }>("/notifications", 10000);
  const location = useLocation();
  const outlet = useOutlet();
  const reduce = useReducedMotion();

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

  const initials = (me?.full_name ?? "")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2);

  return (
    <div className="min-h-dvh lg:flex">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line/[0.06] px-4 py-6 lg:flex">
        <Logo className="px-2 text-[17px]" />
        <p className="label mb-2 mt-10 px-3">Menu</p>
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} className="relative">
              {({ isActive }) => (
                <span className={cn("relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition", isActive ? "text-ink" : "text-muted hover:text-ink")}>
                  {isActive && (
                    <motion.span layoutId="nav-active" className="absolute inset-0 rounded-lg border border-line/[0.07] bg-raised" transition={{ type: "spring", stiffness: 500, damping: 40 }}>
                      <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-primary" />
                    </motion.span>
                  )}
                  <Icon className={cn("relative h-[18px] w-[18px]", isActive && "text-primary")} aria-hidden />
                  <span className="relative font-medium">{label}</span>
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3 px-2">
          <SimulationBadge />
          <p className="text-xs leading-relaxed text-muted">Fake money, fake banks, a mock UPI switch. Nothing here touches a real bank or NPCI.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line/[0.06] bg-canvas/70 backdrop-blur-xl">
          <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4 sm:px-6">
            <Logo className="lg:hidden" />
            <SimulationBadge className="ml-2 lg:hidden" />
            <div className="ml-auto flex items-center gap-1">
              <Link
                to="/notifications"
                className="relative grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-raised hover:text-ink"
                aria-label={`Notifications${notes.data?.unread ? `, ${notes.data.unread} unread` : ""}`}
              >
                <Bell className="h-[18px] w-[18px]" aria-hidden />
                {!!notes.data?.unread && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-primary ring-2 ring-canvas" />}
              </Link>
              <IconButton label={senior ? "Turn off senior mode (larger text)" : "Turn on senior mode (larger text)"} onClick={toggleSenior} active={senior}>
                <Type className="h-[18px] w-[18px]" aria-hidden />
              </IconButton>
              <IconButton label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} onClick={toggle}>
                {theme === "dark" ? <Sun className="h-[18px] w-[18px]" aria-hidden /> : <Moon className="h-[18px] w-[18px]" aria-hidden />}
              </IconButton>
              <IconButton label="Log out" onClick={logout}>
                <LogOut className="h-[18px] w-[18px]" aria-hidden />
              </IconButton>
              <span className="ml-2 hidden h-8 w-8 place-items-center rounded-full bg-accent text-xs font-semibold text-white sm:grid" title={me?.full_name} aria-hidden>
                {initials}
              </span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-32 pt-8 sm:px-6 lg:pb-14">
          <motion.div
            key={location.pathname}
            // No CSS filter here: an animated blur left Chrome showing a low-res copy of
            // busy pages after the animation ended.
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            {outlet}
          </motion.div>
        </main>
      </div>

      {/* Phone tab bar */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-line/[0.06] bg-canvas/85 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl lg:hidden"
      >
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className="relative flex min-w-14 flex-col items-center gap-1 px-2 py-1 text-[10px] font-medium">
            {({ isActive }) => (
              <>
                {isActive && <motion.span layoutId="tab-active" className="absolute -top-2 h-[2px] w-8 rounded-full bg-primary" />}
                <Icon className={cn("h-5 w-5", isActive ? "text-primary" : "text-muted")} aria-hidden />
                <span className={isActive ? "text-ink" : "text-muted"}>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
