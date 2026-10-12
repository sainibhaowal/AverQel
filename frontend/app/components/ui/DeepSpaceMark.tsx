import Image from "next/image";

type DeepSpaceMarkProps = {
  size?: number;
  strokeWidth?: number;
  className?: string;
};

/** Shared DeepSpace Orbital Vortex logo for navigation and welcome surfaces. */
export default function DeepSpaceMark({ size = 24, className }: DeepSpaceMarkProps) {
  return (
    <Image
      src="/brand/deepspace-orbital-vortex.svg"
      alt=""
      aria-hidden="true"
      className={className}
      width={size}
      height={size}
      unoptimized
      style={{ objectFit: "contain" }}
    />
  );
}
