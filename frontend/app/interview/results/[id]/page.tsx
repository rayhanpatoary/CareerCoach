import { InterviewResults } from "@/components/interview/results";
export const metadata = {title: "Interview Feedback"};
export default async function ResultsPage({params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  return <InterviewResults id={id}/>;
}
