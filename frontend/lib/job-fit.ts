import {record} from "@/lib/interview-session";
import type {JobFitRequest,JobFitReview,JobFitHistory} from "@/types/job-fit";
import type {Configuration} from "@/types/interview";
const strings=(v:unknown)=>Array.isArray(v)&&v.every(x=>typeof x==="string");
const numeric=(v:unknown):v is number=>typeof v==="number"&&Number.isFinite(v);
export function validJobFit(v:unknown):v is JobFitReview {
  if(!record(v)||!["id","job_role","created_at","expires_at"].every(k=>typeof v[k]==="string")||!strings(v.limitations)||
    !["pdf","text"].includes(String(v.source))||!numeric(v.character_count)||!(v.page_count===null||numeric(v.page_count))||
    !["processing","failed","finished"].includes(String(v.status)))return false;
  if(v.analysis===null)return v.status!=="finished";
  if(v.status!=="finished"||!record(v.analysis))return false;
  const a=v.analysis,s=a.score;
  return typeof a.company==="string"&&typeof a.language==="string"&&typeof a.coverage_complete==="boolean"&&strings(a.warnings)&&
    record(a.extraction)&&typeof a.extraction.confidence==="string"&&numeric(a.extraction.source_block_count)&&strings(a.extraction.warnings)&&
    record(s)&&(s.overall===null||(numeric(s.overall)&&s.overall>=0&&s.overall<=100))&&typeof s.reason==="string"&&typeof s.meaning==="string"&&numeric(s.evidence_coverage)&&numeric(s.uncertain_share)&&
    Array.isArray(s.categories)&&s.categories.every(c=>record(c)&&["mandatory","preferred","alignment"].includes(String(c.category))&&numeric(c.count)&&numeric(c.effective_weight)&&numeric(c.contribution)&&(c.score===null||numeric(c.score)))&&
    Array.isArray(a.requirements)&&a.requirements.every(r=>record(r)&&["id","label","category","jd_source_id","jd_quote","action_kind","suggested_action","explanation"].every(k=>typeof r[k]==="string")&&
      ["mandatory","preferred","alignment"].includes(String(r.importance))&&["matched","partial","not_evidenced","uncertain"].includes(String(r.status))&&
      Array.isArray(r.evidence)&&r.evidence.every(e=>record(e)&&typeof e.source_id==="string"&&typeof e.quote==="string"&&(e.page===null||numeric(e.page))&&(e.section===null||typeof e.section==="string")))&&
    Array.isArray(a.improvements)&&a.improvements.every(p=>record(p)&&["immediate","strengthen","longer_term"].includes(String(p.horizon))&&Number.isInteger(p.requirement_index)&&typeof p.action==="string")&&
    Array.isArray(a.rewrites)&&a.rewrites.every(r=>record(r)&&["original","suggested","rationale","source_id"].every(k=>typeof r[k]==="string"));
}

async function request(path:string,body?:JobFitRequest,method?:string){
  const response=await fetch(`/api/job-fit/${path}`,{method:method??(body?"POST":"GET"),headers:body?{"Content-Type":"application/json"}:undefined,
    body:body?JSON.stringify(body):undefined,cache:"no-store",signal:AbortSignal.timeout(body?80000:15000)});
  if(response.status===204)return null;
  const data:unknown=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(record(data)&&typeof data.error==="string"?data.error:"The analysis service could not respond. Retry the same action.");
  return data;
}
let establishingSession:Promise<void>|null=null;
export function ensureJobFitSession(){
  // Initial history and a fast submit share one cookie-setting request.
  if(!establishingSession)establishingSession=(async()=>{const r=await fetch("/api/job-fit/session",{method:"POST",signal:AbortSignal.timeout(15000)});if(!r.ok)throw new Error("Could not establish your private session. Retry shortly.");})().finally(()=>{establishingSession=null;});
  return establishingSession;
}
export async function analyzeJobFit(body:JobFitRequest){const data=await request("analyze",body);if(!validJobFit(data))throw new Error("The analysis response could not be verified. Retry the same action.");return data;}
export async function readJobFit(id:string){const data=await request(id);if(!validJobFit(data))throw new Error("The saved analysis could not be read.");return data;}
export async function jobFitHistory(cursor?:string):Promise<JobFitHistory>{
  const v=await request(`history${cursor?`?cursor=${encodeURIComponent(cursor)}`:""}`);
  if(!record(v)||!Array.isArray(v.items)||!v.items.every(x=>record(x)&&["id","job_role","status","created_at","expires_at"].every(k=>typeof x[k]==="string"))||!(v.next_cursor===null||typeof v.next_cursor==="string"))throw new Error("Analysis history could not be read.");
  return v as unknown as JobFitHistory;
}
export async function deleteJobFit(id:string){await request(id,undefined,"DELETE");}

export function jobFitInterviewSetup(review:JobFitReview):Configuration {
  const requirements=review.analysis?.requirements??[];
  const seniority=[review.job_role,...requirements.filter(r=>r.category==="seniority").map(r=>r.label)].join(" ");
  const topics=requirements.filter(r=>r.status!=="matched").slice(0,6).map(r=>r.label);
  return {job_role:review.job_role,difficulty:/senior|lead|advanced|fortgeschritten/i.test(seniority)?"advanced":
    /junior|entry|trainee|einsteiger/i.test(seniority)?"beginner":"intermediate",interview_type:"mixed",question_count:5,
    job_description:topics.length?`Practice these job criteria: ${topics.join("; ")}. Ask about my actual knowledge; do not assume experience.`:""};
}
