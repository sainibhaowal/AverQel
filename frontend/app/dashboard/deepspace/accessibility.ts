/**
 * Accessibility and Error Handling Utilities for AI Status System
 * Complete ARIA support, error handling, and user-friendly error management
 */

import { AIStatus, AIStatusType, STATUS_CONFIG } from "./stateManagement";

// ============================================================================
// ACCESSIBILITY UTILITIES
// ============================================================================

/**
 * Get ARIA label for status type
 */
export function getAriaLabel(status: AIStatus): string {
  const config = STATUS_CONFIG[status.type];
  const message = status.message || status.type;
  const progress =
    status.progress !== undefined ? `${Math.round(status.progress * 100)} percent complete` : "";

  return `${message} ${progress}`.trim();
}

/**
 * Get ARIA live region setting based on status priority
 */
export function getAriaLive(statusType: AIStatusType): "polite" | "assertive" | "off" {
  const config = STATUS_CONFIG[statusType];

  if (config.priority >= 90) {
    return "assertive"; // High priority: errors, cancellations
  } else if (config.priority >= 50) {
    return "polite"; // Medium priority: active operations
  } else {
    return "off"; // Low priority: idle, completed
  }
}

/**
 * Get ARIA role for status indicator
 */
export function getAriaRole(statusType: AIStatusType): "status" | "alert" | "progressbar" {
  const config = STATUS_CONFIG[statusType];

  if (statusType === "error" || statusType === "cancelled") {
    return "alert";
  } else if (statusType === "timeout") {
    return "alert";
  } else {
    return "status";
  }
}

/**
 * Check if reduced motion is preferred
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;

  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Get appropriate animation duration based on user preferences
 */
export function getAnimationDuration(baseDuration: number): number {
  return prefersReducedMotion() ? 0 : baseDuration;
}

// ============================================================================
// REACT COMPONENTS (See accessibilityComponents.tsx for React implementations)
// ============================================================================

// ============================================================================
// ERROR HANDLING UTILITIES
// ============================================================================

export class StatusError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusType?: AIStatusType,
    public recoverable: boolean = true,
  ) {
    super(message);
    this.name = "StatusError";
  }
}

/**
 * Handle status-related errors with user-friendly messages
 */
export function handleStatusError(error: unknown): {
  message: string;
  recoverable: boolean;
  userAction?: string;
} {
  if (error instanceof StatusError) {
    return {
      message: error.message,
      recoverable: error.recoverable,
      userAction: error.recoverable ? "Please try again" : "Contact support",
    };
  }

  if (error instanceof Error) {
    return {
      message: "An unexpected error occurred",
      recoverable: true,
      userAction: "Please refresh the page",
    };
  }

  return {
    message: "Unknown error occurred",
    recoverable: true,
    userAction: "Please try again",
  };
}

/**
 * Create a status error with context
 */
export function createStatusError(
  message: string,
  code: string,
  statusType?: AIStatusType,
): StatusError {
  return new StatusError(message, code, statusType);
}

// ============================================================================
// ERROR RECOVERY STRATEGIES
// ============================================================================

export interface RecoveryStrategy {
  attempt: () => Promise<boolean>;
  maxAttempts: number;
  delay: number;
  backoffMultiplier: number;
}

export class ErrorRecoveryManager {
  private strategies: Map<string, RecoveryStrategy>;
  private attemptCounts: Map<string, number>;

  constructor() {
    this.strategies = new Map();
    this.attemptCounts = new Map();
  }

  registerStrategy(key: string, strategy: RecoveryStrategy): void {
    this.strategies.set(key, strategy);
    this.attemptCounts.set(key, 0);
  }

  async recover(key: string): Promise<boolean> {
    const strategy = this.strategies.get(key);
    if (!strategy) {
      return false;
    }

    const attempts = this.attemptCounts.get(key) || 0;

    if (attempts >= strategy.maxAttempts) {
      return false;
    }

    const delay = strategy.delay * Math.pow(strategy.backoffMultiplier, attempts);

    await new Promise((resolve) => setTimeout(resolve, delay));

    try {
      const success = await strategy.attempt();

      if (success) {
        this.attemptCounts.set(key, 0); // Reset on success
      } else {
        this.attemptCounts.set(key, attempts + 1);
      }

      return success;
    } catch (error) {
      this.attemptCounts.set(key, attempts + 1);
      return false;
    }
  }

  reset(key: string): void {
    this.attemptCounts.set(key, 0);
  }

  resetAll(): void {
    this.attemptCounts.clear();
  }
}

// ============================================================================
// USER-FRIENDLY ERROR MESSAGES
// ============================================================================

