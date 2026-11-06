import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import type { Doc, Finding } from "../types";
import { Area, Btn, Input, Muted, Pane, StatusPill, Tag, errMsg, sevBorder, sevMark, useToast } from "../ui";

export const SAMPLE = `Hi everyone! Our Customers LOVE Lumora!! Over 10,000 clients already trust us, and we’re the best in the industry. Our Starter plan is still the cheapest way to sign up, and the Spring Sale is on now. Pro plan is just ₹1,299 a month. Members see 40% better sleep. Obviously you’d be silly to miss it. Sneak peek: Project Aurora launches next quarter.

<img src="hero.png"> <a href="/join">click here</a>
Banner text: #9aa0a6 on #ffffff`;

const EXTRA_DEMO_DRAFTS = [
  { title: "Wellness week social caption", text: "Join Lumora for Wellness Week! We’re the best in the industry, and our classes guarantee a calmer you. Sign up today." },
  { title: "Pro plan price announcement", text: "A better routine starts here. The Pro plan is now only ₹1,299 per month. Join today for the same trusted Lumora experience." },
  { title: "Member welcome email", text: "Welcome to Lumora. Your membership is ready. Explore the class schedule, choose a session that suits you, and reach out if you need help getting started." },
  { title: "Sleep campaign claim check", text: "Our clinically proven program helps members get 40% better sleep in just seven days. Try it now for guaranteed results." },
  { title: "Social story call to action", text: "Ready to begin? <a href=\"/join\">Click here</a> to sign up for your first class. Our friendly instructors are ready to help." },
  { title: "Influencer wellness caption", text: "Obviously, you’d be silly to miss Lumora’s world-class sessions. Our teachers are the #1 choice for everyone who wants to feel amazing." },
  { title: "Partner introduction email", text: "Lumora is the only wellness app you need. Over 9,000 users trust us, and our method is guaranteed to work. We’d love to discuss a partnership." },
  { title: "Limited-time offer notification", text: "LAST CHANCE!!! Join now for the cheapest classes in town. This unbeatable offer guarantees you’ll feel better immediately." },
  { title: "Class booking FAQ", text: "How do I book a class? Open the schedule, choose a session, and select Book. You can review or cancel your booking from My Classes." },
  { title: "Community event landing page", text: "Spend Saturday morning with the Lumora community. Join a guided stretch session, meet local members, and enjoy a relaxed start to the weekend." },
  { title: "Project Aurora teaser", text: "Sneak peek: Project Aurora launches next quarter. The new experience brings guided routines and member check-ins into one place." },
];

