import { createContext, useCallback, useContext, useRef, useState, type ReactNode, type ButtonHTMLAttributes } from "react";

const SEV: Record<string, string> = {
  High: "bg-hib text-hi", Medium: "bg-mdb text-md", Low: "bg-lob text-lo", "Cannot verify": "bg-cvb text-cv",
};
export const sevBorder: Record<string, string> = { High: "border-l-hi", Medium: "border-l-md", Low: "border-l-lo", "Cannot verify": "border-l-cv" };
export const sevMark: Record<string, string> = {
  High: "bg-hib border-b-2 border-hi", Medium: "bg-mdb border-b-2 border-md", Low: "bg-lob border-b-2 border-lo", "Cannot verify": "bg-cvb border-b-2 border-cv",
};

export const Tag = ({ children, sev, title }: { children: ReactNode; sev?: string; title?: string }) => (
  <span title={title} className={`text-xs rounded px-2 py-px border ${sev ? SEV[sev] + " border-transparent" : "border-ln"}`}>{children}</span>
);

const PILL: Record<string, string> = { draft: "bg-acb text-ac", changes_requested: "bg-hib text-hi", pending_reviewer: "bg-mdb text-md", pending_manager: "bg-mdb text-md", approved: "bg-okb text-ok", published: "bg-okb text-ok" };
export const StatusPill = ({ status, label }: { status: string; label: string }) => (
  <span className={`inline-block rounded-full px-3 py-0.5 font-semibold text-sm ${PILL[status] || "bg-acb text-ac"}`}>{label}</span>
);

type BP = ButtonHTMLAttributes<HTMLButtonElement> & { v?: "p" | "g" | "s" | "r" };
export const Btn = ({ v = "p", className = "", ...p }: BP) => {
  const c = { p: "bg-ink text-bg", g: "bg-ac text-white", s: "bg-transparent text-ink border border-ln", r: "bg-hi text-white" }[v];
  return <button {...p} className={`${c} rounded-md px-3.5 py-2 font-semibold cursor-pointer disabled:opacity-45 disabled:cursor-not-allowed ${className}`} />;
};

export const Pane = ({ children, className = "" }: { children: ReactNode; className?: string }) => (
  <section className={`bg-sf border border-ln rounded-lg p-4 ${className}`}>{children}</section>
);
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`w-full bg-bg border border-ln rounded-md px-2.5 py-1.5 ${p.className || ""}`} />;
export const Area = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={`w-full bg-bg border border-ln rounded-md px-2.5 py-1.5 ${p.className || ""}`} />;
export const Muted = ({ children, className = "" }: { children: ReactNode; className?: string }) => <p className={`text-mut my-1.5 ${className}`}>{children}</p>;

type Toast = (m: string, err?: boolean) => void;
const ToastCtx = createContext<Toast>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastHost({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<{ m: string; err: boolean } | null>(null);
  const h = useRef<number>(0);
  const toast = useCallback<Toast>((m, err = false) => {
    setMsg({ m, err });
    window.clearTimeout(h.current);
    h.current = window.setTimeout(() => setMsg(null), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div role="status" aria-live="polite" className="fixed left-1/2 -translate-x-1/2 bottom-5 z-50">
        {msg && <div className={`px-4 py-2 rounded-md shadow-lg ${msg.err ? "bg-hi text-white" : "bg-ink text-bg"}`}>{msg.m}</div>}
      </div>
    </ToastCtx.Provider>
  );
}

export const when = (s: string) => new Date(s.includes("Z") || s.includes("+") ? s : s.replace(" ", "T") + "Z").toLocaleString();
export const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");
