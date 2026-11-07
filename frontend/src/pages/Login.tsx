import { useEffect, useState, type FormEvent } from "react";
import { api, setToken } from "../api";
import type { User } from "../types";
import { Btn, Input, Muted, Pane, errMsg } from "../ui";

const DEMO_EMAIL = "aria@lumora.demo";
const DEMO_PASSWORD = "demo123";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [name, setName] = useState("");
  const [team, setTeam] = useState("Marketing");
  const [err, setErr] = useState("");
  const [accounts, setAccounts] = useState<User[]>([]);
  useEffect(() => { api.demoUsers().then(setAccounts).catch(() => setAccounts([])); }, []);
  const go = async (e: string, p: string) => {
    setErr("");
    try { const r = await api.login(e, p); setToken(r.token); onLogin(r.user); } catch (x) { setErr(errMsg(x)); }
  };
  const createAccount = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      const r = await api.signup({ name, email, team, password: pw });
      setToken(r.token);
      onLogin(r.user);
    } catch (x) { setErr(errMsg(x)); }
  };
  const continueAs = (account: User) => {
    const password = account.password || DEMO_PASSWORD;
    setEmail(account.email);
    setPw(password);
    void go(account.email, password);
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
        <h2 className="text-xl mb-2">{mode === "signin" ? "Sign in" : "Create your account"}</h2>
        <Muted>{mode === "signin" ? "Sign in with your workspace account, or choose a Lumora account below to explore a role." : "Create a Lumora Creator account. Your account will be ready to use right away."}</Muted>
        {mode === "signup" && <form onSubmit={createAccount} className="grid gap-3 mt-4">
          <label className="grid gap-1">
            <span>Full name</span>
            <Input value={name} onChange={e => setName(e.target.value)} autoComplete="name" placeholder="Your name" minLength={2} maxLength={120} required />
          </label>
          <label className="grid gap-1">
            <span>Email address</span>
            <Input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com" required />
          </label>
          <label className="grid gap-1">
            <span>Team</span>
            <Input value={team} onChange={e => setTeam(e.target.value)} maxLength={80} placeholder="Marketing" />
          </label>
          <label className="grid gap-1">
            <span>Password</span>
            <Input type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="new-password" minLength={10} maxLength={72} placeholder="At least 10 characters" required />
            <span className="text-xs text-mut">Use at least 10 characters and no more than 72 UTF-8 bytes.</span>
          </label>
          {err && <p role="alert" className="text-hi">{err}</p>}
          <Btn v="g" type="submit">Create account</Btn>
        </form>}
        {mode === "signin" && <form onSubmit={e => { e.preventDefault(); go(email, pw); }} className="grid gap-3">
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
        </form>}
        <p className="mt-4 text-sm text-mut">
          {mode === "signin" ? "New to Lumora? " : "Already have an account? "}
          <button type="button" className="text-ac underline cursor-pointer" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setErr(""); }}>
            {mode === "signin" ? "Create account" : "Sign in"}
          </button>
        </p>
      </Pane>
      <Pane className="login-card mt-4">
        <h2 className="text-xl mb-1">Explore Lumora</h2>
        <Muted>Choose a name to open the workspace with that role’s view and permissions.</Muted>
        <div className="grid gap-2 mt-3 sm:grid-cols-2">
          {(accounts.length ? accounts : [{ id: 0, name: "Aria Menon", email: DEMO_EMAIL, role: "Creator" as const, team: "Marketing", tenant: "lumora", password: DEMO_PASSWORD }]).map(account => (
            <button key={account.id} type="button" onClick={() => continueAs(account)}
              className="w-full text-left border border-ln rounded-xl px-3 py-3 cursor-pointer hover:border-ac hover:bg-acb">
              <b className="block">{account.name}</b>
              <span className="text-mut text-sm">{account.role} · {account.team}</span>
            </button>
          ))}
        </div>
      </Pane>
      <p className="text-center text-xs text-mut mt-5">No source, no finding.</p>
      </div>
    </main>
  );
}
