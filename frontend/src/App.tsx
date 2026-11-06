import { useCallback, useEffect, useState } from "react";
import { api, hasToken, setToken, setUnauthorisedHandler } from "./api";
import type { Doc, DocSummary, User } from "./types";
import { ToastHost, errMsg, useToast } from "./ui";
import Login from "./pages/Login";
import Documents from "./pages/Documents";
import Review from "./pages/Review";
import Workflow from "./pages/Workflow";
import Audit from "./pages/Audit";
import Kit from "./pages/Kit";
import Insights from "./pages/Insights";

export interface Ctx {
  user: User; doc: Doc | null; setDoc: (d: Doc | null) => void; open: (id: number, tab?: string) => Promise<void>;
  docs: DocSummary[]; reload: () => Promise<void>; go: (t: string) => void;
}

const TABS: [string, string, string[] | null][] = [
  ["docs", "Documents", null], ["review", "Review", null], ["flow", "Approval and history", null],
  ["audit", "Audit log", ["Brand Manager", "Brand Admin"]], ["kit", "Brand kit", null], ["ins", "Insights", ["Brand Manager", "Brand Admin"]],
];

function Shell() {
  const toast = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(hasToken());
  const [tab, setTab] = useState("docs");
  const [doc, setDoc] = useState<Doc | null>(null);
  const [docs, setDocs] = useState<DocSummary[]>([]);

  const logout = useCallback(() => { setToken(""); setUser(null); setDoc(null); setDocs([]); setTab("docs"); }, []);
  useEffect(() => { setUnauthorisedHandler(logout); }, [logout]);
  useEffect(() => {
    if (hasToken()) api.me().then(setUser).catch(() => setToken("")).finally(() => setBooting(false));
  }, []);

  const reload = useCallback(async () => { try { setDocs(await api.docs()); } catch (e) { toast(errMsg(e), true); } }, [toast]);
  useEffect(() => { if (user) reload(); }, [user, reload]);

  const open = useCallback(async (id: number, t = "review") => {
    try { setDoc(await api.doc(id)); setTab(t); } catch (e) { toast(errMsg(e), true); }
  }, [toast]);

  if (booting) return <p className="p-6 text-mut">Loading…</p>;
  if (!user) return <Login onLogin={u => { setUser(u); setTab("docs"); }} />;

  const ctx: Ctx = { user, doc, setDoc, open, docs, reload, go: setTab };
  const tabs = TABS.filter(t => !t[2] || t[2].includes(user.role));
  const page = { docs: <Documents ctx={ctx} />, review: <Review ctx={ctx} />, flow: <Workflow ctx={ctx} />, audit: <Audit ctx={ctx} />, kit: <Kit ctx={ctx} />, ins: <Insights ctx={ctx} /> }[tab];

  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-sf focus:p-2">Skip to content</a>
      <header className="brand-header flex flex-wrap gap-3 items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="brand-mark" aria-hidden="true">B</span>
          <div>
            <h1 className="text-[26px] font-bold">BrandSentinel</h1>
            <small className="block text-mut text-xs">Evidence-led brand review · Lumora Wellness</small>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span><b>{user.name}</b> <span className="text-mut">· {user.role}</span></span>
          <button onClick={logout} className="border border-ln rounded-md px-3 py-1.5 cursor-pointer">Sign out</button>
        </div>
      </header>
      <nav role="tablist" aria-label="Sections" className="app-nav flex gap-1 px-5 overflow-x-auto">
        {tabs.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`px-3 py-2.5 whitespace-nowrap cursor-pointer ${tab === k ? "font-semibold text-ink" : "text-mut"}`}>{l}</button>
        ))}
      </nav>
      <main id="main" className="app-main max-w-[1280px] mx-auto px-5 pt-6 pb-16">{page}</main>
    </>
  );
}

export default function App() { return <ToastHost><Shell /></ToastHost>; }
