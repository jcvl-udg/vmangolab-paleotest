"""
export_quercus_geometry.py
==========================
Exporta la geometria 3D del simulador vmlab/vmango.

DOS PERFILES DE EXPORTACION:
-----------------------------
  'archival'   -> Para Blender. Calidad alta, hojas con forma correcta,
                  todos los materiales editables. (~30-80 MB)

  'realtime'   -> Para visualizadores web (Three.js / React Three Fiber).
                  Hojas agresivamente decimadas (planas), Draco-ready.
                  (~3-8 MB antes de comprimir con Draco)

USO RAPIDO:
    from export_quercus_geometry import make_capture_hook, export_scene, scene_info

    hook, scenes = make_capture_hook(capture_every=10)
    ds_out = vmlab.run(setup, vmango, geometry=False, hooks=[hook])

    scene_info(scenes[-1])

    # Para Blender
    export_scene(scenes[-1], 'quercus_v0_blender', profile='archival')

    # Para visualizador web
    export_scene(scenes[-1], 'quercus_v0_web', profile='realtime')
"""

import numpy as np
import pathlib
import xsimlab as xs
import openalea.plantgl.all as pgl


# ---------------------------------------------------------------------------
# MATERIALES PBR ESTANDAR
# Paleta fija con nombres semanticos editables en Blender.
# Los shapes PlantGL se clasifican automaticamente al material mas cercano
# por distancia euclidiana en espacio RGB.
# ---------------------------------------------------------------------------

STANDARD_MATERIALS = {
    # nombre          RGB difuso (0-1)          metallic  roughness
    'bark_old':      ((0.25, 0.18, 0.12),       0.0,      0.90),
    'bark_young':    ((0.45, 0.32, 0.18),        0.0,      0.80),
    'wood':          ((0.35, 0.22, 0.14),        0.0,      0.85),
    'leaf_mature':   ((0.15, 0.32, 0.10),        0.0,      0.60),
    'leaf_young':    ((0.40, 0.55, 0.15),        0.0,      0.55),
    'leaf_senesc':   ((0.55, 0.38, 0.10),        0.0,      0.65),
    'fruit':         ((0.60, 0.25, 0.10),        0.0,      0.50),
    'inflo':         ((0.80, 0.75, 0.30),        0.0,      0.45),
}

MAT_NAMES = list(STANDARD_MATERIALS.keys())
_MAT_RGB_REF = np.array([v[0] for v in STANDARD_MATERIALS.values()], dtype=np.float32)


# ---------------------------------------------------------------------------
# PERFILES DE DECIMACION
#
# Por que las hojas se tratan diferente segun el perfil:
#
#   En PlantGL, cada hoja es una superficie NURBS o Sweep que el Tesselator
#   convierte en decenas o cientos de triangulos curvos. En un arbol con
#   miles de hojas esto suma millones de triangulos, y las hojas representan
#   tipicamente el 90-95% del total de poligonos.
#
#   'archival': las hojas conservan su curvatura 3D porque en Blender
#   vamos a asignarles un shader SSS (subsurface scattering) que aprovecha
#   la forma real. Ratio 0.5 = conserva la mitad.
#
#   'realtime': las hojas se aplanan casi por completo (ratio 0.05-0.1).
#   En un visualizador web la curvatura de la hoja no se percibe; lo que
#   define su apariencia es la textura/transparencia que se aplica en el
#   shader de Three.js. Un quad plano (2 triangulos con alphaTest) se ve
#   igual que 200 triangulos curvos pero cuesta 100x menos.
# ---------------------------------------------------------------------------

PROFILES = {
    'archival': {
        # Para Blender: conservar forma real de cada organo
        'bark_old':    0.35,   # cilindros: quadric decimation los simplifica bien
        'bark_young':  0.45,
        'wood':        0.35,
        'leaf_mature': 0.50,   # conservar curvatura para SSS en Blender
        'leaf_young':  0.50,
        'leaf_senesc': 0.45,
        'fruit':       0.65,   # frutos: maximo detalle para morfologia
        'inflo':       0.55,
    },
    'realtime': {
        # Para Three.js / R3F: hojas casi planas, ramas simplificadas
        'bark_old':    0.15,   # tronco: pocos lados en el cilindro son suficientes
        'bark_young':  0.20,
        'wood':        0.15,
        'leaf_mature': 0.05,   # ~2-4 triangulos por hoja -> usa alphaTest en shader
        'leaf_young':  0.05,
        'leaf_senesc': 0.05,
        'fruit':       0.20,   # frutos: algo de detalle para reconocerlos
        'inflo':       0.15,
    },
}


