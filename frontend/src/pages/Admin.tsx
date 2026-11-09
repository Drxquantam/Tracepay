// Admin panel (simulation controls): run the demo story, time travel, make banks
// misbehave, check the ledger, and settle stuck payments by hand.

import { Clapperboard, Clock3, FastForward, RotateCcw, ServerCrash, ShieldCheck, ShieldX, Wrench } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useToast } from "../components/Toast";
import { Button, Card, cn, EmptyState, SectionTitle, Skeleton, StateBadge } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { formatDateTime, formatINR } from "../lib/format";
import type { Fault, Payment } from "../lib/types";
import { useApi } from "../lib/useApi";

type Bank = { code: string; name: string; profile: string; is_down: boolean; fault: Fault | null; response_delay_seconds: number };
type Integrity = {
  ok: boolean;
  ledger_total_paise: number;
  unbalanced_transactions: string[];
  balance_mismatches: { vpa: string }[];
  suspense_balance_paise: number;
  in_flight_payments_paise: number;
};

const FAULT_OPTIONS: { value: Fault | ""; label: string }[] = [
  { value: "", label: "Healthy" },
  { value: "slow_response", label: "Slow response" },
  { value: "timeout", label: "Timeout" },
  { value: "debited_not_credited", label: "Debited, not credited" },
  { value: "duplicate_callback", label: "Duplicate callback" },
  { value: "bank_down", label: "Down (fault)" },
];

