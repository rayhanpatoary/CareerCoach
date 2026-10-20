// Explicit opt-in live verification, never included in CI. No API mocks.
// Uses only same-origin browser APIs; all provider/database secrets stay in FastAPI.
import { chromium } from "@playwright/test";
import { randomUUID, randomBytes } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const base = process.env.LIVE_FRONTEND_URL ?? "http://127.0.0.1:3011";
const backend = process.env.LIVE_BACKEND_URL ?? "http://127.0.0.1:8011";
const output = path.resolve("test-results/live");
const resume = process.argv.includes("--resume");
const browser = await chromium.launch();
const context = await browser.newContext({viewport:{width:1440,height:1000},
  ...(resume ? {storageState:path.join(output,"browser-state.json")} : {})});
if (resume) {
  const tab = JSON.parse(await readFile(path.join(output,"tab-state.json"), "utf8"));
  await context.addInitScript(values => {
    if (!sessionStorage.getItem("liveVerificationRestored")) {
      for (const [key,value] of Object.entries(values)) sessionStorage.setItem(key,value);
      sessionStorage.setItem("liveVerificationRestored", "true");
    }
  }, tab);
}
const page = await context.newPage();
page.setDefaultTimeout(15000);
let stage = "setup";
const report = resume ? JSON.parse(await readFile(path.join(output,"report.json"), "utf8")) :
  {started_at:new Date().toISOString(), questions:[], checks:{}, timings_ms:{}};
