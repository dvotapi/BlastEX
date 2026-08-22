import { useState } from "react";
import type { User } from "../types";
import { WorkspaceProvider } from "./useWorkspace";
import { WorkspaceBar } from "./WorkspaceBar";
import { CalcPage } from "../pages/CalcPage";
import { DrillingPage } from "../pages/DrillingPage";
import { LaborPage } from "../pages/LaborPage";
import { ReferencesPage } from "../pages/ReferencesPage";

const PAGES = ["Расчёт", "Бурение", "ФОТ", "Справочники"] as const;
type Page = (typeof PAGES)[number];
const ICONS: Record<Page, string> = { "Расчёт": "◫", "Бурение": "⌁", "ФОТ": "◎", "Справочники": "▤" };

export function AppShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState<Page>("Расчёт");

  return (
    <WorkspaceProvider user={user}>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand"><span>BX</span>BlastEX</div>
          <nav>
            {PAGES.map((item) => (
              <button key={item} className={page === item ? "active" : ""} onClick={() => setPage(item)}>
                <i>{ICONS[item]}</i>{item}
              </button>
            ))}
          </nav>
          <div className="user-box">
            <div>{(user.display_name || user.email).slice(0, 2).toUpperCase()}</div>
            <span>
              <b>{user.display_name}</b>
              <small>{user.role === "admin" ? "Администратор" : user.role === "reference_editor" ? "Редактор" : "Пользователь"}</small>
            </span>
          </div>
        </aside>
        <main className="workspace">
          <header className="topbar">
            <div><b>{page === "Расчёт" ? "Расчёт БВР" : page}</b><span>{user.organization_name}</span></div>
            <button className="logout-button" onClick={onLogout}>Выйти</button>
          </header>
          <WorkspaceBar />
          {page === "Расчёт" && <CalcPage />}
          {page === "Бурение" && <DrillingPage />}
          {page === "ФОТ" && <LaborPage />}
          {page === "Справочники" && <ReferencesPage />}
        </main>
        <nav className="mobile-nav">
          {PAGES.map((item) => (
            <button key={item} className={page === item ? "active" : ""} onClick={() => setPage(item)}>
              <b>{ICONS[item]}</b>{item}
            </button>
          ))}
        </nav>
      </div>
    </WorkspaceProvider>
  );
}
