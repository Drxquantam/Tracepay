// A dispute: compensation owed (and by whom), the escalation checklist, and the claim
// summary to copy or download.

import { CheckCircle2, Circle, ClipboardCopy, Download, Lock, Scale } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { formatDate, formatDateTime, formatINR } from "../lib/format";
import type { Dispute } from "../lib/types";
import { useToast } from "./Toast";
import { AnimatedAmount, Button, Card, cn } from "./ui";

// simNow: the simulated time (from the server). Unlock dates are in simulated time too.
export function DisputeCard({ dispute, simNow, onChange }: { dispute: Dispute; simNow: string; onChange: () => void }) {
  const toast = useToast();
  const [busyStep, setBusyStep] = useState<string | null>(null);
  const open = dispute.status === "open";

  async function claimText() {
    return api<string>(`/disputes/${dispute.id}/claim`, { asText: true });
  }

  async function copyClaim() {
    try {
      await navigator.clipboard.writeText(await claimText());
      toast("Claim summary copied. Paste it into your bank's complaint form.", "success");
    } catch {
      toast("Couldn't copy. Try the download button instead.", "error");
    }
  }

  async function downloadClaim() {
    const blob = new Blob([await claimText()], { type: "text/plain" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `tracepay-claim-${dispute.payment_reference}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  async function complete(step: string) {
    setBusyStep(step);
    try {
      await api(`/disputes/${dispute.id}/steps/${step}/complete`, { method: "POST" });
      toast("Step marked as done", "success");
      onChange();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't update the step", "error");
    } finally {
      setBusyStep(null);
    }
  }

  return (
    <Card className={cn(open && "border-bad/30")}>
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Scale className="h-4 w-4 text-violet" aria-hidden />
        Dispute opened automatically
        <span className={cn("ml-auto rounded-full px-2.5 py-0.5 text-xs", open ? "bg-bad/15 text-bad" : "bg-ok/15 text-ok")}>{open ? "Open" : "Resolved"}</span>
      </div>

      <div className="mt-4">
        <p className="text-sm text-muted">Compensation owed to you</p>
        <AnimatedAmount paise={dispute.compensation_owed_paise} className="block text-4xl font-extrabold text-gradient" />
        <p className="mt-1 font-semibold">{dispute.headline}</p>
      </div>

      {/* The single most important sentence on this card. */}
      <p className="mt-4 rounded-2xl bg-violet/10 px-4 py-3 text-sm font-medium">{dispute.who_owes}</p>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-muted">Rule</dt>
          <dd className="font-medium">
            T+{dispute.tat_days}, {formatINR(dispute.compensation_paise_per_day)}/day
          </dd>
        </div>
        <div>
          <dt className="text-muted">Deadline was</dt>
          <dd className="font-medium">{formatDateTime(dispute.deadline_at)}</dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-muted">Modelled on RBI rules for failed transactions. Verify against the current circular before relying on it.</p>

      <h3 className="mb-2 mt-6 text-sm font-semibold">What to do next</h3>
      <ol className="space-y-2">
        {dispute.steps.map((s, i) => {
          const previousDone = dispute.steps.slice(0, i).every((p) => p.completed_at);
          const locked = s.step === "ombudsman" && (!s.available_at || new Date(s.available_at) > new Date(simNow));
          return (
            <li key={s.step} className="flex gap-3 rounded-2xl bg-line/5 p-3">
              {s.completed_at ? (
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ok" aria-label="Done" />
              ) : locked ? (
                <Lock className="mt-0.5 h-5 w-5 shrink-0 text-muted" aria-label="Locked" />
              ) : (
                <Circle className="mt-0.5 h-5 w-5 shrink-0 text-muted" aria-label="To do" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{s.title}</p>
                <p className="text-xs text-muted">{s.description}</p>
                {s.completed_at ? (
                  <p className="mt-1 text-xs text-ok">Done {formatDateTime(s.completed_at)}</p>
                ) : s.step === "ombudsman" && s.available_at ? (
                  <p className="mt-1 text-xs text-muted">Available from {formatDate(s.available_at)} if your bank hasn't fixed it.</p>
                ) : null}
              </div>
              {!s.completed_at && previousDone && s.step !== "app" && (
                <Button variant="ghost" className="h-9 shrink-0 self-center px-3 text-xs" loading={busyStep === s.step} onClick={() => complete(s.step)}>
                  Mark done
                </Button>
              )}
            </li>
          );
        })}
      </ol>

      <div className="mt-5 flex flex-wrap gap-2">
        <Button onClick={copyClaim}>
          <ClipboardCopy className="h-4 w-4" aria-hidden /> Copy claim summary
        </Button>
        <Button variant="ghost" onClick={downloadClaim}>
          <Download className="h-4 w-4" aria-hidden /> Download
        </Button>
      </div>
    </Card>
  );
}
