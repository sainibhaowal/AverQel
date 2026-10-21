"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import AverQelLoading from "@/app/components/ui/AverQelLoading";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/auth/login");
    }
  }, [user, loading, router]);

  if (loading) {
    return <AverQelLoading label="Checking your session…" size="page" />;
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}
