"""
BVBS a RBL Converter v3.0
Convierte archivos .bvbs a base de datos .RBL (Firebird 2.5).

Correcciones v3.0:
  - ID_MODELO correcto segun numero de doblados
  - Geometria PUNTOS con formato exacto del template (longitud en punto 1 = 0)
  - Calculo correcto de LONGITUD_CENTRAL, ALTURA, ANCHURA, DIAGONAL
  - DOBLADOS contado correctamente desde los angulos no-cero

Requires:
  - fdb (pip install fdb)
  - Firebird 2.5 Embedded DLL en subcarpeta 'firebird25/'
  - Archivo plantilla 'Prueba Petricio.RBL' en el mismo directorio

Uso:
  python bvbs_to_rbl.py <archivo.bvbs> [salida.RBL]
"""

import os
import sys
import re
import shutil
import math
import hashlib
from datetime import datetime


# =============================================================================
# BVBS PARSER
# =============================================================================

def parse_bvbs_file(filepath):
    """
    Parse BVBS file. Returns list of bar dicts.
    
    Format de segmentos BVBS:
      @G@l<long1>@w<ang1>@l<long2>@w<ang2>...@l<longN>@w0@C<chk>
      El primer @w es el angulo antes del primer tramo (gancho inicial)
      El ultimo @w0 indica fin, sin siguiente doblado
    
    Mapeo a PUNTOS RBL:
      - Punto 1: LONGITUD=0, ANG_DOBLADO=angulo_del_gancho_inicial (o 0)
      - Punto 2..N: LONGITUD=tramo, ANG_DOBLADO=angulo_siguiente_doblez
      - El ultimo tramo tiene ANG_DOBLADO=0 (fin de barra)
    """
    bars = []
    
    with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith('BF2D'):
                continue
            
            bar = {}
            pre_g = line.split('@G')[0]
            
            # Proyecto (@H o @j)
            m = re.search(r'@H([^@]+)', line)
            if m: bar['project'] = m.group(1).strip()
            m = re.search(r'@j([^@]+)', line)
            if m: bar['project'] = m.group(1).strip()
            
            # Referencia (@r)
            m = re.search(r'@r([^@]+)', pre_g)
            if m: bar['reference'] = m.group(1).strip()
            
            # Posicion (@p)
            m = re.search(r'@p([^@]+)', pre_g)
            if m: bar['position'] = m.group(1).strip()
            
            # Longitud total (@l - primer @l antes de @G)
            m = re.search(r'@l(\d+(?:\.\d+)?)', pre_g)
            if m: bar['total_length'] = float(m.group(1))
            
            # Cantidad (@n)
            m = re.search(r'@n(\d+)', pre_g)
            if m: bar['quantity'] = int(m.group(1))
            
            # Peso por barra en kg (@e)
            m = re.search(r'@e([\d.]+)', pre_g)
            if m: bar['weight'] = float(m.group(1))
            
            # Diametro en mm (@d)
            m = re.search(r'@d(\d+(?:\.\d+)?)', pre_g)
            if m: bar['diameter'] = int(float(m.group(1)))
            
            # Codigo de acero (@g)
            m = re.search(r'@g(\d+)', pre_g)
            if m: bar['steel_grade_code'] = m.group(1).strip()
            
            # Mandril en mm (@s)
            m = re.search(r'@s(\d+(?:\.\d+)?)', pre_g)
            if m: bar['mandrel'] = int(float(m.group(1)))
            
            # Geometria: @G@l<L1>@w<W1>@l<L2>@w<W2>...@l<LN>@w0
            segments = []
            geom_match = re.search(r'@G(.+?)(?:@C\d+@?|$)', line)
            if geom_match:
                geom_str = geom_match.group(1)
                lens = re.findall(r'@l([\d.]+)', geom_str)
                angs = re.findall(r'@w(-?[\d.]+)', geom_str)
                
                for i, seg_len in enumerate(lens):
                    ang = float(angs[i]) if i < len(angs) else 0.0
                    segments.append({'length': float(seg_len), 'angle': ang})
            
            bar['segments'] = segments
            bars.append(bar)
    
    return bars


