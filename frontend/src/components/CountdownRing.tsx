// Countdown ring: how much of the turnaround window is left before the bank owes
// compensation. Ticks every second between server polls.
//
// The server sends seconds_to_deadline in *simulated* time. Simulated time runs at the
// same speed as real time (only admin jumps change it), so counting down locally from the
// last answer is accurate, and the next poll corrects any jump.

import { CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { formatDuration } from "../lib/format";

type Props = {
  secondsToDeadline: number | null; // null once resolved
  windowSeconds: number; // from payment time to deadline
  fetchedAt: number; // Date.now() when secondsToDeadline arrived
  breached: boolean;
  daysLate: number;
};

const SIZE = 132;
const STROKE = 10;
const R = (SIZE - STROKE) / 2;
const CIRC = 2 * Math.PI * R;

export function CountdownRing({ secondsToDeadline, windowSeconds, fetchedAt, breached, daysLate }: Props) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const resolved = secondsToDeadline === null;
  const left = resolved ? 0 : secondsToDeadline - (now - fetchedAt) / 1000;
  const late = breached || left <= 0;
  const fraction = resolved ? 1 : late ? 1 : Math.max(0, Math.min(1, left / windowSeconds));
  const color = resolved ? (breached ? "rgb(var(--warn))" : "rgb(var(--ok))") : late ? "rgb(var(--bad))" : fraction < 0.25 ? "rgb(var(--warn))" : "rgb(var(--teal))";

  let big: string;
  let small: string;
  if (resolved) {
    big = breached ? `${daysLate}d late` : "On time";
    small = "resolved";
  } else if (late) {
    big = `${Math.max(daysLate, 1)} ${Math.max(daysLate, 1) === 1 ? "day" : "days"}`;
    small = "late";
  } else {
    big = formatDuration(left);
    small = "left";
  }

  return (
    <div className="relative grid place-items-center" style={{ width: SIZE, height: SIZE }} role="timer" aria-label={`${big} ${small}`}>
      <svg width={SIZE} height={SIZE} className="-rotate-90">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="rgb(var(--line) / 0.1)" strokeWidth={STROKE} />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={R}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={CIRC * (1 - fraction)}
          style={{ transition: "stroke-dashoffset 1s linear, stroke 0.5s", filter: `drop-shadow(0 0 6px ${color})` }}
        />
      </svg>
      <div className="absolute text-center">
        {resolved && !breached ? <CheckCircle2 className="mx-auto mb-1 h-5 w-5 text-ok" aria-hidden /> : null}
        <p className="money text-xl font-extrabold leading-none">{big}</p>
        <p className="mt-1 text-xs text-muted">{small}</p>
      </div>
    </div>
  );
}
