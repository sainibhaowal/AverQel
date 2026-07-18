/**
 * Complete React Component Library for AI Status Animations
 * All components with smooth animations and full state support
 */

import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AIStatus,
  AIStatusType,
  STATUS_CONFIG,
  formatStatus,
  AIStatusManager,
} from "./stateManagement";

// ============================================================================
// ICON COMPONENTS
// ============================================================================

interface StatusIconProps {
  type: AIStatusType;
  size?: number;
  className?: string;
}

const StatusIcon: React.FC<StatusIconProps> = ({ type, size = 24, className = "" }) => {
  const config = STATUS_CONFIG[type];

  const icons: Record<string, React.ReactNode> = {
    circle: <circle cx="12" cy="12" r="10" />,
    brain: (
      <path d="M9.5 2A2.5 2.5 0 0 0 7 4.5v.5c-.6 0-1 .4-1 1v1c-.6 0-1 .4-1 1v1c-.6 0-1 .4-1 1v3c0 .6.4 1 1 1v1c0 .6.4 1 1 1v1c0 .6.4 1 1 1v.5A2.5 2.5 0 0 0 9.5 22h5a2.5 2.5 0 0 0 2.5-2.5v-.5c.6 0 1-.4 1-1v-1c.6 0 1-.4 1-1v-1c.6 0 1-.4 1-1v-3c0-.6-.4-1-1-1v-1c0-.6-.4-1-1-1v-1c0-.6-.4-1-1-1v-.5A2.5 2.5 0 0 0 14.5 2h-5z" />
    ),
    microscope: (
      <path d="M6 3h12v2H6V3zm0 4h12v2H6V7zm0 4h12v2H6v-2zm0 4h12v2H6v-2zm-4 4h20v2H2v-2z" />
    ),
    cpu: (
      <path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6zm2 0v12h12V6H6zm2 2h2v2H8V8zm0 4h2v2H8v-2zm0 4h2v2H8v-2zm4-8h2v2h-2V8zm0 4h2v2h-2v-2zm0 4h2v2h-2v-2zm4-8h2v2h-2V8zm0 4h2v2h-2v-2zm0 4h2v2h-2v-2z" />
    ),
    calculator: (
      <path d="M4 2h16a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm0 2v16h16V4H4zm2 2h4v4H6V6zm0 6h4v4H6v-4zm0 6h4v4H6v-4zm6-12h4v4h-4V6zm0 6h4v4h-4v-4zm0 6h4v4h-4v-4zm6-12h4v4h-4V6zm0 6h4v4h-4v-4zm0 6h4v4h-4v-4z" />
    ),
    search: (
      <path d="M11 2a9 9 0 0 1 6.36 15.36l4.12 4.12a1 1 0 0 1-1.42 1.42l-4.12-4.12A9 9 0 1 1 11 2zm0 2a7 7 0 1 0 0 14 7 7 0 0 0 0-14z" />
    ),
    globe: (
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 17.93a8 8 0 0 0 6.92-6.93h-6.92v6.93zM11 19.93v-6.93H4.08a8 8 0 0 0 6.92 6.93zM11 12V5.07a8 8 0 0 0-6.92 6.93H11zm1 0h6.92a8 8 0 0 0-6.92-6.93V12zm-1 1v6.93a8 8 0 0 0 6.92-6.93H12z" />
    ),
    "book-open": (
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2V3zm7 15a1 1 0 0 1 1-1V7a2 2 0 0 0-2-2H4v13h5zm5-15h6a2 2 0 0 1 2 2v14a3 3 0 0 0-3-3h-6V3zm7 15a1 1 0 0 1-1-1V7a2 2 0 0 0-2-2h-5v13h8z" />
    ),
    scan: (
      <path d="M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5zm2 0v14h14V5H5zm2 2h2v2H7V7zm0 4h2v2H7v-2zm0 4h2v2H7v-2zm4-8h2v2h-2V7zm0 4h2v2h-2v-2zm0 4h2v2h-2v-2zm4-8h2v2h-2V7zm0 4h2v2h-2v-2zm0 4h2v2h-2v-2z" />
    ),
    download: <path d="M12 2v13l-4-4h8l-4 4V2zM4 18h16v2H4v-2z" />,
    "download-cloud": <path d="M12 2v10l-3-3h6l-3 3V2zM5 15h14v5H5v-5zm2 2v1h10v-1H7z" />,
    "upload-cloud": <path d="M12 12V2l3 3H9l3-3v10zM5 15h14v5H5v-5zm2 2v1h10v-1H7z" />,
    "pen-tool": <path d="M12 19l7-7 3 3-7 7-3-3zM2 20l3-3 3 3-3 3-3-3zm7-9l2-2 7 7-2 2-7-7z" />,
    sparkles: (
      <path d="M12 2l2.4 7.2h7.6l-6 4.8 2.4 7.2-6-4.8-6 4.8 2.4-7.2-6-4.8h7.6L12 2zM12 8l-1.2 3.6H7l3 2.4-1.2 3.6 3-2.4 3 2.4-1.2-3.6 3-2.4h-3.8L12 8z" />
    ),
    "plus-circle": (
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z" />
    ),
    edit: (
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7H4V6h7V4zm2.5 2.5l5.5 5.5-9 9H5v-5l9-9zm2.5 2.5l-2.5 2.5 3 3 2.5-2.5-3-3z" />
    ),
    "align-left": <path d="M4 4h16v2H4V4zm0 4h12v2H4V8zm0 4h16v2H4v-2zm0 4h12v2H4v-2z" />,
    code: (
      <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z" />
    ),
    play: <path d="M8 5v14l11-7z" />,
    zap: <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />,
    flask: (
      <path d="M6 2v6l-4 8v4h20v-4l-4-8V2H6zm2 2h8v5.2l3.6 7.2H4.4L8 9.2V4zm4 8a2 2 0 1 1 0 4 2 2 0 0 1 0-4z" />
    ),
    image: <path d="M4 4h16v16H4V4zm2 2v12h12V6H6zm2 2h8v8H8V8zm2 2h4v4H10v-4z" />,
    send: <path d="M2 12l20-9-9 20-2-9-9-2z" />,
    inbox: <path d="M4 4h16v16H4V4zm2 2v12h12V6H6zm2 2h8v8H8V8z" />,
    waves: (
      <path d="M2 12c2.5-2.5 5.5-2.5 8 0s5.5 2.5 8 0 5.5-2.5 8 0M2 16c2.5-2.5 5.5-2.5 8 0s5.5 2.5 8 0 5.5-2.5 8 0M2 8c2.5-2.5 5.5-2.5 8 0s5.5 2.5 8 0 5.5-2.5 8 0" />
    ),
    link: (
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71a1 1 0 1 0 1.42 1.42l1.71-1.71a3 3 0 0 1 4.24 4.24l-3 3a3 3 0 0 1-4.24 0 1 1 0 0 0-1.42 1.42 5 5 0 0 0 7.07 0l-3-3zm-6 0a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71a1 1 0 1 0-1.42-1.42l-1.71 1.71a3 3 0 0 1-4.24-4.24l3-3a3 3 0 0 1 4.24 0 1 1 0 0 0 1.42-1.42 5 5 0 0 0-7.07 0l3 3z" />
    ),
    unlink: (
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71a1 1 0 1 0 1.42 1.42l1.71-1.71a3 3 0 0 1 4.24 4.24l-3 3a3 3 0 0 1-4.24 0 1 1 0 0 0-1.42 1.42 5 5 0 0 0 7.07 0l-3-3zm-6 0a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71a1 1 0 1 0-1.42-1.42l-1.71 1.71a3 3 0 0 1-4.24-4.24l3-3a3 3 0 0 1 4.24 0 1 1 0 0 0 1.42-1.42 5 5 0 0 0-7.07 0l3 3zM2 2l20 20" />
    ),
    "alert-triangle": (
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01" />
    ),
    "refresh-cw": <path d="M23 4v6h-6M1 20v-6h6M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />,
    redo: <path d="M3 7v6h6M3 13a9 9 0 1 0 3-7.7L7 8" />,
    clock: (
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm.5-13h-1v6l5.2 3.2.8-1.3-5-3V7z" />
    ),
    pause: <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />,
    "check-circle": (
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm-1-13l-4 4 1.41 1.41L11 9.83l7.59 7.59L20 16l-9-9z" />
    ),
    "thumbs-up": (
      <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
    ),
    "x-circle": (
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm4-9l-1.41-1.41L12 12.17l-2.59-2.58L8 11l2.59 2.59L8 16.17 9.41 17.59 12 15l2.59 2.58L16 16.17l-2.59-2.58L16 11z" />
    ),
    hourglass: (
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm-2-13h4v2h-4V7zm0 8h4v2h-4v-2z" />
    ),
  };

  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      transition={{ duration: 0.3 }}
    >
      {icons[config.icon] || icons.circle}
    </motion.svg>
  );
};

