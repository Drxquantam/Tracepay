// Pay flow: choose who → enter amount → confirm.
//
// Idempotency in the UI: one Idempotency-Key is made when the user reaches the confirm
// step and is reused for every retry of *that* payment. If the network drops after the
// server took the money, "Try again" sends the same key and the server replays its first
// answer instead of charging twice. Going back to change anything makes a new key.

import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Check, FlaskConical, Search, Store, User } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useToast } from "../components/Toast";
import { Button, Card, cn, Skeleton, TextField } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatINR, rupeesToPaise } from "../lib/format";
import type { Fault, Payee, Payment } from "../lib/types";
import { useApi } from "../lib/useApi";

type Step = "who" | "amount" | "confirm";
const UPI_LIMIT_PAISE = 1_00_000 * 100; // mirrors backend/app/rules.py
const QUICK_AMOUNTS = [50, 100, 200, 500];

const FAULTS: { value: Fault | ""; label: string; hint: string }[] = [
  { value: "", label: "No problem", hint: "The payment goes through normally." },
  { value: "slow_response", label: "Slow bank", hint: "The payee's bank takes about 8 seconds to answer." },
  { value: "debited_not_credited", label: "Debited, not credited", hint: "Money leaves you but the payee's bank never confirms." },
  { value: "timeout", label: "Bank timeout", hint: "The switch gives up and refunds you." },
  { value: "duplicate_callback", label: "Duplicate confirmation", hint: "The bank confirms twice; you're only charged once." },
  { value: "bank_down", label: "Payee bank down", hint: "The payee's bank is unreachable when the credit is due." },
];

const slide = {
  initial: { opacity: 0, x: 24 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -24 },
  transition: { duration: 0.25 },
};

