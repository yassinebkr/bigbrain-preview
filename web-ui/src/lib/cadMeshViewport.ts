/** Own the GPU resources and camera for one document's interactive mesh view. */
import * as THREE from 'three';
import { TrackballControls } from 'three/addons/controls/TrackballControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { inspectStl } from './cadMesh';

export class CadMeshViewport {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(40, 1, .001, 100);
  private readonly material = new THREE.MeshStandardMaterial({ color: 0x91b6d5, metalness: .25, roughness: .5 });
  private readonly piece = new THREE.Mesh(new THREE.BufferGeometry(), this.material);
  private readonly light = new THREE.DirectionalLight(0xffffff, 3);
  private renderer?: THREE.WebGLRenderer;
  private controls?: TrackballControls;
  private resize?: ResizeObserver;
  private intersection?: IntersectionObserver;
  private anchor?: THREE.Vector3;
  private radius = 1;
  private frame = 0;
  private disposed = false;
  private contextLost = false;

  private readonly host: HTMLElement;
  private readonly status: (error: string) => void;

  constructor(host: HTMLElement, status: (error: string) => void) {
    this.host = host;
    this.status = status;
    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      const canvas = this.renderer.domElement;
      canvas.setAttribute('aria-label', 'Vue 3D interactive de la pièce');
      canvas.setAttribute('role', 'img');
      canvas.setAttribute('aria-description', 'Glisser pour tourner, clic droit pour déplacer, molette pour zoomer.');
      canvas.tabIndex = 0;
      host.append(canvas);
      this.scene.add(this.piece, new THREE.HemisphereLight(0xffffff, 0x243446, 2.5), this.light);
      this.camera.up.set(0, 0, 1);
      this.controls = new TrackballControls(this.camera, canvas);
      this.controls.staticMoving = true;
      this.controls.addEventListener('change', this.render);
      canvas.addEventListener('pointermove', this.requestUpdate);
      canvas.addEventListener('wheel', this.requestUpdate);
      canvas.addEventListener('webglcontextlost', this.loseContext);
      canvas.addEventListener('webglcontextrestored', this.restoreContext);
      document.addEventListener('visibilitychange', this.render);
      this.resize = new ResizeObserver(this.resizeViewport);
      this.resize.observe(host);
      this.intersection = new IntersectionObserver(entries => {
        if (entries[0]?.isIntersecting) this.render();
      });
      this.intersection.observe(host);
      this.resizeViewport();
    } catch (error) {
      this.dispose();
      throw error;
    }
  }

  /** Validate the whole replacement before releasing the displayed geometry. */
  update(buffer: ArrayBuffer) {
    if (this.disposed) throw new Error('Vue 3D fermée');
    if (this.contextLost) throw new Error('Contexte graphique indisponible');
    inspectStl(buffer);
    const geometry = new STLLoader().parse(buffer);
    try {
      const positions = geometry.getAttribute('position');
      for (const value of positions.array) {
        if (!Number.isFinite(value)) throw new Error('Coordonnées du maillage invalides');
      }
      geometry.computeBoundingSphere();
      const radius = geometry.boundingSphere?.radius || 0;
      if (!(radius > 0) || !Number.isFinite(radius)) throw new Error('Maillage sans étendue exploitable');
      const first = !this.anchor;
      const anchor = this.anchor || geometry.boundingSphere!.center.clone();
      // One document keeps its original world origin as features are added.
      // Updating geometry therefore preserves the user's camera and pan target.
      geometry.translate(-anchor.x, -anchor.y, -anchor.z);
      geometry.computeVertexNormals();
      const previous = this.piece.geometry;
      this.piece.geometry = geometry;
      previous.dispose();
      this.anchor = anchor;
      this.radius = radius;
      this.camera.near = radius / 1000;
      this.camera.far = radius * 100;
      this.camera.updateProjectionMatrix();
      this.controls!.minDistance = radius * .15;
      this.controls!.maxDistance = radius * 20;
      this.light.position.set(radius, -radius, radius * 3);
      if (first) this.fit();
      this.render();
    } catch (error) {
      if (this.piece.geometry !== geometry) geometry.dispose();
      throw error;
    }
  }

  /** Reflect checkpoints that remove the last solid while retaining camera ownership. */
  clear() {
    if (this.disposed) return;
    const previous = this.piece.geometry;
    this.piece.geometry = new THREE.BufferGeometry();
    previous.dispose();
    this.render();
  }

  fit = () => {
    if (!this.controls || !this.piece.geometry.boundingSphere || this.disposed) return;
    const center = this.piece.geometry.boundingSphere!.center;
    const distance = this.radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2))
      * Math.max(1, 1 / this.camera.aspect) * 1.15;
    this.camera.position.set(distance, -distance, distance * .75).setLength(distance).add(center);
    this.camera.up.set(0, 0, 1);
    this.controls.target.copy(center);
    this.controls.update();
    this.render();
  };

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.resize?.disconnect();
    this.intersection?.disconnect();
    document.removeEventListener('visibilitychange', this.render);
    const canvas = this.renderer?.domElement;
    canvas?.removeEventListener('pointermove', this.requestUpdate);
    canvas?.removeEventListener('wheel', this.requestUpdate);
    canvas?.removeEventListener('webglcontextlost', this.loseContext);
    canvas?.removeEventListener('webglcontextrestored', this.restoreContext);
    this.controls?.dispose();
    this.piece.geometry.dispose();
    this.material.dispose();
    this.renderer?.dispose();
    this.renderer?.forceContextLoss();
    canvas?.remove();
  }

  private render = () => {
    if (!this.disposed && !this.contextLost && !document.hidden) this.renderer?.render(this.scene, this.camera);
  };

  private requestUpdate = () => {
    if (this.frame || this.disposed || this.contextLost) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.controls?.update();
    });
  };

  private resizeViewport = () => {
    const { clientWidth: width, clientHeight: height } = this.host;
    if (!width || !height || this.disposed) return;
    this.renderer?.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.controls?.handleResize();
    this.render();
  };

  private loseContext = (event: Event) => {
    event.preventDefault();
    this.contextLost = true;
    this.status('Vue 3D interrompue : contexte graphique indisponible');
  };

  private restoreContext = () => {
    this.contextLost = false;
    this.render();
    this.status('');
  };
}
