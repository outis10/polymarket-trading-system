import { useState } from "react";
import { login } from "./useAuth";

interface LoginScreenProps {
    onSuccess: () => void;
}

export default function LoginScreen({ onSuccess }: LoginScreenProps) {
    const [password, setPassword] = useState("");
    const [error, setError] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        setError(false);
        const ok = login(password);
        if (ok) {
            onSuccess();
        } else {
            setError(true);
            setPassword("");
        }
        setSubmitting(false);
    };

    return (
        <div className="login-screen">
            <div className="login-card">
                <div className="login-logo">⚡</div>
                <h1 className="login-title">Polymarket Bot</h1>
                <form className="login-form" onSubmit={handleSubmit}>
                    <input
                        className={`login-input${error ? " login-input-error" : ""}`}
                        type="password"
                        placeholder="Password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoFocus
                        autoComplete="current-password"
                    />
                    {error && (
                        <div className="login-error">Incorrect password</div>
                    )}
                    <button
                        className="login-btn"
                        type="submit"
                        disabled={submitting || !password}
                    >
                        Enter
                    </button>
                </form>
            </div>
        </div>
    );
}
