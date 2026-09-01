// Императивная three.js-сцена: просмотр блока и скважин в 3D. Источник
// истины по-прежнему 2D-план — здесь только визуализация и клик-выделение,
// без редактирования геометрии.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { BlockContour, Hole, SurfaceModel, SurfaceSet } from "../../types/design";
import type { HoleHealth } from "./holeHealth";
import { healthColor } from "./holeHealth";
import type { CameraMode3d } from "./viewPresets";

const KIND_COLOR: Record<string, number> = {
  production: 0x2d7556,
  contour: 0xe5b94c,
  presplit: 0x7a6ee0,
  trim: 0x7a6ee0,
};
const SELECTED_COLOR = 0xd8455a;
const DISABLED_COLOR = 0xc3cdc7;

type Vec3 = { x: number; y: number; z: number };

type SceneState = {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  holeGroup: THREE.Group;
  contourGroup: THREE.Group;
  surfaceGroup: THREE.Group;
  observer: ResizeObserver;
  rafId: number;
  framed: boolean;
};

export function Scene3D({
  contour,
  holes,
  surfaces,
  selected,
  onSelectHole,
  cameraMode = "collar",
  holeColors,
}: {
  contour: BlockContour;
  holes: Hole[];
  surfaces?: SurfaceSet;
  selected: Set<string>;
  onSelectHole: (id: string, additive: boolean) => void;
  cameraMode?: CameraMode3d;
  holeColors?: Record<string, HoleHealth>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<SceneState | null>(null);
  const [reframeTick, setReframeTick] = useState(0);
  const onSelectHoleRef = useRef(onSelectHole);
  useEffect(() => {
    onSelectHoleRef.current = onSelectHole;
  }, [onSelectHole]);

  // Инициализация рендерера — один раз за время жизни компонента.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f6f4);

    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 20000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x445544, 1.3));
    const sun = new THREE.DirectionalLight(0xffffff, 0.7);
    sun.position.set(120, 200, 100);
    scene.add(sun);

    const holeGroup = new THREE.Group();
    const contourGroup = new THREE.Group();
    const surfaceGroup = new THREE.Group();
    scene.add(surfaceGroup);
    scene.add(contourGroup);
    scene.add(holeGroup);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    function resize() {
      const w = container!.clientWidth || 1;
      const h = container!.clientHeight || 1;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    function onPointerDown(e: PointerEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(holeGroup.children, false);
      if (hits.length > 0) {
        const id = hits[0].object.userData.holeId as string | undefined;
        if (id) onSelectHoleRef.current(id, e.shiftKey);
      }
    }
    renderer.domElement.addEventListener("pointerdown", onPointerDown);

    let rafId = 0;
    function animate() {
      controls.update();
      renderer.render(scene, camera);
      rafId = requestAnimationFrame(animate);
    }
    animate();

    stateRef.current = { scene, camera, renderer, controls, holeGroup, contourGroup, surfaceGroup, observer, rafId, framed: false };

    return () => {
      cancelAnimationFrame(rafId);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      stateRef.current = null;
    };
  }, []);

  // Перестройка геометрии контура/скважин при изменении данных.
  useEffect(() => {
    const state = stateRef.current;
    if (!state) return;
    const { scene, camera, controls, holeGroup, contourGroup, surfaceGroup } = state;

    const points: Vec3[] = [...contour.vertices];
    for (const h of holes) {
      points.push(h.collar, h.toe);
    }
    for (const surface of [surfaces?.top, surfaces?.floor, surfaces?.face, surfaces?.post_blast]) {
      if (surface?.tin.vertices.length) points.push(...surface.tin.vertices);
    }
    if (points.length === 0) {
      clearGroup(holeGroup);
      clearGroup(contourGroup);
      clearGroup(surfaceGroup);
      return;
    }

    const centerX = points.reduce((s, p) => s + p.x, 0) / points.length;
    const centerY = points.reduce((s, p) => s + p.y, 0) / points.length;
    const centerZ = points.reduce((s, p) => s + p.z, 0) / points.length;
    const toThree = (p: Vec3) => new THREE.Vector3(p.x - centerX, p.z - centerZ, -(p.y - centerY));

    clearGroup(surfaceGroup);
    addSurfaceMesh(surfaceGroup, surfaces?.top, toThree, 0x6f9e7a, 0.38);
    addSurfaceMesh(surfaceGroup, surfaces?.floor, toThree, 0x8a8175, 0.32);
    addSurfaceMesh(surfaceGroup, surfaces?.face, toThree, 0xc4a574, 0.4);
    addSurfaceMesh(surfaceGroup, surfaces?.post_blast, toThree, 0x8b5a3c, 0.28);

    clearGroup(contourGroup);
    if (contour.vertices.length >= 2) {
      const freeSet = new Set(contour.free_faces.map((f) => f.join("-")));
      const n = contour.vertices.length;
      for (let i = 0; i < n; i += 1) {
        const a = contour.vertices[i];
        const b = contour.vertices[(i + 1) % n];
        const isFree = freeSet.has([i, (i + 1) % n].join("-"));
        const color = isFree ? 0xe5b94c : 0x8fa399;
        const width = isFree ? 3 : 1.5;
        addLine(contourGroup, [{ ...a, z: contour.bench.crest_z_m }, { ...b, z: contour.bench.crest_z_m }], toThree, color, width);
        addLine(contourGroup, [{ ...a, z: contour.bench.toe_z_m }, { ...b, z: contour.bench.toe_z_m }], toThree, 0xc7d1cc, 1);
        addLine(contourGroup, [{ ...a, z: contour.bench.crest_z_m }, { ...a, z: contour.bench.toe_z_m }], toThree, 0xc7d1cc, 1);
      }
    }

    clearGroup(holeGroup);
    for (const h of holes) {
      const isSelected = selected.has(h.id);
      const health = holeColors?.[h.id];
      let color = !h.enabled ? DISABLED_COLOR : isSelected ? SELECTED_COLOR : KIND_COLOR[h.kind] ?? 0x2d7556;
      if (health && health.severity > 0 && !isSelected) {
        color = parseInt(healthColor(health.code, health.severity).replace("#", ""), 16);
      }
      addLine(holeGroup, [h.collar, h.toe], toThree, color, isSelected ? 3 : 1.5);

      const collarPos = toThree(h.collar);
      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(isSelected ? 0.6 : 0.4, 12, 12),
        new THREE.MeshStandardMaterial({ color, emissive: isSelected ? 0x552222 : 0x000000 }),
      );
      sphere.position.copy(collarPos);
      sphere.userData.holeId = h.id;
      holeGroup.add(sphere);
    }

    if (!state.framed && points.length > 0) {
      const box = new THREE.Box3();
      for (const p of points) box.expandByPoint(toThree(p));
      const size = box.getSize(new THREE.Vector3());
      const radius = Math.max(10, size.length() * 0.7);
      if (cameraMode === "collar") {
        camera.position.set(radius * 0.8, radius * 0.7, radius * 0.8);
        controls.target.set(0, -size.y / 4, 0);
      } else if (cameraMode === "shaft") {
        camera.position.set(radius * 1.1, radius * 0.15, 0);
        controls.target.set(0, -size.y / 3, 0);
      } else {
        camera.position.set(radius * 0.5, -radius * 0.35, radius * 0.9);
        controls.target.set(0, -size.y / 2, 0);
      }
      controls.update();
      state.framed = true;
    }

  }, [contour, holes, surfaces, selected, reframeTick, cameraMode, holeColors]);

  return (
    <div className="scene3d-wrap">
      <div ref={containerRef} className="scene3d-canvas" />
      <button
        type="button"
        className="scene3d-reset"
        onClick={() => {
          if (stateRef.current) stateRef.current.framed = false;
          setReframeTick((tick) => tick + 1);
        }}
      >
        ⟲ Сбросить обзор
      </button>
      <div className="scene3d-hint">
        Вращение — перетаскивание · зум — колесо · клик по скважине — выделение · режим камеры: {cameraMode === "collar" ? "устье" : cameraMode === "shaft" ? "ствол" : "забой"}
      </div>
    </div>
  );
}

