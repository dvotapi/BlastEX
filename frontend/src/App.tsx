import { FormEvent, useEffect, useState } from "react";
import { api } from "./api/endpoints";
import type { User } from "./types";
import { AppShell } from "./app/AppShell";

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await api.login(email, password));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-brand"><span>BX</span> BlastEX</div>
        <h1>Внутренний сервис БВР</h1>
        <p>Расчёт технологических параметров и стоимости буровзрывных работ.</p>
        <form onSubmit={submit}>
          <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Пароль<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="primary-button" disabled={busy}>{busy ? "Выполняется вход…" : "Войти"}</button>
        </form>
        <div className="external-stub"><b>Доступ для внешних организаций</b><span>Подключение пока недоступно</span></div>
      </section>
    </main>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => { api.me().then(setUser).catch(() => setUser(null)).finally(() => setChecking(false)); }, []);
  async function logout() { await api.logout().catch(() => undefined); setUser(null); }
  if (checking) return <div className="loading-screen"><span>BX</span><p>Загрузка BlastEX…</p></div>;
  return user ? <AppShell user={user} onLogout={logout} /> : <Login onLogin={setUser} />;
}
