"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, LoaderCircle, MessageSquare, Send, Sparkles } from "lucide-react";
import { ensureSession, save, saved, sessionRequest } from "@/lib/interview-session";
import { difficulties, type Configuration, type Difficulty, type InterviewState, type InterviewType, type PendingAction } from "@/types/interview";
const roles = ["Python Developer", "Frontend Developer", "Backend Developer", "Full Stack Developer", "Data Scientist", "Machine Learning Engineer", "AI Engineer", "Data Analyst", "Custom role"];
const levels = ["Beginner / Junior", "Intermediate / Mid-level", "Advanced / Senior"];
const initial: Configuration = {job_role: roles[0], difficulty: "beginner", interview_type: "technical", question_count: 5, job_description: ""};

export function InterviewWorkspace() {
  const router = useRouter();
  const [config, setConfig] = useState(initial), [role, setRole] = useState(roles[0]);
  const [state, setState] = useState<InterviewState | null>(null);
  const [draft, setDraft] = useState(""), [error, setError] = useState("");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [loading, setLoading] = useState(false), [ready, setReady] = useState(false);
  const guard = useRef(false), nearBottom = useRef(true);
  const transcript = useRef<HTMLDivElement>(null), input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    let alive = true;
    async function resume() {
      try {
        const storedConfig = saved("configuration"), previous = saved("pending"), id = saved("active");
        if (storedConfig) {const c = JSON.parse(storedConfig) as Configuration; if (typeof c.job_role === "string") {setConfig(c); setRole(roles.includes(c.job_role) ? c.job_role : "Custom role");}}
        if (previous) setPending(JSON.parse(previous) as PendingAction);
        if (id) {
          const value = await sessionRequest(id); if (!alive) return;
          if (value.status === "finished") {router.replace(`/interview/results/${value.id}`); return;}
          setState(value); setDraft(saved(`draft:${id}`) ?? "");
          if (previous) setError("An earlier request needs confirmation. Retry it to recover your progress.");
        }
      } catch (e) {if (alive) setError(e instanceof Error ? e.message : "Could not resume your interview.");}
      finally {if (alive) setReady(true);}
    }
    void resume(); return () => {alive = false;};
  }, [router]);
  useEffect(() => {
    if (nearBottom.current && transcript.current) transcript.current.scrollTo({top: transcript.current.scrollHeight, behavior: "instant"});
  }, [state?.turns.length, state?.answered_count, loading]);
  async function execute(action: PendingAction) {
    if (guard.current) return;
    guard.current = true; setLoading(true); setError(""); setPending(action); save("pending", JSON.stringify(action));
    try {
      await ensureSession(); const value = await sessionRequest(action.path, action.body);
      setState(value); save("active", value.id); setPending(null); save("pending", null);
      if (action.path.endsWith("/answer")) {setDraft(""); save(`draft:${value.id}`, null);}
      if (value.status === "finished") {save(`draft:${value.id}`, null); router.push(`/interview/results/${value.id}`);}
      else input.current?.focus();
    } catch (e) {setError(e instanceof Error && e.name === "TimeoutError" ? "The service is taking longer than expected. Retry to recover the result safely." : e instanceof Error ? e.message : "The request failed. Please retry.");}
    finally {setLoading(false); guard.current = false;}
  }
  function start() {
    const job_role = (role === "Custom role" ? config.job_role : role).trim();
    if (job_role.length < 2 || job_role.length > 100) {setError("Enter a role between 2 and 100 characters."); return;}
    const configuration = {...config, job_role}, id = crypto.randomUUID();
    save("configuration", JSON.stringify(configuration)); save("active", id);
    void execute({path: "start", body: {...configuration, persistent: true, operation_id: id}});
  }
  function answer() {
    const turn = state?.turns.at(-1);
    if (!state || !turn || !draft.trim() || draft.length > 6000 || pending || loading) return;
    void execute({path: `${state.id}/answer`, body: {operation_id: crypto.randomUUID(), question_id: turn.id, answer: draft.trim()}});
  }
  function finish() {if (state) void execute({path: `${state.id}/finish`, body: {operation_id: crypto.randomUUID()}});}
  const locked = loading || !!pending || !!state?.busy;
  function resetLocal() {
    save("active", null); save("pending", null); setPending(null); setState(null); setDraft(""); setError("");
  }
  async function refreshProgress() {
    if (!state) return;
    setLoading(true); setError("");
    try {
      const value = await sessionRequest(state.id);
      setState(value);
      if (!value.busy && !["generating_question", "evaluating"].includes(value.status)) {
        setPending(null); save("pending", null);
      } else setError("The last request still needs recovery. Retry it after processing finishes.");
    } catch (e) {setError(e instanceof Error ? e.message : "Could not refresh progress.");}
    finally {setLoading(false);}
  }
  return <div className="shell page-content"><p className="eyebrow">YOUR PRACTICE SPACE</p><h1 className="page-title">{state ? "One answer. A little more confidence." : "A stronger interview starts here."}</h1><p className="page-description">A focused conversation, tailored to your next opportunity. Specific feedback when you finish.</p>
    {!ready ? <div className="panel loading-panel" role="status"><LoaderCircle className="spin"/> Restoring your practice space…</div> : <>
      {error && <div className="error interview-error" role="alert" aria-label="Interview error">{error}</div>}
      {error && !state && !loading && <button className="text-button mb-5" onClick={resetLocal}>Start a new interview instead</button>}
      {pending && !loading && <div className="recovery panel"><p>Your last action is saved. Retrying uses the same request ID and will not submit another answer.</p><button className="button primary" onClick={() => void execute(pending)}>Retry last action</button></div>}
      {state && (pending || state.busy || ["generating_question", "evaluating"].includes(state.status)) && !loading && <button className="text-button mb-5" onClick={() => void refreshProgress()}>Check saved progress before continuing</button>}
      {!state ? <div className="workspace setup-workspace"><section className="panel setup"><div className="panel-heading"><span className="icon-box"><MessageSquare size={22}/></span><div><h2>Make it yours</h2><p>Set your interview focus</p></div></div>
        <form onSubmit={e => {e.preventDefault(); start();}}><fieldset disabled={locked}>
          <label htmlFor="role">Target job role</label><select id="role" value={role} onChange={e => {setRole(e.target.value); setConfig({...config, job_role: e.target.value === "Custom role" ? "" : e.target.value});}}>{roles.map(r => <option key={r}>{r}</option>)}</select>
          {role === "Custom role" && <><label htmlFor="custom">Your job role</label><input id="custom" required minLength={2} maxLength={100} value={config.job_role} onChange={e => setConfig({...config, job_role: e.target.value})} placeholder="e.g. Cloud Engineer"/></>}
          <label htmlFor="difficulty">Experience level</label><select id="difficulty" value={config.difficulty} onChange={e => setConfig({...config, difficulty: e.target.value as Difficulty})}>{difficulties.map((d,i) => <option key={d} value={d}>{levels[i]}</option>)}</select>
          <label htmlFor="type">Interview type</label><select id="type" value={config.interview_type} onChange={e => setConfig({...config, interview_type: e.target.value as InterviewType})}><option value="technical">Technical Interview</option><option value="behavioral">Behavioral Interview</option><option value="mixed">Mixed Interview</option></select>
          <label htmlFor="count">Number of questions</label><select id="count" value={config.question_count} onChange={e => setConfig({...config, question_count: Number(e.target.value) as 3 | 5 | 8})}>{[3,5,8].map(n => <option key={n} value={n}>{n} questions</option>)}</select>
          <label htmlFor="description">Job description <span className="muted">(optional)</span></label><textarea id="description" rows={5} maxLength={8000} value={config.job_description} onChange={e => setConfig({...config, job_description: e.target.value})} placeholder="Paste the responsibilities and skills you want to prepare for."/>
          <p className="field-help">{config.job_description.length.toLocaleString()} / 8,000 characters. Each follow-up counts as one question.</p>
          <button className="button primary w-full" type="submit">{loading ? <><LoaderCircle className="spin" size={18}/> Preparing your interview…</> : <>Start Interview <ArrowUpRight size={18}/></>}</button>
        </fieldset></form></section>
        <aside className="panel interview-intro"><span className="empty-icon"><Sparkles size={32}/></span><p className="eyebrow">PRACTICE WITH PURPOSE</p><h2>A conversation.<br/>A clearer path forward.</h2><p>Your interviewer listens to your answers, asks relevant follow-ups, and explores the skills that matter for your role.</p><ol><li>Choose your focus and experience level.</li><li>Answer one question at a time, at your pace.</li><li>Leave with specific feedback and a practice plan.</li></ol><div className="setup-note"><p>Powered by NVIDIA Nemotron. Submitted interviews expire after seven days and can be deleted from your results. Drafts stay in this browser tab. Avoid confidential or sensitive personal information.</p></div></aside>
      </div> : <section className="panel live-interview" aria-busy={loading}>
        <header className="interview-header"><div><p className="eyebrow">{state.interview_type.toUpperCase()} INTERVIEW</p><h2>{state.job_role}</h2><p className="field-help">{levels[difficulties.indexOf(state.difficulty)]} · {state.answered_count} of {state.question_count} answered</p></div><button className="button secondary" disabled={locked} onClick={finish}>Finish Interview</button></header>
        <progress className="interview-progress" value={state.answered_count} max={state.question_count} aria-label="Interview progress"/>
        <div ref={transcript} className="transcript" role="log" aria-label="Interview conversation" aria-live="polite" onScroll={() => {const el = transcript.current; if (el) nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;}}>{state.turns.map(turn => <div className="exchange" key={turn.id}><article className="chat-message ai-message"><p className="message-label"><Sparkles size={15}/> AI Interviewer <span>Question {turn.position} / {state.question_count}</span></p><p>{turn.question}</p></article>{turn.answer !== null && <article className="chat-message user-message"><p className="message-label">Your answer</p><p>{turn.answer}</p></article>}</div>)}</div>
        <div className="thinking" role="status">{loading && <><LoaderCircle size={16} className="spin"/> {pending?.path.endsWith("finish") ? "Reviewing your submitted answers…" : "Your interviewer is preparing the next question…"} This may take up to a minute.</>}</div>
        {state.status === "completed" ? <div className="completion-card"><h3>Interview complete. Make your practice count.</h3><p>All {state.answered_count} answers are saved. Generate your personal feedback to see what to practice next.</p><button className="button primary" disabled={locked} onClick={finish}>Get my feedback <ArrowUpRight size={17}/></button></div> : <form className="answer-composer" onSubmit={e => {e.preventDefault(); answer();}}><label htmlFor="answer">Your answer</label><textarea ref={input} id="answer" rows={5} maxLength={6000} disabled={locked} value={draft} onChange={e => {setDraft(e.target.value); save(`draft:${state.id}`, e.target.value);}} onKeyDown={e => {if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {e.preventDefault(); answer();}}} placeholder="Explain your thinking. Use a practical example where useful." aria-describedby="answer-help"/><div className="composer-actions"><span id="answer-help" className="field-help">{draft.length.toLocaleString()} / 6,000 · Ctrl / ⌘ + Enter to submit</span><button className="button primary" type="submit" disabled={locked || !draft.trim()}>Submit Answer <Send size={16}/></button></div></form>}
        <p className="conversation-note">Finish early at any time. Feedback covers only submitted answers. Every follow-up counts toward your selected length.</p>
      </section>}
    </>}
  </div>;
}
