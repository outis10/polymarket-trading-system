import { useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import LoginScreen from "./auth/LoginScreen";
import { isAuthenticated } from "./auth/useAuth";
import "./styles/global.css";

function Root() {
    const [authed, setAuthed] = useState(isAuthenticated());

    if (!authed) {
        return <LoginScreen onSuccess={() => setAuthed(true)} />;
    }

    return <App />;
}

createRoot(document.getElementById("root")!).render(<Root />);