# ---------------------------------------------------------------------------
# BLOQUE 1 - Hook de captura
# ---------------------------------------------------------------------------

def make_capture_hook(capture_every=1):
    """
    Crea un RuntimeHook valido para xsimlab que captura escenas PlantGL.

    Returns
    -------
    hook   : RuntimeHook  ->  pasar a vmlab.run(hooks=[hook])
    scenes : list         ->  scenes[-1] es la ultima escena capturada
    """
    scenes = []
    counter = {'step': 0}

    @xs.runtime_hook(stage='run_step')
    def _hook(model, context, state):
        if counter['step'] % capture_every == 0:
            try:
                scene = state[('geometry', 'scene')]
                if scene is not None:
                    scenes.append(scene)
            except KeyError:
                pass
        counter['step'] += 1

    return _hook, scenes


# ---------------------------------------------------------------------------
# BLOQUE 2 - API publica
# ---------------------------------------------------------------------------

def export_scene(scene, output_path='quercus_v0', fmt='gltf',
                 profile='archival', scale=1/100):
    """
    Exporta una pgl.Scene con optimizacion de geometria y materiales PBR.

    Parameters
    ----------
    scene : pgl.Scene
        Escena PlantGL generada por vmlab.
    output_path : str
        Ruta base sin extension.
    fmt : str
        'gltf'  -> GLB con materiales PBR (recomendado)
        'obj'   -> OBJ + MTL con materiales estandar
        'ply'   -> PLY con colores por vertice
        'bgeom' -> Binario nativo PlantGL sin decimacion
        'all'   -> Todos los anteriores
    profile : str
        'archival' -> Para Blender. Hojas con forma 3D, ~30-80 MB.
        'realtime' -> Para Three.js/R3F. Hojas planas, ~3-8 MB.
                      Usar con Draco compression en gltf-pipeline o Blender.
    scale : float
        1/100 convierte cm del simulador a metros (estandar Blender/GLTF).
    """
    if scene is None:
        print("[ERROR] La escena es None.")
        return

    if profile not in PROFILES:
        print(f"[ERROR] profile='{profile}' no valido. Usa 'archival' o 'realtime'.")
        return

    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    targets = ['gltf', 'obj', 'ply', 'bgeom'] if fmt.lower() == 'all' else [fmt.lower()]
    ratios = PROFILES[profile]

    print(f"\n[EXPORT] Perfil: {profile.upper()}  |  Formato(s): {targets}")

    for target in targets:
        if target == 'gltf':
            _export_gltf(scene, output_path, scale, ratios)
        elif target == 'obj':
            _export_obj(scene, output_path, scale, ratios)
        elif target == 'ply':
            _export_ply(scene, output_path, scale, ratios)
        elif target == 'bgeom':
            _export_bgeom(scene, output_path)
        else:
            print(f"[WARN] Formato '{target}' no reconocido. Opciones: gltf, obj, ply, bgeom, all")


# ---------------------------------------------------------------------------
# BLOQUE 3 - Teselacion y optimizacion
# ---------------------------------------------------------------------------

def _triangulate_scene(scene, scale):
    """
    Convierte cada shape PlantGL a triangulos.
    Devuelve lista de dicts: {vertices, faces, mat_name}
    """
    tessellator = pgl.Tesselator()
    shapes_out = []

    for shape in scene:
        try:
            shape.geometry.apply(tessellator)
            mesh = tessellator.triangulation
            if mesh is None or len(mesh.pointList) == 0:
                continue

            pts = np.array(
                [(p.x, p.y, p.z) for p in mesh.pointList], dtype=np.float32
            ) * scale
            tris = np.array(
                [(t[0], t[1], t[2]) for t in mesh.indexList], dtype=np.int32
            )
            mat_name = _classify_color(_get_raw_color(shape))

            shapes_out.append({'vertices': pts, 'faces': tris, 'mat_name': mat_name})
        except Exception:
            continue

    if not shapes_out:
        print("[WARN] La escena no produjo ningun triangulo.")
        print("       Verifica que geometry__interpretation_freq este configurado.")
    return shapes_out


