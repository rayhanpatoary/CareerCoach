import {test,expect,type Page} from "@playwright/test";
import type {JobFitRequest,JobFitReview} from "../types/job-fit";
const cv="Python developer building reliable APIs with FastAPI and SQL Server. Developed automated tests and documented deployment procedures. Collaborated with designers on customer workflows.";
const jd="Python is required for backend development. PostgreSQL is required for relational data. Docker is preferred for packaging services.";
function result(body:JobFitRequest,withheld=false):JobFitReview{
  return {id:body.operation_id,job_role:body.job_role,source:body.pdf_base64?"pdf":"text",status:"finished",character_count:cv.length,page_count:body.pdf_base64?1:null,created_at:new Date().toISOString(),expires_at:new Date(Date.now()+7*86400000).toISOString(),limitations:["Not evidenced does not establish your actual knowledge.","Raw CVs are not stored."],analysis:{company:body.company,language:"en",coverage_complete:!withheld,warnings:[],extraction:{confidence:"high",warnings:[],source_block_count:1,page_count:body.pdf_base64?1:null},score:{overall:withheld?null:53,reason:withheld?"Overall score withheld: job-description coverage is incomplete.":"Equal criterion weights; unused alignment weight is redistributed.",evidence_coverage:66.67,uncertain_share:0,rubric_version:"job-fit-v1",meaning:"Estimated document alignment, not a hiring probability.",categories:[{category:"mandatory",count:2,matched:1,partial:1,not_evidenced:0,uncertain:0,base_weight:60,effective_weight:70.5882,score:75,contribution:52.9412},{category:"preferred",count:1,matched:0,partial:0,not_evidenced:1,uncertain:0,base_weight:25,effective_weight:29.4118,score:0,contribution:0},{category:"alignment",count:0,matched:0,partial:0,not_evidenced:0,uncertain:0,base_weight:15,effective_weight:0,score:null,contribution:0}]},requirements:[{id:"requirement_01",label:"Python",category:"technical",importance:"mandatory",jd_source_id:"jd_001",jd_quote:"Python is required for backend development.",status:"matched",evidence:[{source_id:"text_001",quote:"Python developer building reliable APIs",page:body.pdf_base64?1:null,section:"experience"}],action_kind:"improve_wording",suggested_action:"Describe a Python API project using only actual experience.",explanation:"The quoted CV directly supports Python."},{id:"requirement_02",label:"PostgreSQL",category:"technical",importance:"mandatory",jd_source_id:"jd_002",jd_quote:"PostgreSQL is required for relational data.",status:"partial",evidence:[{source_id:"text_001",quote:"FastAPI and SQL Server",page:null,section:"experience"}],action_kind:"clarify_experience",suggested_action:"Clarify your database work and any actual PostgreSQL usage.",explanation:"SQL Server provides transferable relational database evidence."},{id:"requirement_03",label:"Docker",category:"tools",importance:"preferred",jd_source_id:"jd_003",jd_quote:"Docker is preferred for packaging services.",status:"not_evidenced",evidence:[],action_kind:"develop_skill",suggested_action:"Practice packaging a service with Docker.",explanation:"Docker is not evidenced in the supplied CV."}],improvements:[{horizon:"immediate",requirement_index:0,action:"Explain your Python API project scope."},{horizon:"strengthen",requirement_index:1,action:"Practice PostgreSQL queries."},{horizon:"longer_term",requirement_index:2,action:"Build a Docker practice project."}],rewrites:[]}};
}
async function mock(page:Page,{fail=false,hold=false,withheld=false,denied=false}={}){
  const bodies:JobFitRequest[]=[];let review:JobFitReview|null=null,failed=false;
  let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route("**/api/job-fit/**",async route=>{
    const r=route.request(),path=new URL(r.url()).pathname;
    if(path.endsWith("session"))return route.fulfill({json:{ready:true}});
    if(denied)return route.fulfill({status:404,json:{error:"Job-fit analysis not found or expired."}});
    if(r.method()==="DELETE"){review=null;return route.fulfill({status:204});}
    if(path.endsWith("analyze")){
      const body=r.postDataJSON() as JobFitRequest;bodies.push(body);if(hold)await gate;
      if(fail&&!failed){failed=true;return route.fulfill({status:503,json:{error:"NVIDIA temporarily unavailable. Retry this action."}});}
      review=result(body,withheld);
    }
    return route.fulfill({json:path.endsWith("history")?{items:review?[review]:[],next_cursor:null}:review});
  });return {bodies,release};
}
async function fill(page:Page){
  await page.getByRole("button",{name:"Paste CV text",exact:true}).click();await page.getByLabel("Your CV text",{exact:true}).fill(cv);
  await page.getByLabel("Job title",{exact:true}).fill("Python Developer");await page.getByLabel("Company (optional)").fill("Example Company");
  await page.getByLabel("Target job description").fill(jd);
}

