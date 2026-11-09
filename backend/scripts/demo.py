"""Play the Money in Flight demo story from a terminal and narrate it. SIMULATION ONLY.

    make demo
    # or: docker compose exec api python scripts/demo.py
    # or, from your machine:  python backend/scripts/demo.py --api http://localhost:8000

Uses only the Python standard library, so it runs anywhere Python 3.10+ does.
"""

import argparse
import json
import sys
import time
import urllib.request

PASSWORD = "demo1234"  # seeded demo users only; see README


def call(api: str, method: str, path: str, token: str | None = None, body: dict | None = None):
    req = urllib.request.Request(
        api + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def login(api: str, user: str) -> str:
    return call(api, "POST", "/auth/login", body={"username": user, "password": PASSWORD})[
        "access_token"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--web", default="http://localhost:5173")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # ₹ on Windows consoles

    admin, aarav = login(args.api, "admin"), login(args.api, "aarav")
    print("TracePay demo (simulation only)\n")
    print("1. Aarav pays Ravi General Store ₹450. Ravi's bank is slow to answer...")
    payment_id = call(args.api, "POST", "/admin/demo", admin)["payment_id"]
    print(f"   Watch it live: {args.web}/payments/{payment_id}  (log in as aarav)\n")

    last = None
    deadline = time.time() + 60
    while time.time() < deadline:
        t = call(args.api, "GET", f"/payments/{payment_id}/tracker", aarav)
        snapshot = (t["payment"]["state"], t["health"], bool(t["dispute"]))
        if snapshot != last:
            last = snapshot
            print(f"   [{t['payment']['state']:>12} | {t['health']:<7}] {t['headline']}")
            if t["health"] == "delayed":
                print("   -> The demo killed Suraksha Bank mid-flight. The tracker shows it:")
                print(f"      {t['detail']}")
                print("   -> Jumping the simulated clock 8 days ahead, past the T+5 deadline...")
            if t["dispute"]:
                d = t["dispute"]
                print("\n2. No one clicked anything. The system opened a dispute by itself:")
                print(f"   {d['headline']}")
                print(f"   {d['who_owes']}")
                print(f"\nClaim summary: {args.api}/disputes/{d['id']}/claim")
                print("Reset afterwards from the admin panel (Chaos: reset; Time: reset).")
                return 0
        time.sleep(1)
    print("The story didn't finish in 60 s. Is the API running?")
    return 1


if __name__ == "__main__":
    sys.exit(main())
