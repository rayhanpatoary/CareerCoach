"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, Sparkles } from "lucide-react";
export function Navbar() {
  const path = usePathname();
  return <header className="header"><nav className="shell nav" aria-label="Main navigation"><Link href="/" className="brand"><span className="brand-icon"><Sparkles size={20}/></span>AI Career Coach<span className="beta">BETA</span></Link><div className="nav-links">{[["/", "Overview"], ["/interview", "Mock Interview"], ["/cv-review", "CV Reviewer"]].map(([href,label]) => <Link key={href} href={href} aria-current={path === href ? "page" : undefined} className={path === href ? "active" : ""}>{label}</Link>)}</div><Link href="/interview" className="nav-cta">Let’s practice <ArrowUpRight size={16}/></Link></nav></header>;
}
