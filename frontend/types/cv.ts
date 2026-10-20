export const MAX_CV_PDF_BYTES = 3 * 1024 * 1024;
export interface CvFinding {title:string; evidence:string; recommendation:string}
export interface CvSkill {skill:string; reason:string; evidence_status:"not_evidenced"|"partially_evidenced"; recommendation:string}
export interface CvRewrite {original:string; suggested:string; rationale:string}
export interface CvAnalysis {
  summary:string; strengths:CvFinding[]; weaknesses:CvFinding[];
  missing_skills:CvSkill[]; unclear_descriptions:CvFinding[]; content_errors:CvFinding[];
  rewrites:CvRewrite[]; practice_plan:string[];
}
export interface CvSummary {
  id:string; job_role:string; source:"pdf"|"text"; status:"processing"|"failed"|"finished";
  character_count:number; page_count:number|null; created_at:string; expires_at:string;
}
export interface CvReview extends CvSummary {analysis:CvAnalysis|null; limitations:string[]}
export interface CvHistory {items:CvSummary[]; next_cursor:string|null}
export interface CvRequest {operation_id:string; job_role:string; job_description:string; cv_text?:string; pdf_base64?:string}
