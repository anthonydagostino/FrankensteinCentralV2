import { useState } from "react";
import { useLogin } from "../api/hooks";

export function LoginPage({ passwordConfigured }: { passwordConfigured?: boolean }) {
  const login = useLogin();
  const [password, setPassword] = useState("");
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form
        className="w-full max-w-sm space-y-4 rounded-2xl border border-ink-700 bg-ink-900 p-6"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate(password);
        }}
      >
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-xl font-black text-accent">F</span>
          <div>
            <h1 className="text-lg font-semibold text-ink-200">FrankensteinCentral</h1>
            <p className="text-xs text-ink-400">Sign in to continue</p>
          </div>
        </div>
        {passwordConfigured === false && <p className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">No DASHBOARD_PASSWORD_HASH is set, so any password works. Generate one with python -m app.hash_password (see README).</p>}
        <label className="block text-xs text-ink-400">
          Password
          <input type="password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-200 outline-none focus:border-accent" />
        </label>
        {login.isError && <p className="text-xs text-red-300">{(login.error as Error).message}</p>}
        <button type="submit" disabled={login.isPending || !password} className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-ink-950 hover:brightness-110 disabled:opacity-50">
          {login.isPending ? "Signing in" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