// ============================================================================
// ANIMATION VARIANTS
// ============================================================================

type MotionAnimate = React.ComponentProps<typeof motion.div>["animate"];

const animationVariants: Record<string, MotionAnimate> = {
  pulse: {
    scale: [1, 1.1, 1],
    opacity: [0.7, 1, 0.7],
    transition: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
  },
  bounce: {
    y: [0, -8, 0],
    transition: { duration: 0.8, repeat: Infinity, ease: "easeInOut" },
  },
  spin: {
    rotate: [0, 360],
    transition: { duration: 1, repeat: Infinity, ease: "linear" },
  },
  float: {
    y: [0, -5, 0],
    x: [0, 3, 0],
    transition: { duration: 2, repeat: Infinity, ease: "easeInOut" },
  },
  slide: {
    x: [-5, 5, -5],
    transition: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
  },
  scan: {
    x: [-10, 10, -10],
    transition: { duration: 0.8, repeat: Infinity, ease: "easeInOut" },
  },
  typing: {
    scale: [1, 1.05, 1],
    transition: { duration: 0.1, repeat: Infinity },
  },
  sparkle: {
    scale: [1, 1.3, 1],
    rotate: [0, 180, 360],
    transition: { duration: 0.8, repeat: Infinity },
  },
  expand: {
    scale: [1, 1.2, 1],
    transition: { duration: 0.6, repeat: Infinity },
  },
  blink: {
    opacity: [1, 0.3, 1],
    transition: { duration: 0.4, repeat: Infinity },
  },
  flash: {
    opacity: [1, 0.5, 1, 0.5, 1],
    transition: { duration: 0.5, repeat: Infinity },
  },
  count: {
    scale: [1, 1.1, 1],
    transition: { duration: 0.3, repeat: Infinity },
  },
  bubble: {
    y: [0, -3, 0],
    scale: [1, 1.05, 1],
    transition: { duration: 1.2, repeat: Infinity },
  },
  fade: {
    opacity: [0.5, 1, 0.5],
    transition: { duration: 1, repeat: Infinity },
  },
  flow: {
    x: [0, 5, 0],
    opacity: [0.7, 1, 0.7],
    transition: { duration: 0.6, repeat: Infinity },
  },
  wave: {
    y: [0, -2, 0],
    transition: { duration: 0.2, repeat: Infinity },
  },
  shake: {
    x: [0, -3, 3, -3, 3, 0],
    transition: { duration: 0.5, repeat: Infinity },
  },
  success: {
    scale: [1, 1.2, 1],
    opacity: [1, 0.8, 1],
    transition: { duration: 1, repeat: 1 },
  },
  freeze: {
    scale: 1,
    opacity: 1,
  },
  progress: {
    scaleX: [0.8, 1, 0.8],
    transition: { duration: 0.5, repeat: Infinity },
  },
};