# =============================================================================
# UTILITIES
# =============================================================================

def get_steel_name(grade_code):
    """Convierte codigo BVBS a nombre de acero en sistema espanol."""
    code = str(grade_code).strip()
    mapping = {
        '630': 'A630-420H', '420': 'A420', '500': 'B500B',
        '550': 'B500C', '600': 'B600', 'B500B': 'B500B', 'B500C': 'B500C',
    }
    return mapping.get(code, f'A{code}')


def calc_wpm(diam_mm):
    """Peso teorico por metro en kg/m (formula estandar)."""
    d = float(diam_mm)
    return round(d * d / 162.0, 4)


def get_mandrel(diam_mm, raw=None):
    """Diametro de mandril. Usa el del BVBS si existe, sino calcula segun norma."""
    if raw and raw > 0:
        return float(raw)
    d = int(diam_mm)
    return float(d * 5 if d <= 16 else d * 8)


def to_safe(s, maxlen):
    """Convierte string a latin-1 seguro y limita longitud para Firebird."""
    if not s:
        return ''
    try:
        return s.encode('latin-1', errors='replace').decode('latin-1')[:maxlen]
    except Exception:
        return str(s).encode('ascii', errors='replace').decode('ascii')[:maxlen]


# =============================================================================
# MODELO ID MAPPING
#
# El ID_MODELO referencia el catalogo interno de formas de ferralla.
# Basado en el analisis del archivo ejemplo (Prueba Petricio.RBL):
#   - 0 doblados (barra recta)                             -> ID_MODELO = 5
#   - 1 doblados (forma L, dos tramos)                     -> ID_MODELO = 10
#   - 2 doblados (estribo U/Z, 4 puntos normalmente)       -> ID_MODELO = 3
#   - 3+ doblados (formas complejas)                       -> ID_MODELO = 236
#
# Estos valores son correctos para el software Ductisa/Graphico Pro.
# =============================================================================

def get_id_modelo(segments):
    """Devuelve ID_MODELO segun la forma de la barra."""
    # Contar doblados reales: segmentos donde el angulo != 0
    n_bends = sum(1 for seg in segments if abs(seg['angle']) > 0.5)
    
    if n_bends == 0:
        return 5    # Barra recta
    elif n_bends == 1:
        return 10   # Forma L (un doblado)
    elif n_bends == 2:
        return 3    # Estribo / U / Z (dos doblados)
    else:
        return 236  # Formas complejas (3+ doblados)


def count_bends(segments):
    """Cuenta doblados reales (angulos distintos de cero)."""
    return sum(1 for seg in segments if abs(seg['angle']) > 0.5)


# =============================================================================
# DIMENSIONES DE LA BARRA
#
# El template RBL almacena en FIGURAS:
#   LONGITUD         = longitud total del alambre (mm)
#   LONGITUD_CENTRAL = longitud del tramo central mas largo
#   ALTURA           = dimension en altura (perpendicular a eje principal)
#   ANCHURA          = dimension en anchura (eje principal)
#   DIAGONAL         = longitud diagonal de la caja envolvente
# =============================================================================

def calc_dimensions(segments):
    """
    Calcula dimensiones geometricas de la barra a partir de los segmentos BVBS.
    Retorna (longitud_total, long_central, altura, anchura, diagonal).
    """
    if not segments:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    
    # Recorrer la barra acumulando posicion 2D
    x, y = 0.0, 0.0
    direction = 0.0  # grados, 0=derecha, 90=arriba, -90=abajo
    
    # El primer segmento en BVBS puede tener un angulo inicial (gancho)
    # que define la orientacion del primer tramo
    # Pero la convencion es: angulo del segmento N indica el giro DESPUES de ese tramo
    
    points = [(x, y)]
    seg_lengths = []
    
    for seg in segments:
        L = seg['length']
        ang = seg['angle']
        
        if L > 0:
            # Avanzar en la direction actual
            rad = math.radians(direction)
            x += L * math.cos(rad)
            y += L * math.sin(rad)
            points.append((x, y))
            seg_lengths.append(L)
        
        # Girar para el siguiente tramo
        # En BVBS el angulo es el giro respecto a la direction actual
        # Angulo positivo = giro en sentido antihorario (izquierda)
        # Angulo negativo = giro en sentido horario (derecha)
        direction += ang  # Acumular giros
    
    if len(points) < 2:
        total = sum(s['length'] for s in segments)
        return total, total, 0.0, total, total
    
    # Calcular bounding box
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    anchura = round(max_x - min_x, 1)   # Dimension horizontal
    altura = round(max_y - min_y, 1)     # Dimension vertical
    diagonal = round(math.sqrt(anchura**2 + altura**2), 1)
    
    longitud_total = round(sum(s['length'] for s in segments if s['length'] > 0), 1)
    
    # Longitud central: el tramo mas largo (o la recta principal)
    long_central = round(max(seg_lengths) if seg_lengths else longitud_total, 1)
    
    return longitud_total, long_central, altura, anchura, diagonal