export default function Review({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const { doc, user } = ctx;
  const [text, setText] = useState(doc?.text ?? "");
  const [title, setTitle] = useState(doc?.title ?? "");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<"all" | "open" | "high">("all");
  const [imgUrl, setImgUrl] = useState("");
  const [up, setUp] = useState({ alt: "", fg: "", bg: "" });
  const timer = useRef<number>(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const docId = doc?.id;

  const pending = useRef(false);   // true while a local edit has not been saved yet
  useEffect(() => { pending.current = false; setText(doc?.text ?? ""); setTitle(doc?.title ?? ""); }, [docId]);  // eslint-disable-line
  useEffect(() => { if (!pending.current) setText(doc?.text ?? ""); }, [doc?.text]);  // server-side fixes flow back into the editor
  useEffect(() => {
    setImgUrl("");
    if (doc?.source_type === "image") api.imageUrl(doc.id).then(setImgUrl).catch(() => {});
  }, [docId, doc?.source_type]);

  const run = async <T,>(f: () => Promise<T>, ok?: string) => {
    setBusy(true);
    try { const r = await f(); if (ok) toast(ok); return r; } catch (e) { toast(errMsg(e), true); } finally { setBusy(false); }
  };
  const apply = async (p: Promise<Doc>) => { const d = await p; ctx.setDoc(d); await ctx.reload(); return d; };

  if (!doc) {
    return (
      <Pane>
        <h2 className="text-[22px] mb-1">Review a draft</h2>
        {user.role === "Creator" ? (
          <>
            <Muted>Start a blank draft, load the sample, or upload a .txt, .md, .html, .docx, .pdf or image file. In the editor, add a title and your content, then select Run review. Check each finding against its cited approved source and accept, edit, or dispute it before submitting for approval.</Muted>
            <div className="flex flex-wrap gap-2 mt-3">
              <Btn v="g" onClick={() => run(() => apply(api.createDoc({ title: "Untitled draft", text: "", team: user.team })))}>New draft</Btn>
              <Btn v="s" onClick={() => run(() => apply(api.createDoc({ title: "Sample launch post", text: SAMPLE, team: user.team })))}>Load sample draft</Btn>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer font-semibold">Browse 11 more demo drafts</summary>
              <Muted>Choose a sample to create a draft in your workspace. It will not be submitted until you run the review and send it for approval.</Muted>
              <div className="grid gap-2 mt-2 sm:grid-cols-2">
                {EXTRA_DEMO_DRAFTS.map(sample => (
                  <div key={sample.title} className="border border-ln rounded-md p-3">
                    <b>{sample.title}</b>
                    <p className="text-sm text-mut my-1">{sample.text}</p>
                    <Btn v="s" onClick={() => run(() => apply(api.createDoc({ title: sample.title, text: sample.text, team: user.team })))}>Use this draft</Btn>
                  </div>
                ))}
              </div>
            </details>
          </>
        ) : <Muted>Open a document from the Documents tab to see its findings.</Muted>}
      </Pane>
    );
  }

  const editable = doc.perms.edit;
  const dirty = editable && doc.source_type !== "image" && !["docx", "pdf"].includes(doc.source_type) && text !== doc.text;
  const canEditText = editable && !["image", "docx", "pdf"].includes(doc.source_type);

  const onText = (v: string) => {
    setText(v);
    pending.current = true;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => api.saveText(doc.id, v).then(d => { pending.current = false; ctx.setDoc(d); }).catch(e => toast(errMsg(e), true)), 900);
  };
  const runReview = () => run(async () => {
    window.clearTimeout(timer.current);
    if (dirty) await api.saveText(doc.id, text, title);
    pending.current = false;
    await apply(api.review(doc.id));
  });
  const decide = (f: Finding, action: string, extra: { text?: string; reason?: string } = {}) =>
    run(() => apply(api.decide(doc.id, f.id, { action, ...extra })));
  const upload = (f: File | undefined) => {
    if (!f) return;
    run(() => apply(api.upload(f, { title: f.name, local_only: doc.local_only, alt_text: up.alt, text_colour: up.fg, bg_colour: up.bg })), "File uploaded. Run the review.");
    if (fileRef.current) fileRef.current.value = "";
  };

  const fresh = doc.fresh && !dirty;
  const shown = doc.findings.filter(f => (filter === "open" ? !f.decision : filter === "high" ? f.risk === "high" : true));
  const openN = doc.findings.filter(f => !f.decision).length;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Pane>
        <div className="flex flex-wrap items-center gap-3 mb-2">
          <h2 className="text-[22px] mr-auto">Draft</h2>
          <StatusPill status={doc.status} label={doc.status_label} /><span className="text-mut">Version {doc.version}</span>
        </div>
        <label className="block text-mut text-sm" htmlFor="title">Title</label>
        <Input id="title" value={title} onChange={e => setTitle(e.target.value)} onBlur={() => canEditText && title !== doc.title && api.saveText(doc.id, text, title).then(d => { ctx.setDoc(d); ctx.reload(); })} disabled={!editable} />
        {editable && <p className="text-mut text-xs mt-1">Add a short name that helps reviewers identify this draft or campaign.</p>}
        {doc.source_type === "image" ? (
          <div className="mt-3">
            {imgUrl ? <img src={imgUrl} alt={doc.alt_text || "Uploaded image under review (no alt text supplied)"} className="max-h-64 rounded border border-ln" /> : <Muted>Loading image…</Muted>}
            {doc.image_stats && <Muted>{doc.image_stats.width}×{doc.image_stats.height}px. Dominant colours: {doc.image_stats.dominant.map(c => `${c.hex} (${c.share}%)`).join(", ")}.
              {doc.image_stats.clearspace_pct !== undefined && ` Clearspace ${doc.image_stats.clearspace_pct}%.`}</Muted>}
            <Muted>Alt text: {doc.alt_text ? `“${doc.alt_text}”` : "none supplied"}. To change it, upload the image again.</Muted>
          </div>
        ) : (
          <>
            <label className="block text-mut text-sm mt-3" htmlFor="draft">Text or HTML to review before publication</label>
            {editable && <p className="text-mut text-xs mb-1">Paste the exact copy you plan to publish. Edits save automatically; select Run review to check the current version.</p>}
            <textarea id="draft" className="mono w-full min-h-[230px] bg-bg border border-ln rounded-md p-2.5 resize-y" value={text} readOnly={!canEditText}
              onChange={e => onText(e.target.value)} placeholder="Paste your draft here" />
          </>
        )}
        {doc.notes.map(n => <p key={n} className="text-md bg-mdb rounded p-2 mt-2">{n}</p>)}
        <div className="flex flex-wrap gap-2 mt-3 items-center">
          <Btn v="g" disabled={busy || !editable} onClick={runReview}>{busy ? "Working…" : "Run review"}</Btn>
          {editable && doc.source_type !== "image" && <Btn v="s" disabled={busy} onClick={() => { setText(SAMPLE); onText(SAMPLE); }}>Load sample draft</Btn>}
          {editable && <label className="border border-ln rounded-md px-3.5 py-2 font-semibold cursor-pointer focus-within:outline-3">
            Upload file<input ref={fileRef} type="file" className="sr-only" accept=".txt,.md,.html,.htm,.docx,.pdf,.png,.jpg,.jpeg,.webp,.gif" onChange={e => upload(e.target.files?.[0])} /></label>}
          {user.role === "Creator" && <Btn v="s" onClick={() => { ctx.setDoc(null); }}>Close</Btn>}
        </div>
        <details className="mt-3">
          <summary className="cursor-pointer font-semibold">How to prepare and review a draft</summary>
          <ol className="list-decimal pl-5 mt-2 grid gap-1 text-sm">
            <li>Give the draft a short title that identifies its campaign or purpose.</li>
            <li>Paste the exact copy you plan to publish, or upload a supported document or image.</li>
            <li>For confidential content, open Options and turn on Local-only mode.</li>
            <li>Select Run review to check the draft against approved brand sources.</li>
            <li>Review the cited findings, resolve each one, then continue to approval.</li>
          </ol>
        </details>
        {editable && (
          <details className="mt-3">
            <summary className="cursor-pointer">Options for uploaded images and confidentiality</summary>
            <div className="grid gap-2 mt-2">
              <label className="flex items-center gap-2"><input type="checkbox" checked={doc.local_only}
                onChange={e => run(() => apply(api.localOnly(doc.id, e.target.checked)))} />
                Local-only mode: never send this draft to an external AI model</label>
              <label>Alt text for the next image upload<Input value={up.alt} onChange={e => setUp({ ...up, alt: e.target.value })} /></label>
              <div className="grid grid-cols-2 gap-2">
                <label>Text colour (optional)<Input placeholder="#9aa0a6" value={up.fg} onChange={e => setUp({ ...up, fg: e.target.value })} /></label>
                <label>Background colour (optional)<Input placeholder="#ffffff" value={up.bg} onChange={e => setUp({ ...up, bg: e.target.value })} /></label>
              </div>
            </div>
          </details>
        )}
        {doc.source_type !== "image" && (
          <>
            <h3 className="text-[17px] mt-4">Highlighted draft</h3>
            <Preview text={doc.text} findings={fresh ? doc.findings : []} />
          </>
        )}
        <p className="text-mut text-sm mt-2">Rule and heuristic checks run on the server. Draft text is encrypted at rest.{doc.local_only ? " Local-only mode is on." : ""}</p>
      </Pane>

      <Pane>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h2 className="text-[22px] mr-auto">Findings</h2>
          <label className="text-sm text-mut">Show <select value={filter} onChange={e => setFilter(e.target.value as any)} className="bg-bg border border-ln rounded px-1.5 py-1 text-ink">
            <option value="all">all</option><option value="open">open</option><option value="high">high-risk</option></select></label>
        </div>
        <Muted>Each finding shows the passage, why it was flagged, its approved source, and a suggested fix. Accept the fix, edit it, or dispute it with a reason. Resolve findings before continuing to approval.</Muted>
        <details className="mb-2">
          <summary className="cursor-pointer font-semibold">How to handle findings</summary>
          <ol className="list-decimal pl-5 mt-2 grid gap-1 text-sm">
            <li>Read the highlighted passage and the reason for the flag.</li>
            <li>Check the cited guideline or approved fact.</li>
            <li>Accept the suggested fix or edit the wording to keep your intent.</li>
            <li>If the flag is wrong, dispute it and explain why or provide evidence.</li>
            <li>After changing the draft, run the review again; decide every finding before approval.</li>
          </ol>
        </details>
        {!doc.run && <Muted>Choose “Run review” to check this draft. Every finding will cite an approved source.</Muted>}
        {doc.run && !fresh && <p className="bg-mdb text-md rounded p-2 my-2">{dirty ? "You have edited the draft. " : ""}Run the review again to see findings for the current text.</p>}
        {doc.run && fresh && (
          <>
            <p><b>{doc.findings.length}</b> finding{doc.findings.length === 1 ? "" : "s"}, <b>{openN}</b> awaiting a decision.{doc.findings.length > 0 && !openN && " All decided."}</p>
            <p className="text-mut text-sm">Verifier: {doc.run.kept} of {doc.run.raw} candidate findings kept in {doc.run.ms} ms. A finding needs an approved source and quoted text from the draft, or it is dropped. AI: {doc.run.ai_status}.</p>
            {doc.run.dropped.length > 0 && (
              <details className="text-sm"><summary className="cursor-pointer">Rejected by the verifier ({doc.run.dropped.length})</summary>
                <ul className="list-disc pl-5">{doc.run.dropped.map((d, i) => <li key={i}>“{d.text}” ({d.method}, {d.src}): {d.reason}</li>)}</ul></details>
            )}
            {doc.findings.length === 0 && <Muted>No issues found against the approved sources.</Muted>}
            {shown.map(f => <Card key={f.id} f={f} doc={doc} busy={busy} onDecide={decide} />)}
          </>
        )}
        {doc.perms.submit && <div className="mt-4"><Btn v="g" onClick={() => ctx.go("flow")}>Continue to approval</Btn></div>}
      </Pane>
    </div>
  );
}

