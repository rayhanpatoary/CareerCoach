import {proxyAnalysis} from "@/lib/analysis-proxy";
export const maxDuration=90;
async function handle(request:Request,context:{params:Promise<{segments:string[]}>}){
  return proxyAnalysis(request,"job-fit",(await context.params).segments);
}
export const GET=handle;export const POST=handle;export const DELETE=handle;
