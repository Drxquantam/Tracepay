// Shapes returned by the API (mirrors backend/app/schemas.py). Money is integer paise.

export type Account = {
  id: number;
  vpa: string;
  display_name: string;
  kind: "user" | "merchant" | "system";
  bank_code: string;
  bank_name: string;
  balance_paise: number;
  is_frozen: boolean;
};

export type Me = {
  id: number;
  username: string;
  full_name: string;
  role: "customer" | "merchant" | "admin";
  senior_mode: boolean;
  accounts: Account[];
};

export type PaymentState =
  | "initiated"
  | "held"
  | "bank_debited"
  | "in_switch"
  | "credited"
  | "failed"
  | "reversal_pending"
  | "reversed";

export type Payment = {
  id: string;
  reference: string;
  payer_vpa: string;
  payer_name: string;
  payee_vpa: string;
  payee_name: string;
  amount_paise: number;
  state: PaymentState;
  failure_reason: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type PaymentEvent = {
  kind: "transition" | "note" | "dispute";
  from_state: PaymentState | null;
  to_state: PaymentState;
  reason: string | null;
  occurred_at: string;
};

export type PaymentDetail = Payment & { events: PaymentEvent[] };

export type DisputeStep = {
  step: "app" | "bank" | "ombudsman";
  title: string;
  description: string;
  completed_at: string | null;
  available_at: string | null;
};

export type Dispute = {
  id: number;
  status: "open" | "resolved";
  payment_id: string;
  payment_reference: string;
  amount_paise: number;
  payee_name: string;
  rule_code: string;
  tat_days: number;
  compensation_paise_per_day: number;
  deadline_at: string;
  opened_at: string;
  resolved_at: string | null;
  days_late: number;
  compensation_owed_paise: number;
  owed_by_bank: string;
  headline: string;
  who_owes: string;
  steps: DisputeStep[];
};

export type Position = "payer_bank" | "switch" | "payee_bank" | "returning";
export type Health = "ok" | "delayed" | "late" | "failed";

export type Tracker = {
  payment: PaymentDetail;
  stages: { key: string; label: string }[];
  position: Position;
  health: Health;
  headline: string;
  detail: string;
  rule: { code: string; title: string; tat_days: number; compensation_paise_per_day: number } | null;
  deadline_at: string | null;
  seconds_to_deadline: number | null;
  breached: boolean;
  days_late: number;
  dispute: Dispute | null;
  hold: { id: number; kind: "approval" | "cooling_off"; status: string; reasons: string; due_at: string; guardian_name: string | null } | null;
  sim_now: string;
};

export type Payee = { vpa: string; name: string; kind: "user" | "merchant"; bank_name: string };

export type Fault =
  | "slow_response"
  | "timeout"
  | "debited_not_credited"
  | "duplicate_callback"
  | "bank_down";

export type Person = { username: string; full_name: string };

export type GuardianOverview = {
  rules: {
    guardian: Person | null;
    threshold_paise: number | null;
    new_payee_approval: boolean;
    cooling_off_threshold_paise: number | null;
    cooling_off_minutes: number;
  };
  is_frozen: boolean;
  protecting: (Person & { is_frozen: boolean; pending_requests: number })[];
  candidates: Person[];
};

export type Hold = {
  id: number;
  payment_id: string;
  kind: "approval" | "cooling_off";
  status: string;
  reasons: string;
  created_at: string;
  due_at: string;
  payer_name: string;
  payee_name: string;
  amount_paise: number;
  guardian_name: string | null;
};

export type Holds = { to_decide: Hold[]; mine: Hold[] };

export type Notification = {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
};
