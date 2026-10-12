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

  interface Window {
    electron?: {
      isElectron: true;
      window: {
        minimize: () => Promise<void>;
        toggleMaximize: () => Promise<boolean>;
        isMaximized: () => Promise<boolean>;
        hide: () => Promise<void>;
      };
      openExternal: (url: string) => Promise<boolean>;
      workspace: {
        openNeosis: () => Promise<{ ok: boolean; error?: string }>;
        openAverQel: () => Promise<{ ok: boolean; error?: string }>;
      };
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
    };
  }
}
