// k6 load test for POST /payments. SIMULATION ONLY (fake money, local stack).
//
//   make loadtest
//   # or: docker run --rm -i --network tracepay_default -e BASE_URL=http://api:8000 \
//   #       grafana/k6:0.57.0 run - < loadtest/pay.js
//
// Three demo users pay each other ₹0.01 in a ring (Aarav→Ravi, Ravi→Shanti, Shanti→Aarav),
// so balances barely move and nobody runs out of money. Every payment also touches the
// shared settlement suspense row, so this measures the platform's real bottleneck.
// 1 in 10 iterations replays its previous request with the same Idempotency-Key and
// checks the server returns the saved answer instead of charging again.

import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const replays = new Counter("idempotent_replays_ok");

export const options = {
  scenarios: {
    pay: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "15s", target: 20 },
        { duration: "30s", target: 20 },
        { duration: "5s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"], // fewer than 1% errors
    // 20 virtual users share only 3 paying accounts, and payments from one account must
    // run one at a time (that row lock is what prevents overdrafts), so some queueing is
    // expected by design. Target: p95 under 2 s on a laptop.
    "http_req_duration{name:pay}": ["p(95)<2000"],
    checks: ["rate>0.99"],
  },
};

const RING = [
  ["aarav", "ravistore@suraksha"],
  ["ravi", "shanti@suraksha"],
  ["shanti", "aarav@swissbank"],
];

export function setup() {
  const tokens = {};
  for (const [user] of RING) {
    const res = http.post(`${BASE}/auth/login`, JSON.stringify({ username: user, password: "demo1234" }), {
      headers: { "Content-Type": "application/json" },
    });
    tokens[user] = res.json("access_token");
  }
  return tokens;
}

export default function (tokens) {
  const [user, payee] = RING[(__VU + __ITER) % RING.length];
  const key = `k6-${__VU}-${__ITER}-${Date.now()}`;
  const body = JSON.stringify({ payee_vpa: payee, amount_paise: 1, note: "k6 load test" });
  const params = {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokens[user]}`, "Idempotency-Key": key },
    tags: { name: "pay" },
  };

  const res = http.post(`${BASE}/payments`, body, params);
  check(res, {
    "201 created": (r) => r.status === 201,
    "accepted (debited)": (r) => r.json("state") === "bank_debited",
  });

  if (__ITER % 10 === 0) {
    const again = http.post(`${BASE}/payments`, body, { ...params, tags: { name: "replay" } });
    const ok = check(again, {
      "replay returns same payment": (r) => r.json("id") === res.json("id"),
      "replay flagged": (r) => r.headers["Idempotent-Replayed"] === "true",
    });
    if (ok) replays.add(1);
  }
}
