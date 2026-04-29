"""
export_quercus_geometry.py
==========================
Exporta la geometria 3D del simulador vmlab/vmango.

TRES PERFILES:
  'archival'   -> Blender. Calidad alta, todas las capas. (~30-80 MB)
  'realtime'   -> Three.js. Hojas decimadas en el GLB. (~3-8 MB)
  'r3f_split'  -> NUEVO. Exporta DOS archivos:
                    quercus_trunk.glb  -> solo tronco + ramas (sin hojas)
                    quercus_leaves.json -> array de transforms de cada hoja
                  Las hojas se instancian en R3F con InstancedMesh.
                  El GLB pesa <1 MB. Las hojas no ocupan GPU geometry extra.

USO:
    from export_quercus_geometry import make_capture_hook, export_scene, scene_info

    hook, scenes = make_capture_hook(capture_every=10)
    ds_out = vmlab.run(setup, vmango, geometry=False, hooks=[hook])

    scene_info(scenes[-1])

    # Mejor opcion para R3F:
    export_scene(scenes[-1], 'quercus_v0', profile='r3f_split')

    # Blender:
    export_scene(scenes[-1], 'quercus_v0_blender', profile='archival')
"""

import json
import numpy as np
import pathlib
import xsimlab as xs
import openalea.plantgl.all as pgl


# ---------------------------------------------------------------------------
# MATERIALES PBR ESTANDAR
# ---------------------------------------------------------------------------

STANDARD_MATERIALS = {
    'bark_old':    ((0.25, 0.18, 0.12), 0.0, 0.90),
    'bark_young':  ((0.45, 0.32, 0.18), 0.0, 0.80),
    'wood':        ((0.35, 0.22, 0.14), 0.0, 0.85),
    'leaf_mature': ((0.15, 0.32, 0.10), 0.0, 0.60),
    'leaf_young':  ((0.40, 0.55, 0.15), 0.0, 0.55),
    'leaf_senesc': ((0.55, 0.38, 0.10), 0.0, 0.65),
    'fruit':       ((0.60, 0.25, 0.10), 0.0, 0.50),
    'inflo':       ((0.80, 0.75, 0.30), 0.0, 0.45),
}

# Leaf material names — these get extracted as transforms, not baked geometry
LEAF_MATS = {'leaf_mature', 'leaf_young', 'leaf_senesc'}

MAT_NAMES = list(STANDARD_MATERIALS.keys())
_MAT_RGB_REF = np.array([v[0] for v in STANDARD_MATERIALS.values()], dtype=np.float32)


# ---------------------------------------------------------------------------
# DECIMATION PROFILES
# ---------------------------------------------------------------------------

