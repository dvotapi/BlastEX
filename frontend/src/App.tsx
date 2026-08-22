import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { Calculator } from "./pages/Calculator";
import { DesignPage } from "./pages/design/DesignPage";
import type { BlastVariant, User } from "./types";

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

const NAV_ITEMS = [
  { key: "Расчёт", title: "Расчёт БВР", icon: "◫" },
  { key: "Проектирование", title: "Проектирование БВР", icon: "⛏" },
  { key: "Бурение", title: "Бурение", icon: "⌁" },
  { key: "ФОТ", title: "ФОТ", icon: "◎" },
  { key: "Справочники", title: "Справочники", icon: "▤" },
];

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState("Расчёт");
  const [pendingVariant, setPendingVariant] = useState<BlastVariant | null>(null);
  const current = NAV_ITEMS.find((item) => item.key === page) ?? NAV_ITEMS[0];

  function sendToDesign(variant: BlastVariant) {
    setPendingVariant(variant);
    setPage("Проектирование");
  }

  function renderPage() {
    if (page === "Расчёт") return <Calculator user={user} onSendToDesign={sendToDesign} />;
    if (page === "Проектирование") {
      return (
        <DesignPage
          user={user}
          incomingVariant={pendingVariant}
          onVariantConsumed={() => setPendingVariant(null)}
        />
      );
    }
    return (
      <div className="coming-soon">
        <span>{current.icon}</span>
        <h1>{page}</h1>
        <p>Раздел будет перенесён из Streamlit на следующем этапе.</p>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span>BX</span>BlastEX</div>
        <nav>
          {NAV_ITEMS.map((item) => (
            <button key={item.key} className={page === item.key ? "active" : ""} onClick={() => setPage(item.key)}>
              <i>{item.icon}</i>{item.key}
            </button>
          ))}
        </nav>
        <div className="user-box">
          <div>{(user.display_name || user.email).slice(0, 2).toUpperCase()}</div>
          <span><b>{user.display_name}</b><small>{user.role === "admin" ? "Администратор" : user.role === "reference_editor" ? "Редактор" : "Пользователь"}</small></span>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><b>{current.title}</b><span>{user.organization_name}</span></div>
          <button className="logout-button" onClick={onLogout}>Выйти</button>
        </header>
        {renderPage()}
      </main>
      <nav className="mobile-nav">
        {NAV_ITEMS.map((item) => (
          <button key={item.key} className={page === item.key ? "active" : ""} onClick={() => setPage(item.key)}>
            <b>{item.icon}</b>{item.key}
          </button>
        ))}
      </nav>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => { api.me().then(setUser).catch(() => setUser(null)).finally(() => setChecking(false)); }, []);
  async function logout() { await api.logout().catch(() => undefined); setUser(null); }
  if (checking) return <div className="loading-screen"><span>BX</span><p>Загрузка BlastEX…</p></div>;
  return user ? <Workspace user={user} onLogout={logout} /> : <Login onLogin={setUser} />;
}
