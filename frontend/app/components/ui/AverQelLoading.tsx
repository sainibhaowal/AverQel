import { useId, type CSSProperties } from "react";
import { AVERQEL_MARK_PATHS, AVERQEL_WORDMARK_PATHS } from "./AverQelLoadingArtwork";

const screenReaderOnlyStyle: CSSProperties = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  whiteSpace: "nowrap",
  clip: "rect(0, 0, 0, 0)",
  clipPath: "inset(50%)",
  border: 0,
};

export type AverQelLoadingSize = "page" | "section" | "compact" | "inline";

interface AverQelLoadingProps {
  label?: string;
  size?: AverQelLoadingSize;
  className?: string;
}

function pieceStyle(index: number): CSSProperties {
  return {
    "--averqel-piece-delay": `${index * -72}ms`,
    "--averqel-piece-x": `${(index % 5) - 2}px`,
    "--averqel-piece-y": `${((index * 3) % 5) - 2}px`,
    "--averqel-piece-turn": `${((index % 3) - 1) * 2}deg`,
  } as CSSProperties;
}

/** Shared branded loading state for route, panel, and conversation transitions. */
export default function AverQelLoading({
  label = "Loading AverQel…",
  size = "section",
  className = "",
}: AverQelLoadingProps) {
  const gradientId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const Container = size === "inline" ? "span" : "div";
  const Brand = size === "inline" ? "span" : "div";
  const Visual = size === "inline" ? "span" : "div";

  return (
    <Container
      role="status"
      aria-label={label}
      aria-live="polite"
      aria-busy="true"
      className={`averqel-loading averqel-loading--${size} ${className}`.trim()}
    >
      <Brand className="averqel-loading__brand" aria-hidden="true">
        <Visual className="averqel-loading__visual">
          <span className="averqel-loading__halo" />
          <svg
            className="averqel-loading__logo"
            viewBox="225 20 700 650"
            focusable="false"
            preserveAspectRatio="xMidYMid meet"
          >
            {AVERQEL_MARK_PATHS.map((piece, index) => (
              <path
                key={piece.id}
                d={piece.d}
                fill={piece.fill}
                fillRule={piece.fillRule}
                fillOpacity={piece.fillOpacity}
                className="averqel-loading__piece"
                style={pieceStyle(index)}
              />
            ))}
          </svg>
          <span className="averqel-loading__orbit">
            <span className="averqel-loading__orbit-dot" />
          </span>
        </Visual>
        {size === "page" && (
          <svg
            className="averqel-loading__wordmark"
            viewBox="0 0 1371 254"
            focusable="false"
            preserveAspectRatio="xMidYMid meet"
          >
            <defs>
              <linearGradient id={`${gradientId}-navy`} x1="0" y1="0" x2="0.15" y2="1">
                <stop stopColor="#00133f" />
                <stop offset="1" stopColor="#021036" />
              </linearGradient>
              <linearGradient id={`${gradientId}-q`} x1="0.03" y1="0" x2="1" y2="1">
                <stop stopColor="#00f3f0" />
                <stop offset="0.25" stopColor="#00adfc" />
                <stop offset="0.55" stopColor="#125cff" />
                <stop offset="0.84" stopColor="#7122ff" />
                <stop offset="1" stopColor="#dc00f2" />
              </linearGradient>
            </defs>
            {AVERQEL_WORDMARK_PATHS.map((piece, index) => (
              <path
                key={piece.id}
                d={piece.d}
                fill={piece.fill
                  .replace("#navy", "#" + gradientId + "-navy")
                  .replace("#q", "#" + gradientId + "-q")}
                fillRule={piece.fillRule}
                fillOpacity={piece.fillOpacity}
                className={`averqel-loading__piece averqel-loading__wordmark-piece averqel-loading__wordmark-piece--${index + 1}`}
                style={pieceStyle(AVERQEL_MARK_PATHS.length + index)}
              />
            ))}
          </svg>
        )}
      </Brand>
      <span className="averqel-loading__label" style={screenReaderOnlyStyle}>
        {label}
      </span>
    </Container>
  );
}
