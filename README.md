# Trámites urbanísticos — El Carmen de Viboral

Aplicación local (Python + Streamlit) para consultar la norma, revisar trámites
y producir conceptos técnicos de la Secretaría de Planeación.

**Instalación y uso:** ver [docs/INSTALACION.md](docs/INSTALACION.md).

## Estado

| Módulo | Estado |
| --- | --- |
| 0. Parámetros normativos, normas, cartografía, usuarios, auditoría, configuración | Listo (esta versión) |
| 1. Consulta normativa (fichas por zona, cesiones explicadas) | Siguiente |
| 2. Expedientes y trámites | Pendiente |
| 3. Gestión documental | Pendiente |
| 5. Listas de chequeo | Pendiente |
| 6. Calculadoras (IO/IC, cuadro de áreas, cesiones, plusvalía, liquidación) | Pendiente |
| Análisis de planos (DXF/DWG, IFC, .e2k/.s2k, PDF/OCR/IA, cruce) | Versión inicial: verificación sísmica y geotécnica rápida |
| 7. Informes Word/PDF | Pendiente |

## Principio

Ninguna cifra normativa está escrita en el código. Todas salen de
`config/parametros/*.yaml`, con norma y artículo. Donde la norma tiene varias
lecturas (área neta, base del IO/IC, IC 2,5 o 4, redondeo de tarifas, tasa de
plusvalía), el archivo trae las opciones y la Secretaría elige una; el cambio
queda con usuario, fecha y motivo.

## Estructura

```
app.py                  entrada
config/parametros/      nacional, nsr10, pbot, d152, tarifas (+ CSV art. 138)
config/ajustes.yaml     lectura de escaneos (local/IA/auto), DWG (ODA/LibreDWG), repositorio
core/                   bd, usuarios, auditoría, parámetros, NSR-10, lectura, normas, cartografía, conversores
paginas/                pantallas Streamlit
datos/                  base de datos, normas, capas, expedientes (no se suben al repositorio)
tests/                  pruebas
```
