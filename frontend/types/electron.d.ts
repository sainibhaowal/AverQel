export {};

declare global {
  type ElectronCodexAccount = {
    id: string;
    email: string | null;
    name: string | null;
    connected: boolean;
    source?: "chatgpt" | "codex_cli";
    planType?: string | null;
  };

  type ElectronCodexModel = {
    id: string;
    name: string;
    kind: "chat";
    supportedReasoningEfforts?: string[];
    reasoningEffortValues?: Record<string, string>;
  };

  type ElectronCodexStreamFrame = {
    streamId: string;
    kind: "event" | "error" | "closed";
    event?: Record<string, unknown>;
    message?: string;
    httpStatus?: number;
    code?: string;
    param?: string;
    requestId?: string;
  };

  type ElectronLocalRuntimeStreamFrame = {
    streamId: string;
    kind: "event" | "error" | "closed";
    event?: Record<string, unknown>;
    message?: string;
    httpStatus?: number;
    code?: string;
  };

  interface Window {
    electron?: {
      isElectron: true;
      window: {
        minimize: () => Promise<void>;
        close: () => Promise<void>;
        toggleMaximize: () => Promise<boolean>;
        isMaximized: () => Promise<boolean>;
      };
      openExternal: (url: string) => Promise<boolean>;
      codex: {
        status: () => Promise<{
          available: boolean;
          chatgptSignInAvailable?: boolean;
          accounts: ElectronCodexAccount[];
          message?: string;
          cliMessage?: string;
        }>;
        connect: (
          accountId?: string | null,
          source?: "chatgpt" | "codex_cli",
        ) => Promise<{
          account: ElectronCodexAccount;
          models: ElectronCodexModel[];
          modelError?: string;
        }>;
        models: (accountId: string) => Promise<ElectronCodexModel[]>;
        disconnect: (accountId: string) => Promise<{ ok: boolean; revoked: boolean }>;
        startStream: (input: {
          streamId: string;
          accountId: string;
          request: Record<string, unknown>;
        }) => Promise<{ started: boolean }>;
        cancelStream: (streamId: string) => Promise<boolean>;
        onStreamEvent: (callback: (frame: ElectronCodexStreamFrame) => void) => () => void;
      };
      localRuntime?: {
        status: () => Promise<{ available: boolean; providers: string[]; active_streams: number }>;
        startStream: (input: {
          streamId: string;
          providerType: "lmstudio" | "ollama";
          baseUrl: string;
          operation?: "chat" | "health" | "models" | "embed" | "pull";
          request?: Record<string, unknown>;
        }) => Promise<unknown>;
        cancelStream: (streamId: string) => Promise<boolean>;
        onStreamEvent: (callback: (frame: ElectronLocalRuntimeStreamFrame) => void) => () => void;
      };
    };
  }
}