def _weld_vertices(vertices, faces):
    """Fusiona vertices duplicados en las juntas entre shapes."""
    try:
        import trimesh
        m = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        m.merge_vertices(merge_tex=False, merge_norm=False)
        m.remove_degenerate_faces()
        m.remove_duplicate_faces()
        return np.array(m.vertices, dtype=np.float32), np.array(m.faces, dtype=np.int32)
    except Exception:
        return vertices, faces


def _decimate_mesh(vertices, faces, ratio):
    """
    Decimacion con Garland-Heckbert (quadric error metrics).
    Intenta open3d primero (mejor calidad), luego trimesh como fallback.
    """
    if ratio >= 1.0 or len(faces) < 20:
        return vertices, faces

    target = max(2, int(len(faces) * ratio))

    try:
        import open3d as o3d
        m = o3d.geometry.TriangleMesh()
        m.vertices = o3d.utility.Vector3dVector(vertices.astype(np.float64))
        m.triangles = o3d.utility.Vector3iVector(faces)
        m.compute_vertex_normals()
        md = m.simplify_quadric_decimation(target_number_of_triangles=target)
        v = np.array(md.vertices, dtype=np.float32)
        f = np.array(md.triangles, dtype=np.int32)
        if len(f) > 0:
            return v, f
    except Exception:
        pass

    try:
        import trimesh
        m = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        md = m.simplify_quadric_decimation(target)
        if len(md.faces) > 0:
            return np.array(md.vertices, dtype=np.float32), np.array(md.faces, dtype=np.int32)
    except Exception:
        pass

    return vertices, faces


def _process_shapes(shapes, ratios):
    """
    Aplica weld + decimacion a cada shape y agrupa por material.
    Devuelve dict: mat_name -> (vertices, faces)
    """
    by_mat = {name: {'verts': [], 'faces': [], 'offset': 0} for name in MAT_NAMES}

    total_before = sum(len(s['faces']) for s in shapes)
    total_after = 0

    for s in shapes:
        mat = s['mat_name']
        ratio = max(0.02, ratios.get(mat, 0.3))

        v, f = _weld_vertices(s['vertices'], s['faces'])
        v, f = _decimate_mesh(v, f, ratio)

        if len(f) == 0:
            continue

        slot = by_mat[mat]
        slot['faces'].append(f + slot['offset'])
        slot['verts'].append(v)
        slot['offset'] += len(v)
        total_after += len(f)

    result = {}
    for name, slot in by_mat.items():
        if slot['verts']:
            result[name] = (
                np.vstack(slot['verts']).astype(np.float32),
                np.vstack(slot['faces']).astype(np.int32),
            )

    pct = 100.0 * (1 - total_after / max(1, total_before))
    print(f"     Triangulos antes  : {total_before:>10,}")
    print(f"     Triangulos despues: {total_after:>10,}  (-{pct:.1f}%)")
    print(f"     Materiales activos: {list(result.keys())}")

    return result


# ---------------------------------------------------------------------------
# BLOQUE 4 - Exportadores
# ---------------------------------------------------------------------------

def _export_gltf(scene, base, scale, ratios):
    """
    GLB con un mesh por material PBR.
    - perfil archival : ~30-80 MB, hojas con forma 3D
    - perfil realtime : ~3-8 MB,  listo para Draco compression
    """
    glb_path = base.with_suffix('.glb')
    try:
        import trimesh
    except ImportError:
        print("[WARN] trimesh no instalado:  pip install trimesh")
        return

    shapes = _triangulate_scene(scene, scale)
    if not shapes:
        return

    print(f"[GLTF] {len(shapes)} shapes -> teselacion + decimacion...")
    by_mat = _process_shapes(shapes, ratios)

    scene_tm = trimesh.Scene()

    for mat_name, (verts, faces) in by_mat.items():
        if len(faces) == 0:
            continue

        mat_def = STANDARD_MATERIALS[mat_name]
        rgb = mat_def[0]

        material = trimesh.visual.material.PBRMaterial(
            name=mat_name,
            baseColorFactor=np.array([rgb[0], rgb[1], rgb[2], 1.0], dtype=np.float32),
            metallicFactor=float(mat_def[1]),
            roughnessFactor=float(mat_def[2]),
            doubleSided=True,  # necesario para hojas (visible por ambas caras)
        )

        # Swap Y/Z: PlantGL Z-up -> GLTF Y-up
        v = verts[:, [0, 2, 1]].copy()
        v[:, 1] *= -1

        visual = trimesh.visual.TextureVisuals(material=material)
        mesh = trimesh.Trimesh(vertices=v, faces=faces, visual=visual, process=False)
        mesh.fix_normals()
        scene_tm.add_geometry(mesh, geom_name=mat_name, node_name=mat_name)

    scene_tm.export(str(glb_path))
    size_mb = glb_path.stat().st_size / (1024 ** 2)

    print(f"[OK] GLB  -> {glb_path}  ({size_mb:.1f} MB)")
    print(f"\n     BLENDER:")
    print(f"       File > Import > glTF 2.0")
    print(f"       Cada material ({', '.join(by_mat.keys())})")
    print(f"       aparece como objeto separado en el Outliner.")
    if size_mb > 15:
        print(f"\n     Para comprimir con Draco (reduce ~5-10x adicional):")
        print(f"       npm install -g @gltf-transform/cli")
        print(f"       gltf-transform draco {glb_path.name} {base.stem}_draco.glb")


