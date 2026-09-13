"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

type Mode = "login" | "request-reset" | "reset";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pinFile, setPinFile] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token } = await api.login(username, password);
      setToken(access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRequestReset(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const { pin_file } = await api.requestPasswordReset(username);
      setPinFile(pin_file);
      setMode("reset");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not request a reset PIN");
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.resetPassword(username, pin, newPassword);
      setInfo("Password reset. You can sign in with your new password now.");
      setMode("login");
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-sm">
      <h1 className="mb-6 text-center text-2xl font-bold">
        {mode === "login" ? "Sign in to Vault" : "Reset your password"}
      </h1>

      {mode === "login" && (
        <>
          <p className="mb-6 text-center text-sm text-vault-muted">
            Uses your existing Jellyfin account — no separate signup needed.
          </p>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              className="rounded-md border border-vault-border bg-vault-surface px-3 py-2 focus:border-vault-accent focus:outline-none"
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="rounded-md border border-vault-border bg-vault-surface px-3 py-2 focus:border-vault-accent focus:outline-none"
            />
            {info && <p className="text-sm text-green-400">{info}</p>}
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-vault-accent px-4 py-2.5 font-semibold hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
          <button
            onClick={() => {
              setMode("request-reset");
              setError(null);
              setInfo(null);
            }}
            className="mt-4 w-full text-center text-sm text-vault-muted hover:text-vault-text"
          >
            Forgot password?
          </button>
        </>
      )}

      {mode === "request-reset" && (
        <>
          <p className="mb-6 text-center text-sm text-vault-muted">
            Enter your Jellyfin username. We&apos;ll ask Jellyfin to generate a one-time PIN — you&apos;ll
            need terminal access to your server to read it, which is what proves you&apos;re the admin.
          </p>
          <form onSubmit={handleRequestReset} className="flex flex-col gap-4">
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              className="rounded-md border border-vault-border bg-vault-surface px-3 py-2 focus:border-vault-accent focus:outline-none"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-vault-accent px-4 py-2.5 font-semibold hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? "Requesting..." : "Send reset PIN"}
            </button>
          </form>
          <button
            onClick={() => setMode("login")}
            className="mt-4 w-full text-center text-sm text-vault-muted hover:text-vault-text"
          >
            Back to sign in
          </button>
        </>
      )}

      {mode === "reset" && (
        <>
          <div className="mb-6 rounded-md border border-vault-border bg-vault-surface p-4 text-sm">
            <p className="mb-2 text-vault-muted">
              Jellyfin wrote the PIN to a file on your server. Run this on the machine hosting Vault:
            </p>
            <code className="block break-all rounded bg-black/40 p-2 text-xs text-vault-text">
              docker exec media-jellyfin-1 cat {pinFile ?? "/config/data/passwordreset/passwordreset-*.json"}
            </code>
            <p className="mt-2 text-vault-muted">Copy the &quot;Pin&quot; value from that file below.</p>
          </div>
          <form onSubmit={handleResetPassword} className="flex flex-col gap-4">
            <input
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="PIN from the file"
              className="rounded-md border border-vault-border bg-vault-surface px-3 py-2 focus:border-vault-accent focus:outline-none"
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="New password"
              className="rounded-md border border-vault-border bg-vault-surface px-3 py-2 focus:border-vault-accent focus:outline-none"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-vault-accent px-4 py-2.5 font-semibold hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? "Resetting..." : "Reset password"}
            </button>
          </form>
          <button
            onClick={() => setMode("login")}
            className="mt-4 w-full text-center text-sm text-vault-muted hover:text-vault-text"
          >
            Back to sign in
          </button>
        </>
      )}
    </div>
  );
}