# =============================================================================
# PUNTOS GEOMETRY ENCODING
#
# Formato exacto del template Prueba Petricio.RBL:
# El primer punto tiene LONGITUD=0 y ANG_DOBLADO = angulo_gancho_inicial
# Los siguientes puntos tienen LONGITUD = tramo y ANG_DOBLADO = angulo_siguiente
#
# Ejemplo barra recta (BVBS: @G@l12000@w0):
#   segments = [{'length': 12000, 'angle': 0}]
#   -> Pt1: LONG=0,    ANG=0      (inicio)
#   -> Pt2: LONG=12000, ANG=0     (fin)
#
# Ejemplo estribo (BVBS: @G@l500@w90@l10000@w90@l500@w0):
#   segments = [{'length':500,'angle':90}, {'length':10000,'angle':90}, {'length':500,'angle':0}]
#   -> Pt1: LONG=0,     ANG=90   (inicio con gancho)
#   -> Pt2: LONG=500,   ANG=-90  (primer tramo, gira -90)
#   -> Pt3: LONG=10000, ANG=-90  (tramo central, gira -90)
#   -> Pt4: LONG=500,   ANG=0    (ultimo tramo, fin)
#
# NOTA: En el template los angulos de doblez se invierten a negativos
# cuando van hacia abajo (convencion de dibujo).
# =============================================================================

def calc_puntos_xy(segments):
    """
    Calcula coordenadas X/Y normalizadas para cada punto de la barra.
    Rango: [0.1, 0.9] para cumplir con la convencion del software.
    """
    if not segments:
        return [(0.1, 0.5), (0.9, 0.5)]
    
    # Construir path 2D
    x, y = 0.0, 0.0
    direction = 0.0
    path = [(x, y)]
    
    for seg in segments:
        L = seg['length']
        ang = seg['angle']
        if L > 0:
            rad = math.radians(direction)
            x += L * math.cos(rad)
            y += L * math.sin(rad)
            path.append((x, y))
        direction += ang
    
    if len(path) < 2:
        return [(0.1, 0.5), (0.9, 0.5)]
    
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    span_x = max_x - min_x
    span_y = max_y - min_y
    max_span = max(span_x, span_y, 1.0)
    
    def norm(val, lo, hi):
        if abs(hi - lo) < 1e-9:
            return 0.5
        return 0.1 + (val - lo) / (hi - lo) * 0.8
    
    # Centrar el span menor para preservar aspecto
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    half = max_span / 2
    
    result = []
    for px, py in path:
        nx = norm(px, cx - half, cx + half)
        ny = norm(py, cy - half, cy + half)
        result.append((nx, ny))
    
    return result


