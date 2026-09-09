import { useState } from "react";
import type { BlastVariant, User } from "../types";
import { BRAND } from "./brand";
import { WorkspaceProvider } from "./useWorkspace";
import { WorkspaceBar } from "./WorkspaceBar";
import { TopbarSlotProvider } from "./topbarSlot";
import { CalcPage } from "../pages/CalcPage";
import { DesignPage } from "../pages/design/DesignPage";
import { DrillingPage } from "../pages/DrillingPage";
import { LaborPage } from "../pages/LaborPage";
import { EconomicsPage } from "../pages/EconomicsPage";
import { BlockEconomicsPage } from "../pages/economics/BlockEconomicsPage";
import { ReferencesPage } from "../pages/references/ReferencesPage";

const PAGES = ["Расчёт", "Проектирование", "Экономика", "Экономика юнита", "Бурение", "ФОТ", "Справочники"] as const;
type Page = (typeof PAGES)[number];
const ICONS: Record<Page, string> = {
  "Расчёт": "◫",
  "Проектирование": "⛏",
  "Экономика": "₽",
  "Экономика юнита": "◱",
  "Бурение": "⌁",
  "ФОТ": "◎",
  "Справочники": "▦",
};
const TITLES: Record<Page, string> = {
  "Расчёт": "Расчёт БВР",
  "Проектирование": "Проектирование БВР",
  "Экономика": "Экономика блока",
  "Экономика юнита": "Экономика производственного юнита",
  "Бурение": "Бурение",
  "ФОТ": "ФОТ",
  "Справочники": "Справочники",
};

export function AppShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState<Page>("Расчёт");
  const [pendingVariant, setPendingVariant] = useState<BlastVariant | null>(null);
  const [economicsPassportId, setEconomicsPassportId] = useState<string | null>(null);
  // Узел в шапке, куда лист «Расчёт» переносит свою полосу инструментов
  // через createPortal (см. topbarSlot.tsx); callback-ref, чтобы страницы
  // узнали об узле сразу после его монтирования.
  const [topbarSlot, setTopbarSlot] = useState<HTMLDivElement | null>(null);
  // Узел рядом с заголовком страницы: сюда вкладка «Экономика блока» кладёт
  // кнопку «Справка» через тот же портальный механизм (см. topbarSlot.tsx).
  const [titleSlot, setTitleSlot] = useState<HTMLDivElement | null>(null);
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

  function openEconomics(passportId: string) {
    setEconomicsPassportId(passportId);
    setPage("Экономика");
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
            <div className="topbar-lead">
              <b className="topbar-title">{TITLES[page]}</b>
              <div className="topbar-title-slot" ref={setTitleSlot} />
              {/* Бренд поставщика сервиса — не орг-данные пользователя: та же
                  строка раньше показывала `user.organization_name`, это поле
                  осталось (см. ReferencesPage.tsx), здесь только вид сменился. */}
              <div className="topbar-brand">
                <span className="topbar-brand-mark" aria-hidden="true">{BRAND.mark}</span>
                <span className="topbar-brand-text">
                  <b>{BRAND.name}</b>
                  <i>{BRAND.tagline}</i>
                </span>
              </div>
            </div>
            <div className="topbar-slot" ref={setTopbarSlot} />
            <button className="logout-button" onClick={onLogout}>Выйти</button>
          </header>
          <TopbarSlotProvider slot={topbarSlot} titleSlot={titleSlot}>
            {page !== "Расчёт" && page !== "Проектирование" && page !== "Экономика" && page !== "Экономика юнита" && page !== "Справочники" && <WorkspaceBar />}
            {page === "Расчёт" && <CalcPage onSendToDesign={sendToDesign} onOpenEconomics={openEconomics} />}
            {page === "Проектирование" && (
              <DesignPage
                user={user}
                incomingVariant={pendingVariant}
                onVariantConsumed={() => setPendingVariant(null)}
              />
            )}
            {page === "Экономика" && <BlockEconomicsPage passportId={economicsPassportId} />}
            {page === "Экономика юнита" && <EconomicsPage />}
            {page === "Бурение" && <DrillingPage />}
            {page === "ФОТ" && <LaborPage />}
            {page === "Справочники" && <ReferencesPage user={user} />}
          </TopbarSlotProvider>
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