function clearGroup(group: THREE.Group) {
  for (const child of [...group.children]) {
    group.remove(child);
    if (child instanceof THREE.Mesh || child instanceof THREE.Line) {
      child.geometry.dispose();
      const material = child.material;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material.dispose();
    }
  }
}

function addSurfaceMesh(
  group: THREE.Group,
  surface: SurfaceModel | null | undefined,
  toThree: (p: Vec3) => THREE.Vector3,
  color: number,
  opacity: number,
) {
  if (!surface?.tin.triangles.length) return;
  const positions: number[] = [];
  for (const tri of surface.tin.triangles) {
    if (tri.length < 3) continue;
    for (const index of tri.slice(0, 3)) {
      const vertex = surface.tin.vertices[index];
      if (!vertex) continue;
      const p = toThree(vertex);
      positions.push(p.x, p.y, p.z);
    }
  }
  if (positions.length < 9) return;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  group.add(new THREE.Mesh(geometry, new THREE.MeshLambertMaterial({
    color,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
  })));
}

function addLine(group: THREE.Group, points: Vec3[], toThree: (p: Vec3) => THREE.Vector3, color: number, width: number) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points.map(toThree));
  const material = new THREE.LineBasicMaterial({ color, linewidth: width });
  group.add(new THREE.Line(geometry, material));
}