def _export_obj(scene, base, scale, ratios):
    """OBJ + MTL con materiales estandar y grupos por organo."""
    obj_path = base.with_suffix('.obj')
    mtl_path = base.with_suffix('.mtl')

    shapes = _triangulate_scene(scene, scale)
    if not shapes:
        return

    print(f"[OBJ] {len(shapes)} shapes -> decimacion...")
    by_mat = _process_shapes(shapes, ratios)

    with open(mtl_path, 'w', encoding='utf-8') as f:
        f.write('# Quercus cretacico - vmlab export\n\n')
        for mat_name, mat_def in STANDARD_MATERIALS.items():
            rgb = mat_def[0]
            roughness = mat_def[2]
            spec = (1.0 - roughness) * 0.25
            f.write(f'newmtl {mat_name}\n')
            f.write(f'Kd {rgb[0]:.4f} {rgb[1]:.4f} {rgb[2]:.4f}\n')
            f.write(f'Ka {rgb[0]*0.1:.4f} {rgb[1]*0.1:.4f} {rgb[2]*0.1:.4f}\n')
            f.write(f'Ks {spec:.4f} {spec:.4f} {spec:.4f}\n')
            f.write(f'Ns {int((1-roughness)*100 + 5)}\n\n')

    total_verts = 0
    with open(obj_path, 'w', encoding='utf-8') as f:
        f.write('# Quercus cretacico - vmlab export\n')
        f.write(f'mtllib {mtl_path.name}\n\n')
        for mat_name, (verts, faces) in by_mat.items():
            f.write(f'g {mat_name}\nusemtl {mat_name}\n')
            for v in verts:
                f.write(f'v {v[0]:.5f} {v[2]:.5f} {v[1]:.5f}\n')  # Y/Z swap
            for tri in faces:
                b = total_verts + 1
                f.write(f'f {tri[0]+b} {tri[1]+b} {tri[2]+b}\n')
            total_verts += len(verts)

    size_mb = obj_path.stat().st_size / (1024 ** 2)
    print(f"[OK] OBJ  -> {obj_path}  ({size_mb:.1f} MB)")
    print(f"[OK] MTL  -> {mtl_path}")
    print(f"     Blender: File > Import > Wavefront (.obj)")
    print(f"              Forward Axis = Y  |  Up Axis = Z")


def _export_ply(scene, base, scale, ratios):
    """PLY ASCII con colores por vertice."""
    ply_path = base.with_suffix('.ply')
    shapes = _triangulate_scene(scene, scale)
    if not shapes:
        return

    print(f"[PLY] {len(shapes)} shapes -> decimacion...")
    by_mat = _process_shapes(shapes, ratios)

    all_v, all_f, all_c = [], [], []
    offset = 0
    for mat_name, (verts, faces) in by_mat.items():
        rgb = STANDARD_MATERIALS[mat_name][0]
        color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        all_v.append(verts)
        all_f.append(faces + offset)
        all_c.extend([color] * len(verts))
        offset += len(verts)

    verts = np.vstack(all_v)
    faces = np.vstack(all_f)
    colors = np.array(all_c, dtype=np.uint8)

    with open(ply_path, 'w', encoding='utf-8') as f:
        f.write('ply\nformat ascii 1.0\n')
        f.write('comment Quercus cretacico - vmlab export\n')
        f.write(f'element vertex {len(verts)}\n')
        f.write('property float x\nproperty float y\nproperty float z\n')
        f.write('property uchar red\nproperty uchar green\nproperty uchar blue\n')
        f.write(f'element face {len(faces)}\n')
        f.write('property list uchar int vertex_indices\nend_header\n')
        for v, c in zip(verts, colors):
            f.write(f'{v[0]:.5f} {v[2]:.5f} {v[1]:.5f} {c[0]} {c[1]} {c[2]}\n')
        for tri in faces:
            f.write(f'3 {tri[0]} {tri[1]} {tri[2]}\n')

    size_mb = ply_path.stat().st_size / (1024 ** 2)
    print(f"[OK] PLY  -> {ply_path}  ({size_mb:.1f} MB)")


