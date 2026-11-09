// Phase 1 placeholder: proves the web container can reach the API.
// The real design system and screens arrive in Phase 4.
import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [status, setStatus] = useState("checking…");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((d) => setStatus(d.status === "ok" ? "API is up" : "API returned an error"))
      .catch(() => setStatus("API unreachable"));
  }, []);

  return (
    <main style={{ padding: 24, maxWidth: 480, margin: "0 auto" }}>
      <p
        style={{
          display: "inline-block", padding: "4px 10px", borderRadius: 999,
          background: "#f59e0b22", color: "#fbbf24", fontSize: 12, fontWeight: 600,
        }}
      >
        Simulation only: no real money
      </p>
      <h1>TracePay</h1>
      <p>See what happens to your money after something goes wrong.</p>
      <p>Backend status: {status}</p>
    </main>
  );
}
