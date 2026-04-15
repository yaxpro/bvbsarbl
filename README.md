# Convertidor BVBS → RBL

Convierte archivos de lista de ferralla en formato **BVBS** (.bvbs) a bases de datos **RBL** (Firebird 2.5) compatibles con software de ferralla español (Ductisa/Graphico Pro).

## Requisitos

- Python 3.8+
- Paquete `fdb`: `pip install fdb`
- Firebird 2.5 Embedded (incluido en carpeta `firebird25/`)
- Archivo plantilla `Prueba Petricio.RBL` en el mismo directorio

## Uso

```
python bvbs_to_rbl.py <archivo.bvbs> [salida.RBL]
```

### Ejemplos

```bash
# Conversión básica (mismo nombre, extensión .RBL)
python bvbs_to_rbl.py MAD42168803.bvbs

# Especificar nombre de archivo de salida
python bvbs_to_rbl.py MAD42168803.bvbs MAD42168803_convertido.RBL

# Especificar plantilla personalizada
python bvbs_to_rbl.py MAD42168803.bvbs salida.RBL mi_plantilla.RBL
```

## Formato BVBS

El formato BVBS (Bundesvereinigung der BauSoftwarehäuser) es un estándar ASCII para intercambio de datos de ferralla:

```
BF2D@H<proyecto>@r<referencia>@i@p<posicion>@l<long_total>@n<cantidad>@e<peso>@d<diametro>@g<acero>@s<mandril>@G@l<tramo1>@w<ang1>@l<tramo2>@w<ang2>...@w0@C<checksum>
```

| Campo | Descripción |
|-------|-------------|
| `@H` / `@j` | Nombre del proyecto |
| `@r` | Referencia / plano |
| `@p` | Número de posición |
| `@l` (cabecera) | Longitud total (mm) |
| `@n` | Cantidad de barras |
| `@e` | Peso por barra (kg) |
| `@d` | Diámetro (mm) |
| `@g` | Código de acero (ej: 630 = A630-420H) |
| `@s` | Diámetro de mandril (mm) |
| `@G` | Inicio de geometría |
| `@l` (geometría) | Longitud de tramo (mm) |
| `@w` | Ángulo de doblado (grados, 0 = recto) |
| `@C` | Checksum |

## Base de datos RBL

El archivo RBL es una base de datos **Firebird 2.5** (ODS 11.2) con las siguientes tablas principales:

| Tabla | Descripción |
|-------|-------------|
| `FASES` | Fases de obra |
| `PLANTAS` | Plantas / niveles |
| `GRUPOS` | Grupos de ferralla (por elemento estructural) |
| `ELEMENTOS` | Elementos estructurales |
| `FIGURAS` | Barras de ferralla (forma, diámetro, cantidad) |
| `PUNTOS` | Geometría de cada barra (tramos y ángulos) |
| `AGRUPACION` | Códigos de agrupación para clasificación |

## Conversión de aceros

| Código BVBS | Nombre RBL |
|-------------|-----------|
| 630 | A630-420H |
| 500 | B500B |
| 550 | B500C |
| 420 | A420 |

## Estructura de archivos

```
bvbs a rbl/
├── bvbs_to_rbl.py          ← Script principal
├── firebird25/              ← Firebird 2.5 Embedded
│   ├── fbembed.dll
│   └── ...
├── Prueba Petricio.RBL      ← Plantilla RBL
└── MAD42168803.bvbs         ← Ejemplo de entrada
```
