import {record} from "@/lib/interview-session";
import type {CvHistory,CvReview,CvSummary,CvRequest} from "@/types/cv";
const text = (v:unknown) => typeof v === "string";
const texts = (v:unknown) => Array.isArray(v) && v.every(text);
const citation = (v:unknown) => record(v) &&
  (v.source_id==null||text(v.source_id)) && (v.source_section==null||text(v.source_section)) &&
  (v.source_page==null||Number.isInteger(v.source_page));
const fields = (v:unknown,keys:string[]) => record(v) && keys.every(k=>text(v[k]));
function validSummary(v:unknown):v is CvSummary {
  return record(v) && fields(v,["id","job_role","created_at","expires_at"]) &&
    ["pdf","text"].includes(String(v.source)) && ["processing","failed","finished"].includes(String(v.status)) &&
    Number.isInteger(v.character_count) && (v.page_count===null || Number.isInteger(v.page_count));
}
export function validCvReview(v:unknown):v is CvReview {
  if (!validSummary(v) || !record(v) || !texts(v.limitations)) return false;
  if (v.analysis===null) return v.status!=="finished";
  if (!record(v.analysis) || v.status!=="finished") return false;
  const a=v.analysis;
  return (a.extraction==null||(record(a.extraction)&&["high","medium","low"].includes(String(a.extraction.confidence))&&
    texts(a.extraction.warnings)&&Number.isInteger(a.extraction.source_block_count)&&
    (a.extraction.page_count===null||Number.isInteger(a.extraction.page_count)))) && text(a.summary) && texts(a.practice_plan) &&
    ["strengths","weaknesses","unclear_descriptions","content_errors"].every(key=>Array.isArray(a[key]) &&
      a[key].every(item=>fields(item,["title","evidence","recommendation"]) && citation(item))) &&
    Array.isArray(a.missing_skills) && a.missing_skills.every(item=>fields(item,["skill","reason","evidence_status","recommendation"]) &&
      ["not_evidenced","partially_evidenced"].includes(item.evidence_status)) &&
    Array.isArray(a.rewrites) && a.rewrites.every(item=>fields(item,["original","suggested","rationale"]) && citation(item));
}
export class CvError extends Error {constructor(message:string,public status:number){super(message);}}
async function request(path:string,body?:CvRequest,method?:string) {
  const response=await fetch(`/api/cv/${path}`,{method:method??(body?"POST":"GET"),
    headers:body?{"Content-Type":"application/json"}:undefined,body:body?JSON.stringify(body):undefined,
    signal:AbortSignal.timeout(body?80000:15000),cache:"no-store"});
  if(response.status===204)return null;
  const data:unknown=await response.json().catch(()=>null);
  if(!response.ok)throw new CvError(record(data)&&text(data.error)?String(data.error):
    response.status===413?"Choose a PDF no larger than 3 MiB.":"The CV service could not respond. Please retry.",response.status);
  return data;
}
export async function ensureCvSession(){
  const response=await fetch("/api/cv/session",{method:"POST"});
  if(!response.ok)throw new Error("Could not establish your private review session. Please retry.");
}
export async function analyzeCv(body:CvRequest):Promise<CvReview>{
  const value=await request("reviews",body);
  if(!validCvReview(value))throw new Error("The server returned an invalid CV review. Retry the same action.");
  return value;
}
export async function readCv(id:string):Promise<CvReview>{
  const value=await request(`reviews/${id}`);
  if(!validCvReview(value))throw new Error("The saved CV review could not be read.");
  return value;
}
export async function cvHistory(cursor?:string):Promise<CvHistory>{
  const value=await request(`reviews${cursor?`?cursor=${encodeURIComponent(cursor)}`:""}`);
  if(!record(value)||!Array.isArray(value.items)||!value.items.every(validSummary)||
    !(value.next_cursor===null||text(value.next_cursor)))throw new Error("Review history could not be read.");
  return value as unknown as CvHistory;
}
export async function deleteCv(id:string){await request(`reviews/${id}`,undefined,"DELETE");}
export function pdfBase64(file:File):Promise<string>{
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(String(reader.result).split(",")[1]);
    reader.onerror=()=>reject(new Error("The selected PDF could not be read. Select it again."));
    reader.readAsDataURL(file);
  });
}