def build_puntos_for_figura(fig_id, segments):
    """
    Construye la lista de registros para insertar en PUNTOS.

    Formato correcto del template (foto "buena"):
      - El punto 1 es el ORIGEN: LONGITUD=0, ANG_DOBLADO=0 (marcador de inicio)
      - Los puntos 2..N llevan LONGITUD=tramo_i y ANG_DOBLADO=angulo_al_final_de_ese_tramo
      - El ultimo punto tiene ANG_DOBLADO=0

    Esto hace que el primer segmento (gancho izquierdo) SI aparezca dibujado.
    El angulo en cada punto indica el giro que ocurre al FINAL de ese tramo.
    """
    if not segments:
        return []

    xy = calc_puntos_xy(segments)
    puntos = []

    # Punto 1: origen fijo, longitud=0, angulo=0
    xy0 = xy[0] if xy else (0.1, 0.5)
    puntos.append({
        'id_entidad': fig_id,
        'id_punto': 1,
        'id_figura': fig_id,
        'x': xy0[0],
        'y': xy0[1],
        'longitud': 0.0,
        'ang_doblado': 0.0,
        'tabulacion': 0,
    })

    # Puntos 2 a N: uno por cada segmento BVBS
    for seg_i, seg in enumerate(segments):
        L = seg['length']
        is_last = (seg_i == len(segments) - 1)

        # El angulo en este punto es el giro que ocurre al final de este tramo.
        # El ultimo tramo siempre termina con angulo=0 (fin de barra).
        ang = 0.0 if is_last else seg['angle']

        xy_pt = xy[seg_i + 1] if (seg_i + 1) < len(xy) else (0.9, 0.5)

        puntos.append({
            'id_entidad': fig_id,
            'id_punto': seg_i + 2,
            'id_figura': fig_id,
            'x': xy_pt[0],
            'y': xy_pt[1],
            'longitud': round(L, 1),
            'ang_doblado': ang,
            'tabulacion': 0 if is_last else 1,
        })

    return puntos


# =============================================================================
# AGRUPACION CODES
# =============================================================================

def build_agrupacion_primary(bar, fig_id):
    """Codigo primario de agrupacion unico por figura."""
    qty = bar.get('quantity', 1)
    diam = bar.get('diameter', 12)
    total_len = int(bar.get('total_length', 0))
    steel = get_steel_name(bar.get('steel_grade_code', '630'))
    segments = bar.get('segments', [])
    
    # Codificar geometria
    geom_parts = []
    for seg in segments:
        ang_int = int(abs(seg['angle']))
        geom_parts.append(f"@{int(seg['length']):05d}@{ang_int:04d}")
    geom_str = ''.join(geom_parts) if geom_parts else f"@{total_len:06d}@0000"
    
    # Formato: B<long_trunc4><diam2><steel>@0@0@<geom>@F<figid5>
    long_str = str(int(total_len / 10)).zfill(4)[:4]  # long/10 padded 4 digits
    
    code = f"B{long_str}{diam:02d}{steel}@0@0{geom_str}@F{fig_id:05d}"
    return code[:250]


def build_agrupacion_hash(bar, suffix):
    """Codigo hash secundario/terciario."""
    key = f"{bar.get('quantity')}_{bar.get('diameter')}_{bar.get('total_length')}_{suffix}"
    for s in bar.get('segments', []):
        key += f"_{int(s['length'])}_{int(s['angle'])}"
    return hashlib.sha256(key.encode()).hexdigest()[:72]


# =============================================================================
# MAIN CONVERTER
# =============================================================================

