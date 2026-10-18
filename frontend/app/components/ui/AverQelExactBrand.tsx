import Image from "next/image";

/** Shared exact artwork and RGB treatment for the login and signup screens. */
export default function AverQelExactBrand() {
  return (
    <>
      <span className="login-exact-logo-wrap">
        <Image
          src="/brand/AverQel_Exact_Logo.svg"
          alt="AverQel"
          width={296}
          height={222}
          priority
          sizes="(max-width: 640px) 82vw, 296px"
          className="login-exact-logo"
        />
        <span aria-hidden="true" className="login-exact-logo--animated login-exact-logo--aver" />
        <span aria-hidden="true" className="login-exact-logo--animated login-exact-logo--el" />
      </span>
      <span className="login-brand-tagline">INTELLIGENCE ALL YOU NEED</span>
    </>
  );
}
