// A held payment, in plain language, with big obvious buttons.
// As the trusted person: Approve / Stop. As the payer: Cancel.

import { Hourglass, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { formatDateTime, formatINR } from "../lib/format";
import type { Hold } from "../lib/types";
import { useToast } from "./Toast";
import { Button, Card } from "./ui";

export function HoldCard({ hold, as, onDone }: { hold: Hold; as: "guardian" | "payer"; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const approval = hold.kind === "approval";

  async function act(action: "approve" | "deny" | "cancel") {
    setBusy(action);
    try {
      const r = await api<{ state: string }>(`/guardian/holds/${hold.id}/${action}`, { method: "POST" });
      const msg =
        action === "approve"
          ? r.state === "failed"
            ? "Approved, but the bank declined it"
            : "Approved. The payment is on its way."
          : action === "deny"
            ? "Payment stopped. No money moved."
            : "Payment cancelled. No money moved.";
      toast(msg, r.state === "failed" && action === "approve" ? "error" : "success");
      onDone();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Something went wrong", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="border-warn/30">
      <div className="flex items-start gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-warn/15 text-warn">
          {approval ? <ShieldAlert className="h-5 w-5" aria-hidden /> : <Hourglass className="h-5 w-5" aria-hidden />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-lg font-bold leading-snug">
            {as === "guardian" ? `${hold.payer_name} wants to pay` : "You're paying"} <span className="money">{formatINR(hold.amount_paise)}</span> to{" "}
            {hold.payee_name}
          </p>
          <p className="mt-1 text-sm text-muted">Why: {hold.reasons}.</p>
          <p className="mt-1 text-sm text-muted">
            {approval
              ? `${as === "guardian" ? "Decide" : `Waiting for ${hold.guardian_name}`} before ${formatDateTime(hold.due_at)}, or it is cancelled.`
              : `Sends automatically at ${formatDateTime(hold.due_at)}.`}
          </p>
          <Link to={`/payments/${hold.payment_id}`} className="mt-1 inline-block text-sm font-semibold text-teal hover:underline">
            See details
          </Link>
        </div>
      </div>
      <div className="mt-4 flex gap-3">
        {as === "guardian" ? (
          <>
            {approval && (
              <Button size="lg" className="flex-1" loading={busy === "approve"} onClick={() => act("approve")}>
                Approve
              </Button>
            )}
            <Button size="lg" variant="danger" className="flex-1" loading={busy === "deny"} onClick={() => act("deny")}>
              Stop payment
            </Button>
          </>
        ) : (
          <Button size="lg" variant="ghost" className="flex-1" loading={busy === "cancel"} onClick={() => act("cancel")}>
            Cancel this payment
          </Button>
        )}
      </div>
    </Card>
  );
}
