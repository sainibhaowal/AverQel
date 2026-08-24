export {};

declare global {
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
    };
  }
}
