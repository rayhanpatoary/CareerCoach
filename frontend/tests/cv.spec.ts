import {test,expect,type Page} from "@playwright/test";
import type {CvReview,CvRequest} from "../types/cv";
const cv="Python developer building reliable APIs with FastAPI and PostgreSQL. Developed automated tests and documented deployment procedures. Collaborated with designers to improve customer workflows.";
async function mock(page:Page,fail=false,hold=false){
  let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
  const bodies:CvRequest[]=[];let review:CvReview|null=null,failed=false;
  await page.route("**/api/cv/**",async route=>{
    const r=route.request(),path=new URL(r.url()).pathname;
    if(path.endsWith("session"))return route.fulfill({json:{ready:true}});
    if(r.method()==="DELETE"){review=null;return route.fulfill({status:204});}
    if(r.method()==="POST"){
      const body=r.postDataJSON() as CvRequest;bodies.push(body);
      if(hold)await gate;
      if(fail&&!failed){failed=true;return route.fulfill({status:503,json:{error:"NVIDIA temporarily unavailable. Retry this action."}});}
      review={id:body.operation_id,job_role:body.job_role,source:body.pdf_base64?"pdf":"text",status:"finished",character_count:cv.length,page_count:body.pdf_base64?1:null,created_at:new Date().toISOString(),expires_at:new Date(Date.now()+7*86400000).toISOString(),limitations:["Plain-text extraction cannot assess visual layout.","Do not invent qualifications or experience."],analysis:{summary:"Your backend experience is relevant. Explain the outcomes of your projects.",strengths:[{title:"Relevant backend skills",evidence:"FastAPI and PostgreSQL",recommendation:"Describe one API project.",source_id:body.pdf_base64?"p01_r01_b001":"text_001",source_page:body.pdf_base64?1:null,source_section:"experience"}],weaknesses:[],missing_skills:[{skill:"CI/CD",reason:"Expected in the target role.",evidence_status:"not_evidenced",recommendation:"Add a deployment example only if you have one."}],unclear_descriptions:[],content_errors:[],rewrites:[{original:"Developed automated tests",suggested:"Created automated tests for the application",rationale:"Make the scope clearer."}],practice_plan:["Add a verified project outcome."],extraction:{confidence:body.pdf_base64?"medium":"high",warnings:[],source_block_count:1,page_count:body.pdf_base64?1:null}}};
    }
    return route.fulfill({json:path.endsWith("reviews")&&r.method()==="GET"?{items:review?[review]:[],next_cursor:null}:review});
  });return {bodies,release};
}
test("pasted CV, personalized dashboard, persistence and deletion",async({page},info)=>{
  const {bodies,release}=await mock(page,false,true);await page.goto("/cv-review");
  await page.getByRole("button",{name:"Paste text",exact:true}).click();
  await page.getByLabel("CV text",{exact:true}).fill(cv);await page.getByLabel("Target job role").fill("Python Developer");
  await page.getByLabel("Job description (optional)").fill("Build APIs and maintain CI/CD pipelines.");
  await page.getByRole("button",{name:"Analyze My CV"}).click();await expect(page.getByRole("status")).toContainText("Analyzing");
  await expect(page.getByRole("button",{name:"Analyze My CV"})).toBeDisabled();release();
  await expect(page.getByRole("heading",{name:"Your strengths"})).toBeVisible();
  await expect(page.getByText("Not evidenced",{exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Your next steps"})).toBeVisible();expect(bodies).toHaveLength(1);
  await page.screenshot({path:info.outputPath("cv-results.png"),fullPage:true});
  expect(await page.evaluate(()=>JSON.stringify(sessionStorage))).not.toContain(cv);
  await page.reload();await expect(page.getByRole("heading",{name:"Your strengths"})).toBeVisible();
  await page.getByRole("button",{name:"Delete review",exact:true}).click();await page.getByRole("button",{name:"Confirm deletion"}).click();
  await expect(page.getByRole("button",{name:"Analyze My CV"})).toBeVisible();await expect(page.getByText("Your reviews will appear here for 7 days.")).toBeVisible();
});
test("retry reuses operation ID and preserves original content",async({page})=>{
  const {bodies}=await mock(page,true);await page.goto("/cv-review");await page.getByRole("button",{name:"Paste text",exact:true}).click();await page.getByLabel("CV text",{exact:true}).fill(cv);await page.getByLabel("Target job role").fill("Developer");
  await page.getByRole("button",{name:"Analyze My CV"}).click();await expect(page.getByRole("main").getByRole("alert")).toContainText("NVIDIA temporarily");await expect(page.getByLabel("CV text",{exact:true})).toHaveValue(cv);
  await page.getByRole("button",{name:"Retry analysis"}).click();await expect(page.getByRole("heading",{name:"Your strengths"})).toBeVisible();expect(bodies).toHaveLength(2);expect(bodies[0]).toEqual(bodies[1]);
});
test("PDF upload and unsupported or oversized files",async({page},info)=>{
  const {bodies}=await mock(page);await page.goto("/cv-review");const input=page.getByLabel("Select PDF CV");
  await input.setInputFiles({name:"resume.docx",mimeType:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",buffer:Buffer.from("invalid")});await expect(page.getByRole("main").getByRole("alert")).toContainText("select a PDF");
  await input.setInputFiles({name:"large.pdf",mimeType:"application/pdf",buffer:Buffer.alloc(3*1024*1024+1)});await expect(page.getByRole("main").getByRole("alert")).toContainText("3 MiB");
  await input.setInputFiles({name:"cv.pdf",mimeType:"application/pdf",buffer:Buffer.from("%PDF-1.7 test fixture %%EOF")});await page.getByLabel("Target job role").fill("Developer");
  await page.screenshot({path:info.outputPath("cv-upload.png"),fullPage:true});
  await page.getByRole("button",{name:"Analyze My CV"}).click();await expect(page.getByRole("heading",{name:"Your strengths"})).toBeVisible();expect(bodies[0].pdf_base64).toBeTruthy();expect(bodies[0].cv_text).toBeUndefined();
  await expect(page.getByText(/Source: experience · Page 1/)).toBeVisible();
  await expect(page.getByText(/Reading-order confidence: medium/)).toBeVisible();
});

test("CV proxy protects the session, origin and body size",async({request})=>{
  expect((await request.get("/api/cv/reviews")).status()).toBe(401);
  expect((await request.post("/api/cv/session",{headers:{Origin:"https://untrusted.example"}})).status()).toBe(403);
  const session=await request.post("/api/cv/session",{headers:{Origin:"http://127.0.0.1:3001"}});
  expect(session.status()).toBe(200);expect(session.headers()["set-cookie"]).toContain("HttpOnly");
  expect((await request.delete(`/api/cv/reviews/${crypto.randomUUID()}`,{headers:{Origin:"https://untrusted.example"}})).status()).toBe(403);
  expect((await request.post("/api/cv/reviews",{headers:{Origin:"http://127.0.0.1:3001"},data:{pdf_base64:"A".repeat(4_300_001)}})).status()).toBe(413);
});

