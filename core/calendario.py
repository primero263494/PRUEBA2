"""Días hábiles en Colombia (festivos de la Ley 51 de 1983, 'Ley Emiliani',
y los que dependen de la Pascua). Sirve para el término de 45 días hábiles
del Decreto 1077 de 2015, art. 2.2.6.1.2.3.1."""
from datetime import date, timedelta
from functools import lru_cache


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo de Gauss/Meeus)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _lunes_siguiente(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=64)
def festivos(anio: int) -> frozenset:
    fijos = [date(anio, 1, 1), date(anio, 5, 1), date(anio, 7, 20), date(anio, 8, 7),
             date(anio, 12, 8), date(anio, 12, 25)]
    trasladables = [date(anio, 1, 6), date(anio, 3, 19), date(anio, 6, 29), date(anio, 8, 15),
                    date(anio, 10, 12), date(anio, 11, 1), date(anio, 11, 11)]
    p = _pascua(anio)
    pascuales = [p - timedelta(days=3), p - timedelta(days=2)]           # jueves y viernes santo
    pascuales_lunes = [p + timedelta(days=43), p + timedelta(days=64), p + timedelta(days=71)]  # Ascensión, Corpus, Sagrado Corazón
    return frozenset(fijos + [_lunes_siguiente(d) for d in trasladables] + pascuales + pascuales_lunes)


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in festivos(d.year)


def sumar_dias_habiles(inicio: date, dias: int) -> date:
    """Fecha en que vence un término de `dias` hábiles contados desde el día siguiente a `inicio`."""
    d, n = inicio, 0
    while n < dias:
        d += timedelta(days=1)
        if es_habil(d):
            n += 1
    return d


def dias_habiles_entre(inicio: date, fin: date) -> int:
    if fin <= inicio:
        return 0
    return sum(1 for i in range(1, (fin - inicio).days + 1) if es_habil(inicio + timedelta(days=i)))


def sumar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    import calendar
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))