delete report.error; delete report.failed_stage;
function assert(condition, message) {if (!condition) throw new Error(message);}
async function resultAfter(action, suffix, allowRecovery = true) {
  const started = Date.now();
  const responsePromise = page.waitForResponse(response => response.request().method() === "POST" &&
    new URL(response.url()).pathname.endsWith(suffix), {timeout:85000});
  await action(); const response = await responsePromise;
  const data = await response.json();
  if (allowRecovery && response.status() === 409 && typeof data.error === "string" && data.error.includes("still processing")) {
    // The deliberately injected duplicate can win the race. Recover through the
    // real UI with the same operation ID; it reads the winner's committed result.
    report.checks.concurrent_loser_recovered = true;
    const recovered = await resultAfter(() => page.getByRole("button", {name:"Retry last action"}).click(), suffix, false);
    report.timings_ms[stage] = Date.now()-started;
    return recovered;
  }
  assert(response.ok(), `${stage} failed with HTTP ${response.status()}: ${typeof data.error === "string" ? data.error : "invalid response"}`);
  report.timings_ms[stage] = Date.now()-started;
  return {data, payload:response.request().postDataJSON()};
}
function answerFor(question) {
  if (/sort|even|integer|write a.*function/i.test(question)) return "I would build a new result without changing the input. For the requested restriction I can use insertion sort on the even values:\n\ndef sorted_evens(values):\n    result = []\n    for value in values:\n        if value % 2 == 0:\n            position = len(result)\n            result.append(value)\n            while position > 0 and result[position - 1] > value:\n                result[position] = result[position - 1]\n                position -= 1\n            result[position] = value\n    return result\n\nThis preserves duplicate even values, handles negative integers and returns an empty list when none qualify. For k even values it uses O(k^2) time in the worst case and O(k) additional space. I would test empty input, already sorted values, reverse order and duplicates. If built-in sorting were allowed, sorted would normally be clearer and faster for large inputs.";
  if (/copy|alias|nested/i.test(question)) return "A shallow copy creates a new outer collection but retains references to nested objects. For nested lists, list.copy() prevents top-level append changes from affecting the original, but editing an inner list still changes the shared object. I use copy.deepcopy when independent nested values are required, and I test that the original remains unchanged. Immutable elements can safely be shared.";
  if (/dict|hash|key|set/i.test(question)) return "Dictionary keys and set elements must be hashable, with stable hash and equality semantics. An immutable tuple containing only hashable values, such as (latitude, longitude), works as a key; a tuple containing a list does not. A list is mutable and unhashable. Dictionary lookups are average O(1), though collisions can make the worst case linear. I would use a dictionary to index records by a stable identifier.";
  if (/tuple|list|mutab|collection|sequence/i.test(question)) return "Lists are mutable sequences: I can append, remove or replace elements. Tuples are immutable sequences: their item references cannot be reassigned, although a mutable object inside a tuple can still change. I use a list for a growing batch of API results and a tuple for a fixed coordinate pair. A tuple is hashable only when every element is hashable. Both support indexing and iteration. I choose based on the data's intended semantics rather than assuming tuples are always faster.";
  if (/exception|error|validat/i.test(question)) return "I validate inputs at the API boundary, catch specific expected exceptions and preserve useful error context without exposing secrets. For a collection lookup I handle an absent key explicitly rather than swallowing all exceptions. I test valid inputs, boundary cases, malformed values and failure recovery. A failed operation should leave durable state unchanged, or clearly record a recoverable intermediate state.";
  return "I would clarify the expected inputs, outputs and constraints before selecting a solution. For Python collection processing I choose a dictionary for keyed lookup, a list for an ordered mutable sequence, and a tuple for a fixed grouping. I explain the trade-offs, test empty and malformed inputs, and measure performance with representative data instead of assuming an optimization helps. I have not demonstrated every detail of this topic here, so I would verify uncertain claims with documentation and a small executable example.";
}
try {
  await mkdir(output, {recursive:true});
  await page.goto(`${base}/interview`, {waitUntil:"networkidle", timeout:60000});
  let state;
  if (resume) {
    const response = await context.request.get(`${base}/api/interview/${report.interview_id}`);
    assert(response.ok(), "Cannot resume the saved verification credential"); state = await response.json();
    const savedAction = await page.evaluate(() => sessionStorage.getItem("interview:pending"));
    if (savedAction && JSON.parse(savedAction).path.endsWith("/answer")) {
      stage = `answer_${state.answered_count+1}`;
      const recovered = await resultAfter(() => page.getByRole("button", {name:"Retry last action"}).click(), "/answer");
      state = recovered.data;
      if (state.turns.length > report.questions.length) report.questions.push(state.turns.at(-1).question);
    }
  } else {
    await page.getByLabel("Number of questions").selectOption("3");
    await page.getByLabel("Interview type").selectOption("technical");
    await page.getByLabel("Job description").fill("Automated live verification interview. Focus on Python lists, tuples, dictionaries, mutability, hashability and practical collection choices. This record contains synthetic practice answers, not a real applicant's personal information.");
    stage = "start";
    ({data:state} = await resultAfter(() => page.getByRole("button", {name:"Start Interview", exact:true}).click(), "/start"));
    report.interview_id = state.id;
    assert(state.turns.length === 1, "Expected one real first question");
    report.questions.push(state.turns[0].question);
    console.log(JSON.stringify({stage, question:state.turns[0].question, elapsed_ms:report.timings_ms[stage]}));
  }
  for (let index=state.answered_count; index<3; index++) {
    const question = state.turns.at(-1);
    stage = `answer_${index+1}`;
    await page.getByLabel("Your answer", {exact:true}).fill(answerFor(question.question));
    const operation = await resultAfter(async () => {
      const requestPromise = page.waitForRequest(request => request.method() === "POST" && request.url().endsWith("/answer"));
      await page.getByRole("button", {name:"Submit Answer"}).click();
      const request = await requestPromise;
      if (index === 0) {
        const duplicate = await context.request.post(`${base}/api/interview/${state.id}/answer`, {
          data:request.postDataJSON(), headers:{Origin:base}, timeout:75000});
        assert([200,409].includes(duplicate.status()), "Concurrent duplicate failed unexpectedly");
        report.checks.concurrent_duplicate_status = duplicate.status();
      }
    }, "/answer");
    state = operation.data;
    assert(state.answered_count === index+1, "Answer count drifted");
    const ids = state.turns.map(turn => turn.id);
    const replay = await context.request.post(`${base}/api/interview/${state.id}/answer`, {data:operation.payload, headers:{Origin:base}});
    assert(replay.ok(), "Idempotent replay failed");
    assert(JSON.stringify((await replay.json()).turns.map(turn => turn.id)) === JSON.stringify(ids), "Replay duplicated a question");
    if (index < 2) {
      report.questions.push(state.turns.at(-1).question);
      console.log(JSON.stringify({stage, next_question:state.turns.at(-1).question, elapsed_ms:report.timings_ms[stage]}));
    }
  }
  assert(["completed","finished"].includes(state.status) && state.turns.length === 3, "Configured completion failed");
  report.checks.three_answers_and_questions = true;
  const closed = await context.request.post(`${base}/api/interview/${state.id}/answer`, {
    data:{operation_id:randomUUID(),question_id:state.turns.at(-1).id,answer:"Must be rejected."},headers:{Origin:base}});
  assert(closed.status() === 409, "Completed interview accepted another answer");
  report.checks.completed_answer_rejected = true;
  stage = "finish";
  const finishButton = page.getByRole("button", {name:await page.getByRole("button", {name:"Retry last action"}).count() ? "Retry last action" : "Get my feedback"});
  const finished = state.status === "finished" ? {data:state,payload:{operation_id:randomUUID()}} :
    await resultAfter(() => finishButton.click(), "/finish");
  state = finished.data;
  assert(state.status === "finished" && state.feedback.reviews.length === 3, "Evaluation was not completed");
  const replayFinish = await context.request.post(`${base}/api/interview/${state.id}/finish`, {data:finished.payload,headers:{Origin:base}});
  assert(replayFinish.ok() && JSON.stringify((await replayFinish.json()).feedback) === JSON.stringify(state.feedback), "Final evaluation changed on retry");
  await page.waitForURL(`**/interview/results/${state.id}`, {timeout:20000});
  await page.getByRole("heading", {name:"Performance breakdown"}).waitFor();
  await page.reload({waitUntil:"networkidle"});
  await page.getByRole("heading", {name:"Performance breakdown"}).waitFor();
  report.checks.results_reload = true;
  const persisted = await context.request.get(`${base}/api/interview/${state.id}`);
  assert(persisted.ok() && (await persisted.json()).answered_count === 3, "Persisted state could not be reloaded");
  const feedback = await context.request.get(`${base}/api/interview/${state.id}/feedback`);
  assert(feedback.ok() && JSON.stringify(await feedback.json()) === JSON.stringify(state.feedback), "Feedback GET changed the stored evaluation");
  const denied = await context.request.get(`${backend}/api/interview/${state.id}`, {headers:{Authorization:`Bearer ${randomBytes(32).toString("base64url")}`}});
  assert(denied.status() === 404, "An unrelated anonymous owner accessed the interview");
  report.checks.ownership_isolation = true;
  const categories = state.feedback.categories, weights = state.feedback.rubric;
  const scored = Object.keys(weights).filter(key => categories[key].score !== null);
  const coverage = scored.reduce((total,key) => total+weights[key], 0);
  const expected = coverage ? Math.round(scored.reduce((total,key) => total+weights[key]*categories[key].score, 0)/coverage) : null;
  assert(state.feedback.overall_score === expected, "Weighted score mismatch");
  report.checks.weighted_score = true; report.overall_score = state.feedback.overall_score;
  report.checks.idempotent_answers_and_feedback = true;
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({path:path.join(output,"results.png"), fullPage:true});
  await page.getByRole("button", {name:"Start New Interview",exact:true}).click();
  await page.getByRole("button", {name:"Start Interview",exact:true}).waitFor();
  report.checks.new_interview_setup = true;
  report.status = "passed";
} catch (error) {
  report.status = "failed"; report.failed_stage = stage;
  report.error = error instanceof Error ? error.message.slice(0,700) : "Verification failed";
  process.exitCode = 1;
} finally {
  report.completed_at = new Date().toISOString();
  if (report.status === "failed") {
    // Standard Playwright auth artifacts: local/ignored, never printed or committed.
    await context.storageState({path:path.join(output,"browser-state.json")});
    await writeFile(path.join(output,"tab-state.json"), JSON.stringify(await page.evaluate(() => Object.fromEntries(Object.entries(sessionStorage)))));
  }
  await writeFile(path.join(output,"report.json"), JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  await browser.close();
}