export default function Admin() {
  const toast = useToast();
  const navigate = useNavigate();
  const clock = useApi<{ now: string; offset_seconds: number }>("/clock", 5000);
  const banks = useApi<Bank[]>("/admin/chaos/banks", 5000);
  const integrity = useApi<Integrity>("/admin/ledger/integrity", 5000);
  const attention = useApi<Payment[]>("/admin/payments", 5000);
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState<string | null>(null);

  async function run<T>(key: string, fn: () => Promise<T>, done?: (r: T) => void) {
    setBusy(key);
    try {
      const r = await fn();
      done?.(r);
      clock.reload();
      banks.reload();
      integrity.reload();
      attention.reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Something went wrong", "error");
    } finally {
      setBusy(null);
    }
  }

  const jump = (seconds: number) =>
    run(`jump${seconds}`, () => api<{ disputes_opened: number }>("/admin/clock/advance", { method: "POST", body: { seconds } }), (r) =>
      toast(r.disputes_opened ? `Time moved. ${r.disputes_opened} dispute(s) opened automatically.` : "Time moved.", "info"),
    );

  const updateBank = (code: string, body: Partial<Bank>) => run(`bank${code}`, () => api(`/admin/chaos/banks/${code}`, { method: "PUT", body }));

  const offsetDays = clock.data ? clock.data.offset_seconds / 86400 : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Admin panel</h1>
        <p className="mt-1 text-sm text-muted">Simulation controls. Nothing here affects anything real.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Demo story */}
        <Card glow>
          <div className="flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent text-white">
              <Clapperboard className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <p className="font-semibold">Run the demo story</p>
              <p className="mt-1 text-sm text-muted">
                Aarav pays Ravi's shop. Suraksha Bank is killed mid-flight, the clock jumps 8 days, and a dispute opens by itself with ₹300 owed. Takes about 15 seconds.
              </p>
            </div>
          </div>
          <Button
            size="lg"
            className="mt-4 w-full"
            loading={busy === "demo"}
            onClick={() =>
              run("demo", () => api<{ payment_id: string }>("/admin/demo", { method: "POST" }), (r) => navigate(`/payments/${r.payment_id}`))
            }
          >
            Start demo and watch the tracker
          </Button>
        </Card>

        {/* Ledger integrity */}
        <Card>
          <SectionTitle>Ledger integrity</SectionTitle>
          {!integrity.data ? (
            <Skeleton className="h-28" />
          ) : (
            <>
              <div className={cn("flex items-center gap-3 rounded-xl p-3", integrity.data.ok ? "bg-ok/10 text-ok" : "bg-bad/10 text-bad")}>
                {integrity.data.ok ? <ShieldCheck className="h-6 w-6" aria-hidden /> : <ShieldX className="h-6 w-6" aria-hidden />}
                <p className="font-semibold">{integrity.data.ok ? "All checks pass" : "A check failed"}</p>
              </div>
              <ul className="mt-3 space-y-2 text-sm">
                <Check ok={integrity.data.ledger_total_paise === 0} label="All ledger rows sum to zero" value={formatINR(integrity.data.ledger_total_paise)} />
                <Check ok={integrity.data.unbalanced_transactions.length === 0} label="Every transaction balances" value={`${integrity.data.unbalanced_transactions.length} unbalanced`} />
                <Check ok={integrity.data.balance_mismatches.length === 0} label="Balances match the ledger" value={`${integrity.data.balance_mismatches.length} mismatched`} />
                <Check
                  ok={integrity.data.suspense_balance_paise === integrity.data.in_flight_payments_paise}
                  label="Suspense = money in flight"
                  value={`${formatINR(integrity.data.suspense_balance_paise)} / ${formatINR(integrity.data.in_flight_payments_paise)}`}
                />
              </ul>
            </>
          )}
        </Card>

        {/* Time travel */}
        <Card>
          <SectionTitle>Time travel</SectionTitle>
          <div className="flex items-center gap-3">
            <Clock3 className="h-5 w-5 text-primary" aria-hidden />
            <div>
              <p className="font-semibold">{clock.data ? formatDateTime(clock.data.now) : "…"} IST (simulated)</p>
              <p className="text-xs text-muted">{offsetDays > 0 ? `${offsetDays.toFixed(1)} days ahead of real time` : "In sync with real time"}</p>
            </div>
          </div>
          <label htmlFor="hours" className="mt-5 block text-sm font-medium text-muted">
            Jump forward: <span className="font-semibold text-ink">{describeHours(hours)}</span>
          </label>
          <input id="hours" type="range" min={1} max={240} value={hours} onChange={(e) => setHours(Number(e.target.value))} className="mt-2 w-full accent-primary" />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button loading={busy === `jump${hours * 3600}`} onClick={() => jump(hours * 3600)}>
              <FastForward className="h-4 w-4" aria-hidden /> Jump
            </Button>
            {[
              ["+1 h", 3600],
              ["+1 day", 86400],
              ["+3 days", 3 * 86400],
              ["+8 days", 8 * 86400],
            ].map(([label, s]) => (
              <Button key={label} variant="ghost" onClick={() => jump(Number(s))}>
                {label}
              </Button>
            ))}
            <Button variant="ghost" onClick={() => run("reset", () => api("/admin/clock/reset", { method: "POST" }), () => toast("Clock back to real time", "info"))}>
              <RotateCcw className="h-4 w-4" aria-hidden /> Reset
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted">Each jump runs the deadline, guardian and mandate jobs straight away.</p>
        </Card>

        {/* Chaos */}
        <Card>
          <SectionTitle
            action={
              <Button variant="ghost" className="h-9 text-xs" onClick={() => run("chaosReset", () => api("/admin/chaos/reset", { method: "POST" }), () => toast("All banks healthy", "success"))}>
                <Wrench className="h-4 w-4" aria-hidden /> Heal all
              </Button>
            }
          >
            Chaos controls
          </SectionTitle>
          <div className="space-y-4">
            {(banks.data ?? []).map((b) => (
              <div key={b.code} className={cn("rounded-xl p-4", b.is_down ? "bg-bad/10" : "bg-line/5")}>
                <div className="flex items-center gap-3">
                  <ServerCrash className={cn("h-5 w-5", b.is_down ? "text-bad" : "text-muted")} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{b.name}</p>
                    <p className="text-xs text-muted">{b.profile} · {b.is_down ? "DOWN" : "up"}</p>
                  </div>
                  <Button variant={b.is_down ? "ghost" : "danger"} className="h-9 text-xs" onClick={() => updateBank(b.code, { is_down: !b.is_down })}>
                    {b.is_down ? "Bring up" : "Kill bank"}
                  </Button>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <label className="text-xs text-muted">
                    Fault
                    <select
                      value={b.fault ?? ""}
                      onChange={(e) => updateBank(b.code, { fault: (e.target.value || null) as Fault | null })}
                      className="panel mt-1 h-10 w-full rounded-xl px-2 text-sm text-ink"
                    >
                      {FAULT_OPTIONS.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs text-muted">
                    Latency: {b.response_delay_seconds.toFixed(1)} s
                    <input
                      type="range"
                      min={0}
                      max={10}
                      step={0.5}
                      defaultValue={b.response_delay_seconds}
                      onMouseUp={(e) => updateBank(b.code, { response_delay_seconds: Number((e.target as HTMLInputElement).value) })}
                      onKeyUp={(e) => updateBank(b.code, { response_delay_seconds: Number((e.target as HTMLInputElement).value) })}
                      className="mt-3 w-full accent-primary"
                    />
                  </label>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Payments needing attention */}
      <Card>
        <SectionTitle
          action={
            <Button variant="ghost" className="h-9 text-xs" onClick={() => run("sweep", () => api<{ disputes_opened: number }>("/admin/deadlines/sweep", { method: "POST" }), (r) => toast(`Jobs ran. ${r.disputes_opened} dispute(s) opened.`, "info"))}>
              Run jobs now
            </Button>
          }
        >
          Unsettled payments
        </SectionTitle>
        {!attention.data ? (
          <Skeleton className="h-20" />
        ) : attention.data.length === 0 ? (
          <EmptyState icon={<ShieldCheck className="h-5 w-5" />} title="Nothing stuck">
            Every payment has either arrived or been refunded.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line/5">
            {attention.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 py-3">
                <Link to={`/payments/${p.id}`} className="min-w-0 flex-1 hover:underline">
                  <span className="block font-semibold">
                    <span className="money">{formatINR(p.amount_paise)}</span> {p.payer_name} → {p.payee_name}
                  </span>
                  <span className="block text-xs text-muted">{formatDateTime(p.created_at)}</span>
                </Link>
                <StateBadge state={p.state} />
                {p.state === "in_switch" && (
                  <>
                    <Button className="h-9 text-xs" onClick={() => run(`c${p.id}`, () => api(`/admin/payments/${p.id}/resolve`, { method: "POST", body: { outcome: "credit" } }))}>
                      Bank credits
                    </Button>
                    <Button variant="ghost" className="h-9 text-xs" onClick={() => run(`r${p.id}`, () => api(`/admin/payments/${p.id}/resolve`, { method: "POST", body: { outcome: "reverse" } }))}>
                      Refund
                    </Button>
                  </>
                )}
                {p.state === "reversal_pending" && (
                  <Button variant="ghost" className="h-9 text-xs" onClick={() => run(`rr${p.id}`, () => api(`/admin/payments/${p.id}/retry-refund`, { method: "POST" }))}>
                    Retry refund
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function describeHours(h: number): string {
  if (h < 24) return h === 1 ? "1 hour" : `${h} hours`;
  const days = h / 24;
  const text = Number.isInteger(days) ? String(days) : days.toFixed(1);
  return days === 1 ? "1 day" : `${text} days`;
}

function Check({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-2">
        <span className={cn("h-2 w-2 rounded-full", ok ? "bg-ok" : "bg-bad")} aria-hidden />
        {label}
        <span className="sr-only">{ok ? "(pass)" : "(fail)"}</span>
      </span>
      <span className="money text-muted">{value}</span>
    </li>
  );
}
