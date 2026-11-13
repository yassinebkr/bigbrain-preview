/** Exercise mesh replacement and GPU resource ownership without a graphics driver. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mesh, PerspectiveCamera, Scene, Vector3 } from 'three';

interface RendererRecord {
  domElement: EventTarget & { remove: ReturnType<typeof vi.fn> };
  scene?: Scene;
  camera?: PerspectiveCamera;
  dispose: ReturnType<typeof vi.fn>;
  forceContextLoss: ReturnType<typeof vi.fn>;
  render: ReturnType<typeof vi.fn>;
}
interface ControlsRecord {
  target: Vector3;
  dispose: ReturnType<typeof vi.fn>;
}
const state = vi.hoisted(() => ({ renderers: [] as RendererRecord[], controls: [] as ControlsRecord[], failControls: false }));

vi.mock('three', async () => {
  const actual = await vi.importActual<typeof import('three')>('three');
  class Renderer {
    domElement = Object.assign(new EventTarget(), { setAttribute: vi.fn(), remove: vi.fn(), tabIndex: 0 });
    scene?: Scene;
    camera?: PerspectiveCamera;
    dispose = vi.fn();
    forceContextLoss = vi.fn();
    setPixelRatio = vi.fn();
    setSize = vi.fn();
    render = vi.fn((scene: Scene, camera: PerspectiveCamera) => { this.scene = scene; this.camera = camera; });
    constructor() { state.renderers.push(this); }
  }
  return { ...actual, WebGLRenderer: Renderer };
});
vi.mock('three/addons/controls/TrackballControls.js', async () => {
  const { Vector3 } = await vi.importActual<typeof import('three')>('three');
  class Controls {
    target = new Vector3();
    dispose = vi.fn();
    addEventListener = vi.fn();
    update = vi.fn();
    handleResize = vi.fn();
    constructor() {
      if (state.failControls) throw new Error('Controls initialization failed');
      state.controls.push(this);
    }
  }
  return { TrackballControls: Controls };
});
import { CadMeshViewport } from './cadMeshViewport';

function triangle(size = 10, offset = 0) {
  return new TextEncoder().encode(`solid fixture
facet normal 0 0 1
outer loop
vertex ${offset} 0 0
vertex ${offset + size} 0 0
vertex ${offset} ${size} 0
endloop
endfacet
endsolid fixture`).buffer;
}
function host() {
  return { append: vi.fn(), clientWidth: 800, clientHeight: 400 } as unknown as HTMLElement;
}
function piece(renderer: RendererRecord) {
  return renderer.scene!.children.find(item => item.type === 'Mesh') as Mesh;
}
beforeEach(() => {
  state.renderers.length = 0;
  state.controls.length = 0;
  state.failControls = false;
  vi.stubGlobal('window', { devicePixelRatio: 1 });
  vi.stubGlobal('document', Object.assign(new EventTarget(), { hidden: false }));
  vi.stubGlobal('ResizeObserver', class { observe = vi.fn(); disconnect = vi.fn(); });
  vi.stubGlobal('IntersectionObserver', class { observe = vi.fn(); disconnect = vi.fn(); });
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 7));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

describe('retained CAD mesh viewport', () => {
  it('reuses its renderer and keeps the camera, target and document origin across checkpoints', () => {
    const viewport = new CadMeshViewport(host(), vi.fn());
    viewport.update(triangle());
    const renderer = state.renderers[0];
    const camera = renderer.camera!;
    camera.position.set(20, 30, 40);
    state.controls[0].target.set(1, 2, 3);
    const oldGeometry = piece(renderer).geometry;
    const disposed = vi.fn();
    oldGeometry.addEventListener('dispose', disposed);
    viewport.update(triangle(20));
    expect(state.renderers).toHaveLength(1);
    expect(renderer.camera).toBe(camera);
    expect(camera.position.toArray()).toEqual([20, 30, 40]);
    expect(state.controls[0].target.toArray()).toEqual([1, 2, 3]);
    expect(piece(renderer).geometry.getAttribute('position').getX(0)).toBe(-5);
    expect(disposed).toHaveBeenCalledTimes(1);
    expect(renderer.dispose).not.toHaveBeenCalled();
    viewport.fit();
    expect(state.controls[0].target.toArray()).toEqual([5, 5, 0]);
    viewport.dispose();
  });

  it('retains the last valid geometry after malformed or non-finite replacements', () => {
    const viewport = new CadMeshViewport(host(), vi.fn());
    viewport.update(triangle());
    const renderer = state.renderers[0];
    const geometry = piece(renderer).geometry;
    expect(() => viewport.update(new ArrayBuffer(0))).toThrow('vide');
    const binary = new ArrayBuffer(134);
    const values = new DataView(binary);
    values.setUint32(80, 1, true);
    values.setFloat32(96, Infinity, true);
    expect(() => viewport.update(binary)).toThrow('invalides');
    expect(piece(renderer).geometry).toBe(geometry);
    expect(renderer.dispose).not.toHaveBeenCalled();
    viewport.dispose();
  });

  it('keeps graphics loss visible until restoration and releases resources exactly once', () => {
    const status = vi.fn();
    const viewport = new CadMeshViewport(host(), status);
    viewport.update(triangle());
    const renderer = state.renderers[0];
    renderer.domElement.dispatchEvent(new Event('webglcontextlost', { cancelable: true }));
    expect(status).toHaveBeenLastCalledWith(expect.stringContaining('contexte graphique'));
    expect(() => viewport.update(triangle(20))).toThrow('Contexte graphique');
    renderer.domElement.dispatchEvent(new Event('webglcontextrestored'));
    viewport.update(triangle(20));
    expect(status).toHaveBeenLastCalledWith('');
    const disposed = vi.fn();
    piece(renderer).geometry.addEventListener('dispose', disposed);
    viewport.dispose();
    viewport.dispose();
    expect(disposed).toHaveBeenCalledTimes(1);
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    expect(renderer.forceContextLoss).toHaveBeenCalledTimes(1);
    expect(renderer.domElement.remove).toHaveBeenCalledTimes(1);
    expect(state.controls[0].dispose).toHaveBeenCalledTimes(1);
    expect(() => viewport.update(triangle())).toThrow('fermée');
  });

  it('clears a removed solid without replacing the renderer or moving the camera', () => {
    const viewport = new CadMeshViewport(host(), vi.fn());
    viewport.update(triangle());
    const renderer = state.renderers[0];
    const position = renderer.camera!.position.clone();
    const oldGeometry = piece(renderer).geometry;
    const disposed = vi.fn();
    oldGeometry.addEventListener('dispose', disposed);
    viewport.clear();
    viewport.fit();
    expect(piece(renderer).geometry.getAttribute('position')).toBeUndefined();
    expect(disposed).toHaveBeenCalledTimes(1);
    viewport.update(triangle(20));
    expect(renderer.camera!.position.toArray()).toEqual(position.toArray());
    expect(state.renderers).toHaveLength(1);
    viewport.dispose();
  });

  it('cleans up a renderer when control initialization fails', () => {
    state.failControls = true;
    expect(() => new CadMeshViewport(host(), vi.fn())).toThrow('initialization failed');
    expect(state.renderers[0].dispose).toHaveBeenCalledTimes(1);
    expect(state.renderers[0].domElement.remove).toHaveBeenCalledTimes(1);
  });
});
