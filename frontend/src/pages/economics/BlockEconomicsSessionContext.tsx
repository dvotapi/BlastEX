import { createContext, useContext, type ReactNode } from "react";
import { useBlockEconomicsSession, type BlockEconomicsSession } from "./useBlockEconomicsSession";

const BlockEconomicsSessionContext = createContext<BlockEconomicsSession | null>(null);

/**
 * Держит расчёт блока над страницами «Экономика» и «Бурение»: черновики и
 * результаты не теряются при переходе между ними.
 */
export function BlockEconomicsSessionProvider({
  passportId,
  children,
}: {
  passportId?: string | null;
  children: ReactNode;
}) {
  const session = useBlockEconomicsSession(passportId);
  return <BlockEconomicsSessionContext.Provider value={session}>{children}</BlockEconomicsSessionContext.Provider>;
}

/** `null` — над компонентом нет провайдера. */
export function useOptionalBlockEconomicsSession(): BlockEconomicsSession | null {
  return useContext(BlockEconomicsSessionContext);
}

export function useBlockEconomicsSessionContext(): BlockEconomicsSession {
  const session = useContext(BlockEconomicsSessionContext);
  if (!session) throw new Error("BlockEconomicsSessionProvider не найден над компонентом.");
  return session;
}
