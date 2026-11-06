import { useEffect, useState } from "react";
import { api, setToken } from "../api";
import type { User } from "../types";
import { Btn, Input, Muted, Pane, errMsg } from "../ui";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [demo, setDemo] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api.demoUsers().then(setDemo).catch(() => {}); }, []);
  const go = async (e: string, p: string) => {
    setErr("");
    try { const r = await api.login(e, p); setToken(r.token); onLogin(r.user); } catch (x) { setErr(errMsg(x)); }
  };
  return (
    <main className="max-w-md mx-auto px-5 py-16">
      <h1 className="text-4xl font-bold">BrandSentinel</h1>
      <Muted>Pre-publication brand governance. Every finding cites an approved source; humans make every decision.</Muted>
      <Pane className="mt-6">
        <h2 className="text-xl mb-2">Sign in</h2>
        <form onSubmit={e => { e.preventDefault(); go(email, pw); }} className="grid gap-3">
          <label>Email<Input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" required /></label>
          <label>Password<Input type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="current-password" required /></label>
          {err && <p role="alert" className="text-hi">{err}</p>}
          <Btn v="g" type="submit">Sign in</Btn>
        </form>
      </Pane>
      {demo.length > 0 && (
        <Pane className="mt-4">
          <h2 className="text-xl mb-1">Demo workspace</h2>
          <Muted>Try each role. Aria drafts, Leela is the Authorised Reviewer, Meera approves, Ishaan manages the brand kit.</Muted>
          <div className="grid gap-2 mt-2">
            {demo.map(u => (
              <button key={u.id} onClick={() => go(u.email, u.password || "")} className="text-left border border-ln rounded-md px-3 py-2 cursor-pointer">
                <b>{u.name}</b> <span className="text-mut">· {u.role} · {u.team}</span>
              </button>
            ))}
          </div>
        </Pane>
      )}
    </main>
  );
}
