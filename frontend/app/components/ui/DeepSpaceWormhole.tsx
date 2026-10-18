import Image from "next/image";

type DeepSpaceWormholeProps = {
  size?: number;
  className?: string;
};

const WORMHOLE_SOURCE = "/AverQel Logo/deepspace-wormhole-aperture.svg";

/** DeepSpace's compact response indicator. */
export default function DeepSpaceWormhole({ size = 24, className = "" }: DeepSpaceWormholeProps) {
  return (
    <span
      className={`deepspace-wormhole ${className}`.trim()}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Image
        src={WORMHOLE_SOURCE}
        alt=""
        width={size}
        height={size}
        unoptimized
        className="deepspace-wormhole__asset"
      />
    </span>
  );
}
