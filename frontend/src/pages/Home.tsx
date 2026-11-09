// Home dashboard: balance, anything that needs attention (money in flight, disputes),
// spending, and recent payments.

import { motion } from "framer-motion";
import { ArrowRight, Inbox, PlaneTakeoff, Scale, Send, ShieldCheck, Snowflake } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { HoldCard } from "../components/HoldCard";
import { PaymentRow } from "../components/PaymentRow";
import { SpendChart } from "../components/SpendChart";
import { AnimatedAmount, Button, Card, EmptyState, SectionTitle, Skeleton } from "../components/ui";
import { useAuth } from "../lib/auth";
import { formatDateTime, formatINR } from "../lib/format";
import type { Dispute, Holds, Payment } from "../lib/types";
import { useApi } from "../lib/useApi";

const IN_FLIGHT = new Set(["bank_debited", "in_switch", "reversal_pending"]);

function greeting() {
  const hour = Number(new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", hourCycle: "h23" }).format(new Date()));
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export default function Home() {
  const { me, refreshMe } = useAuth();
  // Poll faster while something is in flight, so the dashboard reflects reality.
  const payments = useApi<Payment[]>("/payments", (list) => (list.some((p) => IN_FLIGHT.has(p.state)) ? 3000 : 15000));
  const disputes = useApi<Dispute[]>("/disputes", 15000);
  const clock = useApi<{ now: string }>("/clock");
  const holds = useApi<Holds>(me?.role === "admin" ? null : "/guardian/holds", 5000);

  // Keep the balance fresh whenever the payment list changes.
  useEffect(() => {
    refreshMe().catch(() => {});
  }, [payments.data, refreshMe]);

  if (me?.role === "admin") return <AdminHome />;

  const account = me?.accounts[0];
  const list = payments.data ?? [];
  const openDisputes = (disputes.data ?? []).filter((d) => d.status === "open");
  // A payment with an open dispute is already shown as that dispute; don't list it twice.
  const disputed = new Set(openDisputes.map((d) => d.payment_id));
  const inFlight = list.filter((p) => IN_FLIGHT.has(p.state) && p.payer_vpa === account?.vpa && !disputed.has(p.id));

  return (
    <div className="space-y-6">
      <div>
        <p className="text-muted">{greeting()},</p>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{me?.full_name.split(" ")[0]}</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Balance */}
        <Card glow className="relative overflow-hidden lg:col-span-3">
          <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-accent opacity-25 blur-3xl" aria-hidden />
          <p className="text-sm font-medium text-muted">Available balance</p>
          {account ? (
            <AnimatedAmount paise={account.balance_paise} className="mt-1 block text-4xl font-extrabold sm:text-5xl" />
          ) : (
            <Skeleton className="mt-2 h-12 w-48" />
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="glass rounded-full px-3 py-1 font-medium">{account?.vpa}</span>
            <span className="text-muted">{account?.bank_name}</span>
            {account?.is_frozen && (
              <span className="inline-flex items-center gap-1 rounded-full bg-warn/15 px-2.5 py-1 text-xs font-semibold text-warn">
                <Snowflake className="h-3.5 w-3.5" aria-hidden /> Payments frozen
              </span>
            )}
          </div>
          <div className="mt-6 flex gap-3">
            <Link to="/pay" className="flex-1 sm:flex-none">
              <Button size="lg" className="w-full sm:w-40">
                <Send className="h-5 w-5" aria-hidden /> Pay
              </Button>
            </Link>
            <Link to="/disputes" className="flex-1 sm:flex-none">
              <Button size="lg" variant="ghost" className="w-full sm:w-40">
                <Scale className="h-5 w-5" aria-hidden /> Disputes
              </Button>
            </Link>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          {payments.loading || clock.loading ? (
            <Skeleton className="h-44" />
          ) : (
            <SpendChart payments={list} myVpa={account?.vpa} now={clock.data ? new Date(clock.data.now) : new Date()} />
          )}
        </Card>
      </div>

      {/* Requests waiting on this person come first: they're time-limited. */}
      {holds.data && (holds.data.to_decide.length > 0 || holds.data.mine.length > 0) && (
        <section aria-label="Payments on hold" className="grid gap-3 md:grid-cols-2">
          {holds.data.to_decide.map((h) => (
            <HoldCard key={h.id} hold={h} as="guardian" onDone={() => { holds.reload(); payments.reload(); }} />
          ))}
          {holds.data.mine.map((h) => (
            <HoldCard key={h.id} hold={h} as="payer" onDone={() => { holds.reload(); payments.reload(); }} />
          ))}
        </section>
      )}

      {/* Alerts: plain language, most urgent first */}
      {(openDisputes.length > 0 || inFlight.length > 0) && (
        <section aria-labelledby="alerts">
          <SectionTitle>
            <span id="alerts">Needs your attention</span>
          </SectionTitle>
          <div className="grid gap-3 md:grid-cols-2">
            {openDisputes.map((d, i) => (
              <motion.div key={`d${d.id}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                <Link to={`/payments/${d.payment_id}`}>
                  <Card className="flex items-center gap-4 border-bad/30 transition hover:shadow-glow">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-bad/15 text-bad">
                      <Scale className="h-5 w-5" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold">{d.headline}</span>
                      <span className="block truncate text-sm text-muted">
                        {formatINR(d.amount_paise)} to {d.payee_name} · owed by {d.owed_by_bank}
                      </span>
                    </span>
                    <ArrowRight className="h-5 w-5 text-muted" aria-hidden />
                  </Card>
                </Link>
              </motion.div>
            ))}
            {inFlight.map((p, i) => (
              <motion.div key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: (openDisputes.length + i) * 0.05 }}>
                <Link to={`/payments/${p.id}`}>
                  <Card className="flex items-center gap-4 transition hover:shadow-glow">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-warn/15 text-warn">
                      <PlaneTakeoff className="h-5 w-5" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold">
                        {formatINR(p.amount_paise)} {p.state === "reversal_pending" ? "refund on its way" : "still in flight"}
                      </span>
                      <span className="block truncate text-sm text-muted">
                        To {p.payee_name} · since {formatDateTime(p.created_at)}
                      </span>
                    </span>
                    <ArrowRight className="h-5 w-5 text-muted" aria-hidden />
                  </Card>
                </Link>
              </motion.div>
            ))}
          </div>
        </section>
      )}

      <section aria-labelledby="recent">
        <Card>
          <SectionTitle>
            <span id="recent">Recent activity</span>
          </SectionTitle>
          {payments.loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <EmptyState icon={<Inbox className="h-5 w-5" />} title="No payments yet">
              Your payments will show up here.
            </EmptyState>
          ) : (
            <div className="-mx-2 divide-y divide-line/5">
              {list.slice(0, 8).map((p) => (
                <PaymentRow key={p.id} payment={p} myVpa={account?.vpa} />
              ))}
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}

function AdminHome() {
  const integrity = useApi<{ ok: boolean; ledger_total_paise: number; suspense_balance_paise: number }>("/admin/ledger/integrity", 10000);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold tracking-tight">Admin</h1>
      <Card glow>
        <div className="flex items-center gap-4">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-ok/15 text-ok">
            <ShieldCheck className="h-6 w-6" aria-hidden />
          </span>
          <div>
            <p className="font-semibold">Ledger integrity</p>
            {integrity.data ? (
              <p className="text-sm text-muted">
                {integrity.data.ok ? "All checks pass" : "Check failed"} · ledger total{" "}
                <span className="money">{formatINR(integrity.data.ledger_total_paise)}</span> · in flight{" "}
                <span className="money">{formatINR(integrity.data.suspense_balance_paise)}</span>
              </p>
            ) : (
              <Skeleton className="mt-1 h-4 w-56" />
            )}
          </div>
        </div>
      </Card>
      <p className="text-sm text-muted">
        Chaos controls and time travel are available through the API: see the interactive docs at <code>localhost:8000/docs</code>.
      </p>
    </div>
  );
}
