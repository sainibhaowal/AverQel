import Image from "next/image";
import { QEL_CONNECT_MARK_SOURCE } from "@/lib/brand";

type QelConnectMarkProps = {
  size?: number;
  className?: string;
};

/** Shared Qel Connect mark for navigation, workspace cards, and feature surfaces. */
export default function QelConnectMark({ size = 24, className }: QelConnectMarkProps) {
  return (
    <Image
      src={QEL_CONNECT_MARK_SOURCE}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      unoptimized
      className={`qel-connect-mark ${className ?? ""}`.trim()}
      style={{ width: size, height: size, display: "block", objectFit: "contain" }}
    />
  );
}