export default function Pay() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const payees = useApi<Payee[]>("/payees");
  const account = me?.accounts[0];

  const [step, setStep] = useState<Step>("who");
  const [query, setQuery] = useState("");
  const [payee, setPayee] = useState<Payee | null>(null);
  const [amountText, setAmountText] = useState("");
  const [note, setNote] = useState("");
  const [fault, setFault] = useState<Fault | "">("");
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; retrySafe: boolean } | null>(null);

  const amount = rupeesToPaise(amountText);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (payees.data ?? []).filter((p) => !q || p.name.toLowerCase().includes(q) || p.vpa.includes(q));
  }, [payees.data, query]);
  const typedVpa = /^[\w.-]+@[\w.-]+$/.test(query.trim()) && !filtered.some((p) => p.vpa === query.trim().toLowerCase());

  function choose(p: Payee) {
    setPayee(p);
    setStep("amount");
  }

  function toConfirm() {
    setKey(crypto.randomUUID()); // one key per payment attempt
    setError(null);
    setStep("confirm");
  }

  async function submit() {
    if (!payee || !amount || !key) return;
    setBusy(true);
    setError(null);
    try {
      const payment = await api<Payment>("/payments", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: { payee_vpa: payee.vpa, amount_paise: amount, note: note.trim() || null, simulate_fault: fault || null },
      });
      if (payment.state === "failed") toast(payment.failure_reason ?? "Payment failed", "error");
      else if (payment.state === "held") toast("Guardian mode is holding this payment. No money has left yet.", "info");
      else toast("Payment sent. Tracking it now.", "success");
      navigate(`/payments/${payment.id}`);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, String(e));
      // status 0 = no answer: the server may or may not have taken the money. Retrying with
      // the same key is safe either way.
      setError({ message: err.message, retrySafe: err.status === 0 });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-5">
      <div className="flex items-center gap-3">
        {step !== "who" && (
          <button
            onClick={() => setStep(step === "confirm" ? "amount" : "who")}
            className="panel grid h-10 w-10 place-items-center rounded-xl"
            aria-label="Back"
          >
            <ArrowLeft className="h-5 w-5" aria-hidden />
          </button>
        )}
        <h1 className="text-2xl font-semibold tracking-tight">
          {step === "who" ? "Pay someone" : step === "amount" ? `Pay ${payee?.name}` : "Check and pay"}
        </h1>
      </div>
      <ol className="flex gap-2" aria-label="Progress">
        {(["who", "amount", "confirm"] as Step[]).map((s, i) => (
          <li key={s} className={cn("h-1.5 flex-1 rounded-full", ["who", "amount", "confirm"].indexOf(step) >= i ? "bg-accent" : "bg-line/10")}>
            <span className="sr-only">
              Step {i + 1} of 3{step === s ? " (current)" : ""}
            </span>
          </li>
        ))}
      </ol>

      <AnimatePresence mode="wait">
        {step === "who" && (
          <motion.div key="who" {...slide} className="space-y-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-[2.6rem] h-5 w-5 text-muted" aria-hidden />
              <TextField
                label="Name or UPI ID"
                placeholder="Search contacts or type a UPI ID"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-11"
                autoFocus
              />
            </div>
            {typedVpa && (
              <button
                onClick={() => choose({ vpa: query.trim().toLowerCase(), name: query.trim().toLowerCase(), kind: "user", bank_name: "Unknown bank" })}
                className="panel w-full rounded-xl p-4 text-left font-semibold hover:shadow-glow"
              >
                Pay UPI ID <span className="text-primary">{query.trim().toLowerCase()}</span>
              </button>
            )}
            <Card className="p-2 sm:p-2">
              {payees.loading ? (
                <div className="space-y-2 p-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-14" />
                  ))}
                </div>
              ) : (
                <ul>
                  {filtered.map((p) => (
                    <li key={p.vpa}>
                      <button onClick={() => choose(p)} className="flex w-full items-center gap-3 rounded-xl p-3 text-left transition hover:bg-line/5">
                        <span className={cn("grid h-11 w-11 place-items-center rounded-xl", p.kind === "merchant" ? "bg-deep/15 text-deep" : "bg-primary/15 text-primary")}>
                          {p.kind === "merchant" ? <Store className="h-5 w-5" aria-hidden /> : <User className="h-5 w-5" aria-hidden />}
                        </span>
                        <span className="min-w-0">
                          <span className="block font-semibold">{p.name}</span>
                          <span className="block truncate text-xs text-muted">
                            {p.vpa} · {p.bank_name}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                  {filtered.length === 0 && !typedVpa && <li className="p-4 text-sm text-muted">No one matches “{query}”.</li>}
                </ul>
              )}
            </Card>
          </motion.div>
        )}

        {step === "amount" && payee && (
          <motion.div key="amount" {...slide} className="space-y-4">
            <Card glow className="text-center">
              <label htmlFor="amount" className="text-sm font-medium text-muted">
                Amount
              </label>
              <div className="mt-2 flex items-center justify-center gap-1">
                <span className="text-4xl font-semibold text-muted" aria-hidden>
                  ₹
                </span>
                <input
                  id="amount"
                  inputMode="decimal"
                  autoFocus
                  placeholder="0"
                  value={amountText}
                  onChange={(e) => setAmountText(e.target.value)}
                  className="money w-full max-w-[14rem] bg-transparent text-center text-5xl font-semibold outline-none placeholder:text-muted/40"
                  aria-describedby="amount-help"
                />
              </div>
              <p id="amount-help" className="mt-2 text-xs text-muted">
                Balance: <span className="money">{account ? formatINR(account.balance_paise) : "…"}</span>
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {QUICK_AMOUNTS.map((r) => (
                  <button key={r} onClick={() => setAmountText(String(r))} className="panel money rounded-full px-4 py-1.5 text-sm font-semibold hover:shadow-glow">
                    ₹{r}
                  </button>
                ))}
              </div>
            </Card>
            {amount && account && amount > account.balance_paise && (
              <p className="rounded-xl bg-warn/10 px-3 py-2 text-sm text-warn">This is more than your balance, so your bank will decline it.</p>
            )}
            {amount && amount > UPI_LIMIT_PAISE && <p className="rounded-xl bg-bad/10 px-3 py-2 text-sm text-bad">UPI payments are limited to ₹1,00,000 each.</p>}
            <TextField label="Note (optional)" placeholder="What's it for?" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
            <Button size="lg" className="w-full" disabled={!amount || amount > UPI_LIMIT_PAISE} onClick={toConfirm}>
              Continue
            </Button>
          </motion.div>
        )}

        {step === "confirm" && payee && amount && (
          <motion.div key="confirm" {...slide} className="space-y-4">
            <Card glow>
              <p className="text-sm text-muted">You're paying</p>
              <p className="money mt-1 text-4xl font-semibold">{formatINR(amount)}</p>
              <dl className="mt-5 space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">To</dt>
                  <dd className="text-right">
                    <span className="block font-semibold">{payee.name}</span>
                    <span className="block text-xs text-muted">{payee.vpa}</span>
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">From</dt>
                  <dd className="text-right">
                    <span className="block font-semibold">{account?.vpa}</span>
                    <span className="block text-xs text-muted">{account?.bank_name}</span>
                  </dd>
                </div>
                {note.trim() && (
                  <div className="flex justify-between gap-4">
                    <dt className="text-muted">Note</dt>
                    <dd className="text-right font-medium">{note.trim()}</dd>
                  </div>
                )}
              </dl>
            </Card>

            <details className="panel group rounded-2xl p-4">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold">
                <FlaskConical className="h-4 w-4 text-warn" aria-hidden />
                Simulate a problem (demo)
                <span className="ml-auto text-xs font-normal text-muted">{FAULTS.find((f) => f.value === fault)?.label}</span>
              </summary>
              <fieldset className="mt-3 space-y-2">
                <legend className="sr-only">Choose what goes wrong</legend>
                {FAULTS.map((f) => (
                  <label key={f.value} className={cn("flex cursor-pointer gap-3 rounded-xl p-3 transition", fault === f.value ? "bg-primary/10 ring-1 ring-primary/40" : "hover:bg-line/5")}>
                    <input type="radio" name="fault" value={f.value} checked={fault === f.value} onChange={() => setFault(f.value)} className="mt-1 accent-primary" />
                    <span>
                      <span className="block text-sm font-semibold">{f.label}</span>
                      <span className="block text-xs text-muted">{f.hint}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
            </details>

            {error && (
              <div role="alert" className={cn("rounded-xl px-4 py-3 text-sm", error.retrySafe ? "bg-warn/10 text-warn" : "bg-bad/10 text-bad")}>
                <p className="font-semibold">{error.message}</p>
                {error.retrySafe && <p className="mt-1">Trying again is safe: it reuses this payment's key, so you can't be charged twice.</p>}
              </div>
            )}

            <Button size="lg" className="w-full" loading={busy} onClick={submit}>
              <Check className="h-5 w-5" aria-hidden />
              {error?.retrySafe ? "Try again" : `Pay ${formatINR(amount)}`}
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
