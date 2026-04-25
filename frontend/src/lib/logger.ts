const IS_DEV = import.meta.env.DEV;

export const logger = {
  info: (message: string, ...args: any[]) => {
    if (IS_DEV) console.info(`[INFO] ${message}`, ...args);
  },
  error: (message: string, ...args: any[]) => {
    console.error(`[ERROR] ${message}`, ...args);
  },
  warn: (message: string, ...args: any[]) => {
    if (IS_DEV) console.warn(`[WARN] ${message}`, ...args);
  }
};
