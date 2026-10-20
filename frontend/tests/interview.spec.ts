import { test, expect, type Page } from "@playwright/test";
import { type InterviewState, type Evaluation } from "../types/interview";

async function mockInterview(page: Page, failAnswer = false) {
  let state: InterviewState;
  let failed = false;
  const operations = new Set<string>(), answerIds: string[] = [];
  await page.route("**/api/interview/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname.split("/").slice(3);
    const body = request.method() === "POST" && request.postData() ? request.postDataJSON() : {};
    if (path[0] === "session") return route.fulfill({json: {ready: true}});
    if (path[0] === "start") {
      await new Promise(resolve => setTimeout(resolve, 150));
      state = {...body, id: body.operation_id, status:"in_progress", question:"How do Python lists and tuples differ?", turns:[], answered_count:0,
        started_at:new Date().toISOString(), completed_at:null, expires_at:"2027-01-01T00:00:00Z", feedback:null, busy:false};
      state.turns.push({id:crypto.randomUUID(), position:1, question:state.question!, answer:null, asked_at:state.started_at, answered_at:null});
    } else if (path[1] === "answer") {
      answerIds.push(body.operation_id);
      if (failAnswer && !failed) {failed = true; return route.fulfill({status:503, json:{error:"NVIDIA is temporarily unavailable. Retry this action."}});}
      if (!operations.has(body.operation_id)) {
        operations.add(body.operation_id);
        state.turns.at(-1)!.answer = body.answer; state.turns.at(-1)!.answered_at = new Date().toISOString();
        state.answered_count++;
        if (state.answered_count === state.question_count) {state.status = "completed"; state.question = null;}
        else {state.question = `Question ${state.answered_count+1}: Can you describe a practical tuple use case?`; state.turns.push({id:crypto.randomUUID(), position:state.answered_count+1, question:state.question, answer:null, asked_at:new Date().toISOString(), answered_at:null});}
      }
    } else if (path[1] === "finish") {
      const feedback: Evaluation = {overall_score:66, evidence_coverage:100, partial:state.answered_count < state.question_count, answered_count:state.answered_count,
        summary:"You explained mutability clearly. Add practical examples to show depth.",
        strengths:["Correctly distinguished mutable lists from tuples."], improvements:["Demonstrate a concrete coordinate tuple."],
        knowledge_gaps:["Hashability of nested values."], recommendations:["Explain which tuples work as dictionary keys."],
        practice_plan:["Write two practical list and tuple examples."], rubric:{accuracy:35,clarity:20,reasoning:20,completeness:15,depth:10},
        categories:{accuracy:{score:80,evidence:"Correct mutability distinction."},clarity:{score:70,evidence:"Clear explanation."},reasoning:{score:60,evidence:"Some rationale."},completeness:{score:50,evidence:"Missing examples."},depth:{score:40,evidence:"Limited practical depth."}},
        reviews:state.turns.filter(t => t.answer !== null).map(t => ({question_id:t.id,effective:"Correct description of mutability.",missing:"A practical example.",improvement:"Show a coordinate pair.",example_answer:"A tuple can represent a fixed coordinate pair."}))};
      if (!state.answered_count) {
        feedback.overall_score = null; feedback.evidence_coverage = 0; feedback.summary = "There are no submitted answers to evaluate.";
        feedback.strengths = []; feedback.improvements = []; feedback.knowledge_gaps = []; feedback.recommendations = [];
        feedback.practice_plan = ["Start a new interview and submit an answer."];
        for (const category of Object.values(feedback.categories)) {category.score = null; category.evidence = "No answers submitted.";}
      }
      state = {...state, status:"finished", feedback, completed_at:new Date().toISOString()};
    } else if (request.method() === "DELETE") return route.fulfill({status:204});
    return route.fulfill({json: state!});
  });
  return {answerIds};
}

