import AverQelLoading from "@/app/components/ui/AverQelLoading";

type MCPLoadingIndicatorProps = {
  label: string;
  size?: "compact" | "standard" | "large";
  className?: string;
};

export default function MCPLoadingIndicator({
  label,
  size = "standard",
  className = "",
}: MCPLoadingIndicatorProps) {
  return (
    <AverQelLoading
      label={label}
      size={size === "large" ? "section" : "compact"}
      className={className}
    />
  );
}