export const ERROR_MESSAGES: Record<string, { message: string; action: string }> = {
  NETWORK_ERROR: {
    message: "Unable to connect to status server",
    action: "Check your internet connection and try again",
  },
  TIMEOUT_ERROR: {
    message: "Status update timed out",
    action: "The operation is taking longer than expected",
  },
  INVALID_STATUS: {
    message: "Invalid status received",
    action: "The system sent an unrecognized status",
  },
  TRANSITION_ERROR: {
    message: "Status transition failed",
    action: "The system could not change to the requested state",
  },
  WEBSOCKET_ERROR: {
    message: "Real-time connection lost",
    action: "Attempting to reconnect automatically",
  },
  RENDER_ERROR: {
    message: "Could not display status indicator",
    action: "Refresh the page to fix display issues",
  },
  PERMISSION_ERROR: {
    message: "Insufficient permissions",
    action: "You may not have access to this status information",
  },
};

export function getUserFriendlyError(errorCode: string): {
  message: string;
  action: string;
} {
  return (
    ERROR_MESSAGES[errorCode] || {
      message: "An error occurred",
      action: "Please try again",
    }
  );
}

// ============================================================================
// KEYBOARD NAVIGATION SUPPORT
// ============================================================================

export function setupKeyboardNavigation(element: HTMLElement): () => void {
  const handleKeyDown = (event: KeyboardEvent) => {
    switch (event.key) {
      case "Escape":
        // Handle escape key (close status panel, etc.)
        element.dispatchEvent(new CustomEvent("status-escape"));
        break;
      case "Enter":
      case " ":
        // Handle activation
        if (element.getAttribute("role") === "button") {
          element.dispatchEvent(new CustomEvent("status-activate"));
          event.preventDefault();
        }
        break;
    }
  };

  element.addEventListener("keydown", handleKeyDown);
  element.setAttribute("tabindex", "0");

  return () => {
    element.removeEventListener("keydown", handleKeyDown);
    element.removeAttribute("tabindex");
  };
}

// ============================================================================
// SCREEN READER ANNOUNCEMENTS
// ============================================================================

export class ScreenReaderAnnouncer {
  private element: HTMLElement | null = null;

  constructor() {
    if (typeof document !== "undefined") {
      this.element = document.createElement("div");
      this.element.setAttribute("role", "status");
      this.element.setAttribute("aria-live", "polite");
      this.element.setAttribute("aria-atomic", "true");
      this.element.style.position = "absolute";
      this.element.style.left = "-10000px";
      this.element.style.width = "1px";
      this.element.style.height = "1px";
      this.element.style.overflow = "hidden";
      document.body.appendChild(this.element);
    }
  }

  announce(message: string, priority: "polite" | "assertive" = "polite"): void {
    if (!this.element) return;

    this.element.setAttribute("aria-live", priority);

    // Clear previous announcement
    this.element.textContent = "";

    // Force reflow
    this.element.offsetHeight;

    // Set new announcement
    this.element.textContent = message;
  }

  destroy(): void {
    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
      this.element = null;
    }
  }
}

// ============================================================================
// FOCUS MANAGEMENT
// ============================================================================

export function trapFocus(element: HTMLElement): () => void {
  const focusableElements = element.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  );

  const firstFocusable = focusableElements[0] as HTMLElement;
  const lastFocusable = focusableElements[focusableElements.length - 1] as HTMLElement;

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Tab") return;

    if (event.shiftKey) {
      if (document.activeElement === firstFocusable) {
        lastFocusable.focus();
        event.preventDefault();
      }
    } else {
      if (document.activeElement === lastFocusable) {
        firstFocusable.focus();
        event.preventDefault();
      }
    }
  };

  element.addEventListener("keydown", handleKeyDown);
  firstFocusable?.focus();

  return () => {
    element.removeEventListener("keydown", handleKeyDown);
  };
}

// ============================================================================
// HIGH CONTRAST MODE SUPPORT
// ============================================================================

export function supportsHighContrast(): boolean {
  if (typeof window === "undefined") return false;

  return window.matchMedia("(forced-colors: active)").matches;
}

export function getHighContrastColors(statusType: AIStatusType): {
  foreground: string;
  background: string;
} {
  const config = STATUS_CONFIG[statusType];

  if (supportsHighContrast()) {
    return {
      foreground: "WindowText",
      background: "Window",
    };
  }

  return {
    foreground: config.color,
    background: `${config.color}20`,
  };
}

// ============================================================================
// EXPORT ALL UTILITIES
// ============================================================================

export default {
  getAriaLabel,
  getAriaLive,
  getAriaRole,
  prefersReducedMotion,
  getAnimationDuration,
  StatusError,
  handleStatusError,
  createStatusError,
  ErrorRecoveryManager,
  ERROR_MESSAGES,
  getUserFriendlyError,
  setupKeyboardNavigation,
  ScreenReaderAnnouncer,
  trapFocus,
  supportsHighContrast,
  getHighContrastColors,
};
