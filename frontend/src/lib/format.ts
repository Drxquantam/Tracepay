// Formatting for people. The API sends money as integer paise and times as ISO strings.

// en-IN gives Indian digit grouping (₹1,00,000) for free.
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2, minimumFractionDigits: 0 });
const inrExact = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

/** ₹1,234 (or ₹1,234.50 when there are paise). */
export function formatINR(paise: number): string {
  return paise % 100 === 0 ? inr.format(paise / 100) : inrExact.format(paise / 100);
}

/**
 * Parse what someone typed ("450", "450.5", "1,200.75") into paise, without floating-point
 * maths: the rupee and paise parts are handled as separate integers.
 * Returns null if it isn't a valid amount.
 */
export function rupeesToPaise(input: string): number | null {
  const cleaned = input.replace(/[,\s₹]/g, "");
  const match = /^(\d{1,7})(?:\.(\d{0,2}))?$/.exec(cleaned);
  if (!match) return null;
  const rupees = Number(match[1]);
  const paise = Number((match[2] ?? "").padEnd(2, "0"));
  const total = rupees * 100 + paise;
  return total > 0 ? total : null;
}

// Times are shown in India Standard Time, matching the T+1 / T+5 day rules.
const dateTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});
const dateOnly = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" });

export const formatDateTime = (iso: string) => dateTime.format(new Date(iso));
export const formatDate = (iso: string) => dateOnly.format(new Date(iso));

/** "1d 4h", "3h 12m", "45s": for the deadline countdown. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

export const STATE_LABEL: Record<string, string> = {
  initiated: "Started",
  held: "On hold",
  bank_debited: "Debited",
  in_switch: "In transit",
  credited: "Completed",
  failed: "Failed",
  reversal_pending: "Refund pending",
  reversed: "Refunded",
};
