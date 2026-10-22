import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {cookieName,sameOrigin} from "@/lib/interview-proxy";
const MAX_BODY=4_300_000;
export async function proxyAnalysis(request:Request,namespace:"cv"|"job-fit",segments:string[]){
  const uuid=(v:string)=>/^[a-f0-9-]{36}$/i.test(v);
  const allowed=namespace==="cv"?(segments[0]==="reviews"&&segments.length<=2&&(segments.length===1||uuid(segments[1]))):
    segments.length===1&&(["analyze","history"].includes(segments[0])||uuid(segments[0]));
  if(!allowed)
    return NextResponse.json({error:"Unknown analysis route."},{status:404});
  if(request.method!=="GET"&&!sameOrigin(request))return NextResponse.json({error:"Use this site's analysis workspace."},{status:403});
  const credential=(await cookies()).get(cookieName)?.value;
  if(!credential||!/^[A-Za-z0-9_-]{43,128}$/.test(credential))return NextResponse.json({error:"Your private session is missing. Start a review in this browser."},{status:401});
  const base=process.env.BACKEND_API_URL;
  if(!base)return NextResponse.json({error:"The backend URL is not configured."},{status:503});
  let body:string|undefined;
  if(request.method==="POST"){
    if(!request.headers.get("content-type")?.includes("application/json"))return NextResponse.json({error:"Send JSON."},{status:415});
    const reader=request.body?.getReader();
    if(!reader)return NextResponse.json({error:"Provide a CV."},{status:400});
    const chunks:Uint8Array[]=[];let size=0;
    while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;
      if(size>MAX_BODY){await reader.cancel();return NextResponse.json({error:"Choose a PDF no larger than 3 MiB."},{status:413});}chunks.push(part.value);}
    const buffer=new Uint8Array(size);let offset=0;for(const chunk of chunks){buffer.set(chunk,offset);offset+=chunk.length;}
    body=new TextDecoder().decode(buffer);
    try{JSON.parse(body);}catch{return NextResponse.json({error:"Send valid JSON."},{status:400});}
  }
  const query=new URL(request.url).searchParams,forward=new URLSearchParams();
  for(const key of ["limit","cursor"])if(query.has(key))forward.set(key,query.get(key)!);
  try{
    const upstream=await fetch(`${base.replace(/\/$/,"")}/api/${namespace}/${segments.join("/")}${forward.size?`?${forward}`:""}`,{
      method:request.method,headers:{"Content-Type":"application/json",Authorization:`Bearer ${credential}`},body,
      cache:"no-store",redirect:"error",signal:AbortSignal.timeout(70000)});
    const headers={"Cache-Control":"no-store",...(upstream.headers.has("retry-after")?{"Retry-After":upstream.headers.get("retry-after")!}:{})};
    if(upstream.status===204)return new NextResponse(null,{status:204,headers});
    const data:unknown=await upstream.json();
    if(!upstream.ok){const detail=data&&typeof data==="object"&&"detail" in data?data.detail:null;
      return NextResponse.json({error:typeof detail==="string"&&detail.length<600?detail:"The analysis request could not be accepted. Check your input and retry."},{status:upstream.status,headers});}
    return NextResponse.json(data,{headers});
  }catch{return NextResponse.json({error:"The analysis service could not respond in time. Retry the same action to recover safely."},{status:503});}
}

