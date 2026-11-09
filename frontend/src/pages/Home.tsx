// Home dashboard: balance and the 3D TracePay Black card, anything that needs attention
// (holds, money in flight, disputes), recent payments and spending.

import { motion } from "framer-motion";
import { ArrowRight, Inbox, PlaneTakeoff, Scale, Send, Snowflake } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { HoldCard } from "../components/HoldCard";
import Admin from "./Admin";
import { PaymentRow } from "../components/PaymentRow";
import { SpendChart } from "../components/SpendChart";
import { Guilloche } from "../components/brand";
import { PremiumCard } from "../components/PremiumCard";
import { AnimatedAmount, Button, Card, cn, EmptyState, SectionTitle, Skeleton } from "../components/ui";
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

  if (me?.role === "admin") return <Admin />;

  const account = me?.accounts[0];
  const list = payments.data ?? [];
  const openDisputes = (disputes.data ?? []).filter((d) => d.status === "open");
  // A payment with an open dispute is already shown as that dispute; don't list it twice.
  const disputed = new Set(openDisputes.map((d) => d.payment_id));
  const inFlight = list.filter((p) => IN_FLIGHT.has(p.state) && p.payer_vpa === account?.vpa && !disputed.has(p.id));

  return (
    <div className="space-y-6">
      {/* Hero: balance and actions beside the 3D card, over a faint banknote engraving. */}
      <section className="panel relative overflow-hidden rounded-2xl p-6 sm:p-8">
        <Guilloche className="absolute -bottom-64 -left-48 h-[560px] w-[560px] text-primary/[0.09]" speed={220} />
        <div className="pointer-events-none absolute -right-32 -top-40 h-80 w-80 rounded-full bg-deep/20 blur-3xl" aria-hidden />
        <div className="relative grid items-center gap-10 lg:grid-cols-[1fr_auto]">
          <div className="order-last lg:order-none">
            <p className="label">
              {greeting()}, {me?.full_name.split(" ")[0]}
            </p>
            <p className="mt-6 text-sm text-muted">Available balance</p>
            {account ? (
              <AnimatedAmount paise={account.balance_paise} className="mt-1 block text-5xl font-semibold sm:text-6xl" />
            ) : (
              <Skeleton className="mt-2 h-14 w-56" />
            )}
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted">
              <span className="font-mono text-[13px] text-ink/80">{account?.vpa}</span>
              <span aria-hidden>·</span>
              {account?.bank_name}
              {account?.is_frozen && (
                <span className="inline-flex items-center gap-1 rounded-md border border-warn/30 bg-warn/10 px-2 py-0.5 text-xs font-medium text-warn">
                  <Snowflake className="h-3 w-3" aria-hidden /> Frozen
                </span>
              )}
            </p>
            <div className="mt-8 flex gap-3">
              <Link to="/pay">
                <Button size="lg" className="w-36">
                  <Send className="h-4 w-4" aria-hidden /> Pay
                </Button>
              </Link>
              <Link to="/disputes">
                <Button size="lg" variant="ghost" className="w-36">
                  <Scale className="h-4 w-4" aria-hidden /> Disputes
                </Button>
              </Link>
            </div>
            <dl className="mt-8 grid max-w-sm grid-cols-2 gap-px overflow-hidden rounded-xl border border-line/[0.07] bg-line/[0.07]">
              <div className="bg-surface px-4 py-3">
                <dt className="label">In flight</dt>
                <dd className="money mt-1 text-lg font-semibold">{inFlight.length}</dd>
              </div>
              <div className="bg-surface px-4 py-3">
                <dt className="label">Open disputes</dt>
                <dd className={cn("money mt-1 text-lg font-semibold", openDisputes.length > 0 && "text-bad")}>{openDisputes.length}</dd>
              </div>
            </dl>
          </div>
          <div className="mx-auto w-full max-w-[400px] lg:w-[400px]">
            {account && <PremiumCard holder={me?.full_name ?? ""} vpa={account.vpa} bank={account.bank_name} frozen={account.is_frozen} />}
          </div>
        </div>
      </section>

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
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-bad/15 text-bad">
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
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-warn/15 text-warn">
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

      <div className="grid gap-6 lg:grid-cols-5">
        <section aria-labelledby="recent" className="lg:col-span-3">
          <Card className="h-full">
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
        <Card className="lg:col-span-2">
          {payments.loading || clock.loading ? (
            <Skeleton className="h-44" />
          ) : (
            <SpendChart payments={list} myVpa={account?.vpa} now={clock.data ? new Date(clock.data.now) : new Date()} />
          )}
        </Card>
      </div>
    </div>
  );
}
