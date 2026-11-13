// Каталог номиналов для тестов — как отдаёт `GET /design/tie/catalog`
// (`tests/test_tie_catalog.py` держит те же числа на сервере).
import type { TieCatalog } from "../../../types/design";

export const TEST_TIE_CATALOG: TieCatalog = {
  systems: {
    nonel: {
      surface_ms: [17, 25, 42, 67, 109],
      downhole_ms: [450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000],
      downhole_default_ms: 500,
      custom_surface: false,
    },
    detcord: { surface_ms: [10, 20, 25, 35, 42], downhole_ms: [], downhole_default_ms: 0, custom_surface: false },
    electronic: { surface_ms: [17, 25, 42, 67, 109], downhole_ms: [], downhole_default_ms: 0, custom_surface: true },
  },
  detcord_velocity_m_s: 7000,
};
