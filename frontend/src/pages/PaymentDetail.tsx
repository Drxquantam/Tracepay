// Payment detail: the Money in Flight tracker for one payment. The flight path, the plain-
// language status, the deadline countdown, any dispute, and the full event timeline.
// Polls the tracker: quickly while the money is moving, slowly while it's stuck, and
// stops once everything is settled.

import { ArrowLeft, Copy, Hourglass, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CountdownRing } from "../components/CountdownRing";
import { DisputeCard } from "../components/DisputeCard";
import { FlightPath } from "../components/FlightPath";
import { Timeline } from "../components/Timeline";
import { useToast } from "../components/Toast";
import { Button, Card, cn, EmptyState, SectionTitle, Skeleton, StateBadge } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatDateTime, formatINR } from "../lib/format";
import type { Tracker } from "../lib/types";
import { useApi } from "../lib/useApi";

function pollDelay(t: Tracker): number | null {
  const s = t.payment.state;
  if ((s === "bank_debited" || s === "in_switch") && t.health === "ok") return 1500; // moving
  if (s === "bank_debited" || s === "in_switch" || s === "reversal_pending") return 5000; // stuck
  if (s === "held") return 3000;
  if (t.dispute?.status === "open") return 5000;
  return null; // settled: nothing more will change on its own
}

const HEALTH_TEXT: Record<string, string> = { ok: "text-primary", delayed: "text-warn", late: "text-bad", failed: "text-bad" };

export default function PaymentDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const toast = useToast();
  const { data: t, error, reload } = useApi<Tracker>(`/payments/${id}/tracker`, pollDelay);
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  useEffect(() => setFetchedAt(Date.now()), [t]);

  if (error) {
    return (
      <Card>
        <EmptyState icon={<Hourglass className="h-5 w-5" />} title="Payment not found">
          {error.message}
        </EmptyState>
      </Card>
    );
  }
  if (!t) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-56" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const p = t.payment;
  const received = me?.accounts.some((a) => a.vpa === p.payee_vpa);
  const stuck = t.health === "delayed" || t.health === "late";
  const finished = p.state === "credited" || p.state === "reversed";
  const windowSeconds = t.deadline_at ? (new Date(t.deadline_at).getTime() - new Date(p.created_at).getTime()) / 1000 : 1;

  async function copyRef() {
    try {
      await navigator.clipboard.writeText(p.reference);
      toast("Reference number copied", "success");
    } catch {
      toast("Couldn't copy", "error");
    }
  }

  return (
    <div className="space-y-6">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Home
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">{received ? `From ${p.payer_name}` : `To ${p.payee_name}`}</p>
          <p className="money text-4xl font-semibold sm:text-5xl">{formatINR(p.amount_paise)}</p>
          <p className="mt-1 text-sm text-muted">
            {p.note ? `${p.note} · ` : ""}
            {formatDateTime(p.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-3 sm:flex-col sm:items-end sm:gap-2">
          <StateBadge state={p.state} stuck={stuck && !finished} />
          <button onClick={copyRef} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink" aria-label={`Copy reference number ${p.reference}`}>
            Ref <span className="money font-semibold text-ink">{p.reference}</span>
            <Copy className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card glow={stuck}>
            <FlightPath position={t.position} health={t.health} state={p.state} stages={t.stages} summary={`${t.headline}. ${t.detail}`} />
            {/* aria-live: status changes are announced as the payment moves. */}
            <div aria-live="polite" className="mt-2 text-center">
              <p className={cn("text-lg font-semibold", finished ? "text-ok" : HEALTH_TEXT[t.health])}>{t.headline}</p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted">{t.detail}</p>
            </div>
          </Card>

          <Card>
            <SectionTitle>What happened</SectionTitle>
            <Timeline events={p.events} />
          </Card>
        </div>

        <div className="space-y-6">
          {t.rule && (
            <Card>
              <SectionTitle>Deadline</SectionTitle>
              <div className="flex items-center gap-5">
                <CountdownRing
                  secondsToDeadline={t.seconds_to_deadline}
                  windowSeconds={windowSeconds}
                  fetchedAt={fetchedAt}
                  breached={t.breached}
                  daysLate={t.days_late}
                />
                <div className="min-w-0 text-sm">
                  <p className="font-semibold">Must be fixed by T+{t.rule.tat_days}</p>
                  <p className="mt-1 text-muted">{t.deadline_at && formatDateTime(t.deadline_at)}</p>
                  <p className="mt-2 text-xs text-muted">
                    After that, your bank owes you {formatINR(t.rule.compensation_paise_per_day)} for each day of delay.
                  </p>
                </div>
              </div>
            </Card>
          )}
          {t.hold && t.hold.status === "pending" && p.state === "held" && (
            <Card className="border-warn/30">
              <div className="flex items-center gap-2 text-sm font-semibold text-warn">
                <ShieldAlert className="h-4 w-4" aria-hidden />
                {t.hold.kind === "approval" ? "Guardian check" : "Cooling-off pause"}
              </div>
              <p className="mt-2 text-sm">{t.hold.reasons}.</p>
              <p className="mt-1 text-xs text-muted">
                {t.hold.kind === "approval" ? `Cancelled automatically if not approved by ${formatDateTime(t.hold.due_at)}.` : `Sends at ${formatDateTime(t.hold.due_at)}.`}
              </p>
              {!received && (
                <Button
                  variant="ghost"
                  className="mt-4 w-full"
                  onClick={async () => {
                    try {
                      await api(`/guardian/holds/${t.hold!.id}/cancel`, { method: "POST" });
                      toast("Payment cancelled. No money moved.", "success");
                      reload();
                    } catch (e) {
                      toast(e instanceof ApiError ? e.message : "Couldn't cancel", "error");
                    }
                  }}
                >
                  Cancel this payment
                </Button>
              )}
            </Card>
          )}
          {t.dispute && <DisputeCard dispute={t.dispute} simNow={t.sim_now} onChange={reload} />}
        </div>
      </div>
    </div>
  );
}
