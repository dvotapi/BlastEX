import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { BlastVariant, Explosive, Rock, User } from "./types";

const crownDiameters = [110, 115, 122, 125, 130, 140, 152, 165, 171, 220, 250];

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

function ResultsChart({ variants }: { variants: BlastVariant[] }) {
  if (!variants.length) return <div className="chart-empty">После расчёта здесь появится сравнение вариантов.</div>;
  const width = 620;
  const height = 190;
  const pad = { left: 42, right: 20, top: 20, bottom: 35 };
  const qValues = variants.map((item) => item.specific_q_kg_m3);
  const minQ = Math.min(...qValues) - 0.04;
  const maxQ = Math.max(...qValues) + 0.04;
  const x = (index: number) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, variants.length - 1));
  const y = (value: number) => pad.top + (maxQ - value) / (maxQ - minQ) * (height - pad.top - pad.bottom);
  const points = variants.map((item, index) => `${x(index)},${y(item.specific_q_kg_m3)}`).join(" ");
  return (
    <svg className="result-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Зависимость удельного расхода от диаметра коронки">
      {[0, 1, 2].map((line) => <line key={line} x1={pad.left} x2={width - pad.right} y1={pad.top + line * 58} y2={pad.top + line * 58} />)}
      <polyline points={points} />
      {variants.map((item, index) => <g key={item.crown_mm}><circle cx={x(index)} cy={y(item.specific_q_kg_m3)} r="5" /><text x={x(index)} y={height - 10} textAnchor="middle">{item.crown_mm}</text></g>)}
    </svg>
  );
}

