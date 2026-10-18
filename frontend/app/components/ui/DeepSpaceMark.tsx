import Image from "next/image";

type DeepSpaceMarkProps = {
  size?: number;
  visualScale?: number;
  source?: string;
  strokeWidth?: number;
  className?: string;
};

/** Compact DeepSpace feature mark using the supplied RGB orbital logo. */
export default function DeepSpaceMark({
  size = 24,
  visualScale = 1,
  source = "/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg",
  className,
}: DeepSpaceMarkProps) {
  return (
    <Image
      src={source}
      alt=""
      aria-hidden="true"
      className={className}
      width={size}
      height={size}
      unoptimized
      // Keep the image in the same fixed flex box as the Lucide nav icons. The
      // supplied artwork is non-square, so contain preserves its proportions
      // while explicit dimensions prevent layout drift in the sidebar. The
      // optional visual scale enlarges only the artwork, keeping its nav slot
      // and the label position unchanged.
      style={{
        width: size,
        height: size,
        display: "block",
        objectFit: "contain",
        transform: visualScale === 1 ? undefined : `scale(${visualScale})`,
        transformOrigin: "center",
      }}
    />
  );
}
