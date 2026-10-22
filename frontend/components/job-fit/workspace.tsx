"use client";
import {useEffect,useRef,useState} from "react";
import {useRouter} from "next/navigation";
import Link from "next/link";
import {ArrowUpRight,LoaderCircle,Target,RefreshCw} from "lucide-react";
import {pdfBase64} from "@/lib/cv";
import {analyzeJobFit,ensureJobFitSession,jobFitHistory} from "@/lib/job-fit";
import type {JobFitRequest,JobFitHistory} from "@/types/job-fit";
import {ResumeInput} from "./resume-input";

const message=(e:unknown)=>e instanceof Error?e.message:"The analysis failed. Please retry.";
export function JobFitWorkspace(){
  const router=useRouter();
  const [mode,setMode]=useState<"pdf"|"text">("pdf"),[file,setFile]=useState<File|null>(null),[text,setText]=useState("");
  const [title,setTitle]=useState(""),[company,setCompany]=useState(""),[jd,setJd]=useState("");
  const [busy,setBusy]=useState(""),[error,setError]=useState(""),[retry,setRetry]=useState(false);
  const [history,setHistory]=useState<JobFitHistory>({items:[],next_cursor:null}),[historyError,setHistoryError]=useState("");
  const guard=useRef(false),pending=useRef<JobFitRequest|null>(null);
  useEffect(()=>{let alive=true;void(async()=>{try{await ensureJobFitSession();const h=await jobFitHistory();if(alive)setHistory(h);}catch(e){if(alive)setHistoryError(message(e));}})();return()=>{alive=false;};},[]);
  function edited(){pending.current=null;setRetry(false);setError("");}
  async function submit(){
    if(guard.current)return;guard.current=true;setError("");setBusy("Preparing your documents…");
    try{
      await ensureJobFitSession();
      if(!pending.current)pending.current={operation_id:crypto.randomUUID(),job_role:title.trim(),company:company.trim(),job_description:jd.trim(),
        ...(mode==="pdf"?{pdf_base64:await pdfBase64(file!)}:{cv_text:text.trim()})};
      setBusy("Comparing job requirements with your CV…");
      const result=await analyzeJobFit(pending.current);
      setText("");setFile(null);setJd("");pending.current=null;setRetry(false);
      router.push(`/job-fit/results/${result.id}`);
    }catch(e){setError(message(e));setRetry(pending.current!==null);setBusy("");guard.current=false;}
  }
  async function refresh(cursor?:string){try{const h=await jobFitHistory(cursor);setHistory(old=>cursor?{items:[...old.items,...h.items],next_cursor:h.next_cursor}:h);setHistoryError("");}catch(e){setHistoryError(message(e));}}
  return <div className="shell page-content job-fit-page"><p className="eyebrow">YOUR EXPERIENCE. THEIR REQUIREMENTS.</p><h1 className="page-title">Find your fit. Plan your next move.</h1><p className="page-description">Compare your CV with a specific job and turn evidence gaps into practical next steps.</p>
    {error&&<div role="alert" className="error interview-error">{error}{retry&&<button className="button secondary" disabled={!!busy} onClick={()=>void submit()}>Retry same analysis</button>}</div>}
    {busy&&<div className="panel loading-panel" role="status"><LoaderCircle className="spin"/>{busy} This may take up to a minute.</div>}
    <div className="job-fit-input-grid"><form className="panel setup" onSubmit={e=>{e.preventDefault();void submit();}}><h2>Your next opportunity</h2><fieldset disabled={!!busy}>
      <ResumeInput disabled={!!busy} mode={mode} setMode={v=>{setMode(v);edited();}} file={file} setFile={v=>{setFile(v);edited();}} text={text} setText={v=>{setText(v);edited();}} onError={setError}/>
      <label htmlFor="fit-title">Job title</label><input id="fit-title" required minLength={2} maxLength={100} value={title} onChange={e=>{setTitle(e.target.value);edited();}} placeholder="e.g. Full Stack Developer"/>
      <label htmlFor="fit-company">Company (optional)</label><input id="fit-company" maxLength={100} value={company} onChange={e=>{setCompany(e.target.value);edited();}} placeholder="Company name"/>
      <label htmlFor="fit-description">Target job description</label><textarea id="fit-description" required minLength={100} maxLength={8000} rows={9} value={jd} onChange={e=>{setJd(e.target.value);edited();}} placeholder="Paste the full English or German job posting, including required and preferred qualifications."/>
      <p className="field-help">{jd.length.toLocaleString()} / 8,000 characters · minimum 100</p>
      <button className="button primary w-full mt-7" disabled={!!busy||title.trim().length<2||jd.trim().length<100||(mode==="pdf"?!file:text.trim().length<100)}>Analyze My Job Fit <ArrowUpRight size={18}/></button>
    </fieldset><p className="field-help">Your extracted CV and job description are sent to NVIDIA. Raw files and complete source text are discarded; saved feedback may contain excerpts. Remove confidential information before submitting.</p></form>
    <aside className="panel job-fit-intro"><span className="icon-box"><Target size={24}/></span><h2>A clearer picture of your next step.</h2><p>See which requirements your CV supports, where experience is transferable, and what needs more context.</p><ol><li>Provide a fresh CV and the actual job posting.</li><li>Review source-backed matches and a transparent score.</li><li>Separate CV improvements from skills to develop.</li></ol><div className="notice"><div><strong>Evidence, not assumptions.</strong><p>Not evidenced means your CV does not show enough information. It does not mean you lack a skill.</p><p>The score estimates document alignment. It does not predict hiring, recruiter approval or ATS results.</p></div></div><p className="field-help">Previous CV feedback cannot reconstruct your complete resume. Please upload or paste it again. Coordinates recover text order; visual design quality is outside this analysis.</p><p className="field-help">Private history is available in this browser for 7 days. You can delete an analysis at any time.</p><Link href="/cv-review" className="text-button">Looking for general CV feedback? Open CV Reviewer.</Link></aside></div>
    <section className="panel cv-history"><div className="cv-result-heading"><div><p className="eyebrow">PRIVATE TO THIS BROWSER</p><h2>Previous job-fit analyses</h2></div><button className="button secondary" disabled={!!busy} onClick={()=>void refresh()}><RefreshCw size={16}/>Refresh history</button></div>{historyError&&<p role="alert" className="error">{historyError}</p>}{!history.items.length&&!historyError&&<p className="field-help">Your saved comparisons will appear here.</p>}<ul>{history.items.map(item=><li key={item.id}><Link href={`/job-fit/results/${item.id}`}><strong>{item.job_role}</strong><span>{new Date(item.created_at).toLocaleDateString()} · {item.status}</span></Link></li>)}</ul>{history.next_cursor&&<button className="button secondary" disabled={!!busy} onClick={()=>void refresh(history.next_cursor!)}>Load more analyses</button>}</section>
  </div>;
}
