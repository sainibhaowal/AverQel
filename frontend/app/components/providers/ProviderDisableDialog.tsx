"use client";

import type { ComponentProps } from "react";
import ProviderDeleteDialog from "@/app/components/providers/ProviderDeleteDialog";

export default function ProviderDisableDialog(props: ComponentProps<typeof ProviderDeleteDialog>) {
  return <ProviderDeleteDialog {...props} />;
}
