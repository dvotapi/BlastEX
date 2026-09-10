/**
 * Ограничитель ошибок вкладки «Экономика блока».
 *
 * Смета — единственное место приложения, где на экране одновременно живут
 * данные трёх поколений: параметры прогона, сохранённого прошлой версией
 * схемы, каталог текущей ревизии справочников и свежий ответ модели. Любое
 * несовпадение между ними раньше уносило всё дерево React: пользователь
 * получал белый экран без единой подсказки и мог вернуться только
 * перезагрузкой страницы.
 *
 * Ограничитель не чинит причину — он оставляет на экране объяснение и путь
 * назад. Каждая конкретная причина чинится отдельно (см. `draftFromRun`).
 *
 * Классовый компонент: перехват ошибок рендера в React 19 по-прежнему
 * существует только в виде `getDerivedStateFromError`/`componentDidCatch`,
 * хука с такой возможностью нет.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  /**
   * Вернуть страницу в рабочее состояние. Простой сброс признака ошибки не
   * помогает: React перерисовал бы то же поддерево с теми же данными и упал
   * снова, поэтому причину убирает страница — она пересобирает черновик из
   * умолчаний.
   */
  onReset: () => void;
};

type State = { error: Error | null };

export class EconomicsErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Консоль — единственный канал диагностики на проде: сборщика ошибок в
    // проекте нет, а текст без стека мало что скажет о месте падения.
    console.error("Экономика блока: ошибка отображения", error, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
    this.props.onReset();
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="economics-crash" role="alert">
        <b>Не удалось показать смету</b>
        <p>
          Сценарий открылся, но страница не смогла его отобразить. Расчёт и сохранённые сценарии не
          пострадали: кнопка ниже соберёт черновик заново с параметров по умолчанию, а сохранённый
          прогон останется в «Истории» как есть.
        </p>
        <code>{error.message}</code>
        <button type="button" className="primary-button" onClick={this.reset}>
          Собрать черновик заново
        </button>
      </div>
    );
  }
}
