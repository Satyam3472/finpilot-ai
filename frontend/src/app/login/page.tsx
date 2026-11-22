"use client";

import { Activity, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorState } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { api, jsonBody } from "@/lib/api";

export default function Login() {
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await api("/auth/login", { method: "POST", ...jsonBody({ password }) });
      window.location.replace("/dashboard");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Sign-in failed.");
      setPending(false);
    }
  }

  return <main className="login-page">
    <section className="panel login-card">
      <div className="login-brand"><span className="brand-mark"><Activity size={21} /></span><strong>FinPilot AI</strong></div>
      <h1>Sign in to FinPilot</h1>
      <p>Use the password set up for this local finance workspace.</p>
      <form onSubmit={submit}>
        <label className="field">Password<input className="control" autoComplete="current-password"
          type="password" required maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error && <ErrorState message={error} />}
        <Button type="submit" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
      </form>
      <div className="login-footer"><ShieldCheck size={16} /> Local workspace</div>
    </section>
  </main>;
}
