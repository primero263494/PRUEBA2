"""Cálculos NSR-10 que usan los parámetros cargados (nunca valores fijos).

Sirven al módulo de análisis de planos para comparar lo que declara la
memoria estructural o el estudio de suelos con la norma.
"""
from core import parametros as P


def _interpolar(fila: list[float], columnas: list[float], x: float) -> float:
    """Interpolación lineal permitida por la NSR-10 (A.2.4)."""
    if x <= columnas[0]:
        return fila[0]
    if x >= columnas[-1]:
        return fila[-1]
    for i in range(len(columnas) - 1):
        x0, x1 = columnas[i], columnas[i + 1]
        if x0 <= x <= x1:
            y0, y1 = fila[i], fila[i + 1]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return fila[-1]


def Fa(perfil: str, Aa: float | None = None) -> float:
    perfil = perfil.upper()
    if perfil == "F":
        raise ValueError("Perfil F: requiere evaluación específica de sitio (NSR-10 A.2.10).")
    Aa = P.valor("nsr10.amenaza_sismica_municipio.Aa") if Aa is None else Aa
    tabla = P.valor("nsr10.Fa.tabla")
    cols = P.valor("nsr10.Fa.columnas")
    return round(_interpolar(tabla[perfil], cols, Aa), 3)


def Fv(perfil: str, Av: float | None = None) -> float:
    perfil = perfil.upper()
    if perfil == "F":
        raise ValueError("Perfil F: requiere evaluación específica de sitio (NSR-10 A.2.10).")
    Av = P.valor("nsr10.amenaza_sismica_municipio.Av") if Av is None else Av
    tabla = P.valor("nsr10.Fv.tabla")
    cols = P.valor("nsr10.Fv.columnas")
    return round(_interpolar(tabla[perfil], cols, Av), 3)


def espectro(perfil: str, grupo_uso: str, Aa=None, Av=None) -> dict:
    """Parámetros del espectro elástico de diseño (NSR-10 A.2.6)."""
    Aa = P.valor("nsr10.amenaza_sismica_municipio.Aa") if Aa is None else Aa
    Av = P.valor("nsr10.amenaza_sismica_municipio.Av") if Av is None else Av
    fa, fv = Fa(perfil, Aa), Fv(perfil, Av)
    I = P.valor("nsr10.coeficiente_importancia")[grupo_uso.upper()]
    T0 = 0.10 * Av * fv / (Aa * fa)
    TC = 0.48 * Av * fv / (Aa * fa)
    TL = 2.4 * fv
    return {
        "Aa": Aa, "Av": Av, "Fa": fa, "Fv": fv, "I": I,
        "T0": round(T0, 3), "TC": round(TC, 3), "TL": round(TL, 3),
        "Sa_meseta": round(2.5 * Aa * fa * I, 4),
        "fuente": "NSR-10 Tablas A.2.4-3, A.2.4-4, A.2.5-1 y ecs. A.2.6",
    }


def Sa(T: float, esp: dict) -> float:
    if T <= esp["TC"]:
        return esp["Sa_meseta"]
    if T <= esp["TL"]:
        return round(1.2 * esp["Av"] * esp["Fv"] * esp["I"] / T, 4)
    return round(1.2 * esp["Av"] * esp["Fv"] * esp["TL"] * esp["I"] / T ** 2, 4)


def deriva_maxima(sistema: str = "concreto") -> float:
    clave = "mamposteria_A6423" if sistema == "mamposteria" else "concreto_acero_madera_mamposteria_A6422"
    return P.valor(f"nsr10.derivas.{clave}")


def categoria_unidad(niveles: int, carga_columna_kN: float | None = None) -> str:
    """Categoría más desfavorable entre niveles y carga (Tabla H.3.1-1)."""
    orden = ["Baja", "Media", "Alta", "Especial"]
    cats = P.valor("nsr10.geotecnia.categorias_unidad_construccion")

    def por_niveles(n):
        for c in orden:
            if n <= cats[c].get("niveles_max", 10 ** 9):
                return c
        return "Especial"

    def por_carga(q):
        for c in orden:
            if q <= cats[c].get("carga_columna_max_kN", 10 ** 12):
                return c
        return "Especial"

    c1 = por_niveles(niveles)
    if carga_columna_kN is None:
        return c1
    c2 = por_carga(carga_columna_kN)
    return max(c1, c2, key=orden.index)


def sondeos_minimos(categoria: str) -> dict:
    return P.valor("nsr10.geotecnia.sondeos_minimos")[categoria]


def separacion_minima(pisos: int, altura_m: float, condicion: str) -> float:
    """condicion: losas_coinciden | losas_no_coinciden | sin_vecino (Tabla A.6.5-1)."""
    tabla = P.valor("nsr10.separacion_sismica_cubierta")
    fila = "1-2 pisos" if pisos <= 2 else "3 pisos" if pisos == 3 else "mas de 3 pisos"
    return round(tabla[fila][condicion] * altura_m, 3)
