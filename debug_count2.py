"""Count FIGURAS INSERT columns vs values."""
import re

sql_cols = """
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
"""

sql_vals = """
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
    0,'',0,0,0,0.0,0,0,'',0
"""

cols = [c.strip() for c in sql_cols.strip().split(',') if c.strip()]
vals = [v.strip() for v in re.split(r',\s*', sql_vals.strip()) if v.strip()]

print(f"Columns: {len(cols)}")
print(f"Values : {len(vals)}")
print(f"Diff   : {len(cols) - len(vals)}")
print()

# Line up columns with values
for i, (c, v) in enumerate(zip(cols, vals), 1):
    q = "?" if v == '?' else " "
    print(f"  {i:2d}. {c:<40s} {q} {v}")

if len(cols) != len(vals):
    print("\nMISSING:")
    if len(cols) > len(vals):
        for c in cols[len(vals):]:
            print(f"  COL: {c}")
    else:
        for v in vals[len(cols):]:
            print(f"  VAL: {v}")

# Also count ?s
q_count = vals.count('?')
print(f"\nTotal ?s: {q_count}")

# Count params provided (from converter)
params = [
    'fig_id', 'now', 'now',
    'id_modelo',
    'fig_id', 'pos', 'ref',
    'n_bends',
    'qty',
    'long_total', 'long_central', 'altura', 'anchura', 'diagonal', 'w_unit',
    'qty',
    'long_total', 'long_central', 'altura', 'anchura', 'diagonal', 'w_total',
    'str(diam)', 'str(diam)', 'float(diam)', 'wpm', 'mandrel', 'steel',
    'str(diam)', 'str(diam)', 'float(diam)', 'wpm', 'mandrel', 'steel',
    'a1', 'a2', 'a3',
]
print(f"Provided params: {len(params)}")
print(f"Diff: {q_count - len(params)}")
