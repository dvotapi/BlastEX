import { createContext, useContext, type ReactNode } from "react";
import { useBlockEconomicsSession, type BlockEconomicsSession } from "./useBlockEconomicsSession";

const BlockEconomicsSessionContext = createContext<BlockEconomicsSession | null>(null);

/**
 * Держит расчёт блока над страницами «Экономика» и «Бурение»: черновики и
 * результаты не теряются при переходе между ними.
 */
export function BlockEconomicsSessionProvider({
  passportId,
  requestKey,
  children,
}: {
  passportId?: string | null;
  /** См. `useBlockEconomicsSession`. */
  requestKey?: number;
  children: ReactNode;
}) {
  const session = useBlockEconomicsSession(passportId, requestKey);
  return <BlockEconomicsSessionContext.Provider value={session}>{children}</BlockEconomicsSessionContext.Provider>;
}

/** Сессия блока, если над компонентом есть провайдер; иначе null (тесты, встраиваемые панели). */
export function useOptionalBlockEconomicsSession(): BlockEconomicsSession | null {
  return useContext(BlockEconomicsSessionContext);
}

export function useBlockEconomicsSessionContext(): BlockEconomicsSession {
  const session = useContext(BlockEconomicsSessionContext);
  if (!session) throw new Error("BlockEconomicsSessionProvider не найден над компонентом.");
  return session;
}
