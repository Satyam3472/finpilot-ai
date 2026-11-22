"use client";

import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ErrorState, Skeleton } from "@/components/shared";
import { Shell } from "@/components/shell";
import { useApi } from "@/hooks/use-api";

export function AuthGate({ children }: { children: ReactNode }) {
  const login = usePathname() === "/login";
  const session = useApi<{ csrf_token: string }>(login ? null : "/auth/session");

  useEffect(() => {
    if (login) return;
    const signIn = () => window.location.replace("/login");
    window.addEventListener("finpilot:unauthenticated", signIn);
    return () => window.removeEventListener("finpilot:unauthenticated", signIn);
  }, [login]);

  if (login) return children;
  if (!session.data) return <main className="login-page">
    {session.error ? <ErrorState message={session.error} retry={session.refresh} /> : <Skeleton className="w-full max-w-sm" />}
  </main>;
  return <Shell>{children}</Shell>;
}
