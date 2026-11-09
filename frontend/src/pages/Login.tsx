// Login for the seeded demo users. There is no signup: this is a simulation.

import { motion } from "framer-motion";
import { GraduationCap, HeartHandshake, ShieldCheck, Store } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Logo } from "../components/AppShell";
import { Button, Card, cn, SimulationBadge, TextField } from "../components/ui";
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
    <div className="grid min-h-dvh place-items-center px-4 py-10">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="w-full max-w-md space-y-6">
        <div className="space-y-3 text-center">
          <Logo className="justify-center text-2xl" />
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Know where your <span className="text-gradient">money</span> is.
          </h1>
          <p className="text-muted">Track every payment, see the true state when something breaks, and know what your bank owes you.</p>
          <SimulationBadge />
        </div>

        <Card glow>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <TextField label="Username" name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            <TextField
              label="Password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && (
              <p role="alert" className="rounded-xl bg-bad/10 px-3 py-2 text-sm text-bad">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!username || !password}>
              Log in
            </Button>
          </form>

          <div className="mt-6">
            <p className="mb-3 text-center text-xs font-semibold uppercase tracking-wider text-muted">Or try a demo account</p>
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
                  className={cn("glass flex items-center gap-3 rounded-2xl p-3 text-left transition hover:shadow-glow", username === u && "ring-2 ring-teal/60")}
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent/90 text-white">
                    <Icon className="h-4 w-4" aria-hidden />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">{name}</span>
                    <span className="block truncate text-xs text-muted">{role}</span>
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-3 text-center text-xs text-muted">
              Demo password: <code className="font-semibold text-ink">{DEMO_PASSWORD}</code>
            </p>
          </div>
        </Card>
      </motion.div>
    </div>
  );
}
