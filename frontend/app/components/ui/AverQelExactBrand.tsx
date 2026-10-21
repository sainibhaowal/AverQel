import Image from "next/image";
import AverQelWordmark from "./AverQelWordmark";

/** Shared AverQel icon and animated RGB wordmark used by login and signup. */
export default function AverQelExactBrand() {
  return (
    <>
      <span className="login-exact-logo-wrap">
        <Image
          src="/AverQel%20Logo/AverQel_Icon.svg"
          alt=""
          width={1202}
          height={675}
          priority
          sizes="(max-width: 640px) 82vw, 296px"
          className="login-exact-logo"
        />
      </span>
      <span className="login-exact-wordmark-wrap">
        <AverQelWordmark size="hero" className="login-brand-wordmark" />
        <span aria-hidden="true" className="login-exact-wordmark-rgb" />
      </span>
      <span className="login-brand-tagline">INTELLIGENCE ALL YOU NEED</span>
    </>
  );
}
