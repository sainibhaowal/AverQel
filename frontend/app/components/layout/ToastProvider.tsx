"use client";

import { Toaster } from "react-hot-toast";

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "#0a0f18",
            color: "#e2e8f0",
            border: "1px solid rgba(255, 255, 255, 0.05)",
            borderRadius: "12px",
            boxShadow: "0 10px 40px rgba(0, 0, 0, 0.5)",
            fontSize: "13px",
          },
          success: {
            iconTheme: {
              primary: "#3b82f6",
              secondary: "#fff",
            },
            style: {
              borderLeft: "3px solid #3b82f6",
            },
          },
          error: {
            style: {
              borderLeft: "3px solid #ef4444",
            },
          },
        }}
      />
      {children}
    </>
  );
}
