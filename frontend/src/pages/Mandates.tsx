// Mandate Manager: every recurring debit in one place, with the next date, amount,
// trial-to-paid warnings, one-tap pause/resume/revoke, a calendar and monthly totals.

import { CalendarClock, Pause, Play, Plus, Repeat, Sparkles, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { MandateCalendar } from "../components/MandateCalendar";
import { useToast } from "../components/Toast";
import { Button, Card, cn, EmptyState, SectionTitle, Skeleton, TextField } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { formatDate, formatDateTime, formatINR, rupeesToPaise } from "../lib/format";
import type { Mandate, MandateDebit, Payee } from "../lib/types";
import { useApi } from "../lib/useApi";

const monthKey = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit" });
const monthShort = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", month: "short" });

const DEBIT_TONE: Record<MandateDebit["status"], string> = {
  notified: "bg-teal/15 text-teal",
  retrying: "bg-warn/15 text-warn",
  succeeded: "bg-ok/15 text-ok",
  failed: "bg-bad/15 text-bad",
  skipped: "bg-line/10 text-muted",
  cancelled: "bg-line/10 text-muted",
};
const DEBIT_LABEL: Record<MandateDebit["status"], string> = {
  notified: "Notice sent",
  retrying: "Retrying",
  succeeded: "Paid",
  failed: "Failed",
  skipped: "Skipped (paused)",
  cancelled: "Cancelled",
};

export default function Mandates() {
  const toast = useToast();
  const { data, reload, loading } = useApi<Mandate[]>("/mandates", 10000);
  const clock = useApi<{ now: string }>("/clock", 10000);
  const [creating, setCreating] = useState(false);
  const now = clock.data ? new Date(clock.data.now) : new Date();

  const active = (data ?? []).filter((m) => m.status === "active");
  // Projected totals for the next 6 months, from every active mandate's schedule.
  const months = Array.from({ length: 6 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 15);
    return { key: monthKey.format(d), label: monthShort.format(d), paise: 0 };
  });
  for (const m of active) for (const u of m.upcoming) {
    const bucket = months.find((b) => b.key === monthKey.format(new Date(u.due_at)));
    if (bucket) bucket.paise += u.amount_paise;
  }

  async function action(m: Mandate, verb: "pause" | "resume" | "revoke") {
    if (verb === "revoke" && !window.confirm(`Cancel the ${m.merchant_name} mandate for good? No more debits will happen.`)) return;
    try {
      await api(`/mandates/${m.id}/${verb}`, { method: "POST" });
      toast(verb === "pause" ? "Paused. Upcoming debits will be skipped." : verb === "resume" ? "Resumed." : "Mandate cancelled. No more debits.", "success");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't update", "error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Mandates</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Every subscription and auto-debit in one place. You get a notice 24 hours before each debit, and can pause or cancel any of them in one tap.
          </p>
        </div>
        <Button variant="ghost" onClick={() => setCreating(!creating)}>
          {creating ? <X className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
          {creating ? "Close" : "New mandate"}
        </Button>
      </div>

      {creating && <NewMandate now={now} onCreated={() => { setCreating(false); reload(); }} />}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          {loading ? (
            <>
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
            </>
          ) : !data || data.length === 0 ? (
            <Card>
              <EmptyState icon={<Repeat className="h-5 w-5" />} title="No mandates">
                Subscriptions and bills you've set to auto-pay will appear here.
              </EmptyState>
            </Card>
          ) : (
            data.map((m) => <MandateCard key={m.id} m={m} onAction={action} />)
          )}
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <SectionTitle>Calendar</SectionTitle>
            <MandateCalendar mandates={data ?? []} now={now} />
          </Card>
          <Card>
            <SectionTitle>Next 6 months</SectionTitle>
            <div className="h-36" role="img" aria-label={`Projected auto-debits: ${months.map((b) => `${b.label} ${formatINR(b.paise)}`).join(", ")}`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={months} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
                  <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: "rgb(var(--muted))", fontSize: 11 }} />
                  <Tooltip
                    cursor={{ fill: "rgb(var(--line) / 0.06)" }}
                    content={({ active: on, payload }) =>
                      on && payload?.length ? (
                        <div className="glass rounded-xl px-3 py-2 text-xs">
                          <span className="money font-semibold">{formatINR(Number(payload[0].value))}</span>
                        </div>
                      ) : null
                    }
                  />
                  <Bar dataKey="paise" radius={[8, 8, 8, 8]} fill="rgb(var(--violet))" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function MandateCard({ m, onAction }: { m: Mandate; onAction: (m: Mandate, verb: "pause" | "resume" | "revoke") => void }) {
  const next = m.upcoming[0];
  const firstPaid = m.upcoming.find((u) => !u.is_trial);
  const onTrial = m.trial_amount_paise !== null && m.trial_debits_left > 0;
  return (
    <Card className={cn(m.status === "revoked" && "opacity-60")}>
      <div className="flex items-start gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-violet/15 text-violet">
          <CalendarClock className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-bold">{m.merchant_name}</p>
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-semibold",
                m.status === "active" ? "bg-ok/15 text-ok" : m.status === "paused" ? "bg-warn/15 text-warn" : "bg-line/10 text-muted",
              )}
            >
              {m.status === "active" ? "Active" : m.status === "paused" ? "Paused" : "Cancelled"}
            </span>
          </div>
          <p className="text-sm text-muted">
            {m.purpose} · {m.frequency} · cap {formatINR(m.max_amount_paise)}
          </p>
        </div>
        <div className="text-right">
          <p className="money text-xl font-extrabold">{formatINR(next?.amount_paise ?? m.amount_paise)}</p>
          <p className="text-xs text-muted">{next ? `next on ${formatDate(next.due_at)}` : m.status === "paused" ? "paused" : "no more debits"}</p>
        </div>
      </div>

      {/* Trial-to-paid: the classic "₹1 that becomes ₹499" surprise, flagged loudly. */}
      {onTrial && firstPaid && (
        <p className="mt-4 flex items-start gap-2 rounded-2xl bg-violet/10 px-3 py-2 text-sm">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-violet" aria-hidden />
          <span>
            <span className="font-semibold">Trial: {formatINR(m.trial_amount_paise!)} now, then {formatINR(m.amount_paise)}</span> every month from {formatDate(firstPaid.due_at)}.
            Cancel before then if you don't want the paid plan.
          </span>
        </p>
      )}

      {m.debits.length > 0 && (
        <ul className="mt-4 space-y-2 text-sm">
          {m.debits.slice(0, 3).map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2">
              <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", DEBIT_TONE[d.status])}>{DEBIT_LABEL[d.status]}</span>
              <span className="money font-semibold">{formatINR(d.amount_paise)}</span>
              <span className="text-muted">due {formatDate(d.due_at)}</span>
              {d.status === "retrying" && d.next_attempt_at && <span className="text-warn">· try {d.attempts + 1} at {formatDateTime(d.next_attempt_at)}</span>}
              {d.failure_reason && d.status !== "succeeded" && <span className="w-full text-xs text-muted">{d.failure_reason}</span>}
              {d.payment_id && (
                <Link to={`/payments/${d.payment_id}`} className="ml-auto text-xs font-semibold text-teal hover:underline">
                  Track
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {m.status !== "revoked" && (
        <div className="mt-4 flex gap-2">
          {m.status === "active" ? (
            <Button variant="ghost" onClick={() => onAction(m, "pause")}>
              <Pause className="h-4 w-4" aria-hidden /> Pause
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => onAction(m, "resume")}>
              <Play className="h-4 w-4" aria-hidden /> Resume
            </Button>
          )}
          <Button variant="danger" onClick={() => onAction(m, "revoke")}>
            <X className="h-4 w-4" aria-hidden /> Cancel mandate
          </Button>
        </div>
      )}
    </Card>
  );
}

function NewMandate({ now, onCreated }: { now: Date; onCreated: () => void }) {
  const toast = useToast();
  const payees = useApi<Payee[]>("/payees");
  const merchants = (payees.data ?? []).filter((p) => p.kind === "merchant");
  const defaultDate = new Date(now.getTime() + 2 * 86400_000).toISOString().slice(0, 10);
  const [merchant, setMerchant] = useState("");
  const [purpose, setPurpose] = useState("");
  const [amount, setAmount] = useState("");
  const [cap, setCap] = useState("");
  const [trial, setTrial] = useState("");
  const [date, setDate] = useState(defaultDate);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/mandates", {
        method: "POST",
        body: {
          merchant_vpa: merchant,
          purpose,
          amount_paise: rupeesToPaise(amount),
          max_amount_paise: rupeesToPaise(cap || amount),
          frequency: "monthly",
          first_debit_at: new Date(`${date}T10:00:00+05:30`).toISOString(), // 10 am IST
          trial_amount_paise: trial ? rupeesToPaise(trial) : null,
        },
      });
      toast("Mandate set up. You'll get a notice before each debit.", "success");
      onCreated();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't create", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card glow>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <label htmlFor="merchant" className="block text-sm font-medium text-muted">
            Merchant
          </label>
          <select id="merchant" required value={merchant} onChange={(e) => setMerchant(e.target.value)} className="glass h-12 w-full rounded-2xl px-4 text-ink">
            <option value="">Choose a merchant</option>
            {merchants.map((p) => (
              <option key={p.vpa} value={p.vpa}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <TextField label="What for" required value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="e.g. Gym membership" />
        <TextField label="First debit (10 am IST)" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        <TextField label="Monthly amount (₹)" inputMode="decimal" required value={amount} onChange={(e) => setAmount(e.target.value)} />
        <TextField label="Cap per debit (₹)" inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)} hint="Defaults to the amount. Max ₹15,000." />
        <TextField label="Trial price for the first debit (₹, optional)" inputMode="decimal" value={trial} onChange={(e) => setTrial(e.target.value)} />
        <div className="flex items-end">
          <Button type="submit" size="lg" className="w-full" loading={busy}>
            Set up mandate
          </Button>
        </div>
      </form>
    </Card>
  );
}