function Preview({ text, findings }: { text: string; findings: Finding[] }) {
  const parts = useMemo(() => {
    const out: React.ReactNode[] = [];
    let p = 0;
    for (const f of findings) {
      if (f.start < p || f.start < 0) continue;
      out.push(text.slice(p, f.start));
      out.push(
        <mark key={f.id} tabIndex={0} role="button" aria-label={`${f.category}: ${f.text}. Go to finding`}
          className={f.decision ? "bg-okb border-b-2 border-ok" : sevMark[f.severity]}
          onClick={() => jump(f.id)} onKeyDown={e => e.key === "Enter" && jump(f.id)}>{text.slice(f.start, f.end)}</mark>,
      );
      p = f.end;
    }
    out.push(text.slice(p));
    return out;
  }, [text, findings]);
  return <div aria-live="polite" className="mono whitespace-pre-wrap break-words bg-bg border border-ln rounded-md p-2.5 max-h-[300px] overflow-auto">{text ? parts : <span className="text-mut">Nothing to show yet.</span>}</div>;
}

function jump(id: number) {
  const c = document.getElementById("f-" + id);
  if (!c) return;
  c.scrollIntoView({ block: "center" });
  c.classList.add("ring-4", "ring-ac");
  setTimeout(() => c.classList.remove("ring-4", "ring-ac"), 1500);
}

