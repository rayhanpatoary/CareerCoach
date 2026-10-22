import type { Metadata } from "next";
import { Navbar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import "./globals.css";
import "./interview.css";
import "./cv.css";
import "./job-fit.css";
export const metadata: Metadata = { title: {default: "AI Career Coach — Your next chapter starts here", template: "%s | AI Career Coach"}, description: "Prepare for your next opportunity with role-specific AI interview questions." };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body><a className="skip" href="#main">Skip to content</a><Navbar/><main id="main">{children}</main><Footer/></body></html>; }
