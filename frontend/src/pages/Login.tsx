// Login for the seeded demo users. There is no signup: this is a simulation.
// Desktop: a split screen with the banknote engraving (guilloché) as the brand moment.

import { motion } from "framer-motion";
import { ArrowRight, GraduationCap, HeartHandshake, ShieldCheck, Store } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Guilloche, Logo } from "../components/brand";
import { Button, cn, SimulationBadge, TextField } from "../components/ui";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

// Fictional demo people from the seed data. The shared demo password is documented in the
// README; it is not a real credential for anything.
const DEMO_PASSWORD = "demo1234";
const DEMO_USERS = [
  { username: "aarav", name: "Aarav", role: "College student", icon: GraduationCap },
  { username: "shanti", name: "Shanti", role: "Grandparent", icon: HeartHandshake },
  { username: "ravi", name: "Ravi", role: "Shopkeeper", icon: Store },
  { username: "admin", name: "Admin", role: "Chaos & time travel", icon: ShieldCheck },
];

const ease = [0.16, 1, 0.3, 1] as const;

export default function Login() {
  const { me, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      {/* Brand side */}
      <aside className="relative hidden overflow-hidden border-r border-line/[0.06] lg:flex lg:flex-col lg:justify-between lg:p-12">
        {/* The wrapper centres; the SVG inside rotates. (Putting both on one element fails:
            the rotation's inline transform would replace the centring translate.) */}
        <div className="absolute left-1/2 top-1/2 h-[900px] w-[900px] -translate-x-1/2 -translate-y-1/2">
          <Guilloche className="h-full w-full text-primary/40" speed={180} />
        </div>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,transparent_25%,rgb(var(--canvas))_80%)]" aria-hidden />
        <Logo className="relative text-lg" />
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease }} className="relative max-w-md">
          <p className="label mb-4">Money in flight</p>
          <h1 className="text-5xl font-semibold leading-[1.05] tracking-tight">
            Know where every <span className="text-gradient">rupee</span> is.
          </h1>
          <p className="mt-5 text-muted">
            Track each payment across banks, see the true state when something breaks, and know exactly what your bank owes you when it's late.
          </p>
        </motion.div>
        <div className="relative flex items-center gap-6 font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
          <span>Double-entry ledger</span>
          <span aria-hidden>·</span>
          <span>Idempotent</span>
          <span aria-hidden>·</span>
          <span>T+1 / T+5 tracked</span>
        </div>
      </aside>

      {/* Form side */}
      <main className="flex items-center justify-center px-5 py-12">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease, delay: 0.1 }} className="w-full max-w-sm">
          <Logo className="mb-10 text-lg lg:hidden" />
          <SimulationBadge />
          <h2 className="mt-5 text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use a demo account below, or enter one yourself.</p>

          <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
            <TextField label="Username" name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            <TextField label="Password" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            {error && (
              <p role="alert" className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!username || !password}>
              Continue <ArrowRight className="h-4 w-4" aria-hidden />
            </Button>
          </form>

          <div className="mt-10">
            <p className="label mb-3">Demo accounts</p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map(({ username: u, name, role, icon: Icon }) => (
                <button
                  key={u}
                  type="button"
                  aria-label={`Use demo account: ${name}, ${role}`}
                  onClick={() => {
                    setUsername(u);
                    setPassword(DEMO_PASSWORD);
                    setError(null);
                  }}
                  className={cn(
                    "flex items-center gap-3 rounded-xl border border-line/[0.08] bg-surface p-3 text-left transition hover:border-primary/40",
                    username === u && "border-primary/60 bg-primary/[0.06]",
                  )}
                >
                  <Icon className={cn("h-4 w-4 shrink-0", username === u ? "text-primary" : "text-muted")} aria-hidden />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{name}</span>
                    <span className="block truncate text-xs text-muted">{role}</span>
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-4 text-xs text-muted">
              Demo password: <code className="font-mono text-ink">{DEMO_PASSWORD}</code>
            </p>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
