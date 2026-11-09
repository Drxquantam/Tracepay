// Month calendar of debits: upcoming ones (projected from each active mandate) plus past
// attempts (paid, failed, retrying). Days are counted in IST, like everything else.

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { formatINR } from "../lib/format";
import type { Mandate } from "../lib/types";
import { cn } from "./ui";

type Entry = { day: string; amount: number; merchant: string; kind: "upcoming" | "paid" | "failed" | "retrying" | "trial" };

const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }); // YYYY-MM-DD
const monthTitle = new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function entries(mandates: Mandate[]): Entry[] {
  const out: Entry[] = [];
  for (const m of mandates) {
    for (const u of m.upcoming) {
      out.push({ day: dayKey.format(new Date(u.due_at)), amount: u.amount_paise, merchant: m.merchant_name, kind: u.is_trial ? "trial" : "upcoming" });
    }
    for (const d of m.debits) {
      if (d.status === "succeeded" || d.status === "failed" || d.status === "retrying") {
        out.push({ day: dayKey.format(new Date(d.due_at)), amount: d.amount_paise, merchant: m.merchant_name, kind: d.status === "succeeded" ? "paid" : d.status });
      }
    }
  }
  return out;
}

const DOT: Record<Entry["kind"], string> = {
  upcoming: "bg-teal",
  trial: "bg-violet",
  paid: "bg-ok",
  failed: "bg-bad",
  retrying: "bg-warn",
};

export function MandateCalendar({ mandates, now }: { mandates: Mandate[]; now: Date }) {
  const [offset, setOffset] = useState(0); // months from the current (simulated) month
  const all = useMemo(() => entries(mandates), [mandates]);

  const [y, mo] = dayKey.format(now).split("-").map(Number);
  const first = new Date(Date.UTC(y, mo - 1 + offset, 1));
  const year = first.getUTCFullYear();
  const month = first.getUTCMonth();
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const leadingBlanks = (first.getUTCDay() + 6) % 7; // Monday-first grid
  const prefix = `${year}-${String(month + 1).padStart(2, "0")}-`;
  const inMonth = all.filter((e) => e.day.startsWith(prefix));
  const total = inMonth.filter((e) => e.kind !== "failed").reduce((s, e) => s + e.amount, 0);
  const today = dayKey.format(now);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <button onClick={() => setOffset(offset - 1)} className="glass grid h-9 w-9 place-items-center rounded-xl" aria-label="Previous month">
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </button>
        <h3 className="flex-1 text-center font-bold">{monthTitle.format(first)}</h3>
        <button onClick={() => setOffset(offset + 1)} className="glass grid h-9 w-9 place-items-center rounded-xl" aria-label="Next month">
          <ChevronRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-semibold text-muted">
        {WEEKDAYS.map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {Array.from({ length: leadingBlanks }, (_, i) => (
          <div key={`b${i}`} />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const key = prefix + String(i + 1).padStart(2, "0");
          const here = inMonth.filter((e) => e.day === key);
          const label = here.map((e) => `${formatINR(e.amount)} to ${e.merchant} (${e.kind})`).join(", ");
          return (
            <div
              key={key}
              className={cn("flex aspect-square flex-col items-center justify-start rounded-xl p-1 text-xs", here.length ? "bg-line/10" : "", key === today && "ring-2 ring-teal/60")}
              title={label || undefined}
              aria-label={label ? `${i + 1}: ${label}` : undefined}
            >
              <span className={cn("font-semibold", here.length ? "text-ink" : "text-muted")}>{i + 1}</span>
              <span className="mt-auto flex gap-0.5">
                {here.map((e, j) => (
                  <span key={j} className={cn("h-1.5 w-1.5 rounded-full", DOT[e.kind])} />
                ))}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line/10 pt-4">
        <div>
          <p className="text-xs text-muted">Total for {monthTitle.format(first).split(" ")[0]}</p>
          <p className="money text-2xl font-extrabold">{formatINR(total)}</p>
        </div>
        <ul className="flex flex-wrap gap-3 text-xs text-muted">
          {(
            [
              ["upcoming", "Upcoming"],
              ["trial", "Trial price"],
              ["paid", "Paid"],
              ["retrying", "Retrying"],
              ["failed", "Failed"],
            ] as const
          ).map(([k, label]) => (
            <li key={k} className="flex items-center gap-1.5">
              <span className={cn("h-2 w-2 rounded-full", DOT[k])} /> {label}
            </li>
          ))}
        </ul>
      </div>
      {inMonth.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {inMonth
            .sort((a, b) => a.day.localeCompare(b.day))
            .map((e, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="text-muted">
                  {Number(e.day.slice(8))} · {e.merchant}
                </span>
                <span className={cn("money font-semibold", e.kind === "failed" && "text-bad line-through")}>{formatINR(e.amount)}</span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
