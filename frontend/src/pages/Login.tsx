import { useState } from "react";
import { api, setToken } from "../api";
import type { User } from "../types";
import { Btn, Input, Muted, Pane, errMsg } from "../ui";

const DEMO_EMAIL = "aria@lumora.demo";
const DEMO_PASSWORD = "demo123";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const go = async (e: string, p: string) => {
    setErr("");
    try { const r = await api.login(e, p); setToken(r.token); onLogin(r.user); } catch (x) { setErr(errMsg(x)); }
  };
  return (
    <main className="login-shell max-w-lg mx-auto px-5">
      <div className="w-full">
      <div className="login-brand">
        <span className="brand-mark" aria-hidden="true">B</span>
        <div><h1 className="text-4xl font-bold">BrandSentinel</h1><span className="text-xs text-mut">LUMORA WELLNESS · BRAND REVIEW</span></div>
      </div>
      <Muted className="mt-3">Pre-publication brand governance. Every finding cites an approved source; people make every decision.</Muted>
      <Pane className="login-card mt-6">
        <h2 className="text-xl mb-2">Sign in</h2>
        <Muted>Sign in with your workspace account, or continue with Aria to explore the Lumora workspace.</Muted>
        <form onSubmit={e => { e.preventDefault(); go(email, pw); }} className="grid gap-3">
          <label className="grid gap-1">
            <span>Email address</span>
            <Input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" placeholder="name@company.com" required />
            <span className="text-xs text-mut">Use the email registered to your workspace.</span>
          </label>
          <label className="grid gap-1">
            <span>Password</span>
            <Input type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="current-password" placeholder="Enter your account password" required />
            <span className="text-xs text-mut">Use the password associated with that account.</span>
          </label>
          {err && <p role="alert" className="text-hi">{err}</p>}
          <Btn v="g" type="submit">Sign in</Btn>
        </form>
      </Pane>
      <Pane className="login-card mt-4">
        <h2 className="text-xl mb-1">Explore Lumora</h2>
        <Muted>Continue with Aria’s Creator account to open a workspace with prepared drafts, brand guidance, and approval history.</Muted>
        <button
          type="button"
          onClick={() => {
            setEmail(DEMO_EMAIL);
            setPw(DEMO_PASSWORD);
            void go(DEMO_EMAIL, DEMO_PASSWORD);
          }}
          className="w-full mt-3 text-left border border-ln rounded-md px-3 py-2 cursor-pointer"
        >
          <b>Continue as Aria</b> <span className="text-mut">· Creator workspace</span>
        </button>
      </Pane>
      <p className="text-center text-xs text-mut mt-5">No source, no finding.</p>
      </div>
    </main>
  );
}
