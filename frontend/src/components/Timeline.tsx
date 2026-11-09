// The payment's event log, oldest first: every state change, plus notes like "no reply
// from the bank" and the dispute being opened. This is the "true story" of the money.

import { formatDateTime, STATE_LABEL } from "../lib/format";
import type { PaymentEvent } from "../lib/types";
import { cn } from "./ui";

function tone(e: PaymentEvent): string {
  if (e.kind === "dispute") return "bg-violet";
  if (e.kind === "note") return "bg-warn";
  if (e.to_state === "failed") return "bg-bad";
  if (e.to_state === "held") return "bg-warn";
  if (e.to_state === "credited" || e.to_state === "reversed") return "bg-ok";
  return "bg-teal";
}

export function Timeline({ events }: { events: PaymentEvent[] }) {
  return (
    <ol className="relative space-y-5 pl-6">
      <span className="absolute bottom-2 left-[7px] top-2 w-px bg-line/15" aria-hidden />
      {events.map((e, i) => (
        <li key={i} className="relative">
          <span className={cn("absolute -left-6 top-1 h-[15px] w-[15px] rounded-full ring-4 ring-canvas", tone(e))} aria-hidden />
          <p className="text-sm font-medium">{e.reason ?? STATE_LABEL[e.to_state]}</p>
          <p className="mt-0.5 text-xs text-muted">
            {formatDateTime(e.occurred_at)}
            {e.kind === "transition" && ` · ${STATE_LABEL[e.to_state]}`}
            {e.kind === "note" && " · update"}
            {e.kind === "dispute" && " · dispute"}
          </p>
        </li>
      ))}
    </ol>
  );
}
