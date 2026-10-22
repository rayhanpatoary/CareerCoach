"use client";
import {Upload,FileText} from "lucide-react";
import {MAX_CV_PDF_BYTES} from "@/types/cv";

interface Props {disabled?:boolean;mode:"pdf"|"text";setMode:(v:"pdf"|"text")=>void;file:File|null;setFile:(v:File|null)=>void;text:string;setText:(v:string)=>void;onError:(v:string)=>void}
export function ResumeInput({disabled,mode,setMode,file,setFile,text,setText,onError}:Props){
  function choose(value?:File){
    if(disabled)return;
    onError("");setFile(null);if(!value)return;
    if(!value.name.toLowerCase().endsWith(".pdf")||(value.type&&value.type!=="application/pdf")){onError("Please select a PDF file.");return;}
    if(value.size>MAX_CV_PDF_BYTES){onError("Choose a PDF no larger than 3 MiB.");return;}setFile(value);
  }
  return <div><div className="cv-tabs"><button type="button" aria-pressed={mode==="pdf"} onClick={()=>setMode("pdf")}>Upload PDF</button><button type="button" aria-pressed={mode==="text"} onClick={()=>setMode("text")}>Paste CV text</button></div>
    {mode==="pdf"?<><label className="upload" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();choose(e.dataTransfer.files[0]);}}><Upload size={26}/><strong>Choose your CV</strong><span>Browse or drop a PDF here</span><small>Up to 3 MiB · 10 pages · selectable text</small><input type="file" aria-label="Select PDF CV" accept=".pdf,application/pdf" onChange={e=>choose(e.target.files?.[0])}/></label>{file&&<p className="selected-file"><FileText size={18}/>{file.name}<button type="button" aria-label="Remove selected CV" onClick={()=>setFile(null)}>Remove</button></p>}</>:<><label htmlFor="job-fit-cv">Your CV text</label><textarea id="job-fit-cv" required minLength={100} maxLength={30000} rows={10} value={text} onChange={e=>setText(e.target.value)} placeholder="Paste your experience, projects, education and skills…"/><p className="field-help">{text.length.toLocaleString()} / 30,000 characters · minimum 100</p></>}
  </div>;
}
