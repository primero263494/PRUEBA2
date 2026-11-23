# Instalación y uso — paso a paso

Esta guía es para alguien que no programa. Todo se hace con doble clic, salvo
instalar Python y Tesseract la primera vez.

## 1. Instalar Python (una sola vez)

1. Entre a python.org → Downloads → descargue Python 3.11 o superior para Windows.
2. Al instalar, **marque la casilla "Add Python to PATH"**.
3. Termine la instalación.

## 2. Instalar el programa (una sola vez)

1. Copie la carpeta `tramites_urbanisticos` al computador (por ejemplo en `Documentos`).
2. Haga doble clic en **`instalar.bat`**. Tarda unos minutos porque descarga las librerías.
3. Cuando diga "Instalación terminada", cierre la ventana.

## 3. Abrir el programa

1. Doble clic en **`iniciar.bat`**.
2. Se abre el navegador con el programa. No cierre la ventana negra mientras lo use.
3. La primera vez el programa pide crear el **usuario administrador**.

## 4. Opcionales

### OCR local (leer escaneos sin internet)
Instale Tesseract para Windows (busque "Tesseract OCR Windows UB Mannheim"),
y durante la instalación marque el idioma **Spanish**. Reinicie el programa.

### IA para escaneos (con internet)
1. Obtenga una clave de API del proveedor configurado.
2. Créela como variable de entorno de Windows llamada `ANTHROPIC_API_KEY`
   (Panel de control → Sistema → Variables de entorno). La clave **no** se guarda
   en los archivos del programa.
3. En el programa: Configuración → Lectura de escaneos → "Automático" o "IA".
   En "Automático", si no hay internet en ese momento, el programa usa OCR local.

### Abrir DWG
Elija en Configuración → Conversión de DWG:
- **ODA File Converter**: gratuito (licencia propietaria), descarga en opendesign.com.
- **LibreDWG**: libre (GPL); descargue `dwg2dxf.exe`.
Escriba la ruta del ejecutable y guarde. En "Automático" intenta ODA y luego LibreDWG.

## 5. Cargar la cartografía

Cartografía → Cargar capa. Suba cada plano del PBOT (shapefile en .zip, GeoJSON,
KML o GeoPackage) y elija su **rol** (tratamientos, amenaza, rondas…). El cruce
del predio usa el rol, así que puede cargar las capas en cualquier orden.

## 6. Actualizar la norma

- **Valores** (porcentajes, tarifas, índices): página Parámetros, con motivo.
  O edite `config/parametros/*.yaml` y reinicie.
- **Textos** (una ley nueva, un decreto que modifica): página Normas → Cargar,
  y márquela como verificada. El normograma avisa lo que lleva más de 6 meses
  sin verificar.

## 7. Repositorio en línea (GitHub)

El código y los parámetros se pueden subir a un repositorio. La base de datos,
los expedientes, las normas cargadas y las capas **no** se suben (están en
`.gitignore`), porque contienen datos personales. Haga copia de seguridad de la
carpeta `datos` aparte.

## 8. Pruebas (para soporte técnico)

```
.venv\Scripts\activate
python -m pytest tests
```
