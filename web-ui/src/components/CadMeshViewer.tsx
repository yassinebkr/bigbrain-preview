import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { cadArtifact, type CadView } from '@/lib/cad';
import { inspectStl } from '@/lib/cadMesh';

export default function CadMeshViewer({ cad, sessionId, fallback }: { cad: CadView; sessionId: string; fallback: React.ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const reset = useRef<() => void>(() => {});
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    setError(''); setReady(false);
    const abort = new AbortController();
    let dispose = () => {};
    cadArtifact(cad, sessionId, 'stl', abort.signal).then(async blob => {
      const buffer = await blob.arrayBuffer();
      if (abort.signal.aborted) return;
      inspectStl(buffer);
      const geometry = new STLLoader().parse(buffer);
      let renderer: THREE.WebGLRenderer | undefined;
      try {
        const positions = geometry.getAttribute('position');
        for (const value of positions.array) if (!Number.isFinite(value)) throw new Error('Coordonnées du maillage invalides');
        geometry.computeBoundingSphere();
        const radius = geometry.boundingSphere?.radius || 0;
        if (!(radius > 0) || !Number.isFinite(radius)) throw new Error('Maillage sans étendue exploitable');
        geometry.center(); geometry.computeVertexNormals();
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.domElement.setAttribute('aria-label', 'Vue 3D interactive de la pièce');
        renderer.domElement.setAttribute('role', 'img');
        renderer.domElement.tabIndex = 0;
        renderer.domElement.setAttribute('aria-description', 'Glisser pour tourner, molette pour zoomer. Bouton Recentrer pour rétablir la vue.');
        node.append(renderer.domElement);
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(40, 1, radius / 1000, radius * 100);
        camera.up.set(0, 0, 1);
        const material = new THREE.MeshStandardMaterial({ color: 0x91b6d5, metalness: 0.25, roughness: 0.5 });
        scene.add(new THREE.Mesh(geometry, material));
        scene.add(new THREE.HemisphereLight(0xffffff, 0x243446, 2.5));
        const light = new THREE.DirectionalLight(0xffffff, 3); light.position.set(radius, -radius, radius * 3); scene.add(light);
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.minDistance = radius * 0.15; controls.maxDistance = radius * 20;
        let visible = true;
        const render = () => { if (visible && !document.hidden) renderer?.render(scene, camera); };
        const fit = () => {
          const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * Math.max(1, 1 / camera.aspect) * 1.15;
          camera.position.set(distance, -distance, distance * 0.75); camera.position.setLength(distance);
          controls.target.set(0, 0, 0); controls.update(); render();
        };
        reset.current = fit;
        const resize = new ResizeObserver(() => {
          const width = node.clientWidth, height = node.clientHeight;
          if (!width || !height) return;
          renderer?.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix(); render();
        });
        resize.observe(node);
        const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; render(); });
        intersection.observe(node);
        const lost = (event: Event) => { event.preventDefault(); setError('Vue 3D interrompue : contexte graphique indisponible'); };
        renderer.domElement.addEventListener('webglcontextlost', lost);
        document.addEventListener('visibilitychange', render);
        controls.addEventListener('change', render);
        fit(); setReady(true);
        dispose = () => {
          resize.disconnect(); intersection.disconnect(); controls.dispose(); material.dispose(); geometry.dispose();
          document.removeEventListener('visibilitychange', render);
          renderer?.domElement.removeEventListener('webglcontextlost', lost);
          renderer?.dispose(); renderer?.forceContextLoss(); renderer?.domElement.remove(); reset.current = () => {};
        };
      } catch (failure) { geometry.dispose(); renderer?.dispose(); renderer?.domElement.remove(); throw failure; }
    }).catch(failure => { if (!abort.signal.aborted) setError(String(failure)); });
    return () => { abort.abort(); dispose(); };
  }, [cad.document_id, cad.snapshot?.document.revision, cad.snapshot?.document.native.sha256, sessionId]);
  return <div className="relative w-full h-full min-h-0">
    {(!ready || error) && <div className="absolute inset-0">{fallback}</div>}
    <div ref={host} className="absolute inset-0" style={{ visibility: error ? 'hidden' : 'visible' }} />
    {ready && !error && <button className="absolute top-2 left-2 rounded-full px-3 py-1 text-[11px] bg-black/60 text-white"
      onClick={() => reset.current()}>Recentrer</button>}
    <span className="absolute bottom-2 left-2 right-2 text-[10px] text-center rounded-full px-2 py-1 bg-black/60 text-white pointer-events-none">
      {error ? 'Vue 3D indisponible · aperçu statique conservé' : ready ? 'Glisser pour tourner · molette pour zoomer' : 'Chargement de la vue 3D…'}</span>
  </div>;
}
