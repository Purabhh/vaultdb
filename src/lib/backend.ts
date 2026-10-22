// Transport to the Python backend, exposed by pywebview as window.pywebview.api.
// Keeps the call shapes the app used with Tauri: invoke(command, args), listen(event, handler), open().

export type UnlistenFn = () => void;

type BackendApi = { invoke: (command: string, args: Record<string, unknown>) => Promise<unknown> };

declare global {
  interface Window {
    pywebview?: { api: BackendApi };
    __vaultdbEmit?: (event: string, payload: unknown) => void;
  }
}

let ready: Promise<void> | null = null;

function whenReady(): Promise<void> {
  if (!ready) {
    ready = new Promise((resolve) => {
      if (window.pywebview?.api) return resolve();
      window.addEventListener("pywebviewready", () => resolve(), { once: true });
    });
  }
  return ready;
}

export async function invoke<T = unknown>(command: string, args?: Record<string, unknown>): Promise<T> {
  await whenReady();
  try {
    return (await window.pywebview!.api.invoke(command, args ?? {})) as T;
  } catch (e) {
    // Reject with a plain message, as Tauri did.
    throw typeof e === "string" ? e : ((e as { message?: string })?.message ?? String(e));
  }
}

type Handler = (event: { payload: unknown }) => void;
const listeners = new Map<string, Set<Handler>>();

// The backend pushes events (e.g. "vault-file-change") by calling this from Python.
window.__vaultdbEmit = (event, payload) => {
  listeners.get(event)?.forEach((handler) => handler({ payload }));
};

export async function listen<T>(event: string, handler: (event: { payload: T }) => void): Promise<UnlistenFn> {
  const set = listeners.get(event) ?? new Set<Handler>();
  listeners.set(event, set);
  set.add(handler as Handler);
  return () => {
    set.delete(handler as Handler);
  };
}

export async function open(_options: { directory: true }): Promise<string | null> {
  return invoke<string | null>("pick_folder");
}