// ============================================================================
// MAIN STATUS INDICATOR COMPONENT
// ============================================================================

interface AIStatusIndicatorProps {
  status: AIStatus;
  size?: number;
  showText?: boolean;
  showProgress?: boolean;
  className?: string;
  position?: "top-left" | "top-right" | "bottom-left" | "bottom-right" | "center";
}

export const AIStatusIndicator: React.FC<AIStatusIndicatorProps> = ({
  status,
  size = 24,
  showText = true,
  showProgress = true,
  className = "",
  position = "top-right",
}) => {
  const config = STATUS_CONFIG[status.type];
  const animation =
    animationVariants[config.animation as keyof typeof animationVariants] ||
    animationVariants.pulse;

  const positionStyles = {
    "top-left": { top: 16, left: 16 },
    "top-right": { top: 16, right: 16 },
    "bottom-left": { bottom: 16, left: 16 },
    "bottom-right": { bottom: 16, right: 16 },
    center: { top: "50%", left: "50%", transform: "translate(-50%, -50%)" },
  };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        className={`ai-status-indicator ${className}`}
        style={{
          position: "fixed",
          ...positionStyles[position],
          zIndex: 9999,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          borderRadius: 12,
          backgroundColor: "rgba(0, 0, 0, 0.8)",
          backdropFilter: "blur(10px)",
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.3)",
          border: `1px solid ${config.color}40`,
          color: config.color,
        }}
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
      >
        <motion.div animate={animation}>
          <StatusIcon type={status.type} size={size} />
        </motion.div>

        {showText && (
          <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2, delay: 0.1 }}
          >
            <div className="status-text" style={{ fontSize: 14, fontWeight: 500 }}>
              {formatStatus(status)}
            </div>
          </motion.div>
        )}

        {showProgress && status.progress !== undefined && (
          <motion.div
            className="progress-bar"
            style={{
              width: 100,
              height: 4,
              backgroundColor: "rgba(255, 255, 255, 0.2)",
              borderRadius: 2,
              overflow: "hidden",
            }}
            initial={{ width: 0 }}
            animate={{ width: 100 }}
          >
            <motion.div
              style={{
                height: "100%",
                backgroundColor: config.color,
                borderRadius: 2,
              }}
              initial={{ width: 0 }}
              animate={{ width: `${status.progress * 100}%` }}
              transition={{ duration: 0.3 }}
            />
          </motion.div>
        )}
      </motion.div>
    </AnimatePresence>
  );
};

