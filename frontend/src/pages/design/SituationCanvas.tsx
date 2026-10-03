// Подложка ситуации карьера под SVG плана (TASK-013, PR 4). Тысячи линий
// карьера в SVG сделали бы панорамирование вязким: здесь один `<canvas>`,
// штрихи уже в экранных координатах (`situationStrokes`), мышь проходит
// насквозь к плану.
import { useEffect, useRef } from "react";
import type { SituationStroke } from "./situationLayer";

const POINT_PX = 2;

export function SituationCanvas({ strokes, width, height }: { strokes: SituationStroke[]; width: number; height: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const ratio = typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;

  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.lineWidth = 1;
    for (const stroke of strokes) {
      if (stroke.polylines.length) {
        context.strokeStyle = stroke.color;
        context.beginPath();
        for (const line of stroke.polylines) {
          context.moveTo(line[0], line[1]);
          for (let index = 2; index < line.length; index += 2) context.lineTo(line[index], line[index + 1]);
        }
        context.stroke();
      }
      context.fillStyle = stroke.color;
      for (let index = 0; index < stroke.points.length; index += 2) {
        context.fillRect(stroke.points[index] - POINT_PX / 2, stroke.points[index + 1] - POINT_PX / 2, POINT_PX, POINT_PX);
      }
    }
  }, [strokes, width, height, ratio]);

  return <canvas ref={ref} className="plan-situation" aria-hidden="true" style={{ width, height }} />;
}
