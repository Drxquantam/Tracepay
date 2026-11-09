// "Last 7 days" spending chart (Recharts). Counts money the user sent that actually left
// for good: credited payments, plus ones still in flight. Failed and refunded don't count.

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { formatINR } from "../lib/format";
import type { Payment } from "../lib/types";

const COUNTS = new Set(["credited", "bank_debited", "in_switch"]);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }); // YYYY-MM-DD
const dayLabel = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short" });

export function SpendChart({ payments, myVpa, now }: { payments: Payment[]; myVpa?: string; now: Date }) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now.getTime() - (6 - i) * 86400_000);
    return { key: dayKey.format(d), label: dayLabel.format(d), paise: 0 };
  });
  for (const p of payments) {
    if (p.payer_vpa !== myVpa || !COUNTS.has(p.state)) continue;
    const day = days.find((d) => d.key === dayKey.format(new Date(p.created_at)));
    if (day) day.paise += p.amount_paise;
  }
  const total = days.reduce((sum, d) => sum + d.paise, 0);

  return (
    <div>
      <p className="money text-2xl font-bold">{formatINR(total)}</p>
      <p className="mb-2 text-xs text-muted">spent in the last 7 days</p>
      <div className="h-32" role="img" aria-label={`Spending over the last 7 days, ${formatINR(total)} in total`}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={days} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
            <defs>
              <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgb(var(--teal))" stopOpacity={0.45} />
                <stop offset="100%" stopColor="rgb(var(--violet))" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: "rgb(var(--muted))", fontSize: 11 }} />
            <Tooltip
              cursor={{ stroke: "rgb(var(--line) / 0.15)" }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <div className="glass rounded-xl px-3 py-2 text-xs">
                    <span className="money font-semibold">{formatINR(Number(payload[0].value))}</span>
                  </div>
                ) : null
              }
            />
            <Area type="monotone" dataKey="paise" stroke="rgb(var(--teal))" strokeWidth={2.5} fill="url(#spendFill)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