def _export_bgeom(scene, base):
    """Binario nativo PlantGL. Sin decimacion, copia exacta."""
    bgeom_path = base.with_suffix('.bgeom')
    with open(bgeom_path, 'wb') as f:
        f.write(pgl.tobinarystring(scene, False))
    size_mb = bgeom_path.stat().st_size / (1024 ** 2)
    print(f"[OK] BGEOM -> {bgeom_path}  ({size_mb:.1f} MB)")
    print(f"     Recargar: from export_quercus_geometry import load_bgeom")
    print(f"               scene = load_bgeom('{bgeom_path}')")


# ---------------------------------------------------------------------------
# BLOQUE 5 - Utilidades
# ---------------------------------------------------------------------------

def scene_info(scene):
    """
    Imprime estadisticas detalladas de la escena y estimaciones de tamano
    para cada perfil de exportacion.
    """
    if scene is None:
        print("[INFO] La escena es None.")
        return

    tessellator = pgl.Tesselator()
    total_tris = 0
    type_counts = {}
    mat_counts = {}

    for shape in scene:
        t = type(shape.geometry).__name__
        type_counts[t] = type_counts.get(t, 0) + 1
        try:
            shape.geometry.apply(tessellator)
            mesh = tessellator.triangulation
            if mesh:
                n = len(mesh.indexList)
                total_tris += n
                mat = _classify_color(_get_raw_color(shape))
                mat_counts[mat] = mat_counts.get(mat, 0) + n
        except Exception:
            pass

    # Estimacion de reduccion por perfil
    est_arch = sum(
        mat_counts.get(m, 0) * PROFILES['archival'].get(m, 0.4)
        for m in MAT_NAMES
    )
    est_real = sum(
        mat_counts.get(m, 0) * PROFILES['realtime'].get(m, 0.15)
        for m in MAT_NAMES
    )
    mb_raw   = total_tris * 36 / (1024**2)   # 3 verts x 12 bytes float32
    mb_arch  = est_arch   * 36 / (1024**2)
    mb_real  = est_real   * 36 / (1024**2)

    print(f"\n{'='*55}")
    print(f"  Shapes          : {len(scene):,}")
    print(f"  Triangulos raw  : {total_tris:,}")
    print(f"  Tamano estimado :")
    print(f"    Sin optimizar  -> {mb_raw:.0f} MB")
    print(f"    archival       -> ~{mb_arch:.0f} MB  (para Blender)")
    print(f"    realtime       -> ~{mb_real:.0f} MB  (para Three.js, antes de Draco)")
    print(f"{'='*55}")
    print(f"  Tipos de geometria:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:35s} x {c:,}")
    print(f"  Distribucion por material:")
    for m in MAT_NAMES:
        c = mat_counts.get(m, 0)
        if c > 0:
            pct = 100.0 * c / total_tris
            bar = '█' * int(pct / 3)
            print(f"    {m:15s} {c:>8,} tris  {pct:5.1f}%  {bar}")
    print(f"{'='*55}\n")


def load_bgeom(path):
    """Carga una escena PlantGL desde un archivo .bgeom."""
    with open(path, 'rb') as f:
        return pgl.frombinarystring(f.read())


def _get_raw_color(shape):
    """Extrae color RGB (0-255) del material PlantGL de un shape."""
    try:
        mat = shape.appearance
        if isinstance(mat, pgl.Material):
            c = mat.ambient
            return (int(c.red), int(c.green), int(c.blue))
        if isinstance(mat, pgl.Color4):
            return (int(mat.red), int(mat.green), int(mat.blue))
    except Exception:
        pass
    return (160, 120, 80)


def _classify_color(rgb_uint8):
    """Asigna el material estandar mas cercano a un color RGB (0-255)."""
    rgb_norm = np.array(rgb_uint8, dtype=np.float32) / 255.0
    dists = np.linalg.norm(_MAT_RGB_REF - rgb_norm, axis=1)
    return MAT_NAMES[int(np.argmin(dists))]