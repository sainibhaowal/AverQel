export default function NeoSISMark({ size = 18 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="block shrink-0"
      width={size}
      height={size}
      viewBox="0 0 128 96"
      fill="none"
    >
      <defs>
        <linearGradient id="averqel-neosis-nav-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ff1744" />
          <stop offset="18%" stopColor="#ff8a00" />
          <stop offset="36%" stopColor="#ffd600" />
          <stop offset="54%" stopColor="#31d158" />
          <stop offset="70%" stopColor="#00c7e8" />
          <stop offset="84%" stopColor="#397bff" />
          <stop offset="100%" stopColor="#c13cff" />
        </linearGradient>
      </defs>
      <path
        d="M12 27C16 15 28 8 43 10L53 2L53 15C66 15 79 21 90 31C99 39 106 48 116 51C108 58 99 60 90 57C87 69 79 78 67 84C52 91 35 88 23 79C12 71 7 59 8 46C8 38 9 32 12 27ZM31 9L22 2L24 18C19 20 15 23 12 27ZM70 35A4 4 0 1 0 70 43A4 4 0 1 0 70 35ZM20 50C29 39 42 35 56 39C47 43 41 49 38 57C35 66 39 73 46 80C34 78 25 72 20 64C17 59 17 54 20 50Z"
        fill="url(#averqel-neosis-nav-gradient)"
        fillRule="evenodd"
        clipRule="evenodd"
      />
      <path
        d="M82 25C91 33 99 43 106 49C98 49 91 52 85 56"
        stroke="url(#averqel-neosis-nav-gradient)"
        strokeWidth="3"
        strokeLinecap="round"
        opacity=".92"
      />
    </svg>
  );
}
