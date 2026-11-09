// Guardian mode: choose a trusted person, set rules, the kill switch, and the inbox of
// payments waiting for a decision.

import { Info, Lock, ShieldCheck, Snowflake, Unlock, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { HoldCard } from "../components/HoldCard";
import { useToast } from "../components/Toast";
import { Button, Card, cn, EmptyState, SectionTitle, Skeleton } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatINR, rupeesToPaise } from "../lib/format";
import type { GuardianOverview, Holds } from "../lib/types";
import { useApi } from "../lib/useApi";

const rupees = (paise: number | null) => (paise ? String(paise / 100) : "");

export default function Guardian() {
  const toast = useToast();
  const { refreshMe } = useAuth();
  const overview = useApi<GuardianOverview>("/guardian", 10000);
  const holds = useApi<Holds>("/guardian/holds", 5000);
  const [busy, setBusy] = useState(false);

  // Rule form state, filled from the server once loaded.
  const [guardian, setGuardian] = useState("");
  const [threshold, setThreshold] = useState("");
  const [newPayee, setNewPayee] = useState(false);
  const [cooling, setCooling] = useState("");
  const [coolingMinutes, setCoolingMinutes] = useState("30");
  const rules = overview.data?.rules;
  useEffect(() => {
    if (!rules) return;
    setGuardian(rules.guardian?.username ?? "");
    setThreshold(rupees(rules.threshold_paise));
    setNewPayee(rules.new_payee_approval);
    setCooling(rupees(rules.cooling_off_threshold_paise));
    setCoolingMinutes(String(rules.cooling_off_minutes));
  }, [rules]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/guardian/settings", {
        method: "PUT",
        body: {
          guardian_username: guardian || null,
          threshold_paise: threshold ? rupeesToPaise(threshold) : null,
          new_payee_approval: newPayee,
          cooling_off_threshold_paise: cooling ? rupeesToPaise(cooling) : null,
          cooling_off_minutes: Number(coolingMinutes) || 30,
        },
      });
      toast("Guardian rules saved", "success");
      overview.reload();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't save", "error");
    } finally {
      setBusy(false);
    }
  }

  async function setFrozen(frozen: boolean, username?: string) {
    try {
      await api(frozen ? "/guardian/freeze" : "/guardian/unfreeze", { method: "POST", body: { username: username ?? null } });
      toast(frozen ? "Frozen. Outgoing payments are blocked." : "Unfrozen. Payments work again.", frozen ? "info" : "success");
      overview.reload();
      refreshMe().catch(() => {});
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Couldn't change it", "error");
    }
  }

  const reloadAll = () => {
    holds.reload();
    overview.reload();
  };

  if (!overview.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  const o = overview.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Guardian mode</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          A trusted person double-checks risky payments before any money leaves, and either of you can freeze the account in one tap.
        </p>
      </div>

      {/* Kill switch: the biggest thing on the page. */}
      <Card glow className={cn("flex flex-wrap items-center gap-4", o.is_frozen && "border-warn/40")}>
        <span className={cn("grid h-14 w-14 place-items-center rounded-xl", o.is_frozen ? "bg-warn/15 text-warn" : "bg-ok/15 text-ok")}>
          {o.is_frozen ? <Snowflake className="h-7 w-7" aria-hidden /> : <ShieldCheck className="h-7 w-7" aria-hidden />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-lg font-semibold">{o.is_frozen ? "Your account is frozen" : "Your account is active"}</p>
          <p className="text-sm text-muted">
            {o.is_frozen
              ? "No money can leave until you or your trusted person unfreezes it."
              : "If someone is pressuring you to pay, freeze first and ask questions later."}
          </p>
        </div>
        <Button size="lg" variant={o.is_frozen ? "ghost" : "danger"} onClick={() => setFrozen(!o.is_frozen)} className="w-full sm:w-auto">
          {o.is_frozen ? <Unlock className="h-5 w-5" aria-hidden /> : <Lock className="h-5 w-5" aria-hidden />}
          {o.is_frozen ? "Unfreeze" : "Freeze all payments"}
        </Button>
      </Card>

      {holds.data && holds.data.to_decide.length > 0 && (
        <section>
          <SectionTitle>Waiting for your decision</SectionTitle>
          <div className="grid gap-3 md:grid-cols-2">
            {holds.data.to_decide.map((h) => (
              <HoldCard key={h.id} hold={h} as="guardian" onDone={reloadAll} />
            ))}
          </div>
        </section>
      )}

      {holds.data && holds.data.mine.length > 0 && (
        <section>
          <SectionTitle>Your payments on hold</SectionTitle>
          <div className="grid gap-3 md:grid-cols-2">
            {holds.data.mine.map((h) => (
              <HoldCard key={h.id} hold={h} as="payer" onDone={reloadAll} />
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle>Your rules</SectionTitle>
          <form onSubmit={save} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="guardian" className="block text-sm font-medium text-muted">
                Trusted person
              </label>
              <select id="guardian" value={guardian} onChange={(e) => setGuardian(e.target.value)} className="panel h-12 w-full rounded-xl px-4 text-ink">
                <option value="">Nobody (guardian mode off)</option>
                {o.candidates.map((c) => (
                  <option key={c.username} value={c.username}>
                    {c.full_name}
                  </option>
                ))}
              </select>
            </div>
            <RupeeField id="threshold" label="Ask them before payments of" value={threshold} onChange={setThreshold} hint="Leave empty to switch off." disabled={!guardian} />
            <label className={cn("flex items-start gap-3 rounded-xl bg-line/5 p-3", !guardian && "opacity-50")}>
              <input type="checkbox" checked={newPayee} onChange={(e) => setNewPayee(e.target.checked)} disabled={!guardian} className="mt-1 h-5 w-5 accent-primary" />
              <span>
                <span className="block text-sm font-semibold">Ask them before paying someone new</span>
                <span className="block text-xs text-muted">Scammers usually ask you to pay an account you've never paid before.</span>
              </span>
            </label>
            <div className="grid grid-cols-[1fr_7rem] gap-3">
              <RupeeField id="cooling" label="Pause payments of" value={cooling} onChange={setCooling} disabled={!guardian} />
              <div className="space-y-1.5">
                <label htmlFor="minutes" className="block text-sm font-medium text-muted">
                  for (min)
                </label>
                <input id="minutes" inputMode="numeric" value={coolingMinutes} onChange={(e) => setCoolingMinutes(e.target.value)} disabled={!guardian} className="panel h-12 w-full rounded-xl px-4" />
              </div>
            </div>
            <Button type="submit" size="lg" className="w-full" loading={busy}>
              Save rules
            </Button>
          </form>
        </Card>

        <div className="space-y-6">
          <Card>
            <SectionTitle>People you protect</SectionTitle>
            {o.protecting.length === 0 ? (
              <EmptyState icon={<UserRound className="h-5 w-5" />} title="Nobody yet">
                When someone picks you as their trusted person, you'll see them here.
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {o.protecting.map((p) => (
                  <li key={p.username} className="flex flex-wrap items-center gap-3 rounded-xl bg-line/5 p-3">
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold">{p.full_name}</span>
                      <span className="block text-xs text-muted">
                        {p.is_frozen ? "Frozen" : "Active"} · {p.pending_requests} waiting for you
                      </span>
                    </span>
                    <Button variant={p.is_frozen ? "ghost" : "danger"} onClick={() => setFrozen(!p.is_frozen, p.username)}>
                      {p.is_frozen ? "Unfreeze" : "Freeze"}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="flex gap-3 text-sm">
            <Info className="mt-0.5 h-5 w-5 shrink-0 text-deep" aria-hidden />
            <p className="text-muted">
              <span className="font-semibold text-ink">Guardian mode reduces risk, but it can't stop every scam.</span> Someone being coached by a scammer can be
              talked into asking for approval, or into changing these rules. If a caller is rushing you to pay, stop and call someone you trust.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}

function RupeeField(props: { id: string; label: string; value: string; onChange: (v: string) => void; hint?: string; disabled?: boolean }) {
  const paise = props.value ? rupeesToPaise(props.value) : null;
  return (
    <div className={cn("space-y-1.5", props.disabled && "opacity-50")}>
      <label htmlFor={props.id} className="block text-sm font-medium text-muted">
        {props.label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-4 top-3 text-muted" aria-hidden>
          ₹
        </span>
        <input
          id={props.id}
          inputMode="decimal"
          value={props.value}
          disabled={props.disabled}
          onChange={(e) => props.onChange(e.target.value)}
          className="panel money h-12 w-full rounded-xl pl-8 pr-4"
          aria-describedby={`${props.id}-hint`}
        />
      </div>
      <p id={`${props.id}-hint`} className="text-xs text-muted">
        {paise ? `${formatINR(paise)} or more` : props.hint ?? "Leave empty to switch off."}
      </p>
    </div>
  );
}
