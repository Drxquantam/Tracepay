// All the user's disputes. Each one opened by itself when a payment missed its deadline.

import { ArrowRight, Scale } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, cn, EmptyState, Skeleton } from "../components/ui";
import { formatDateTime, formatINR } from "../lib/format";
import type { Dispute } from "../lib/types";
import { useApi } from "../lib/useApi";

export default function Disputes() {
  const { data, loading } = useApi<Dispute[]>("/disputes", 10000);
  const owed = (data ?? []).reduce((sum, d) => sum + d.compensation_owed_paise, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Disputes</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          If money leaves your account but doesn't arrive or come back in time, TracePay opens a dispute for you automatically and works out what your bank owes.
        </p>
      </div>

      {data && data.length > 0 && (
        <Card glow className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-sm text-muted">Total compensation owed</p>
            <p className="money text-gradient text-4xl font-semibold">{formatINR(owed)}</p>
          </div>
          <p className="max-w-sm text-sm text-muted">Owed by the banks involved, not by the shops or people you paid.</p>
        </Card>
      )}

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : !data || data.length === 0 ? (
        <Card>
          <EmptyState icon={<Scale className="h-5 w-5" />} title="No disputes">
            Nothing is late. If a payment gets stuck past its deadline, it'll appear here.
          </EmptyState>
        </Card>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.map((d) => (
            <li key={d.id}>
              <Link to={`/payments/${d.payment_id}`}>
                <Card className="h-full transition hover:shadow-glow">
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-semibold">{d.headline}</p>
                    <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold", d.status === "open" ? "bg-bad/15 text-bad" : "bg-ok/15 text-ok")}>
                      {d.status === "open" ? "Open" : "Resolved"}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted">
                    {formatINR(d.amount_paise)} to {d.payee_name} · opened {formatDateTime(d.opened_at)}
                  </p>
                  <div className="mt-4 flex items-center justify-between text-sm">
                    <span>
                      Owed by <span className="font-semibold">{d.owed_by_bank}</span>
                    </span>
                    <ArrowRight className="h-4 w-4 text-muted" aria-hidden />
                  </div>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