test("complete text comparison, loading, evidence, history and deletion",async({page},info)=>{
  const {bodies,release}=await mock(page,{hold:true});await page.goto("/job-fit");await fill(page);
  const submit=page.getByRole("button",{name:"Analyze My Job Fit"});await submit.click();await expect(submit).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Comparing job requirements");release();
  await expect(page.getByRole("heading",{name:"Your job-fit analysis",exact:true})).toBeVisible();
  await expect(page.locator(".overall-score strong")).toHaveText("53");await expect(page.getByText("Python developer building reliable APIs",{exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:/Skills and evidence gaps/})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Your improvement roadmap"})).toBeVisible();expect(bodies).toHaveLength(1);
  await page.screenshot({path:info.outputPath("job-fit-results.png"),fullPage:true});
  expect(await page.evaluate(()=>JSON.stringify(sessionStorage))).not.toContain(cv);
  expect(await page.evaluate(()=>JSON.stringify(localStorage))).not.toContain(jd);
  await page.reload();await expect(page.locator(".overall-score strong")).toHaveText("53");
  await page.getByRole("link",{name:"Analyze another job",exact:true}).click();
  await expect(page.locator(".cv-history").getByRole("link",{name:/Python Developer/})).toBeVisible();
  await page.locator(".cv-history").getByRole("link",{name:/Python Developer/}).click();
  await page.getByRole("button",{name:"Delete analysis",exact:true}).click();await page.getByRole("button",{name:"Confirm deletion"}).click();
  await expect(page.getByText("Your saved comparisons will appear here.")).toBeVisible();
});

test("retry preserves inputs and request ID",async({page})=>{
  const {bodies}=await mock(page,{fail:true});await page.goto("/job-fit");await fill(page);
  await page.getByRole("button",{name:"Analyze My Job Fit"}).click();await expect(page.getByRole("main").getByRole("alert")).toContainText("NVIDIA temporarily");
  await expect(page.getByLabel("Your CV text",{exact:true})).toHaveValue(cv);await expect(page.getByLabel("Target job description")).toHaveValue(jd);
  await page.getByRole("button",{name:"Retry same analysis"}).click();await expect(page.locator(".overall-score strong")).toHaveText("53");
  expect(bodies).toHaveLength(2);expect(bodies[0]).toEqual(bodies[1]);
});

test("initial history and fast submit share the private-session request",async({page})=>{
  const {bodies}=await mock(page);let sessions=0,release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route("**/api/job-fit/session",async route=>{sessions++;await gate;await route.fulfill({json:{ready:true}});});
  await page.goto("/job-fit");await fill(page);await page.getByRole("button",{name:"Analyze My Job Fit"}).click();
  await expect(page.getByRole("status")).toContainText("Preparing your documents");expect(sessions).toBe(1);release();
  await expect(page.locator(".overall-score strong")).toHaveText("53");expect(bodies).toHaveLength(1);
});

test("PDF validation, required posting, and withheld score",async({page},info)=>{
  const {bodies}=await mock(page,{withheld:true});await page.goto("/job-fit");const input=page.getByLabel("Select PDF CV");
  await input.setInputFiles({name:"resume.docx",mimeType:"application/octet-stream",buffer:Buffer.from("bad")});await expect(page.getByRole("main").getByRole("alert")).toContainText("select a PDF");
  await input.setInputFiles({name:"large.pdf",mimeType:"application/pdf",buffer:Buffer.alloc(3*1024*1024+1)});await expect(page.getByRole("main").getByRole("alert")).toContainText("3 MiB");
  await input.setInputFiles({name:"cv.pdf",mimeType:"application/pdf",buffer:Buffer.from("%PDF-1.7 synthetic fixture %%EOF")});await page.getByLabel("Job title",{exact:true}).fill("Python Developer");
  const submit=page.getByRole("button",{name:"Analyze My Job Fit"});await expect(submit).toBeDisabled();
  await page.getByLabel("Target job description").fill("Too short");await expect(submit).toBeDisabled();await page.getByLabel("Target job description").fill(jd);
  await page.screenshot({path:info.outputPath("job-fit-upload.png"),fullPage:true});await submit.click();
  await expect(page.getByText("Score withheld",{exact:true})).toBeVisible();await expect(page.locator(".overall-score strong")).toHaveText("—");
  expect(bodies[0].pdf_base64).toBeTruthy();expect(bodies[0].cv_text).toBeUndefined();await expect(page.getByText(/CV source text_001 · Page 1/)).toBeVisible();
});

test("interview setup uses only job criteria and respects existing pending interview",async({page})=>{
  await mock(page);await page.goto("/job-fit");await fill(page);await page.getByRole("button",{name:"Analyze My Job Fit"}).click();
  await page.getByRole("button",{name:"Start relevant mock interview"}).click();await expect(page.getByLabel("Target job role")).toHaveValue("Python Developer");
  await expect(page.getByLabel("Experience level")).toHaveValue("intermediate");await expect(page.getByLabel("Interview type")).toHaveValue("mixed");
  await expect(page.getByLabel("Job description")).toContainText("PostgreSQL");
  expect(await page.getByLabel("Job description").inputValue()).not.toContain(cv);
  await page.goBack();await expect(page.getByRole("heading",{name:"Your job-fit analysis",exact:true})).toBeVisible();
  await page.evaluate(()=>sessionStorage.setItem("interview:pending","existing"));
  await page.getByRole("button",{name:"Start relevant mock interview"}).click();await expect(page.getByText("Your existing interview is preserved.")).toBeVisible();
  expect(await page.evaluate(()=>sessionStorage.getItem("interview:pending"))).toBe("existing");
});

test("unauthorized or expired results show useful error",async({page})=>{
  await mock(page,{denied:true});await page.goto(`/job-fit/results/${crypto.randomUUID()}`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("not found or expired");await expect(page.getByRole("button",{name:"Retry loading"})).toBeVisible();
});

test("job-fit proxy protects session, origin, body size and route allowlist",async({request})=>{
  expect((await request.get("/api/job-fit/history")).status()).toBe(401);
  expect((await request.post("/api/job-fit/session",{headers:{Origin:"https://untrusted.example"}})).status()).toBe(403);
  const session=await request.post("/api/job-fit/session",{headers:{Origin:"http://127.0.0.1:3001"}});
  expect(session.status()).toBe(200);expect(session.headers()["set-cookie"]).toContain("HttpOnly");
  expect((await request.delete(`/api/job-fit/${crypto.randomUUID()}`,{headers:{Origin:"https://untrusted.example"}})).status()).toBe(403);
  expect((await request.post("/api/job-fit/analyze",{headers:{Origin:"http://127.0.0.1:3001"},data:{pdf_base64:"A".repeat(4_300_001)}})).status()).toBe(413);
  expect((await request.get("/api/job-fit/not-a-uuid")).status()).toBe(404);
});