function Calculator({ user }: { user: User }) {
  const [rocks, setRocks] = useState<Rock[]>([]);
  const [explosives, setExplosives] = useState<Explosive[]>([]);
  const [rockName, setRockName] = useState("");
  const [explosiveKey, setExplosiveKey] = useState("");
  const [benchHeight, setBenchHeight] = useState(10);
  const [overdrill, setOverdrill] = useState(1);
  const [lumpSize, setLumpSize] = useState(400);
  const [threshold, setThreshold] = useState(5);
  const [spacing, setSpacing] = useState(1.25);
  const [variants, setVariants] = useState<BlastVariant[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.rocks(), api.explosives()]).then(([rockData, explosiveData]) => {
      setRocks(rockData.items);
      setExplosives(explosiveData.items);
      setRockName(rockData.default_name);
      setExplosiveKey(explosiveData.default_key);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось загрузить справочники."));
  }, []);

  const rock = useMemo(() => rocks.find((item) => item.name === rockName), [rocks, rockName]);
  const explosive = useMemo(() => explosives.find((item) => item.key === explosiveKey), [explosives, explosiveKey]);
  const selected = variants[selectedIndex];

  async function calculate() {
    if (!rock || !explosive) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.optimize({ rock, explosive, lumpSize, benchHeight, overdrill, spacing, threshold });
      setVariants(result.variants);
      const preferred = result.variants.findIndex((item) => item.crown_mm === 152);
      setSelectedIndex(preferred >= 0 ? preferred : 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ошибка расчёта.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-content">
      <div className="page-heading"><div><h1>Параметры взрывания</h1><p>Подберите сетку скважин и сравните технологические варианты</p></div><span className="save-status">● Внутренняя организация</span></div>
      {error && <div className="page-error" role="alert">{error}</div>}
      <div className="calculator-grid">
        <section className="panel input-panel">
          <header><b>Исходные данные</b><span>01</span></header>
          <div className="panel-body">
            <label>Порода<select value={rockName} onChange={(e) => setRockName(e.target.value)}>{rocks.map((item) => <option key={item.name}>{item.name}</option>)}</select></label>
            <label>Взрывчатое вещество<select value={explosiveKey} onChange={(e) => setExplosiveKey(e.target.value)}>{explosives.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label>
            <div className="field-pair">
              <label>Высота уступа, м<input type="number" min="5" max="25" step="0.5" value={benchHeight} onChange={(e) => setBenchHeight(Number(e.target.value))} /></label>
              <label>Перебур, м<input type="number" min="0" max="3" step="0.1" value={overdrill} onChange={(e) => setOverdrill(Number(e.target.value))} /></label>
            </div>
            <label>Кондиционный кусок, мм<input type="number" min="100" max="1200" step="50" value={lumpSize} onChange={(e) => setLumpSize(Number(e.target.value))} /></label>
            <label className="range-label"><span>Допустимый негабарит <b>{threshold}%</b></span><input type="range" min="1" max="15" step="0.5" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label>
            <label className="range-label"><span>Коэффициент сетки a/W <b>{spacing.toFixed(2).replace(".", ",")}</b></span><input type="range" min="1" max="2" step="0.05" value={spacing} onChange={(e) => setSpacing(Number(e.target.value))} /></label>
            <small>Характеристики породы и ВВ загружены из справочников {user.organization_name}.</small>
            <button className="calculate-button" onClick={calculate} disabled={busy || !rock || !explosive}>{busy ? "Выполняется расчёт…" : "Рассчитать варианты"}</button>
          </div>
        </section>
        <div className="results-column">
          <div className="metrics-grid">
            <div><span>Удельный расход</span><strong>{selected?.specific_q_kg_m3.toFixed(2).replace(".", ",") ?? "—"}</strong><small>кг/м³</small></div>
            <div><span>ЛНС W</span><strong>{selected?.line_of_least_resistance_m.toFixed(2).replace(".", ",") ?? "—"}</strong><small>м</small></div>
            <div><span>Средний кусок x50</span><strong>{selected?.x50_mm.toFixed(1).replace(".", ",") ?? "—"}</strong><small>мм</small></div>
            <div><span>Негабарит</span><strong>{selected?.oversize_pct.toFixed(1).replace(".", ",") ?? "—"}</strong><small>%</small></div>
          </div>
          <section className="panel"><header><b>Зависимость расхода от диаметра</b><span>Куз–Рам</span></header><ResultsChart variants={variants} /></section>
          <section className="panel variants-panel"><header><b>Варианты сетки</b><span>{variants.length ? `${variants.length} вариантов` : "Нет расчёта"}</span></header>
            <div className="table-scroll"><table><thead><tr><th></th><th>Коронка</th><th>Сетка a × b</th><th>q, кг/м³</th><th>Негабарит</th></tr></thead><tbody>
              {variants.map((item, index) => <tr key={item.crown_mm} className={index === selectedIndex ? "selected" : ""} onClick={() => setSelectedIndex(index)}><td><span className="row-radio" /></td><td><b>Ø {item.crown_mm} мм</b></td><td>{item.grid_label} м</td><td>{item.specific_q_kg_m3.toFixed(2).replace(".", ",")}</td><td>{item.oversize_pct.toFixed(1).replace(".", ",")}%</td></tr>)}
            </tbody></table></div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState("Расчёт");
  const pages = ["Расчёт", "Бурение", "ФОТ", "Справочники"];
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span>BX</span>BlastEX</div><nav>{pages.map((item, index) => <button key={item} className={page === item ? "active" : ""} onClick={() => setPage(item)}><i>{["◫", "⌁", "◎", "▤"][index]}</i>{item}</button>)}</nav><div className="user-box"><div>{(user.display_name || user.email).slice(0, 2).toUpperCase()}</div><span><b>{user.display_name}</b><small>{user.role === "admin" ? "Администратор" : user.role === "reference_editor" ? "Редактор" : "Пользователь"}</small></span></div></aside>
    <main className="workspace"><header className="topbar"><div><b>{page === "Расчёт" ? "Расчёт БВР" : page}</b><span>{user.organization_name}</span></div><button className="logout-button" onClick={onLogout}>Выйти</button></header>
      {page === "Расчёт" ? <Calculator user={user} /> : <div className="coming-soon"><span>{page === "Бурение" ? "⌁" : page === "ФОТ" ? "◎" : "▤"}</span><h1>{page}</h1><p>Раздел будет перенесён из Streamlit на следующем этапе.</p></div>}
    </main>
    <nav className="mobile-nav">{pages.map((item, index) => <button key={item} className={page === item ? "active" : ""} onClick={() => setPage(item)}><b>{["◫", "⌁", "◎", "▤"][index]}</b>{item}</button>)}</nav>
  </div>;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => { api.me().then(setUser).catch(() => setUser(null)).finally(() => setChecking(false)); }, []);
  async function logout() { await api.logout().catch(() => undefined); setUser(null); }
  if (checking) return <div className="loading-screen"><span>BX</span><p>Загрузка BlastEX…</p></div>;
  return user ? <Workspace user={user} onLogout={logout} /> : <Login onLogin={setUser} />;
}