function Card({ f, doc, busy, onDecide }: { f: Finding; doc: Doc; busy: boolean; onDecide: (f: Finding, a: string, x?: { text?: string; reason?: string }) => void }) {
  const [mode, setMode] = useState<"" | "edit" | "dispute">("");
  const [val, setVal] = useState(f.text);
  const [reason, setReason] = useState("");
  const canFix = !["image", "docx", "pdf"].includes(doc.source_type);
  return (
    <div id={"f-" + f.id} className={`border border-ln border-l-[5px] ${sevBorder[f.severity]} rounded-md p-3 mt-2.5 bg-sf`}>
      <div className="flex flex-wrap gap-1.5 items-center">
        <Tag>{f.category}</Tag><Tag sev={f.severity}>{f.severity}</Tag>
        <Tag title={f.method === "Rule" ? "Deterministic rule" : f.method === "AI" ? "AI model, grounded in retrieved approved sources and re-checked by the verifier" : "Rule-based heuristic"}>{f.method}</Tag>
        <Tag>{f.confidence ? `Confidence ${f.confidence}%` : "No evidence on file"}</Tag>
        {f.block !== null && doc.blocks.length > 1 && <Tag>{doc.source_type === "pdf" ? `Page ${doc.blocks[f.block]?.page}, ` : ""}paragraph {f.block + 1}</Tag>}
      </div>
      <p className="font-serif text-base break-words my-1.5">“{f.text}”</p>
      <p className="my-1.5">{f.why}</p>
      <details className="text-sm my-1"><summary className="cursor-pointer text-mut">Source: <b className="text-ink">{f.src}</b></summary>
        <p className="bg-bg rounded p-2 mt-1">{f.src_text}</p></details>
      {f.rep !== null ? <p>Suggested: <b>{f.rep === "" ? "remove it" : f.rep}</b></p> : <p className="text-mut">{f.tip || "Edit the text to resolve this."}</p>}
      {f.decision ? (
        <p className="mt-1"><span className="bg-okb text-ok rounded-full px-3 py-0.5 font-semibold">Disputed</span> Reason: {f.reason}{" "}
          {doc.perms.decide && <Btn v="s" className="!py-1" disabled={busy} onClick={() => onDecide(f, "undo")}>Undo</Btn>}</p>
      ) : doc.perms.decide ? (
        mode === "edit" ? (
          <div className="flex flex-wrap gap-2 mt-2"><Input aria-label="Your edit" value={val} onChange={e => setVal(e.target.value)} className="!w-auto flex-1" />
            <Btn v="g" disabled={busy} onClick={() => { onDecide(f, "edit", { text: val }); setMode(""); }}>Apply edit</Btn><Btn v="s" onClick={() => setMode("")}>Cancel</Btn></div>
        ) : mode === "dispute" ? (
          <div className="mt-2"><Area rows={2} aria-label="Dispute reason" placeholder="Why is this flag wrong, or where is the evidence?" value={reason} onChange={e => setReason(e.target.value)} />
            <div className="flex gap-2 mt-2"><Btn v="g" disabled={busy || !reason.trim()} onClick={() => { onDecide(f, "dispute", { reason }); setMode(""); }}>Dispute with reason</Btn><Btn v="s" onClick={() => setMode("")}>Cancel</Btn></div></div>
        ) : (
          <div className="flex flex-wrap gap-2 mt-2">
            {f.rep !== null && canFix && <Btn v="g" disabled={busy} onClick={() => onDecide(f, "accept")}>Accept fix</Btn>}
            {canFix && <Btn v="s" disabled={busy} onClick={() => { setVal(f.text); setMode("edit"); }}>Edit</Btn>}
            <Btn v="s" disabled={busy} onClick={() => setMode("dispute")}>Dispute</Btn>
          </div>
        )
      ) : null}
    </div>
  );
}