test("complete interview, progress, dashboard, saved results and retry configuration", async ({page}, testInfo) => {
  await mockInterview(page); await page.goto("/interview");
  await page.getByLabel("Number of questions").selectOption("3");
  await page.getByLabel("Interview type").selectOption("mixed");
  await page.getByLabel("Job description").fill("Build Python APIs with PostgreSQL.");
  await page.screenshot({path:testInfo.outputPath("setup.png"), fullPage:true});
  await page.getByRole("button", {name:"Start Interview", exact:true}).click();
  await expect(page.getByRole("button", {name:"Preparing your interview…"})).toBeDisabled();
  await expect(page.getByText("How do Python lists and tuples differ?", {exact:true})).toBeVisible();
  for (let i=0;i<3;i++) {
    await page.getByLabel("Your answer", {exact:true}).fill(`Lists are mutable; tuples are immutable. Example ${i}.`);
    await page.getByRole("button", {name:"Submit Answer"}).click();
    await expect(page.getByText(`${i+1} of 3 answered`, {exact:false})).toBeVisible();
  }
  await expect(page.getByLabel("Interview progress")).toHaveAttribute("value", "3");
  await page.getByRole("button", {name:"Get my feedback"}).click();
  await expect(page).toHaveURL(/\/interview\/results\//);
  await expect(page.getByText("66", {exact:true})).toBeVisible();
  await expect(page.getByRole("heading", {name:"Performance breakdown"})).toBeVisible();
  await page.getByText(/^Question 1: /).click();
  await expect(page.getByText("Lists are mutable; tuples are immutable. Example 0.", {exact:true})).toBeVisible();
  await page.screenshot({path:testInfo.outputPath("results.png"), fullPage:true});
  await page.reload(); await expect(page.getByText("66", {exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Retry Interview", exact:true}).click();
  await expect(page.getByLabel("Number of questions")).toHaveValue("3");
  await expect(page.getByLabel("Interview type")).toHaveValue("mixed");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("answer failure preserves draft, safe retry reuses operation, refresh resumes", async ({page}) => {
  const {answerIds} = await mockInterview(page, true); await page.goto("/interview");
  await page.getByRole("button", {name:"Start Interview", exact:true}).click();
  await page.getByLabel("Your answer", {exact:true}).fill("Lists are mutable, tuples are immutable.");
  await page.getByRole("button", {name:"Submit Answer"}).click();
  await expect(page.getByRole("alert", {name:"Interview error"})).toContainText("temporarily unavailable");
  await expect(page.getByLabel("Your answer", {exact:true})).toHaveValue("Lists are mutable, tuples are immutable.");
  await page.reload();
  await page.getByRole("button", {name:"Retry last action"}).click();
  await expect(page.getByText("1 of 5 answered", {exact:false})).toBeVisible();
  expect(answerIds).toHaveLength(2); expect(answerIds[0]).toBe(answerIds[1]);
  await expect(page.getByLabel("Your answer", {exact:true})).toHaveValue("");
  await page.getByRole("button", {name:"Finish Interview", exact:true}).click();
  await expect(page.getByText(/PARTIAL INTERVIEW/)).toBeVisible();
});

test("custom role validation and draft recovery", async ({page}) => {
  let starts = 0;
  await mockInterview(page); page.on("request", req => {if(req.url().endsWith("/api/interview/start")) starts++;});
  await page.goto("/interview"); await page.getByLabel("Target job role").selectOption("Custom role");
  await page.getByRole("button", {name:"Start Interview", exact:true}).click(); expect(starts).toBe(0);
  await page.getByLabel("Your job role").fill("Platform Engineer");
  await page.getByRole("button", {name:"Start Interview", exact:true}).click();
  await page.getByLabel("Your answer", {exact:true}).fill("My unfinished draft");
  await page.reload(); await expect(page.getByLabel("Your answer", {exact:true})).toHaveValue("My unfinished draft");
});

test("finish without answers shows no score and deletion returns to setup", async ({page}) => {
  await mockInterview(page); await page.goto("/interview");
  await page.getByRole("button", {name:"Start Interview", exact:true}).click();
  await page.getByRole("button", {name:"Finish Interview", exact:true}).click();
  await expect(page.getByText("Insufficient evidence", {exact:true})).toBeVisible();
  await expect(page.getByText("There are no submitted answers to evaluate.", {exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Delete interview data"}).click();
  await page.getByRole("button", {name:"Confirm deletion"}).click();
  await expect(page.getByRole("button", {name:"Start Interview", exact:true})).toBeEnabled();
});

test("session proxy rejects cross-origin changes and protects missing credentials", async ({request}) => {
  const privateRead = await request.get(`/api/interview/${crypto.randomUUID()}`);
  expect(privateRead.status()).toBe(401);
  const crossOrigin = await request.post("/api/interview/session", {headers:{Origin:"https://untrusted.example"}});
  expect(crossOrigin.status()).toBe(403);
  const session = await request.post("/api/interview/session", {headers:{Origin:"http://127.0.0.1:3001"}});
  expect(session.status()).toBe(200);
  expect(session.headers()["set-cookie"]).toContain("HttpOnly");
  expect(session.headers()["set-cookie"]).toContain("SameSite=strict");
  const forbidden = await request.delete(`/api/interview/${crypto.randomUUID()}`, {headers:{Origin:"https://untrusted.example"}});
  expect(forbidden.status()).toBe(403);
  const oversized = await request.post("/api/interview/start", {data:{job_role:"x".repeat(40001)}});
  expect(oversized.status()).toBe(413);
});