def convert(bvbs_path, output_rbl, template_rbl):
    """Convierte archivo BVBS a base de datos RBL Firebird."""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    FB_DIR = os.path.join(script_dir, 'firebird25')
    fbembed = os.path.join(FB_DIR, 'fbembed.dll')
    fbclient = os.path.join(FB_DIR, 'fbclient.dll')
    
    if not os.path.exists(fbembed):
        raise FileNotFoundError(
            f"fbembed.dll no encontrado en: {FB_DIR}\n"
            "Descarga Firebird 2.5 Embedded x64 y descomprime en la carpeta 'firebird25/'"
        )
    if not os.path.exists(fbclient):
        shutil.copy2(fbembed, fbclient)
    
    os.environ['PATH'] = FB_DIR + ';' + os.environ.get('PATH', '')
    
    import fdb
    
    # ── 1. Parsear BVBS ──────────────────────────────────────────────────────
    print(f"[1/3] Parseando: {os.path.basename(bvbs_path)}")
    bars = parse_bvbs_file(bvbs_path)
    
    if not bars:
        raise ValueError("Sin barras en el archivo BVBS")
    
    project_name = bars[0].get('project', os.path.splitext(os.path.basename(bvbs_path))[0])
    reference    = bars[0].get('reference', '')
    
    print(f"  Proyecto  : {project_name}")
    print(f"  Referencia: {reference}")
    print(f"  Barras    : {len(bars)}")
    print(f"  Unidades  : {sum(b.get('quantity', 1) for b in bars)}")
    
    total_w = sum(b.get('weight', 0) * b.get('quantity', 1) for b in bars)
    if total_w > 0:
        print(f"  Peso total: {total_w:.2f} kg")
    
    # ── 2. Crear BD Firebird ─────────────────────────────────────────────────
    print(f"\n[2/3] Creando BD: {os.path.basename(output_rbl)}")
    shutil.copy2(template_rbl, output_rbl)
    
    con = fdb.connect(
        database=output_rbl,
        user='sysdba', password='masterkey',
        fb_library_name=fbembed,
        charset='WIN1252'
    )
    
    now = datetime.now()
    
    try:
        cur = con.cursor()
        
        # Limpiar datos existentes respetando FKs
        print("  Limpiando datos...")
        for tbl in ['FIGURAS_PEDIDOS_PROD', 'FIGURAS_PRODUCTOS', 'LOCK_ELEMENTO',
                     'PARRILLAS', 'PUNTOS', 'FIGURAS', 'ELEMENTOS', 'GRUPOS',
                     'PLANTAS', 'FASES', 'AGRUPACION', 'DISTRIBUCIONES',
                     'MYMESH', 'TMP_DICT_INT', 'CALIBRE']:
            try:
                cur.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
        con.commit()
        
        # Calcular peso total real
        total_weight = sum(
            calc_wpm(b.get('diameter', 12)) * (b.get('total_length', 0) / 1000.0) * b.get('quantity', 1)
            for b in bars
        )
        
        # Insertar estructura base: FASES -> PLANTAS -> GRUPOS -> ELEMENTOS
        print("  Insertando estructura base...")
        
        cur.execute("""INSERT INTO FASES (ID_FASE, ID_OBRA, ID_USUARIO_CREACION, ORDEN_FASE, NOMBRE)
                       VALUES (1, NULL, 1, 1, 'Fase 1')""")
        
        cur.execute("""INSERT INTO PLANTAS (ID_PLANTA, ID_FASE, ID_USUARIO_CREACION, ORDEN_PLANTA, NOMBRE,
                                             PESO_CONTRATADO, PESO_PREVISTO, M2FORJADO, M3FORJADO, FLAG_USU)
                       VALUES (1, 1, 1, 1, ?, NULL, NULL, NULL, NULL, NULL)""",
                    (to_safe(project_name, 50),))
        
        cur.execute("""INSERT INTO GRUPOS (ID_GRUPO, ID_PLANTA, ID_FASE, ID_USUARIO_CREACION,
                                           ID_TABLA_CALIBRES, ORDEN_GRUPO, NOMBRE,
                                           PESO_TEORICO, PESO_PRODUCCION, PLANO, COLOR,
                                           FIGURAS_EN_FPP, BLOQUEADO_CAD, BLOQUEADO_CRM)
                       VALUES (1, 1, 1, 1, 1, 1, ?, ?, ?, NULL, NULL, 0, 0, 0)""",
                    (to_safe(reference or project_name, 30),
                     round(total_weight, 2), round(total_weight * 0.97, 2)))
        
        cur.execute("""INSERT INTO ELEMENTOS (ID_ELEMENTO, ID_GRUPO, ID_PLANTA, ID_FASE,
                                              ID_USUARIO_CREACION, FECHA_CREACION,
                                              ID_USUARIO_MODIFICACION, FECHA_MODIFICACION,
                                              ID_TABLA_CALIBRES, ID_PRODUCTO, ID_PRODUCTO_VENTA,
                                              ID_PRODUCTO_SERVICIO,
                                              CREACION, ORDEN_ELEMENTO, NOMBRE, REFERENCIA,
                                              FACTOR, LONGITUD, ANCHURA,
                                              PESO_ELEMENTO, PESO_ELEMENTO_FB, PORCENTAJE_PESO,
                                              PUNTOS_SOLDADURA, PLANO, PLANO_DOC_FILE, COLOR,
                                              ID_MAQUINA, ID_MAQUINA_CLASE, ID_MAQUINA_CFG,
                                              TIEMPO_CREACION, COD_UNION, ELIMINADO)
                       VALUES (1,1,1,1, 1,?,1,?, NULL,1,1,NULL, 100,1,?,?,
                               1,NULL,NULL, ?,?,NULL, NULL,NULL,NULL,NULL,
                               NULL,NULL,NULL, NULL,NULL,0)""",
                    (now, now,
                     to_safe(project_name, 30), to_safe(reference, 30),
                     round(total_weight, 2), round(total_weight * 0.97, 2)))
        
        con.commit()
        
        # ── 3. Insertar FIGURAS + PUNTOS + AGRUPACION ────────────────────────
        print(f"  Insertando {len(bars)} barras...")
        agrup_id = 1
        
        for fig_id, bar in enumerate(bars, 1):
            # Posicion real de la barra segun BVBS (ej: 5, 8, 11, 15...)
            pos_raw  = bar.get('position', str(fig_id))
            pos      = to_safe(str(pos_raw), 30)
            ref      = to_safe(str(bar.get('reference', '')), 30)
            qty      = bar.get('quantity', 1)
            # Longitud total: se toma directamente del BVBS (campo @l antes de @G)
            # en mm. Es la longitud desplegada total incluyendo ganchos.
            total_len = bar.get('total_length', 0.0)
            diam     = bar.get('diameter', 12)
            steel    = get_steel_name(bar.get('steel_grade_code', '630'))
            mandrel  = get_mandrel(diam, bar.get('mandrel'))
            wpm      = calc_wpm(diam)
            segments = bar.get('segments', [])

            # ID_MODELO segun forma de la barra
            id_modelo = get_id_modelo(segments)

            # Numero de doblados y dimensiones geometricas (anchura/altura para dibujo)
            n_bends  = count_bends(segments)
            _geom_total, long_central, altura, anchura, diagonal = calc_dimensions(segments)
            # LONGITUD en FIGURAS = longitud total real del BVBS (no recalculada)
            long_total = round(total_len, 1)

            # Pesos basados en longitud real del BVBS
            w_unit   = round(wpm * (total_len / 1000.0), 3)
            w_total  = round(w_unit * qty, 3)

            # Agrupacion
            cod1 = build_agrupacion_primary(bar, fig_id)
            cod2 = build_agrupacion_hash(bar, f'b{fig_id}')
            cod3 = build_agrupacion_hash(bar, f'c{fig_id}')
            
            cur.execute("INSERT INTO AGRUPACION (PALABRA, COD_AGRUPACION) VALUES (?,?)", (cod1, agrup_id))
            a1 = agrup_id; agrup_id += 1
            cur.execute("INSERT INTO AGRUPACION (PALABRA, COD_AGRUPACION) VALUES (?,?)", (cod2, agrup_id))
            a2 = agrup_id; agrup_id += 1
            cur.execute("INSERT INTO AGRUPACION (PALABRA, COD_AGRUPACION) VALUES (?,?)", (cod3, agrup_id))
            a3 = agrup_id; agrup_id += 1
            
            # Insertar FIGURA
            # Columnas: 85 total
            cur.execute("""
                INSERT INTO FIGURAS (
                    ID_FIGURA, ID_ELEMENTO, ID_GRUPO, ID_PLANTA, ID_FASE,
                    ID_USUARIO_CREACION, FECHA_CREACION, MODO_CREACION,
                    ID_USUARIO_MODIFICACION, FECHA_MODIFICACION,
                    ID_MODELO, ID_PRODUCTO, ID_PRODUCTO_VENTA, ID_PRODUCTO_SERVICIO,
                    ID_MAQUINA, ID_PLANILLA_EXTERNA,
                    ORDEN_FIGURA, POSICION, REFERENCIA, ITEM_CLIENTE, TIPO_FIGURA,
                    MODELO_MODIFICADO, EMPAQUETADO_FORZADO,
                    COD_VARIABLE_BASE, COD_VARIABLE, METODO_VARIABLE,
                    TEXTO_VARIABLE, TEXTO_VARIABLE_2,
                    VARIABLE_MODIFICADA, VARIABLE_NO_VISIBLE, DESGLOSE_FORZADO,
                    ANG_DOBLADO_3D, DOBLADOS, ARCOS, GANCHOS,
                    FACTOR,
                    LONGITUD, LONGITUD_CENTRAL, ALTURA, ANCHURA, DIAGONAL, PESO,
                    FACTOR_FB,
                    LONGITUD_FB, LONGITUD_CENTRAL_FB, ALTURA_FB, ANCHURA_FB, DIAGONAL_FB, PESO_FB,
                    CAL_NOMBRE, CAL_NOMBRE_SALIDA, CAL_MM, CAL_PESO_TEORICO, CAL_MANDRINO, CAL_TIPO_ACERO,
                    CAL_NOMBRE_FB, CAL_NOMBRE_SALIDA_FB, CAL_MM_FB, CAL_PESO_TEORICO_FB, CAL_MANDRINO_FB, CAL_TIPO_ACERO_FB,
                    MANDRINO, ROSCAS,
                    ID_TIPO_ROSCA_1, ID_TIPO_ROSCA_2, ID_PRODUCTO_TUERCA_1, ID_PRODUCTO_TUERCA_2,
                    COD_AGRUPACION, COD_AGRUPACION_1, COD_AGRUPACION_2,
                    POSICION_TEXTO, EMPAQUETADO_MODELO, MOD_FIGURAS_PAQUETE, MOD_PESO_PAQUETE,
                    MANTENER_FORMA, FORMULA_LONGITUD_FB, UNIDADES_LONGITUD_FB,
                    PUNTOS_SOLDADURA, TAGGER, TAGGER_NUM_BARRAS_PINTAR, TAGGER_LONG_INICIO,
                    TAGGER_PROTOCOLO_1, TAGGER_PROTOCOLO_2, OBSERVACIONES, ELIMINADA
                ) VALUES (
                    ?,1,1,1,1,
                    1,?,1,1,?,
                    ?,1,1,NULL,0,NULL,
                    ?,?,?,NULL,'0',
                    0,0,0,0,0,'',NULL,0,0,0,
                    0,?,0,0,
                    ?,
                    ?,?,?,?,?,?,
                    ?,
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    0.0,0,NULL,NULL,NULL,NULL,
                    ?,?,?,
                    0,0,0,0.0,
                    0,'',0,0,0,0.0,0,0,'',0,0
                )""",
                (
                    fig_id, now, now,
                    id_modelo,            # ID_MODELO - CLAVE!
                    # ORDEN_FIGURA usa la posicion real de la barra (no el indice secuencial)
                    int(pos_raw) if str(pos_raw).isdigit() else fig_id,
                    pos, ref,
                    n_bends,              # DOBLADOS
                    qty,
                    long_total, long_central, altura, anchura, diagonal, w_unit,
                    qty,
                    long_total, long_central, altura, anchura, diagonal, w_total,
                    str(diam), str(diam), float(diam), wpm, mandrel, steel,
                    str(diam), str(diam), float(diam), wpm, mandrel, steel,
                    a1, a2, a3,
                )
            )
            
            # Insertar PUNTOS (geometria)
            puntos = build_puntos_for_figura(fig_id, segments)
            for pt in puntos:
                cur.execute("""
                    INSERT INTO PUNTOS (
                        ID_ELEMENTO, ID_ENTIDAD, ID_PUNTO, ID_FIGURA,
                        ORDEN_ENTIDAD, TIPO_ENTIDAD, X, Y, TIPO_PUNTO,
                        AUTOMATICO, LONGITUD_ARCO,
                        LONGITUD, LONGITUD_FB,
                        ANG_DOBLADO, ANG_DOBLADO_FB,
                        ANG_DOBLADO_3D, LONGFLIP, INC_LADOVAR, INC_ANGVAR,
                        TABULACION_TRAMO, TABULACION_ANG,
                        IDENTIF_TRAMO, IDENTIF_ANG, UNIDADES_TRAMO,
                        FORMULA_TRAMO, FORMULA_ANGULO,
                        VISIBLE_TRAMO, VISIBLE_ANGULO, VISIBLE_ARCO,
                        TEXTO, TEXTO_TALLA, TEXTO_FORMULA
                    ) VALUES (
                        1,?,?,?,
                        NULL,'F',?,?,'F',
                        0,0,
                        ?,?,
                        ?,?,
                        0,0,0.0,0.0,
                        ?,0,
                        '','',0,'','',
                        1,1,0,
                        '',NULL,0
                    )""",
                    (
                        pt['id_entidad'],
                        pt['id_punto'],
                        pt['id_figura'],
                        pt['x'], pt['y'],
                        pt['longitud'],        # LONGITUD
                        pt['longitud'],        # LONGITUD_FB
                        pt['ang_doblado'],     # ANG_DOBLADO
                        pt['ang_doblado'],     # ANG_DOBLADO_FB
                        pt['tabulacion'],      # TABULACION_TRAMO
                    )
                )
            
            if fig_id % 100 == 0:
                con.commit()
                print(f"  ... {fig_id}/{len(bars)}")
        
        # Actualizar pesos reales
        cur.execute("""UPDATE ELEMENTOS SET
            PESO_ELEMENTO = (SELECT COALESCE(SUM(PESO_FB),0) FROM FIGURAS WHERE ID_ELEMENTO=1 AND ELIMINADA=0),
            PESO_ELEMENTO_FB = (SELECT COALESCE(SUM(PESO_FB),0) FROM FIGURAS WHERE ID_ELEMENTO=1 AND ELIMINADA=0)
            WHERE ID_ELEMENTO=1""")
        cur.execute("""UPDATE GRUPOS SET
            PESO_TEORICO = (SELECT COALESCE(SUM(PESO_FB),0) FROM FIGURAS WHERE ID_GRUPO=1 AND ELIMINADA=0),
            PESO_PRODUCCION = (SELECT COALESCE(SUM(PESO_FB),0) FROM FIGURAS WHERE ID_GRUPO=1 AND ELIMINADA=0)
            WHERE ID_GRUPO=1""")
        
        con.commit()
        print(f"  OK: {len(bars)} barras insertadas")
        
    except Exception as e:
        con.rollback()
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        con.close()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_template = os.path.join(script_dir, 'Prueba Petricio.RBL')
    
    print("=" * 65)
    print("  BVBS -> RBL Converter v3.0")
    print("  Convierte archivos BVBS a base de datos Firebird RBL")
    print("=" * 65)
    
    if len(sys.argv) < 2:
        print("\nUso: python bvbs_to_rbl.py <archivo.bvbs> [salida.RBL] [plantilla.RBL]")
        print("Ej:  python bvbs_to_rbl.py MAD42168803.bvbs MAD42168803.RBL")
        sys.exit(1)
    
    bvbs_path = sys.argv[1]
    if not os.path.exists(bvbs_path):
        print(f"ERROR: Archivo no encontrado: {bvbs_path}")
        sys.exit(1)
    
    output_rbl   = sys.argv[2] if len(sys.argv) >= 3 else os.path.splitext(bvbs_path)[0] + '.RBL'
    template_rbl = sys.argv[3] if len(sys.argv) >= 4 else default_template
    
    if not os.path.exists(template_rbl):
        print(f"ERROR: Plantilla RBL no encontrada: {template_rbl}")
        sys.exit(1)
    
    print(f"\n  Entrada  : {bvbs_path}")
    print(f"  Salida   : {output_rbl}")
    print(f"  Plantilla: {template_rbl}\n")
    
    try:
        convert(bvbs_path, output_rbl, template_rbl)
        size_kb = os.path.getsize(output_rbl) / 1024
        print(f"\n[3/3] Conversion exitosa!")
        print(f"  Archivo: {output_rbl}")
        print(f"  Tamano : {size_kb:.0f} KB")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
