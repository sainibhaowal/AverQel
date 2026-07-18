"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SecurityRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard/settings/privacy");
  }, [router]);

  return (
    <div className="flex h-[50vh] items-center justify-center">
      <div className="text-muted-foreground flex flex-col items-center gap-4">
        <div className="border-primary h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
        <p className="text-sm font-medium tracking-tight">Redirecting to Trust & Privacy...</p>
      </div>
    </div>
  );
}
