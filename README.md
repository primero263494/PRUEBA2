# Trámites urbanísticos — El Carmen de Viboral

Aplicación local (Python + Streamlit) para consultar la norma, revisar trámites
y producir conceptos técnicos de la Secretaría de Planeación.

**Instalación y uso:** ver [docs/INSTALACION.md](docs/INSTALACION.md).

## Estado

| Módulo | Estado |
| --- | --- |
| 0. Parámetros normativos, normas, cartografía, usuarios, auditoría, configuración | Listo (esta versión) |
| 1. Consulta normativa (buscador, fichas por zona/predio, usos del suelo, cesiones con ejemplo, por tipo de suelo) | Listo |
| 2. Expedientes y trámites (radicado, predio, trámites, eliminación con copia, verificación contra la norma, términos en días hábiles) | Listo |
| 3. Gestión documental (carga por trámite, clasificación automática, versiones, vista previa PDF/imagen/Word/Excel/DXF, documentos exigidos, papelera) | Listo |
| 5. Listas de chequeo (por tipo de trámite, cumple/no cumple/no aplica con observaciones, sugerencias automáticas, avance, Excel) | Listo |
| 6. Calculadoras (científica, IO/IC con ficha y planos, cuadro de áreas con Excel/Word, cesiones, plusvalía paso a paso, liquidación) | Listo |
| Análisis de planos (DXF/DWG, IFC, .e2k/.s2k, PDF/OCR/IA, cruce) | Siguiente (versión inicial: verificación sísmica y geotécnica rápida) |
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
config/parametros/      nacional, nsr10, pbot, d152, tarifas (+ CSV art. 138 y usos art. 123)
config/normas_base/     textos de PBOT, D152, tarifas, Ley 388 y Decreto 1077 para el buscador
config/ajustes.yaml     lectura de escaneos (local/IA/auto), DWG (ODA/LibreDWG), repositorio
core/                   bd, usuarios, auditoría, parámetros, NSR-10, lectura, normas, cartografía, conversores
paginas/                pantallas Streamlit
datos/                  base de datos, normas, capas, expedientes (no se suben al repositorio)
tests/                  pruebas
```
