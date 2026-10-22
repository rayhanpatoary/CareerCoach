import type {CvRequest,CvSummary,CvRewrite} from "@/types/cv";
export interface JobFitRequest extends CvRequest {company:string}
export type MatchStatus="matched"|"partial"|"not_evidenced"|"uncertain";
export type Importance="mandatory"|"preferred"|"alignment";
export interface JobEvidence {source_id:string;quote:string;page:number|null;section:string|null}
export interface JobRequirement {
  id:string;label:string;category:string;importance:Importance;jd_source_id:string;jd_quote:string;
  status:MatchStatus;evidence:JobEvidence[];action_kind:"improve_wording"|"add_truthful_evidence"|"develop_skill"|"clarify_experience";
  suggested_action:string;explanation:string;
}
export interface JobImprovement {horizon:"immediate"|"strengthen"|"longer_term";requirement_index:number;action:string}
export interface JobCategoryScore {category:Importance;count:number;matched:number;partial:number;not_evidenced:number;uncertain:number;base_weight:number;effective_weight:number;score:number|null;contribution:number}
export interface JobFitAnalysis {
  company:string;language:string;requirements:JobRequirement[];
  score:{overall:number|null;reason:string;categories:JobCategoryScore[];evidence_coverage:number;uncertain_share:number;rubric_version:string;meaning:string};
  improvements:JobImprovement[];rewrites:CvRewrite[];extraction:{confidence:string;warnings:string[];source_block_count:number;page_count:number|null};
  coverage_complete:boolean;warnings:string[];
}
export interface JobFitReview extends CvSummary {analysis:JobFitAnalysis|null;limitations:string[]}
export interface JobFitHistory {items:CvSummary[];next_cursor:string|null}
