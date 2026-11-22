"use client";

import {
  Activity, ArrowDownUp, ChevronRight, ChartNoAxesCombined, FileUp, LogOut,
  LayoutDashboard, Menu, PanelTop, ShieldCheck, Sparkles, WalletCards,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { toast, Toaster } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

const sections = [
  { title: "WORKSPACE", items: [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/transactions", label: "Transactions", icon: ArrowDownUp },
    { href: "/imports", label: "Import statements", icon: FileUp },
  ] },
  { title: "INTELLIGENCE", items: [
    { href: "/budgets", label: "Budgets", icon: WalletCards },
    { href: "/analytics", label: "Analytics", icon: ChartNoAxesCombined },
    { href: "/assistant", label: "AI Assistant", icon: Sparkles },
  ] },
];

function Brand() {
  return <Link className="brand" href="/dashboard">
    <span className="brand-mark"><Activity size={21} strokeWidth={2.6} aria-hidden="true" /></span>
    <span>FinPilot<span className="brand-accent"> AI</span></span>
  </Link>;
}

function Navigation({ path, close }: { path: string; close?: () => void }) {
  return <nav aria-label="Main navigation" className="navigation">
    {sections.map((section) => <div className="nav-section" key={section.title}>
      <p>{section.title}</p>
      {section.items.map(({ href, label, icon: Icon }) => (
        <Link key={href} href={href} onClick={close} className="nav-item" aria-current={path === href ? "page" : undefined}>
          <Icon size={18} strokeWidth={1.8} aria-hidden="true" /> <span>{label}</span>
        </Link>
      ))}
    </div>)}
  </nav>;
}

function WorkspaceFooter() {
  return <div className="sidebar-footer">
    <span className="workspace-icon"><ShieldCheck size={18} aria-hidden="true" /></span>
    <span><strong>Local workspace</strong><small>Single-user development</small></span>
  </div>;
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [drawer, setDrawer] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  async function signOut() {
    setSigningOut(true);
    try {
      await api("/auth/logout", { method: "POST" });
      window.location.replace("/login");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Sign-out failed.");
      setSigningOut(false);
    }
  }
  const current = sections.flatMap((section) => section.items).find((item) => item.href === path);
  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="desktop-sidebar">
      <Brand /><Navigation path={path} /><WorkspaceFooter />
    </aside>
    <div className="shell-main">
      <header className="topbar">
        <div className="breadcrumb">
          <Dialog open={drawer} onOpenChange={setDrawer}>
            <DialogTrigger asChild><Button className="mobile-menu" size="icon" variant="ghost" aria-label="Open navigation"><Menu size={22} /></Button></DialogTrigger>
            <DialogContent className="drawer">
              <DialogTitle>FinPilot AI</DialogTitle>
              <DialogDescription className="sr-only">Navigate your local finance workspace</DialogDescription>
              <Navigation path={path} close={() => setDrawer(false)} /><WorkspaceFooter />
            </DialogContent>
          </Dialog>
          <PanelTop size={17} aria-hidden="true" className="breadcrumb-icon" />
          <span className="breadcrumb-root">Workspace</span><ChevronRight size={14} aria-hidden="true" className="breadcrumb-divider" />
          <strong>{current?.label ?? "Dashboard"}</strong>
        </div>
        <div className="topbar-actions">
          <span className="topbar-local"><ShieldCheck size={16} aria-hidden="true" /> Local mode</span>
          <Button variant="ghost" size="icon" aria-label="Sign out" disabled={signingOut} onClick={signOut}><LogOut size={17} /></Button>
        </div>
      </header>
      <main id="main-content" className="content">{children}</main>
    </div>
    <Toaster position="bottom-right" richColors closeButton />
  </div>;
}
