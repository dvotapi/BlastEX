import { useState } from "react";
import type { BlastVariant, User } from "../types";
import { WorkspaceProvider } from "./useWorkspace";
import { WorkspaceBar } from "./WorkspaceBar";
import { CalcPage } from "../pages/CalcPage";
import { DesignPage } from "../pages/design/DesignPage";
import { DrillingPage } from "../pages/DrillingPage";
import { LaborPage } from "../pages/LaborPage";
import { ReferencesPage as CalcReferencesPage } from "../pages/ReferencesPage";
import { EconomicsPage } from "../pages/EconomicsPage";
import { ReferencesPage } from "../pages/references/ReferencesPage";

const PAGES = ["Расчёт", "Проектирование", "Экономика юнита", "Бурение", "ФОТ", "Справочники", "Справочники расчёта"] as const;
type Page = (typeof PAGES)[number];
const ICONS: Record<Page, string> = {
  "Расчёт": "◫",
  "Проектирование": "⛏",
  "Экономика юнита": "₽",
  "Бурение": "⌁",
  "ФОТ": "◎",
  "Справочники": "▦",
  "Справочники расчёта": "▤",
};
const TITLES: Record<Page, string> = {
  "Расчёт": "Расчёт БВР",
  "Проектирование": "Проектирование БВР",
  "Экономика юнита": "Экономика производственного юнита",
  "Бурение": "Бурение",
  "ФОТ": "ФОТ",
  "Справочники": "Справочники",
  "Справочники расчёта": "Справочники расчёта БВР",
};

export function AppShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState<Page>("Расчёт");
  const [pendingVariant, setPendingVariant] = useState<BlastVariant | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    const saved = window.localStorage.getItem("blastex.sidebar.collapsed");
    // Start with the workspace-first layout; a user's explicit choice is kept.
    return saved === null ? true : saved === "true";
  });

  function sendToDesign(variant: BlastVariant) {
    setPendingVariant(variant);
    setPage("Проектирование");
  }

  function toggleSidebar() {
    setSidebarCollapsed((collapsed) => {
      const next = !collapsed;
      window.localStorage.setItem("blastex.sidebar.collapsed", String(next));
      return next;
    });
  }

  return (
    <WorkspaceProvider user={user}>
      <div className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}${page === "Проектирование" ? " design-mode" : ""}`}>
        <aside className={`sidebar${sidebarCollapsed ? " collapsed" : ""}`}>
          <div className="brand">
            <span>BX</span>
            <strong className="brand-name">BlastEX</strong>
            <button
              className="sidebar-toggle"
              type="button"
              onClick={toggleSidebar}
              aria-label={sidebarCollapsed ? "Развернуть боковую панель" : "Свернуть боковую панель"}
              title={sidebarCollapsed ? "Развернуть панель" : "Свернуть панель"}
            >
              {sidebarCollapsed ? "›" : "‹"}
            </button>
          </div>
          <nav>
            {PAGES.map((item) => (
              <button
                key={item}
                className={page === item ? "active" : ""}
                onClick={() => setPage(item)}
                title={sidebarCollapsed ? item : undefined}
                aria-label={item}
              >
                <i aria-hidden="true">{ICONS[item]}</i><span>{item}</span>
              </button>
            ))}
          </nav>
          <div className="user-box">
            <div>{(user.display_name || user.email).slice(0, 2).toUpperCase()}</div>
            <span className="user-details">
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
          {page !== "Проектирование" && page !== "Экономика юнита" && page !== "Справочники" && <WorkspaceBar />}
          {page === "Расчёт" && <CalcPage onSendToDesign={sendToDesign} />}
          {page === "Проектирование" && (
            <DesignPage
              user={user}
              incomingVariant={pendingVariant}
              onVariantConsumed={() => setPendingVariant(null)}
            />
          )}
          {page === "Экономика юнита" && <EconomicsPage />}
          {page === "Бурение" && <DrillingPage />}
          {page === "ФОТ" && <LaborPage />}
          {page === "Справочники" && <ReferencesPage user={user} />}
          {page === "Справочники расчёта" && <CalcReferencesPage />}
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
