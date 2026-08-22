import { useState } from "react";
import type { BlastVariant, User } from "../types";
import { WorkspaceProvider } from "./useWorkspace";
import { WorkspaceBar } from "./WorkspaceBar";
import { CalcPage } from "../pages/CalcPage";
import { DesignPage } from "../pages/design/DesignPage";
import { DrillingPage } from "../pages/DrillingPage";
import { LaborPage } from "../pages/LaborPage";
import { ReferencesPage } from "../pages/ReferencesPage";

const PAGES = ["Расчёт", "Проектирование", "Бурение", "ФОТ", "Справочники"] as const;
type Page = (typeof PAGES)[number];
const ICONS: Record<Page, string> = {
  "Расчёт": "◫",
  "Проектирование": "⛏",
  "Бурение": "⌁",
  "ФОТ": "◎",
  "Справочники": "▤",
};
const TITLES: Record<Page, string> = {
  "Расчёт": "Расчёт БВР",
  "Проектирование": "Проектирование БВР",
  "Бурение": "Бурение",
  "ФОТ": "ФОТ",
  "Справочники": "Справочники",
};

export function AppShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState<Page>("Расчёт");
  const [pendingVariant, setPendingVariant] = useState<BlastVariant | null>(null);

  function sendToDesign(variant: BlastVariant) {
    setPendingVariant(variant);
    setPage("Проектирование");
  }

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
            <div><b>{TITLES[page]}</b><span>{user.organization_name}</span></div>
            <button className="logout-button" onClick={onLogout}>Выйти</button>
          </header>
          {page !== "Проектирование" && <WorkspaceBar />}
          {page === "Расчёт" && <CalcPage onSendToDesign={sendToDesign} />}
          {page === "Проектирование" && (
            <DesignPage
              user={user}
              incomingVariant={pendingVariant}
              onVariantConsumed={() => setPendingVariant(null)}
            />
          )}
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
