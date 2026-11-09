// One line in a payment list: who, when, how much (signed), and the state.

import { Link } from "react-router-dom";
import { formatDateTime, formatINR } from "../lib/format";
import type { Payment } from "../lib/types";
import { cn, StateBadge } from "./ui";

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

export function PaymentRow({ payment, myVpa }: { payment: Payment; myVpa: string | undefined }) {
  const sent = payment.payer_vpa === myVpa;
  const other = sent ? payment.payee_name : payment.payer_name;
  // Money only counts as moved for credited payments; show others muted.
  const settled = payment.state === "credited";
  return (
    <Link
      to={`/payments/${payment.id}`}
      className="flex items-center gap-3 rounded-2xl px-2 py-3 transition hover:bg-line/5 focus-visible:bg-line/5"
    >
      <span className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-sm font-bold", sent ? "bg-violet/15 text-violet" : "bg-teal/15 text-teal")} aria-hidden>
        {initials(other)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold">{other}</span>
        <span className="block truncate text-xs text-muted">
          {payment.note ? `${payment.note} · ` : ""}
          {formatDateTime(payment.created_at)}
        </span>
      </span>
      <span className="flex flex-col items-end gap-1">
        <span className={cn("money font-bold", !settled && "text-muted", settled && !sent && "text-ok")}>
          {sent ? "−" : "+"}
          {formatINR(payment.amount_paise)}
        </span>
        <StateBadge state={payment.state} />
      </span>
    </Link>
  );
}
