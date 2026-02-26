import { useEffect } from "react";
import { useEventsStore } from "../stores/useEventsStore";

const AUTO_DISMISS_MS = 5000;

export default function SystemToastBanner() {
    const toast = useEventsStore((s) => s.systemToast);
    const clearSystemToast = useEventsStore((s) => s.clearSystemToast);

    useEffect(() => {
        if (!toast) return;
        const t = setTimeout(clearSystemToast, AUTO_DISMISS_MS);
        return () => clearTimeout(t);
    }, [toast?.id, clearSystemToast]);

    if (!toast) return null;

    return (
        <div
            className={`system-toast system-toast-${toast.type}`}
            onClick={clearSystemToast}
            title="Click to dismiss"
        >
            {toast.message}
        </div>
    );
}
