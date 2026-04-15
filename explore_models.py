"""Explore models and calibres in the template RBL database."""
import os, shutil
FB_DIR = r"c:\Users\rsilv\bvbs a rbl\firebird25"
DB_PATH = r"c:\Users\rsilv\bvbs a rbl\Prueba Petricio.RBL"

import fdb
fbembed = os.path.join(FB_DIR, "fbembed.dll")
os.environ['PATH'] = FB_DIR + ';' + os.environ.get('PATH', '')

con = fdb.connect(database=DB_PATH, user='sysdba', password='masterkey',
                  fb_library_name=fbembed, charset='WIN1252')
cur = con.cursor()

# Check if there's a MODELOS table or similar
cur.execute("SELECT TRIM(rdb$relation_name) FROM rdb$relations WHERE rdb$view_blr IS NULL AND rdb$system_flag = 0 ORDER BY rdb$relation_name")
tables = [r[0] for r in cur.fetchall()]
print("All tables:", tables)

# Check all procedure/stored procs that might reference models
cur.execute("SELECT TRIM(rdb$procedure_name) FROM rdb$procedures")
procs = [r[0] for r in cur.fetchall()]
print("Procedures:", procs[:20])

# Look at FIGURAS ID_MODELO values
cur.execute("SELECT DISTINCT ID_MODELO, DOBLADOS, ARCOS, COUNT(*) FROM FIGURAS WHERE ELIMINADA=0 GROUP BY ID_MODELO, DOBLADOS, ARCOS ORDER BY DOBLADOS")
print("\nID_MODELO by DOBLADOS (bends) in FIGURAS:")
for row in cur.fetchall():
    print(f"  ID_MODELO={row[0]:4d}, DOBLADOS={row[1]}, ARCOS={row[2]}, count={row[3]}")

# Look for CALIBRES data
print("\nCALIBRE table:")
cur.execute("SELECT * FROM CALIBRE")
for row in cur.fetchall():
    print(f"  {row}")

# Check FIGURAS ID_MODELO field - is it a FK?
cur.execute("""
    SELECT TRIM(rc.rdb$constraint_name), TRIM(rc.rdb$relation_name), TRIM(i2.rdb$relation_name)
    FROM rdb$relation_constraints rc
    JOIN rdb$ref_constraints fk ON rc.rdb$constraint_name = fk.rdb$constraint_name
    JOIN rdb$relation_constraints rc2 ON fk.rdb$const_name_uq = rc2.rdb$constraint_name
    JOIN rdb$indices i2 ON rc2.rdb$index_name = i2.rdb$index_name
    WHERE TRIM(rc.rdb$relation_name) = 'FIGURAS'
""")
print("\nFIGURAS foreign keys:")
for row in cur.fetchall():
    print(f"  {row}")

# Check user-tables that might hold models
for t in tables:
    if 'MODEL' in t.upper() or 'FIGURA' in t.upper() and 'PEDIDO' not in t.upper():
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"\nTable {t}: {cnt} rows")
        if cnt > 0:
            cur.execute(f"SELECT FIRST 5 * FROM {t}")
            col_names = [d[0] for d in cur.description]
            print(f"  Cols: {col_names}")
            for r in cur.fetchall():
                print(f"  {r}")

# PUNTOS data for the figures - check the geometry
print("\nPUNTOS full geometry:")
cur.execute("""
    SELECT p.ID_FIGURA, p.ID_PUNTO, p.LONGITUD_FB, p.ANG_DOBLADO_FB,
           f.POSICION, f.DOBLADOS, f.ID_MODELO
    FROM PUNTOS p
    JOIN FIGURAS f ON p.ID_FIGURA = f.ID_FIGURA
    ORDER BY p.ID_FIGURA, p.ID_PUNTO
""")
for row in cur.fetchall():
    print(f"  Fig={row[0]}, Pt={row[1]}, Long={row[2]:8.1f}, Ang={row[3]:6.1f},  Pos={row[4]}, Bends={row[5]}, Model={row[6]}")

con.close()
