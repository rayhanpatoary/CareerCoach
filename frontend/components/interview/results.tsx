"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, LoaderCircle } from "lucide-react";
import { save, sessionRequest } from "@/lib/interview-session";
import { categoryLabels, type CategoryKey, type InterviewState } from "@/types/interview";
export function InterviewResults({id}: {id: string}) {
  const router = useRouter();
  const [state, setState] = useState<InterviewState | null>(null);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false), [confirmDelete, setConfirmDelete] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    sessionRequest(id).then(value => {if (alive) {setState(value); if (value.status === "finished") {save(`draft:${id}`, null); save("pending", null);}}}).catch(e => {if (alive) setError(e.message);});
    return () => {alive = false;};
  }, [id, attempt]);
  function startNew(retry: boolean) {
    save("active", null); save("pending", null);
    if (!retry) save("configuration", null);
    else if (state) save("configuration", JSON.stringify({job_role: state.job_role, difficulty: state.difficulty, interview_type: state.interview_type, question_count: state.question_count, job_description: state.job_description}));
    router.push("/interview");
  }
  async function remove() {
    setDeleting(true); setError("");
    try {
      const response = await fetch(`/api/interview/${id}`, {method: "DELETE"});
      if (!response.ok) throw new Error("Could not delete the interview. Please retry.");
      save(`draft:${id}`, null); startNew(false);
    } catch (e) {setError(e instanceof Error ? e.message : "Deletion failed.");} finally {setDeleting(false);}
  }
  const feedback = state?.feedback;
  return <div className="shell page-content results-page"><p className="eyebrow">YOUR NEXT STEP, MADE CLEARER</p><h1 className="page-title">Turn practice into progress.</h1>
    {error && <div role="alert" className="error interview-error">{error} <button className="text-button" onClick={() => {setError(""); setAttempt(v => v + 1);}}>Retry loading</button></div>}
    {!state && !error && <div className="panel loading-panel" role="status"><LoaderCircle className="spin"/> Loading your saved feedback…</div>}
    {state && !feedback && <div className="panel completion-card"><h2>Your feedback is not ready yet.</h2><p>Return to the interview to finish and request your evaluation.</p><button className="button primary" onClick={() => {save("active", id); router.push("/interview");}}>Return to interview</button></div>}
    {state && feedback && <><p className="page-description">{state.job_role} · {state.difficulty} · {state.interview_type} interview</p>
      <section className="panel score-card"><div className="overall-score"><strong>{feedback.overall_score ?? "—"}</strong><span>{feedback.overall_score === null ? "Insufficient evidence" : "out of 100"}</span></div><div><p className="eyebrow">{feedback.partial ? "PARTIAL INTERVIEW" : "INTERVIEW COMPLETE"} · {feedback.answered_count} ANSWERS</p><h2>Your performance, in perspective.</h2><p>{feedback.summary}</p><small className="muted">Coaching estimates, not objective measures of employability. Scored evidence covers {feedback.evidence_coverage}% of the rubric.</small></div></section>
      <section className="panel results-section"><h2>Performance breakdown</h2><p className="field-help">Weights: 35% role accuracy or behavioral judgment, 20% clarity, 20% reasoning, 15% completeness, 10% depth. Criteria with insufficient evidence are excluded and remaining weights are normalized.</p><div className="category-grid">{(Object.keys(categoryLabels) as CategoryKey[]).map(key => <div className="category" key={key}><div className="category-title"><h3>{key === "accuracy" && state.interview_type === "behavioral" ? "Role-relevant judgment & behavior" : categoryLabels[key]}</h3><strong>{feedback.categories[key].score ?? "N/A"}</strong></div><progress max={100} value={feedback.categories[key].score ?? 0} aria-label={categoryLabels[key]}/><p>{feedback.categories[key].evidence}</p></div>)}</div></section>
      <div className="results-grid"><FeedbackList title="Build on your strengths" items={feedback.strengths}/><FeedbackList title="Your improvement opportunities" items={feedback.improvements}/><FeedbackList title="Knowledge & skill gaps" items={feedback.knowledge_gaps}/><FeedbackList title="Preparation recommendations" items={feedback.recommendations}/></div>
      <section className="panel results-section"><p className="eyebrow">FOCUS YOUR NEXT PRACTICE</p><h2>Your prioritized practice plan</h2><ol className="practice-plan">{feedback.practice_plan.map((item,i) => <li key={i}>{item}</li>)}</ol></section>
      <section id="answers" className="panel results-section"><h2>Question-by-question review</h2><p className="field-help">Open an answer to explore the evidence and a stronger approach.</p>{feedback.reviews.map(review => {const turn = state.turns.find(t => t.id === review.question_id); return <details className="answer-review" key={review.question_id}><summary>Question {turn?.position}: {turn?.question}</summary><div><h3>Your submitted answer</h3><p className="submitted-answer">{turn?.answer}</p><h3>What worked</h3><p>{review.effective}</p><h3>What was missing</h3><p>{review.missing}</p><h3>A stronger approach</h3><p>{review.improvement}</p>{review.example_answer && <><h3>Example stronger answer</h3><p>{review.example_answer}</p><small className="muted">A hypothetical example. Adapt it to your own knowledge and experience.</small></>}</div></details>;})}{!feedback.reviews.length && <p className="field-help">No answers were submitted for review.</p>}</section>
      <div className="results-actions"><button className="button primary" onClick={() => startNew(false)}>Start New Interview <ArrowUpRight size={17}/></button><button className="button secondary" onClick={() => startNew(true)}>Retry Interview</button><a className="button secondary" href="#answers">Review Previous Answers</a></div>
      <div className="retention-note"><p>Available in this browser until {new Date(state.expires_at).toLocaleDateString()}. Interviews expire after seven days. You can delete this interview and its feedback now.</p>{confirmDelete ? <div className="results-actions"><span>Delete all questions, answers and feedback?</span><button className="button secondary" disabled={deleting} onClick={() => void remove()}>{deleting ? "Deleting…" : "Confirm deletion"}</button><button className="text-button" onClick={() => setConfirmDelete(false)}>Cancel</button></div> : <button className="text-button" onClick={() => setConfirmDelete(true)}>Delete interview data</button>}</div>
    </>}
  </div>;
}
function FeedbackList({title, items}: {title: string; items: string[]}) {
  return <section className="panel results-section"><h2>{title}</h2>{items.length ? <ul>{items.map((item,i) => <li key={i}>{item}</li>)}</ul> : <p className="field-help">Not enough evidence to identify a specific finding.</p>}</section>;
}
