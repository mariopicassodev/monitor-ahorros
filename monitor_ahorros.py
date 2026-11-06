#!/usr/bin/env python3
"""
Monitor de ahorros - Argentina
==============================
Junta en un solo lugar los indicadores para vigilar el riesgo sobre tus ahorros:
  - Dólar oficial, MEP y blue, y la brecha entre ellos      (dolarapi.com)
  - Riesgo país y su variación en 30 días                    (argentinadatos.com)
  - Reservas del BCRA y su tendencia semanal                 (API oficial del BCRA)
  - Depósitos en dólares del sistema, si la API los publica  (API oficial del BCRA)
  - Próximas fechas clave de 2027 con días restantes

Solo usa la biblioteca estándar de Python 3 (no hay que instalar nada).

Uso:
    python3 monitor_ahorros.py            # muestra el reporte
    python3 monitor_ahorros.py --json     # salida en JSON (para otros programas)
    python3 monitor_ahorros.py --out docs # además escribe docs/data.json (lo usa el dashboard)

Guarda cada lectura en "historial_ahorros.csv" (en la misma carpeta del script)
para que puedas ver la evolución en el tiempo.

Código de salida: 0 = todo normal, 1 = hay al menos una alerta, 2 = no se pudo leer
ningún dato. Sirve para programarlo y que te avise solo cuando hace falta.

Esto es información, no asesoramiento financiero.
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# UMBRALES DE ALERTA (podés cambiarlos)
# ---------------------------------------------------------------------------
RIESGO_PAIS_ALERTA = 1000        # puntos básicos: por encima, el mercado duda del pago
RIESGO_PAIS_SUBA_30D = 200       # puntos: suba fuerte en 30 días
BRECHA_ALERTA_PCT = 15.0         # % de brecha MEP o blue vs oficial
RESERVAS_SEMANAS_CAIDA = 3       # semanas seguidas de caída de reservas
DEPOSITOS_CAIDA_30D_PCT = 3.0    # % de caída de depósitos en dólares en 30 días

# ---------------------------------------------------------------------------
# FUENTES
# ---------------------------------------------------------------------------
URL_DOLARES = "https://dolarapi.com/v1/dolares"
URL_RIESGO_ULTIMO = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo"
URL_RIESGO_HISTORICO = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
URL_BCRA_VARIABLES = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias"
URL_BCRA_SERIE = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{id}?desde={desde}&hasta={hasta}"

# ---------------------------------------------------------------------------
# CALENDARIO 2027 (fechas "aprox." no tienen día oficial confirmado)
# ---------------------------------------------------------------------------
CALENDARIO = [
    (date(2027, 1, 9),   False, "Pago a bonistas (Bonares y Globales)"),
    (date(2027, 4, 1),   True,  "Vencimiento BOPREAL (deuda del BCRA) - abril"),
    (date(2027, 4, 18),  False, "PASO provinciales en Santa Fe"),
    (date(2027, 5, 9),   False, "Elecciones provinciales en Tucumán"),
    (date(2027, 6, 13),  False, "Elecciones generales en Santa Fe"),
    (date(2027, 7, 9),   False, "Pago a bonistas - el más grande del año"),
    (date(2027, 8, 15),  True,  "PASO nacionales (si no se suspenden) - agosto"),
    (date(2027, 10, 1),  True,  "Vencimiento BOPREAL - octubre"),
    (date(2027, 10, 24), False, "Elecciones generales (presidente)"),
    (date(2027, 10, 29), False, "Vence el Bonar AO27"),
    (date(2027, 11, 21), False, "Posible balotaje"),
    (date(2027, 12, 10), False, "Cambio o continuidad de gobierno"),
]

HISTORIAL_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historial_ahorros.csv")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def obtener_json(url, timeout=20):
    req = urllib.request.Request(
        url, headers={"User-Agent": "monitor-ahorros/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def a_fecha(texto):
    """Convierte '2026-11-05' o '2026-11-05T15:00:00.000Z' en date."""
    return datetime.strptime(str(texto)[:10], "%Y-%m-%d").date()


def valor_en_fecha(serie, objetivo):
    """Último valor de la serie con fecha <= objetivo. serie: lista de (date, valor) ordenada."""
    candidato = None
    for f, v in serie:
        if f <= objetivo:
            candidato = v
        else:
            break
    return candidato


# ---------------------------------------------------------------------------
# Lectores de cada indicador. Cada uno devuelve un dict y nunca corta el script.
# ---------------------------------------------------------------------------
def leer_dolares():
    datos = obtener_json(URL_DOLARES)
    por_casa = {d.get("casa"): d for d in datos}
    oficial = por_casa.get("oficial", {}).get("venta")
    mep = por_casa.get("bolsa", {}).get("venta")
    blue = por_casa.get("blue", {}).get("venta")
    res = {"oficial": oficial, "mep": mep, "blue": blue}
    if oficial:
        res["brecha_mep_pct"] = round((mep / oficial - 1) * 100, 1) if mep else None
        res["brecha_blue_pct"] = round((blue / oficial - 1) * 100, 1) if blue else None
    return res


def leer_riesgo_pais():
    ultimo = obtener_json(URL_RIESGO_ULTIMO)
    res = {"valor": ultimo.get("valor"), "fecha": ultimo.get("fecha")}
    try:
        hist = obtener_json(URL_RIESGO_HISTORICO, timeout=40)
        serie = sorted((a_fecha(h["fecha"]), h["valor"]) for h in hist if h.get("valor") is not None)
        if serie:
            hoy = serie[-1][0]
            hace_30 = valor_en_fecha(serie, hoy - timedelta(days=30))
            if hace_30 is not None and res["valor"] is not None:
                res["variacion_30d"] = res["valor"] - hace_30
            del_anio = [v for f, v in serie if f.year == hoy.year]
            if del_anio:
                res["minimo_anio"] = min(del_anio)
                res["maximo_anio"] = max(del_anio)
    except Exception as e:  # el histórico es opcional
        res["nota"] = f"sin histórico ({e.__class__.__name__})"
    return res


def buscar_variable_bcra(variables, incluye, excluye=(), unidad=None):
    for v in variables:
        desc = (v.get("descripcion") or "").lower()
        uni = (v.get("unidadExpresion") or "").lower()
        if unidad and unidad.lower() not in uni:
            continue
        if all(p in desc for p in incluye) and not any(p in desc for p in excluye):
            return v
    return None


def serie_bcra(id_var, dias=70):
    hasta = date.today()
    desde = hasta - timedelta(days=dias)
    url = URL_BCRA_SERIE.format(id=id_var, desde=desde.isoformat(), hasta=hasta.isoformat())
    datos = obtener_json(url)
    puntos = []
    for r in datos.get("results", []):
        for d in r.get("detalle", []):
            if d.get("valor") is not None:
                puntos.append((a_fecha(d["fecha"]), float(d["valor"])))
    return sorted(puntos)


def leer_bcra():
    variables = obtener_json(URL_BCRA_VARIABLES).get("results", [])
    res = {}

    # Reservas internacionales
    var_res = buscar_variable_bcra(variables, ["reservas internacionales"])
    if var_res:
        serie = serie_bcra(var_res["idVariable"])
        if serie:
            ult_fecha, ult_valor = serie[-1]
            res["reservas_musd"] = ult_valor
            res["reservas_fecha"] = ult_fecha.isoformat()
            # caídas semanales consecutivas (comparando cada 7 días hacia atrás)
            semanas, caidas = [], 0
            for k in range(0, 6):
                semanas.append(valor_en_fecha(serie, ult_fecha - timedelta(days=7 * k)))
            for k in range(len(semanas) - 1):
                a, b = semanas[k], semanas[k + 1]
                if a is None or b is None or a >= b:
                    break
                caidas += 1
            res["reservas_semanas_cayendo"] = caidas
            hace_7 = semanas[1]
            if hace_7:
                res["reservas_var_7d_musd"] = round(ult_valor - hace_7)
    else:
        res["reservas_nota"] = "no se encontró la variable de reservas en la API"

    # Depósitos en dólares (el nombre exacto puede variar)
    # El BCRA no escribe "dólares" en la descripción: lo indica en la unidad ("En millones de USD").
    var_dep = (
        buscar_variable_bcra(variables, ["depósitos", "sector privado"], unidad="usd")
        or buscar_variable_bcra(variables, ["depósitos"], unidad="usd")
        or buscar_variable_bcra(variables, ["depósitos", "dólares"])
    )
    if var_dep:
        serie = serie_bcra(var_dep["idVariable"], dias=45)
        if serie:
            ult_fecha, ult_valor = serie[-1]
            res["depositos_usd_valor"] = ult_valor
            res["depositos_usd_desc"] = var_dep.get("descripcion")
            hace_30 = valor_en_fecha(serie, ult_fecha - timedelta(days=30))
            if hace_30:
                res["depositos_usd_var_30d_pct"] = round((ult_valor / hace_30 - 1) * 100, 2)
    else:
        res["depositos_nota"] = ("la API no publica depósitos en dólares; "
                                 "miralo en el Informe sobre Bancos del BCRA (mensual)")
    return res


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------
def evaluar_alertas(d):
    alertas = []
    rp = d.get("riesgo_pais") or {}
    if rp.get("valor") is not None and rp["valor"] >= RIESGO_PAIS_ALERTA:
        alertas.append(f"Riesgo país en {rp['valor']} pb (umbral {RIESGO_PAIS_ALERTA})")
    if rp.get("variacion_30d") is not None and rp["variacion_30d"] >= RIESGO_PAIS_SUBA_30D:
        alertas.append(f"Riesgo país subió {rp['variacion_30d']} pb en 30 días")

    dol = d.get("dolares") or {}
    for clave, nombre in (("brecha_mep_pct", "MEP"), ("brecha_blue_pct", "blue")):
        b = dol.get(clave)
        if b is not None and b >= BRECHA_ALERTA_PCT:
            alertas.append(f"Brecha {nombre} vs oficial: {b}% (umbral {BRECHA_ALERTA_PCT}%)")

    bc = d.get("bcra") or {}
    if bc.get("reservas_semanas_cayendo", 0) >= RESERVAS_SEMANAS_CAIDA:
        alertas.append(f"Reservas cayendo {bc['reservas_semanas_cayendo']} semanas seguidas "
                       "(revisá si coincide con un pago de deuda)")
    dep = bc.get("depositos_usd_var_30d_pct")
    if dep is not None and dep <= -DEPOSITOS_CAIDA_30D_PCT:
        alertas.append(f"Depósitos en dólares cayeron {abs(dep)}% en 30 días")
    return alertas


def proximas_fechas(hoy, cantidad=4):
    futuras = [(f, aprox, txt) for f, aprox, txt in CALENDARIO if f >= hoy]
    if cantidad is None:
        cantidad = len(futuras)
    return [
        {"fecha": f.isoformat(), "aprox": aprox, "evento": txt, "dias": (f - hoy).days}
        for f, aprox, txt in futuras[:cantidad]
    ]


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
def fmt(n, dec=0, suf=""):
    if n is None:
        return "s/d"
    s = f"{n:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + suf


def imprimir_reporte(d):
    usar_color = sys.stdout.isatty() and os.name != "nt"
    rojo = "\033[91m" if usar_color else ""
    verde = "\033[92m" if usar_color else ""
    neg = "\033[1m" if usar_color else ""
    fin = "\033[0m" if usar_color else ""

    print(f"\n{neg}MONITOR DE AHORROS - {d['fecha_consulta']}{fin}")
    print("=" * 52)

    dol = d.get("dolares")
    print(f"\n{neg}Dólar{fin}")
    if dol:
        print(f"  Oficial (BNA) .... ${fmt(dol.get('oficial'))}")
        print(f"  MEP .............. ${fmt(dol.get('mep'))}   brecha {fmt(dol.get('brecha_mep_pct'), 1, '%')}")
        print(f"  Blue ............. ${fmt(dol.get('blue'))}   brecha {fmt(dol.get('brecha_blue_pct'), 1, '%')}")
    else:
        print(f"  No disponible: {d['errores'].get('dolares')}")

    rp = d.get("riesgo_pais")
    print(f"\n{neg}Riesgo país{fin}")
    if rp:
        print(f"  Último ........... {fmt(rp.get('valor'))} pb  ({rp.get('fecha', 's/d')})")
        if rp.get("variacion_30d") is not None:
            signo = "+" if rp["variacion_30d"] > 0 else ""
            print(f"  Variación 30 días  {signo}{fmt(rp['variacion_30d'])} pb")
        if rp.get("minimo_anio") is not None:
            print(f"  Rango del año .... {fmt(rp['minimo_anio'])} a {fmt(rp['maximo_anio'])} pb")
    else:
        print(f"  No disponible: {d['errores'].get('riesgo_pais')}")

    bc = d.get("bcra")
    print(f"\n{neg}BCRA{fin}")
    if bc:
        if "reservas_musd" in bc:
            v7 = bc.get("reservas_var_7d_musd")
            v7s = f"{'+' if v7 and v7 > 0 else ''}{fmt(v7)}" if v7 is not None else "s/d"
            print(f"  Reservas brutas .. US$ {fmt(bc['reservas_musd'])} M ({bc['reservas_fecha']})")
            print(f"  Cambio 7 días .... US$ {v7s} M")
            print(f"  Semanas cayendo .. {bc.get('reservas_semanas_cayendo', 0)}")
        else:
            print(f"  Reservas: {bc.get('reservas_nota')}")
        if "depositos_usd_valor" in bc:
            print(f"  Depósitos US$ .... {fmt(bc['depositos_usd_valor'])} "
                  f"(30 días: {fmt(bc.get('depositos_usd_var_30d_pct'), 2, '%')})")
            print(f"                     [{bc['depositos_usd_desc']}]")
        else:
            print(f"  Depósitos US$: {bc.get('depositos_nota')}")
    else:
        print(f"  No disponible: {d['errores'].get('bcra')}")

    print(f"\n{neg}Próximas fechas clave{fin}")
    for ev in d["proximas_fechas"]:
        aprox = " (aprox.)" if ev["aprox"] else ""
        print(f"  {ev['fecha']}{aprox}  en {ev['dias']} días: {ev['evento']}")

    print()
    if all(d.get(k) is None for k in ("dolares", "riesgo_pais", "bcra")):
        print(f"{rojo}{neg}No se pudo leer ningún indicador. Revisá tu conexión a internet.{fin}")
    elif d["alertas"]:
        print(f"{rojo}{neg}ALERTAS:{fin}")
        for a in d["alertas"]:
            print(f"{rojo}  ! {a}{fin}")
    else:
        print(f"{verde}Sin alertas: ningún indicador cruzó los umbrales.{fin}")
    print("\nInformación, no asesoramiento financiero.\n")


def guardar_historial(d):
    fila = {
        "fecha": d["fecha_consulta"],
        "oficial": (d.get("dolares") or {}).get("oficial"),
        "mep": (d.get("dolares") or {}).get("mep"),
        "blue": (d.get("dolares") or {}).get("blue"),
        "brecha_mep_pct": (d.get("dolares") or {}).get("brecha_mep_pct"),
        "riesgo_pais": (d.get("riesgo_pais") or {}).get("valor"),
        "reservas_musd": (d.get("bcra") or {}).get("reservas_musd"),
        "depositos_usd": (d.get("bcra") or {}).get("depositos_usd_valor"),
        "alertas": " | ".join(d["alertas"]),
    }
    nuevo = not os.path.exists(HISTORIAL_CSV)
    try:
        with open(HISTORIAL_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(fila.keys()))
            if nuevo:
                w.writeheader()
            w.writerow(fila)
    except OSError:
        pass  # si no se puede escribir, el reporte igual se muestra


def main():
    d = {"fecha_consulta": datetime.now().strftime("%Y-%m-%d %H:%M"), "errores": {}}
    for clave, lector in (("dolares", leer_dolares),
                          ("riesgo_pais", leer_riesgo_pais),
                          ("bcra", leer_bcra)):
        try:
            d[clave] = lector()
        except Exception as e:
            d[clave] = None
            d["errores"][clave] = f"{e.__class__.__name__}: {e}"

    d["alertas"] = evaluar_alertas(d)
    d["proximas_fechas"] = proximas_fechas(date.today())

    if "--out" in sys.argv:
        # Para el dashboard: escribe <carpeta>/data.json con todo lo que necesita la página.
        carpeta = sys.argv[sys.argv.index("--out") + 1]
        os.makedirs(carpeta, exist_ok=True)
        d["generado_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        d["umbrales"] = {
            "riesgo_pais": RIESGO_PAIS_ALERTA,
            "riesgo_pais_suba_30d": RIESGO_PAIS_SUBA_30D,
            "brecha_pct": BRECHA_ALERTA_PCT,
            "reservas_semanas": RESERVAS_SEMANAS_CAIDA,
            "depositos_caida_30d_pct": DEPOSITOS_CAIDA_30D_PCT,
        }
        d["calendario"] = proximas_fechas(date.today(), None)
        with open(os.path.join(carpeta, "data.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2, default=str)

    if "--json" in sys.argv:
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
    else:
        imprimir_reporte(d)

    if all(d.get(k) is None for k in ("dolares", "riesgo_pais", "bcra")):
        sys.exit(2)
    guardar_historial(d)
    sys.exit(1 if d["alertas"] else 0)


if __name__ == "__main__":
    main()
