"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try { await authApi.login(password); router.replace("/cases"); }
    catch (err) { setError(err instanceof Error ? err.message : "Sign in failed"); }
    finally { setBusy(false); }
  }
  return <main style={{maxWidth: 420, margin: "12vh auto", padding: 24}}>
    <h1>Open Blackbox</h1>
    <p>Enter the private case workspace password.</p>
    <form onSubmit={submit}>
      <label htmlFor="password">Access password</label>
      <input id="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required style={{display: "block", width: "100%", margin: "12px 0", padding: 12}} />
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy} className="btn btn-primary">{busy ? "Opening…" : "Open workspace"}</button>
    </form>
  </main>;
}
