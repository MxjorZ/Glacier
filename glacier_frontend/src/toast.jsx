import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner";
import { createContext, useContext } from "react";

// Glacier toasts via Sonner (same toast system SpotiFLAC uses).
export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast: "group font-sans rounded-lg border bg-popover text-popover-foreground shadow-lg",
        },
      }}
    />
  );
}

// Thin helper so call sites can do toast.success(...) / toast.error(...).
export const toast = {
  success: (m) => sonnerToast.success(m),
  error: (m) => sonnerToast.error(m),
  warn: (m) => sonnerToast.warning(m),
  warning: (m) => sonnerToast.warning(m),
  info: (m) => sonnerToast.info(m),
  message: (m) => sonnerToast(m),
};

// Backwards-compatible context/hook (older code used useToast).
const ToastCtx = createContext(toast);
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  return <ToastCtx.Provider value={toast}>{children}</ToastCtx.Provider>;
}
