/**
 * Comprehensive AI Status State Management System
 * Complete implementation with all possible AI states and transitions
 */

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export type AIStatusType =
  // Core Processing States
  | "idle"
  | "thinking"
  | "analyzing"
  | "processing"
  | "computing"

  // Information Gathering States
  | "searching"
  | "browsing"
  | "reading"
  | "scanning"
  | "fetching"
  | "downloading"
  | "uploading"

  // Content Creation States
  | "writing"
  | "generating"
  | "creating"
  | "editing"
  | "formatting"
  | "compiling"

  // Tool Execution States
  | "executing"
  | "running"
  | "calculating"
  | "simulating"
  | "rendering"

  // Communication States
  | "transmitting"
  | "receiving"
  | "streaming"
  | "connecting"
  | "disconnecting"

  // Error and Recovery States
  | "error"
  | "recovering"
  | "retrying"
  | "waiting"
  | "paused"

  // Completion States
  | "completed"
  | "success"
  | "cancelled"
  | "timeout";

export interface AIStatus {
  type: AIStatusType;
  message?: string;
  progress?: number;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface StatusTransition {
  from: AIStatusType;
  to: AIStatusType;
  timestamp: number;
  duration?: number;
}

// ============================================================================
// STATUS CONFIGURATION
// ============================================================================

export const STATUS_CONFIG: Record<
  AIStatusType,
  {
    icon: string;
    color: string;
    animation: string;
    duration: number;
    priority: number;
    allowTransition: boolean;
  }
> = {
  // Core Processing
  idle: {
    icon: "circle",
    color: "#6B7280",
    animation: "pulse",
    duration: 2000,
    priority: 0,
    allowTransition: true,
  },
  thinking: {
    icon: "brain",
    color: "#8B5CF6",
    animation: "bounce",
    duration: 1000,
    priority: 10,
    allowTransition: true,
  },
  analyzing: {
    icon: "microscope",
    color: "#3B82F6",
    animation: "spin",
    duration: 1500,
    priority: 15,
    allowTransition: true,
  },
  processing: {
    icon: "cpu",
    color: "#10B981",
    animation: "pulse",
    duration: 800,
    priority: 12,
    allowTransition: true,
  },
  computing: {
    icon: "calculator",
    color: "#F59E0B",
    animation: "bounce",
    duration: 1200,
    priority: 13,
    allowTransition: true,
  },

  // Information Gathering
  searching: {
    icon: "search",
    color: "#6366F1",
    animation: "spin",
    duration: 1000,
    priority: 20,
    allowTransition: true,
  },
  browsing: {
    icon: "globe",
    color: "#8B5CF6",
    animation: "float",
    duration: 2000,
    priority: 21,
    allowTransition: true,
  },
  reading: {
    icon: "book-open",
    color: "#14B8A6",
    animation: "slide",
    duration: 1500,
    priority: 22,
    allowTransition: true,
  },
  scanning: {
    icon: "scan",
    color: "#EC4899",
    animation: "scan",
    duration: 800,
    priority: 23,
    allowTransition: true,
  },
  fetching: {
    icon: "download",
    color: "#3B82F6",
    animation: "bounce",
    duration: 600,
    priority: 24,
    allowTransition: true,
  },
  downloading: {
    icon: "download-cloud",
    color: "#10B981",
    animation: "progress",
    duration: 500,
    priority: 25,
    allowTransition: true,
  },
  uploading: {
    icon: "upload-cloud",
    color: "#F59E0B",
    animation: "progress",
    duration: 500,
    priority: 26,
    allowTransition: true,
  },

  // Content Creation
  writing: {
    icon: "pen-tool",
    color: "#EF4444",
    animation: "typing",
    duration: 100,
    priority: 30,
    allowTransition: true,
  },
  generating: {
    icon: "sparkles",
    color: "#8B5CF6",
    animation: "sparkle",
    duration: 800,
    priority: 31,
    allowTransition: true,
  },
  creating: {
    icon: "plus-circle",
    color: "#10B981",
    animation: "expand",
    duration: 600,
    priority: 32,
    allowTransition: true,
  },
  editing: {
    icon: "edit",
    color: "#F59E0B",
    animation: "pulse",
    duration: 900,
    priority: 33,
    allowTransition: true,
  },
  formatting: {
    icon: "align-left",
    color: "#6B7280",
    animation: "slide",
    duration: 700,
    priority: 34,
    allowTransition: true,
  },
  compiling: {
    icon: "code",
    color: "#3B82F6",
    animation: "blink",
    duration: 400,
    priority: 35,
    allowTransition: true,
  },

  // Tool Execution
  executing: {
    icon: "play",
    color: "#10B981",
    animation: "pulse",
    duration: 800,
    priority: 40,
    allowTransition: true,
  },
  running: {
    icon: "zap",
    color: "#F59E0B",
    animation: "flash",
    duration: 500,
    priority: 41,
    allowTransition: true,
  },
  calculating: {
    icon: "calculator",
    color: "#3B82F6",
    animation: "count",
    duration: 300,
    priority: 42,
    allowTransition: true,
  },
  simulating: {
    icon: "flask",
    color: "#8B5CF6",
    animation: "bubble",
    duration: 1200,
    priority: 43,
    allowTransition: true,
  },
  rendering: {
    icon: "image",
    color: "#EC4899",
    animation: "fade",
    duration: 1000,
    priority: 44,
    allowTransition: true,
  },

  // Communication
  transmitting: {
    icon: "send",
    color: "#10B981",
    animation: "flow",
    duration: 600,
    priority: 50,
    allowTransition: true,
  },
  receiving: {
    icon: "inbox",
    color: "#3B82F6",
    animation: "flow",
    duration: 600,
    priority: 51,
    allowTransition: true,
  },
  streaming: {
    icon: "waves",
    color: "#8B5CF6",
    animation: "wave",
    duration: 200,
    priority: 52,
    allowTransition: true,
  },
  connecting: {
    icon: "link",
    color: "#F59E0B",
    animation: "pulse",
    duration: 1000,
    priority: 53,
    allowTransition: true,
  },
  disconnecting: {
    icon: "unlink",
    color: "#EF4444",
    animation: "pulse",
    duration: 1000,
    priority: 54,
    allowTransition: true,
  },

  // Error and Recovery
  error: {
    icon: "alert-triangle",
    color: "#EF4444",
    animation: "shake",
    duration: 500,
    priority: 100,
    allowTransition: true,
  },
  recovering: {
    icon: "refresh-cw",
    color: "#F59E0B",
    animation: "spin",
    duration: 1000,
    priority: 90,
    allowTransition: true,
  },
  retrying: {
    icon: "redo",
    color: "#6366F1",
    animation: "bounce",
    duration: 800,
    priority: 85,
    allowTransition: true,
  },
  waiting: {
    icon: "clock",
    color: "#6B7280",
    animation: "pulse",
    duration: 1500,
    priority: 5,
    allowTransition: true,
  },
  paused: {
    icon: "pause",
    color: "#6B7280",
    animation: "freeze",
    duration: 0,
    priority: 3,
    allowTransition: true,
  },

  // Completion States
  completed: {
    icon: "check-circle",
    color: "#10B981",
    animation: "success",
    duration: 1000,
    priority: 1,
    allowTransition: true,
  },
  success: {
    icon: "thumbs-up",
    color: "#10B981",
    animation: "bounce",
    duration: 800,
    priority: 2,
    allowTransition: true,
  },
  cancelled: {
    icon: "x-circle",
    color: "#EF4444",
    animation: "shake",
    duration: 500,
    priority: 95,
    allowTransition: true,
  },
  timeout: {
    icon: "hourglass",
    color: "#F59E0B",
    animation: "spin",
    duration: 2000,
    priority: 80,
    allowTransition: true,
  },
};

// ============================================================================
// STATUS TRANSITION RULES
// ============================================================================

export const TRANSITION_RULES: Record<AIStatusType, AIStatusType[]> = {
  idle: ["thinking", "searching", "reading", "executing", "connecting", "waiting"],
  thinking: ["analyzing", "processing", "writing", "error", "completed", "idle"],
  analyzing: ["thinking", "processing", "computing", "error", "completed"],
  processing: ["thinking", "analyzing", "computing", "writing", "completed", "error"],
  computing: ["processing", "analyzing", "completed", "error"],

  searching: ["reading", "fetching", "browsing", "thinking", "error", "completed"],
  browsing: ["searching", "reading", "fetching", "thinking", "completed"],
  reading: ["thinking", "analyzing", "processing", "writing", "completed"],
  scanning: ["analyzing", "processing", "completed", "error"],
  fetching: ["reading", "downloading", "processing", "error"],
  downloading: ["fetching", "processing", "error", "completed"],
  uploading: ["transmitting", "processing", "error", "completed"],

  writing: ["generating", "editing", "formatting", "compiling", "completed", "error"],
  generating: ["writing", "creating", "editing", "completed", "error"],
  creating: ["generating", "writing", "completed", "error"],
  editing: ["writing", "formatting", "compiling", "completed"],
  formatting: ["writing", "compiling", "completed"],
  compiling: ["writing", "executing", "completed", "error"],

  executing: ["running", "calculating", "simulating", "rendering", "completed", "error"],
  running: ["executing", "calculating", "completed", "error"],
  calculating: ["executing", "running", "computing", "completed"],
  simulating: ["executing", "analyzing", "completed", "error"],
  rendering: ["executing", "completed", "error"],

  transmitting: ["streaming", "connecting", "completed", "error"],
  receiving: ["streaming", "processing", "completed", "error"],
  streaming: ["transmitting", "receiving", "writing", "processing"],
  connecting: ["transmitting", "receiving", "error", "idle"],
  disconnecting: ["idle", "completed"],

  error: ["recovering", "retrying", "idle", "cancelled"],
  recovering: ["thinking", "idle", "error"],
  retrying: ["thinking", "searching", "reading", "error"],
  waiting: ["thinking", "searching", "idle", "timeout"],
  paused: ["thinking", "idle", "cancelled"],

  completed: ["idle", "thinking"],
  success: ["idle", "thinking"],
  cancelled: ["idle"],
  timeout: ["retrying", "idle", "error"],
};

// ============================================================================
// STATUS MANAGER CLASS
// ============================================================================

export class AIStatusManager {
  private currentStatus: AIStatus;
  private statusHistory: AIStatus[];
  private transitionHistory: StatusTransition[];
  private listeners: Set<(status: AIStatus) => void>;
  private transitionListeners: Set<(transition: StatusTransition) => void>;
  private maxHistorySize: number;

