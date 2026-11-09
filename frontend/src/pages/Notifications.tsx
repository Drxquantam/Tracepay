// Notification centre: every alert in plain language (approvals, holds, disputes, freezes,
// mandate pre-debit notices). Stands in for SMS in this simulation.

import { Bell, CheckCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Card, cn, EmptyState, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import type { Notification } from "../lib/types";
import { useApi } from "../lib/useApi";

export default function Notifications() {
  const { data, reload } = useApi<{ unread: number; items: Notification[] }>("/notifications", 10000);

  async function readAll() {
    await api("/notifications/read-all", { method: "POST" });
    reload();
  }
  async function read(n: Notification) {
    if (!n.read_at) await api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => {});
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight">Notifications</h1>
        {data && data.unread > 0 && (
          <Button variant="ghost" onClick={readAll}>
            <CheckCheck className="h-4 w-4" aria-hidden /> Mark all as read
          </Button>
        )}
      </div>
      <Card className="p-2 sm:p-2">
        {!data ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState icon={<Bell className="h-5 w-5" />} title="All quiet">
            Approvals, pre-debit notices and payment problems will show up here.
          </EmptyState>
        ) : (
          <ul>
            {data.items.map((n) => {
              const body = (
                <div className="flex gap-3 rounded-2xl p-3 transition hover:bg-line/5">
                  <span className={cn("mt-2 h-2.5 w-2.5 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-teal")} aria-label={n.read_at ? undefined : "Unread"} />
                  <span className="min-w-0">
                    <span className={cn("block", n.read_at ? "font-medium" : "font-bold")}>{n.title}</span>
                    <span className="block text-sm text-muted">{n.body}</span>
                    <span className="mt-1 block text-xs text-muted">{formatDateTime(n.created_at)}</span>
                  </span>
                </div>
              );
              return (
                <li key={n.id}>
                  {n.link ? (
                    <Link to={n.link} onClick={() => read(n)}>
                      {body}
                    </Link>
                  ) : (
                    body
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
