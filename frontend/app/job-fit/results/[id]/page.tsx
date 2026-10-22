import {notFound} from "next/navigation";
import {JobFitResults} from "@/components/job-fit/results";
export const metadata={title:"Your Job-Fit Analysis",robots:{index:false,follow:false}};
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;if(!/^[a-f0-9-]{36}$/i.test(id))notFound();return <JobFitResults id={id}/>;
}