  constructor(initialStatus: AIStatusType = "idle") {
    this.currentStatus = {
      type: initialStatus,
      timestamp: Date.now(),
    };
    this.statusHistory = [this.currentStatus];
    this.transitionHistory = [];
    this.listeners = new Set();
    this.transitionListeners = new Set();
    this.maxHistorySize = 100;
  }

  /**
   * Set the current AI status
   */
  setStatus(
    type: AIStatusType,
    message?: string,
    progress?: number,
    metadata?: Record<string, unknown>,
  ): void {
    const previousStatus = this.currentStatus;

    // Validate transition
    if (!this.isValidTransition(previousStatus.type, type)) {
      console.warn(`Invalid transition from ${previousStatus.type} to ${type}`);
      return;
    }

    const newStatus: AIStatus = {
      type,
      message,
      progress,
      timestamp: Date.now(),
      metadata,
    };

    // Record transition
    const transition: StatusTransition = {
      from: previousStatus.type,
      to: type,
      timestamp: Date.now(),
      duration: Date.now() - previousStatus.timestamp,
    };

    this.currentStatus = newStatus;
    this.statusHistory.push(newStatus);
    this.transitionHistory.push(transition);

    // Trim history if needed
    if (this.statusHistory.length > this.maxHistorySize) {
      this.statusHistory.shift();
      this.transitionHistory.shift();
    }

    // Notify listeners
    this.notifyListeners(newStatus);
    this.notifyTransitionListeners(transition);
  }