// ============================================================================
// STATUS PROVIDER COMPONENT
// ============================================================================

interface AIStatusProviderProps {
  children: React.ReactNode;
  statusManager: AIStatusManager;
  position?: AIStatusIndicatorProps["position"];
}

export const AIStatusProvider: React.FC<AIStatusProviderProps> = ({
  children,
  statusManager,
  position = "top-right",
}) => {
  const [status, setStatus] = useState<AIStatus>(statusManager.getCurrentStatus());

  useEffect(() => {
    const unsubscribe = statusManager.subscribe((newStatus) => {
      setStatus(newStatus);
    });

    return unsubscribe;
  }, [statusManager]);

  return (
    <>
      <AIStatusIndicator status={status} position={position} />
      {children}
    </>
  );
};

// ============================================================================
// MINIMAL STATUS COMPONENT
// ============================================================================

interface MinimalStatusProps {
  status: AIStatus;
  size?: number;
  className?: string;
}

export const MinimalStatus: React.FC<MinimalStatusProps> = ({
  status,
  size = 16,
  className = "",
}) => {
  const config = STATUS_CONFIG[status.type];
  const animation =
    animationVariants[config.animation as keyof typeof animationVariants] ||
    animationVariants.pulse;

  return (
    <motion.div
      className={`minimal-status ${className}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <motion.div animate={animation}>
        <StatusIcon type={status.type} size={size} />
      </motion.div>
      <span style={{ fontSize: 12, color: config.color }}>{status.type}</span>
    </motion.div>
  );
};

// ============================================================================
// STATUS BADGE COMPONENT
// ============================================================================

interface StatusBadgeProps {
  status: AIStatus;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = "" }) => {
  const config = STATUS_CONFIG[status.type];

  return (
    <motion.div
      className={`status-badge ${className}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 12px",
        borderRadius: 20,
        backgroundColor: `${config.color}20`,
        border: `1px solid ${config.color}40`,
        color: config.color,
        fontSize: 12,
        fontWeight: 500,
        textTransform: "capitalize",
      }}
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={{ scale: 0.8, opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      <StatusIcon type={status.type} size={12} />
      {status.type}
    </motion.div>
  );
};

// ============================================================================
// STATUS HISTORY COMPONENT
// ============================================================================

interface StatusHistoryProps {
  statusManager: AIStatusManager;
  maxItems?: number;
  className?: string;
}

export const StatusHistory: React.FC<StatusHistoryProps> = ({
  statusManager,
  maxItems = 10,
  className = "",
}) => {
  const [history, setHistory] = useState<AIStatus[]>(() =>
    statusManager.getStatusHistory().slice(-maxItems),
  );

  useEffect(() => {
    const unsubscribe = statusManager.subscribe(() => {
      setHistory(statusManager.getStatusHistory().slice(-maxItems));
    });

    return unsubscribe;
  }, [statusManager, maxItems]);

  return (
    <div
      className={`status-history ${className}`}
      style={{
        padding: 16,
        borderRadius: 8,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        maxHeight: 300,
        overflowY: "auto",
      }}
    >
      <h4 style={{ color: "#fff", marginBottom: 12, fontSize: 14 }}>Status History</h4>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {history.map((status, index) => (
          <motion.div
            key={index}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: 8,
              borderRadius: 4,
              backgroundColor: "rgba(255, 255, 255, 0.05)",
            }}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05 }}
          >
            <StatusIcon type={status.type} size={16} />
            <div style={{ flex: 1 }}>
              <div style={{ color: "#fff", fontSize: 12 }}>{formatStatus(status)}</div>
              <div style={{ color: "#888", fontSize: 10 }}>
                {new Date(status.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

// ============================================================================
// EXPORT ALL COMPONENTS
// ============================================================================

export { StatusIcon, animationVariants };

export default AIStatusIndicator;
