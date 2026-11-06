import { useEffect, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import type { KitRec } from "../types";
import { Area, Btn, Input, Muted, Pane, Tag, errMsg, useToast } from "../ui";

const KINDS: [string, string][] = [["glossary", "Glossary"], ["fact", "Fact records"], ["voice", "Voice"], ["claims", "Claims policy"],
  ["evidence", "Evidence on file"], ["sensitive", "Sensitive terms"], ["visual", "Visual identity"]];
const list = (s: string) => s.split(",").map(x => x.trim()).filter(Boolean);
const j = (a?: string[]) => (a || []).join(", ");

type F = Record<string, string>;
function toForm(kind: string, r?: KitRec): F {
  const d = r?.data || {}, c = d.check || {};
  return { text: d.text || "", bad: d.bad || "", good: d.good || "", valid_to: r?.valid_to || "", triggers: j(d.triggers), ctype: c.type || "", cnoun: c.canonical || "members",
    cval: c.value !== undefined ? String(c.value) : "", canchor: c.anchor || "", ccur: c.currency || "₹", banned: j(d.banned), allow: j(d.allow_caps), phrases: j(d.phrases),
    claim: d.claim || "", source: d.source || "", terms: j(d.terms), patterns: j(d.entity_patterns), palette: j(d.palette),
    contrast: String(d.min_contrast ?? 4.5), clear: String(d.min_clearspace_pct ?? 5), tol: String(d.tolerance ?? 60) };
}
function toData(kind: string, f: F): Record<string, any> {
  switch (kind) {
    case "glossary": return { bad: f.bad, good: f.good };
    case "fact": return { text: f.text, triggers: list(f.triggers), check: f.ctype === "count" ? { type: "count", nouns: ["members", "customers", "clients", "users"], canonical: f.cnoun, value: +f.cval }
      : f.ctype === "price" ? { type: "price", anchor: f.canchor, currency: f.ccur, value: +f.cval } : null };
    case "voice": return { text: f.text, banned: list(f.banned), allow_caps: list(f.allow) };
    case "claims": return { text: f.text, phrases: list(f.phrases) };
    case "evidence": return { claim: f.claim, phrases: [f.claim], source: f.source };
    case "sensitive": return { text: f.text, terms: list(f.terms), entity_patterns: list(f.patterns) };
    default: return { text: f.text, palette: list(f.palette), min_contrast: +f.contrast, min_clearspace_pct: +f.clear, tolerance: +f.tol };
  }
}

export default function Kit({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const admin = ctx.user.role === "Brand Admin";
  const [kit, setKit] = useState<{ records: KitRec[]; system: { rid: string; text: string }[] } | null>(null);
  const [edit, setEdit] = useState<{ kind: string; rid?: string; f: F } | null>(null);
  const [hist, setHist] = useState<KitRec[] | null>(null);
  const [imp, setImp] = useState("");
  const [impFile, setImpFile] = useState<File | null>(null);
  const [prev, setPrev] = useState<{ records: any[]; warnings: string[]; committed?: number } | null>(null);
  const [disc, setDisc] = useState<{ text: string; storage: string } | null>(null);
  const load = () => api.kit().then(setKit).catch(e => toast(errMsg(e), true));
  useEffect(() => { load(); api.disclosure().then(setDisc).catch(() => {}); }, []);  // eslint-disable-line

  const save = async () => {
    if (!edit) return;
    try { await api.kitSave({ kind: edit.kind, rid: edit.rid, data: toData(edit.kind, edit.f), valid_to: edit.f.valid_to || null }); setEdit(null); await load(); toast("Saved as a new version."); }
    catch (e) { toast(errMsg(e), true); }
  };
  const doImport = async (commit: boolean) => {
    try {
      const r = impFile ? await api.kitImportFile(impFile, commit) : await api.kitImport(imp, "kit.txt", commit);
      setPrev(r);
      if (commit) { toast(`${r.committed} records imported.`); await load(); }
    } catch (e) { toast(errMsg(e), true); }
  };
  if (!kit) return <Muted>Loading…</Muted>;
  const setF = (k: string, v: string) => edit && setEdit({ ...edit, f: { ...edit.f, [k]: v } });
  const L = ({ k, label, ph }: { k: string; label: string; ph?: string }) => <label className="block">{label}<Input value={edit!.f[k] ?? ""} placeholder={ph} onChange={e => setF(k, e.target.value)} /></label>;

  return (
    <div className="grid gap-4">
      <Pane>
        <h2 className="text-[22px]">Brand kit: Lumora Wellness</h2>
        <Muted>The approved sources every finding cites. {admin ? "Saving a change creates a new version; older versions stay in the history." : "Only a Brand Admin can change these. Sensitive terms are hidden for your role."}</Muted>
        {KINDS.map(([kind, label]) => {
          const rows = kit.records.filter(r => r.kind === kind);
          return (
            <div key={kind} className="mt-4">
              <div className="flex items-center gap-2"><h3 className="text-[17px] mr-auto">{label}</h3>
                {admin && (rows.length === 0 || ["glossary", "fact", "evidence"].includes(kind)) && <Btn v="s" className="!py-1" onClick={() => setEdit({ kind, f: toForm(kind) })}>Add</Btn>}</div>
              <div className="overflow-x-auto"><table><thead><tr><th>ID</th><th>Content</th><th>Valid to</th><th>Version</th>{admin && <th><span className="sr-only">Actions</span></th>}</tr></thead>
                <tbody>{rows.map(r => <tr key={r.rid}><td className="font-semibold whitespace-nowrap">{r.rid}</td><td className="break-words">{r.text}
                  {admin && r.kind === "sensitive" && <div className="text-sm text-mut">{[...(r.data.terms || []), ...(r.data.entity_patterns || [])].join(", ")}</div>}</td>
                  <td>{r.valid_to || ""}</td><td>v{r.version}</td>
                  {admin && <td className="whitespace-nowrap"><Btn v="s" className="!py-0.5 mr-1" onClick={() => setEdit({ kind, rid: r.rid, f: toForm(kind, r) })}>Edit</Btn>
                    <Btn v="s" className="!py-0.5 mr-1" onClick={() => api.kitHistory(r.rid).then(setHist)}>History</Btn>
                    {["glossary", "fact", "evidence"].includes(kind) && <Btn v="s" className="!py-0.5" onClick={async () => { await api.kitRetire(r.rid); await load(); toast(`${r.rid} retired.`); }}>Retire</Btn>}</td>}</tr>)}
                  {!rows.length && <tr><td colSpan={5} className="text-mut">None yet.</td></tr>}</tbody></table></div>
            </div>
          );
        })}
        <h3 className="text-[17px] mt-4">Built-in accessibility sources</h3>
        <table><tbody>{kit.system.map(s => <tr key={s.rid}><td className="font-semibold whitespace-nowrap">{s.rid}</td><td>{s.text}</td></tr>)}</tbody></table>
      </Pane>

      {edit && admin && (
        <Pane>
          <h2 className="text-[22px] mb-2">{edit.rid ? `Edit ${edit.rid}` : `Add ${edit.kind} record`}</h2>
          <div className="grid gap-2 max-w-2xl">
            {edit.kind === "glossary" && <><L k="bad" label="Avoid this word" /><L k="good" label="Use this instead" /></>}
            {edit.kind === "fact" && <><L k="text" label="Fact" /><L k="valid_to" label="Valid to (YYYY-MM-DD)" /><L k="triggers" label="Mentions that this fact retires (comma separated)" ph="Starter plan" />
              <label className="block">Automatic check<select value={edit.f.ctype} onChange={e => setF("ctype", e.target.value)} className="w-full bg-bg border border-ln rounded-md px-2 py-1.5">
                <option value="">None</option><option value="count">Count of members</option><option value="price">Price of a plan</option></select></label>
              {edit.f.ctype === "count" && <><L k="cnoun" label="Noun in the suggested fix" /><L k="cval" label="Correct number" /></>}
              {edit.f.ctype === "price" && <><L k="canchor" label="Appears after this text" ph="Pro plan" /><L k="ccur" label="Currency" /><L k="cval" label="Correct amount" /></>}</>}
            {edit.kind === "voice" && <><L k="text" label="Voice clause" /><L k="banned" label="Phrases to flag (comma separated)" /><L k="allow" label="All-caps words that are fine" /></>}
            {edit.kind === "claims" && <><L k="text" label="Policy text" /><L k="phrases" label="Claim phrases that need evidence (comma separated)" /></>}
            {edit.kind === "evidence" && <><L k="claim" label="Claim this supports (exact wording)" /><L k="source" label="Where the evidence lives" /><L k="valid_to" label="Valid to (optional)" /></>}
            {edit.kind === "sensitive" && <><L k="terms" label="Sensitive terms (comma separated)" /><L k="patterns" label="Entity patterns (regular expressions, comma separated)" /></>}
            {edit.kind === "visual" && <><L k="palette" label="Approved colours (hex, comma separated)" /><L k="tol" label="Colour tolerance" /><L k="contrast" label="Minimum contrast ratio" /><L k="clear" label="Minimum clearspace (%)" /></>}
          </div>
          <div className="flex gap-2 mt-3"><Btn v="g" onClick={save}>Save new version</Btn><Btn v="s" onClick={() => setEdit(null)}>Cancel</Btn></div>
        </Pane>
      )}
      {hist && (
        <Pane><div className="flex items-center"><h2 className="text-[22px] mr-auto">History of {hist[0]?.rid}</h2><Btn v="s" onClick={() => setHist(null)}>Close</Btn></div>
          <table><tbody>{hist.map(h => <tr key={h.version}><td>v{h.version} {h.active && <Tag sev="Low">current</Tag>}</td><td>{h.text}</td><td className="text-mut">{h.created_by}, {h.created_at}</td></tr>)}</tbody></table></Pane>
      )}

      {admin && (
        <Pane>
          <h2 className="text-[22px]">Import brand kit</h2>
          <Muted>Paste text or upload a .txt, .md, .json, .csv, .docx or .pdf. Headings such as Glossary, Facts, Voice, Claims, Evidence, Confidential and Palette are recognised. Nothing is saved until you confirm the preview.</Muted>
          <Area rows={7} className="mono" aria-label="Brand kit text" value={imp} onChange={e => { setImp(e.target.value); setPrev(null); }}
            placeholder={"Glossary\n- avoid 'prospects' => use 'guests'\n\nFacts\n- F-130: Lumora has 3 studios | valid_to=2027-01-01 | triggers=two studios\n\nConfidential\nProject Nimbus, Q1 pricing review"} />
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <input type="file" aria-label="Brand kit file" accept=".txt,.md,.json,.csv,.docx,.pdf" onChange={e => { setImpFile(e.target.files?.[0] || null); setPrev(null); }} />
            <Btn v="s" disabled={!imp.trim() && !impFile} onClick={() => doImport(false)}>Preview</Btn>
            <Btn v="g" disabled={!prev || !prev.records.length || prev.committed !== undefined} onClick={() => doImport(true)}>Import {prev ? prev.records.length : 0} records</Btn>
          </div>
          {prev && <div className="mt-3"><p><b>{prev.records.length}</b> record(s) parsed.</p>
            <ul className="list-disc pl-5 text-sm">{prev.records.map((r, i) => <li key={i}><b>{r.kind}</b>: {JSON.stringify(r.data)}{r.valid_to ? ` (valid to ${r.valid_to})` : ""}</li>)}</ul>
            {prev.warnings.map(w => <p key={w} className="text-md text-sm">{w}</p>)}</div>}
        </Pane>
      )}
      {disc && <Pane><h2 className="text-[22px]">AI and data disclosure</h2><p>{disc.text}</p><p className="mt-2">{disc.storage}</p></Pane>}
    </div>
  );
}