  /**
   * Check if a transition is valid
   */
  private isValidTransition(from: AIStatusType, to: AIStatusType): boolean {
    if (from === to) return true;
    const allowedTransitions = TRANSITION_RULES[from];
    return allowedTransitions?.includes(to) ?? false;
  }

  /**
   * Get current status
   */
  getCurrentStatus(): AIStatus {
    return { ...this.currentStatus };
  }

  /**
   * Get status history
   */
  getStatusHistory(): AIStatus[] {
    return [...this.statusHistory];
  }

  /**
   * Get transition history
   */
  getTransitionHistory(): StatusTransition[] {
    return [...this.transitionHistory];
  }

  /**
   * Subscribe to status changes
   */
  subscribe(callback: (status: AIStatus) => void): () => void {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  /**
   * Subscribe to transition events
   */
  subscribeTransition(callback: (transition: StatusTransition) => void): () => void {
    this.transitionListeners.add(callback);
    return () => this.transitionListeners.delete(callback);
  }

  /**
   * Notify all status listeners
   */
  private notifyListeners(status: AIStatus): void {
    this.listeners.forEach((callback) => callback(status));
  }

  /**
   * Notify all transition listeners
   */
  private notifyTransitionListeners(transition: StatusTransition): void {
    this.transitionListeners.forEach((callback) => callback(transition));
  }

  /**
   * Reset to idle state
   */
  reset(): void {
    this.setStatus("idle");
  }

  /**
   * Clear history
   */
  clearHistory(): void {
    this.statusHistory = [this.currentStatus];
    this.transitionHistory = [];
  }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Create a status manager with default configuration
 */
export function createStatusManager(initialStatus: AIStatusType = "idle"): AIStatusManager {
  return new AIStatusManager(initialStatus);
}

/**
 * Get status configuration
 */
export function getStatusConfig(type: AIStatusType) {
  return STATUS_CONFIG[type];
}

/**
 * Check if status is active (not idle/completed/error)
 */
export function isActiveStatus(status: AIStatusType): boolean {
  return !["idle", "completed", "success", "error", "cancelled", "timeout"].includes(status);
}

/**
 * Get status priority for sorting
 */
export function getStatusPriority(status: AIStatusType): number {
  return STATUS_CONFIG[status]?.priority ?? 0;
}

/**
 * Format status for display
 */
export function formatStatus(status: AIStatus): string {
  const config = STATUS_CONFIG[status.type];
  const message = status.message || status.type.charAt(0).toUpperCase() + status.type.slice(1);
  const progress = status.progress !== undefined ? ` (${Math.round(status.progress * 100)}%)` : "";
  return `${message}${progress}`;
}

export type StatusStepLike = {
  type?: string;
  status?: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: string;
  startedAt?: string;
  completedAt?: string;
  durationMs?: number;
  plan?: string;
  details?: string;
  data?: Record<string, unknown>;
  title?: string;
};

const STATUS_SEARCH_TOOL_NAMES = new Set([
  "grep",
  "glob",
  "web_search",
  "web_fetch",
  "github_search",
  "drive_search",
  "search_ecosystem_docs",
  "crawl_url",
]);

const STATUS_READ_TOOL_NAMES = new Set([
  "read_file",
  "file_read",
  "github_read_file",
  "drive_read_file",
]);
const STATUS_WRITE_TOOL_NAMES = new Set([
  "write_file",
  "file_write",
  "edit_file",
  "file_edit",
  "notion_create_page",
  "notion_append_content",
]);
const STATUS_EXECUTION_TOOL_NAMES = new Set(["bash", "run_command", "kill_shell", "slash_command"]);
const STATUS_DATA_TOOL_NAMES = new Set([
  "todo_write",
  "todo_read",
  "memory_write",
  "memory_read",
  "memory_search",
  "document_convert",
  "data_analyze",
]);

function describeStatusDuration(
  step: Pick<StatusStepLike, "startedAt" | "completedAt" | "durationMs">,
): string | undefined {
  if (typeof step.durationMs === "number" && Number.isFinite(step.durationMs)) {
    return step.durationMs < 1000
      ? `${Math.max(0, Math.round(step.durationMs))}ms`
      : step.durationMs / 1000 < 10
        ? `${(step.durationMs / 1000).toFixed(1)}s`
        : `${Math.round(step.durationMs / 1000)}s`;
  }

  const startedAt = step.startedAt ? Date.parse(step.startedAt) : NaN;
  const completedAt = step.completedAt ? Date.parse(step.completedAt) : NaN;
  if (!Number.isFinite(startedAt) || !Number.isFinite(completedAt) || completedAt < startedAt) {
    return undefined;
  }

  const durationMs = completedAt - startedAt;
  return durationMs < 1000
    ? `${Math.max(0, Math.round(durationMs))}ms`
    : durationMs / 1000 < 10
      ? `${(durationMs / 1000).toFixed(1)}s`
      : `${Math.round(durationMs / 1000)}s`;
}

export function deriveAIStatusFromStep(
  step: StatusStepLike,
  options?: { isStreaming?: boolean; timerSeconds?: number },
): AIStatus {
  const timestamp = Date.now();
  const name = step.toolName || "";
  const isStreaming = options?.isStreaming ?? false;

  if (step.type === "thinking") {
    if (step.status === "failed") {
      return {
        type: "error",
        message: "Thought process failed",
        timestamp,
        metadata: { stepType: step.type },
      };
    }

    if (step.status === "completed") {
      const duration = describeStatusDuration(step);
      return {
        type: "completed",
        message: duration ? `Thought for ${duration}` : "Thought process completed",
        timestamp,
        metadata: { stepType: step.type },
      };
    }

    const timerSeconds = options?.timerSeconds;
    return {
      type: "thinking",
      message: timerSeconds && timerSeconds > 0 ? `Thinking for ${timerSeconds}s` : "Thinking",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  if (step.type === "plan") {
    return {
      type: "processing",
      message: "Planning",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  if (
    step.type === "permission" ||
    step.type === "permission_request" ||
    step.type === "ask_user_question"
  ) {
    return {
      type: "waiting",
      message: step.type === "ask_user_question" ? "Clarification needed" : "Awaiting approval",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  if (step.type === "observing" || step.type === "observation") {
    return {
      type: "analyzing",
      message: "Analyzing",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  if (
    step.type === "agent_testing" ||
    step.type === "agent_verifying" ||
    step.type === "agent_self_correct"
  ) {
    return { type: "simulating", message: "Testing", timestamp, metadata: { stepType: step.type } };
  }

  if (STATUS_SEARCH_TOOL_NAMES.has(name)) {
    return { type: "searching", message: "Searching", timestamp, metadata: { toolName: name } };
  }

  if (STATUS_READ_TOOL_NAMES.has(name)) {
    return { type: "reading", message: "Reading", timestamp, metadata: { toolName: name } };
  }

  if (STATUS_WRITE_TOOL_NAMES.has(name)) {
    return { type: "writing", message: "Writing", timestamp, metadata: { toolName: name } };
  }

  if (STATUS_EXECUTION_TOOL_NAMES.has(name)) {
    return {
      type: "executing",
      message: isStreaming ? "Running" : "Executing",
      timestamp,
      metadata: { toolName: name },
    };
  }

  if (STATUS_DATA_TOOL_NAMES.has(name)) {
    return {
      type: "creating",
      message: "Processing data",
      timestamp,
      metadata: { toolName: name },
    };
  }

  if (step.type === "tool_output") {
    return {
      type: "streaming",
      message: "Streaming output",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  if (step.status === "failed") {
    return { type: "error", message: "Failed", timestamp, metadata: { stepType: step.type } };
  }

  if (step.status === "awaiting_approval") {
    return {
      type: "waiting",
      message: "Awaiting approval",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  if (step.status === "completed") {
    return {
      type: "completed",
      message: "Completed",
      timestamp,
      metadata: { stepType: step.type },
    };
  }

  return {
    type: isStreaming ? "streaming" : "processing",
    message: name ? name.replace(/_/g, " ") : "Processing",
    timestamp,
    metadata: { stepType: step.type, toolName: name || undefined },
  };
}

export function getStepStatusLabel(
  step: StatusStepLike,
  options?: { isStreaming?: boolean; timerSeconds?: number },
): string {
  return formatStatus(deriveAIStatusFromStep(step, options));
}