PROFILES = {
    'archival': {
        'bark_old':    0.35,
        'bark_young':  0.45,
        'wood':        0.35,
        'leaf_mature': 0.50,
        'leaf_young':  0.50,
        'leaf_senesc': 0.45,
        'fruit':       0.65,
        'inflo':       0.55,
    },
    'realtime': {
        'bark_old':    0.15,
        'bark_young':  0.20,
        'wood':        0.15,
        'leaf_mature': 0.05,
        'leaf_young':  0.05,
        'leaf_senesc': 0.05,
        'fruit':       0.20,
        'inflo':       0.15,
    },
    # r3f_split: trunk/branches only — leaves extracted as JSON transforms
    'r3f_split': {
        'bark_old':    0.20,
        'bark_young':  0.25,
        'wood':        0.20,
        'leaf_mature': None,   # None = skip from GLB, extract transforms instead
        'leaf_young':  None,
        'leaf_senesc': None,
        'fruit':       0.30,
        'inflo':       0.20,
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
                 profile='r3f_split', scale=1/100):
    """
    Exporta una pgl.Scene con optimizacion de geometria y materiales PBR.

    Parameters
    ----------
    scene : pgl.Scene
    output_path : str   Ruta base sin extension.
    fmt : str
        'gltf'  -> GLB con materiales PBR
        'obj'   -> OBJ + MTL
        'ply'   -> PLY con colores por vertice
        'bgeom' -> Binario nativo PlantGL
        'all'   -> Todos
    profile : str
        'archival'  -> Blender, ~30-80 MB
        'realtime'  -> Three.js decimado, ~3-8 MB
        'r3f_split' -> GLB sin hojas + JSON de transforms (RECOMENDADO para R3F)
    scale : float
        1/100 convierte cm a metros.
    """
    if scene is None:
        print("[ERROR] La escena es None.")
        return
    if profile not in PROFILES:
        print(f"[ERROR] profile='{profile}' no valido.")
        return

    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ratios = PROFILES[profile]

    print(f"\n[EXPORT] Perfil: {profile.upper()}")

    if profile == 'r3f_split':
        _export_r3f_split(scene, output_path, scale, ratios)
        return

    targets = ['gltf', 'obj', 'ply', 'bgeom'] if fmt.lower() == 'all' else [fmt.lower()]
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
            print(f"[WARN] Formato '{target}' no reconocido.")


# ---------------------------------------------------------------------------
# BLOQUE 3 - r3f_split: el perfil nuevo
# ---------------------------------------------------------------------------

def _export_r3f_split(scene, base, scale, ratios):
    """
    Exporta DOS archivos:
      <base>_trunk.glb    -> tronco + ramas + frutos (sin hojas)
      <base>_leaves.json  -> array de transforms de cada hoja para InstancedMesh

    Por que este enfoque:
      - El GLB del tronco pesa <1 MB (sin la geometria de miles de hojas)
      - Las hojas se instancian en R3F con UNA sola geometria procesal (quad lobulado)
        y N matrices 4x4. El GPU renderiza todas con un solo draw call.
      - El JSON de transforms solo contiene floats (posicion, quaternion, escala),
        no geometria -> pesa ~50-200 KB para 5000 hojas.
    """
    try:
        import trimesh
    except ImportError:
        print("[WARN] trimesh no instalado:  pip install trimesh")
        return

    print(f"[r3f_split] Teselando escena...")
    shapes = _triangulate_scene_with_transforms(scene, scale)
    if not shapes:
        return

    # Separar hojas del resto
    trunk_shapes = [s for s in shapes if s['mat_name'] not in LEAF_MATS]
    leaf_shapes  = [s for s in shapes if s['mat_name'] in LEAF_MATS]

    print(f"[r3f_split] Trunk shapes: {len(trunk_shapes)}  |  Leaf shapes: {len(leaf_shapes)}")

    # --- 1. Exportar GLB del tronco ---
    trunk_ratios = {k: v for k, v in ratios.items() if v is not None}
    trunk_by_mat = _process_shapes(trunk_shapes, trunk_ratios)

    glb_path = base.parent / (base.name + '_trunk.glb')
    scene_tm = trimesh.Scene()

    for mat_name, (verts, faces) in trunk_by_mat.items():
        if len(faces) == 0:
            continue
        mat_def = STANDARD_MATERIALS[mat_name]
        rgb = mat_def[0]
        material = trimesh.visual.material.PBRMaterial(
            name=mat_name,
            baseColorFactor=np.array([rgb[0], rgb[1], rgb[2], 1.0], dtype=np.float32),
            metallicFactor=float(mat_def[1]),
            roughnessFactor=float(mat_def[2]),
            doubleSided=False,
        )
        # Swap Y/Z: PlantGL Z-up -> GLTF Y-up
        v = verts[:, [0, 2, 1]].copy()
        v[:, 1] *= -1
        visual = trimesh.visual.TextureVisuals(material=material)
        mesh = trimesh.Trimesh(vertices=v, faces=faces, visual=visual, process=False)
        mesh.fix_normals()
        scene_tm.add_geometry(mesh, geom_name=mat_name, node_name=mat_name)

    scene_tm.export(str(glb_path))
    size_trunk = glb_path.stat().st_size / (1024 ** 2)
    print(f"[OK] GLB trunk  -> {glb_path}  ({size_trunk:.2f} MB)")

    # --- 2. Exportar JSON de transforms de hojas ---
    # Cada hoja tiene: position [x,y,z], quaternion [x,y,z,w], scale [sx,sy,sz]
    # El R3F InstancedMesh usara estos para construir las matrices 4x4.
    # Tambien guardamos mat_name para que R3F pueda colorear por fenologia.

    leaf_transforms = []

    for s in leaf_shapes:
        verts = s['vertices']  # shape original sin decimar
        if len(verts) == 0:
            continue

        # Centro de masa = posicion de la hoja
        center = verts.mean(axis=0)  # [x,y,z] en PlantGL space

        # Orientacion: normal media del mesh = direccion "arriba" de la hoja
        faces = s['faces']
        if len(faces) >= 1:
            v0 = verts[faces[:, 0]]
            v1 = verts[faces[:, 1]]
            v2 = verts[faces[:, 2]]
            normals = np.cross(v1 - v0, v2 - v0)
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            norms = np.where(norms < 1e-10, 1.0, norms)
            normals = normals / norms
            mean_normal = normals.mean(axis=0)
            mean_normal /= (np.linalg.norm(mean_normal) + 1e-10)
        else:
            mean_normal = np.array([0, 0, 1], dtype=np.float32)

        # Escala: bounding box extent del eje largo
        bbox = verts.max(axis=0) - verts.min(axis=0)
        leaf_len = float(np.max(bbox))
        leaf_w   = float(np.median(bbox))
        sx = leaf_w
        sy = leaf_len
        sz = leaf_w * 0.15  # hojas casi planas

        # Quaternion desde normal de hoja -> Y-up de GLTF
        # Construimos una base ortonormal y la convertimos a quaternion
        up = mean_normal
        right_hint = np.array([1, 0, 0], dtype=np.float64)
        if abs(np.dot(up, right_hint)) > 0.99:
            right_hint = np.array([0, 1, 0], dtype=np.float64)
        fwd = np.cross(up, right_hint)
        fwd /= (np.linalg.norm(fwd) + 1e-10)
        right = np.cross(fwd, up)

        # Rotation matrix 3x3 -> quaternion
        R = np.stack([right, up, fwd], axis=1)
        quat = _mat3_to_quat(R)

        # Swap Y/Z para GLTF
        pos_gltf = [
            float(center[0]),
            float(center[2]),   # Y-up
            float(-center[1]),
        ]

        leaf_transforms.append({
            'p': [round(x, 4) for x in pos_gltf],           # position
            'q': [round(x, 5) for x in quat.tolist()],       # quaternion xyzw
            's': [round(sx, 4), round(sy, 4), round(sz, 4)], # scale
            'm': s['mat_name'],                               # material key
        })

    json_path = base.parent / (base.name + '_leaves.json')
    with open(json_path, 'w') as f:
        json.dump({
            'count': len(leaf_transforms),
            'scale_factor': scale,
            'materials': {k: STANDARD_MATERIALS[k][0] for k in LEAF_MATS},
            'leaves': leaf_transforms,
        }, f, separators=(',', ':'))  # compact JSON

    size_json = json_path.stat().st_size / (1024 ** 2)
    print(f"[OK] JSON leaves -> {json_path}  ({size_json:.3f} MB)  [{len(leaf_transforms)} hojas]")

    print(f"\n[r3f_split] RESUMEN:")
    print(f"   Copia {glb_path.name} y {json_path.name} a /public/models/")
    print(f"   En R3F usa <QuercusTree trunkPath='..._trunk.glb' leavesPath='..._leaves.json' />")


def _mat3_to_quat(R):
    """Convierte una matriz de rotacion 3x3 a quaternion [x,y,z,w]."""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return np.array([x, y, z, w], dtype=np.float64)


# ---------------------------------------------------------------------------
# BLOQUE 4 - Teselacion y optimizacion
# ---------------------------------------------------------------------------

def _triangulate_scene_with_transforms(scene, scale):
    """
    Como _triangulate_scene pero conserva los vertices ORIGINALES (sin decimar)
    para poder extraer transforms precisos de cada hoja.
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
    return shapes_out


def _triangulate_scene(scene, scale):
    return _triangulate_scene_with_transforms(scene, scale)


def _weld_vertices(vertices, faces):
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
    if ratio is None or ratio >= 1.0 or len(faces) < 20:
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
    by_mat = {name: {'verts': [], 'faces': [], 'offset': 0} for name in MAT_NAMES}
    total_before = sum(len(s['faces']) for s in shapes)
    total_after = 0

    for s in shapes:
        mat = s['mat_name']
        ratio = ratios.get(mat, 0.3)
        if ratio is None:
            continue  # skip leaf geometry in r3f_split trunk GLB

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

    if total_before > 0:
        pct = 100.0 * (1 - total_after / max(1, total_before))
        print(f"     Tris antes : {total_before:>10,}  |  despues: {total_after:>10,}  (-{pct:.1f}%)")

    return result


# ---------------------------------------------------------------------------
# BLOQUE 5 - Exportadores estandar (archival / realtime)
# ---------------------------------------------------------------------------

def _export_gltf(scene, base, scale, ratios):
    glb_path = base.with_suffix('.glb')
    try:
        import trimesh
    except ImportError:
        print("[WARN] trimesh no instalado:  pip install trimesh")
        return

    shapes = _triangulate_scene(scene, scale)
    if not shapes:
        return

    print(f"[GLTF] {len(shapes)} shapes -> decimacion...")
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
            doubleSided=(mat_name in LEAF_MATS),
        )
        v = verts[:, [0, 2, 1]].copy()
        v[:, 1] *= -1
        visual = trimesh.visual.TextureVisuals(material=material)
        mesh = trimesh.Trimesh(vertices=v, faces=faces, visual=visual, process=False)
        mesh.fix_normals()
        scene_tm.add_geometry(mesh, geom_name=mat_name, node_name=mat_name)

    scene_tm.export(str(glb_path))
    size_mb = glb_path.stat().st_size / (1024 ** 2)
    print(f"[OK] GLB -> {glb_path}  ({size_mb:.1f} MB)")
    if size_mb > 15:
        print(f"     Comprimir: gltf-transform draco {glb_path.name} {base.stem}_draco.glb")


def _export_obj(scene, base, scale, ratios):
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
            f.write(f'Ns {int((1-roughness)*100+5)}\n\n')
    total_verts = 0
    with open(obj_path, 'w', encoding='utf-8') as f:
        f.write('# Quercus cretacico - vmlab export\n')
        f.write(f'mtllib {mtl_path.name}\n\n')
        for mat_name, (verts, faces) in by_mat.items():
            f.write(f'g {mat_name}\nusemtl {mat_name}\n')
            for v in verts:
                f.write(f'v {v[0]:.5f} {v[2]:.5f} {v[1]:.5f}\n')
            for tri in faces:
                b = total_verts + 1
                f.write(f'f {tri[0]+b} {tri[1]+b} {tri[2]+b}\n')
            total_verts += len(verts)
    size_mb = obj_path.stat().st_size / (1024**2)
    print(f"[OK] OBJ -> {obj_path}  ({size_mb:.1f} MB)")


def _export_ply(scene, base, scale, ratios):
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
        f.write(f'element vertex {len(verts)}\n')
        f.write('property float x\nproperty float y\nproperty float z\n')
        f.write('property uchar red\nproperty uchar green\nproperty uchar blue\n')
        f.write(f'element face {len(faces)}\n')
        f.write('property list uchar int vertex_indices\nend_header\n')
        for v, c in zip(verts, colors):
            f.write(f'{v[0]:.5f} {v[2]:.5f} {v[1]:.5f} {c[0]} {c[1]} {c[2]}\n')
        for tri in faces:
            f.write(f'3 {tri[0]} {tri[1]} {tri[2]}\n')
    size_mb = ply_path.stat().st_size / (1024**2)
    print(f"[OK] PLY -> {ply_path}  ({size_mb:.1f} MB)")


def _export_bgeom(scene, base):
    bgeom_path = base.with_suffix('.bgeom')
    with open(bgeom_path, 'wb') as f:
        f.write(pgl.tobinarystring(scene, False))
    size_mb = bgeom_path.stat().st_size / (1024**2)
    print(f"[OK] BGEOM -> {bgeom_path}  ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# BLOQUE 6 - Utilidades
# ---------------------------------------------------------------------------

def scene_info(scene):
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
    est_real = sum(mat_counts.get(m, 0) * PROFILES['realtime'].get(m, 0.15) for m in MAT_NAMES)
    est_split_trunk = sum(
        mat_counts.get(m, 0) * (PROFILES['r3f_split'].get(m) or 0)
        for m in MAT_NAMES if m not in LEAF_MATS
    )
    mb_raw   = total_tris * 36 / (1024**2)
    mb_real  = est_real * 36 / (1024**2)
    mb_trunk = est_split_trunk * 36 / (1024**2)
    leaf_count = sum(1 for shape in scene if _classify_color(_get_raw_color(shape)) in LEAF_MATS)
    print(f"\n{'='*55}")
    print(f"  Shapes          : {len(scene):,}")
    print(f"  Triangulos raw  : {total_tris:,}")
    print(f"  Hojas estimadas : ~{leaf_count:,} shapes de tipo hoja")
    print(f"  Tamano estimado :")
    print(f"    Sin optimizar  -> {mb_raw:.0f} MB")
    print(f"    realtime GLB   -> ~{mb_real:.0f} MB")
    print(f"    r3f_split GLB  -> ~{mb_trunk:.2f} MB trunk  +  JSON (~hojas*0.1KB)")
    print(f"{'='*55}")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:35s} x {c:,}")
    print(f"  Por material:")
    for m in MAT_NAMES:
        c = mat_counts.get(m, 0)
        if c > 0:
            pct = 100.0 * c / total_tris
            bar = '█' * int(pct / 3)
            tag = ' <- INSTANCED en r3f_split' if m in LEAF_MATS else ''
            print(f"    {m:15s} {c:>8,} tris  {pct:5.1f}%  {bar}{tag}")
    print(f"{'='*55}\n")


def load_bgeom(path):
    with open(path, 'rb') as f:
        return pgl.frombinarystring(f.read())


def _get_raw_color(shape):
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
    rgb_norm = np.array(rgb_uint8, dtype=np.float32) / 255.0
    dists = np.linalg.norm(_MAT_RGB_REF - rgb_norm, axis=1)
    return MAT_NAMES[int(np.argmin(dists))]