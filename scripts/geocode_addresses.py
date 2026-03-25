"""
geocode_addresses.py
Geocodifica os endereços de entrega de 2026 via Nominatim (OpenStreetMap).
- Cacheia resultados em data/geocache.json (não regeocodifica endereços já conhecidos)
- Gera dist/data/routes.json com pedidos agrupados por dia, ordenados por número de pedido
"""

import json
import os
import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID   = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME = "Encomendas"
CSV_URL    = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

CITY_SUFFIX    = ", Dores do Indaiá, Minas Gerais, Brasil"
ORIGIN_ADDRESS = "Rua Espírito Santo 811, Dores do Indaiá, Minas Gerais, Brasil"
NOMINATIM_URL  = "https://nominatim.openstreetmap.org/search"
USER_AGENT     = "pascoa-dashboard/1.0 (luishenriquescarvalho@gmail.com)"
RATE_LIMIT_S   = 1.1  # Nominatim exige >= 1s entre requisições

OUT_DIR      = os.path.join("dist", "data")
CACHE_PATH   = os.path.join("data", "geocache.json")
ROUTES_PATH  = os.path.join(OUT_DIR, "routes.json")

DAY_ORDER   = ["qua", "qui", "sex", "sab", "dom", "seg"]
TURNO_ORDER = ["Manhã", "Tarde", "Noite"]

RETIRADA_RE   = re.compile(r"retirada|retira|pickup|buscar", re.IGNORECASE)
INCOMPLETO_RE = re.compile(
    r"^(vai informar|entrega,|a confirmar|sem endereço)",
    re.IGNORECASE,
)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def day_sort_key(s: str) -> int:
    prefix = str(s).split()[0].lower() if s else ""
    try:
        return DAY_ORDER.index(prefix)
    except ValueError:
        return 99


def route_sort_key(key: str) -> tuple:
    parts = key.split(" · ")
    dia   = parts[0] if parts else key
    turno = parts[1] if len(parts) > 1 else ""
    t_idx = TURNO_ORDER.index(turno) if turno in TURNO_ORDER else 99
    return (day_sort_key(dia), t_idx)


def pedido_sort_key(pedido: dict) -> int:
    """Ordena paradas pelo menor número de pedido dentre as ordens do grupo."""
    nums = []
    for o in pedido.get("ordens", []):
        try:
            nums.append(int(o["pedido"]))
        except (ValueError, KeyError):
            pass
    return min(nums) if nums else 99999


def is_retirada(addr: str) -> bool:
    return bool(RETIRADA_RE.search(addr)) or not addr.strip()


def is_incompleto(addr: str) -> bool:
    return bool(INCOMPLETO_RE.search(addr.strip()))


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def clean_for_geocoding(address: str) -> str:
    cleaned = re.sub(
        r"^[^,]+?\s+((?:Rua|R\.|Beco|Av\.?|Avenida|Travessa|Alameda)\b)",
        r"\1",
        address,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*[\(\[].+?[\)\]]", "", cleaned)
    cleaned = re.sub(r",?\s*(perto|próximo|ao lado|em frente).+$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(",")


def parse_faltante(val) -> float:
    try:
        return float(str(val).replace("R$", "").replace(" ", "").replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def geocode(address: str, cache: dict) -> dict | None:
    if address in cache:
        return cache[address]

    queries = [address]
    cleaned = clean_for_geocoding(address)
    if cleaned != address:
        queries.append(cleaned)

    result = None
    for query in queries:
        query_full = query + CITY_SUFFIX
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": query_full, "format": "json", "limit": 1, "addressdetails": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            api_results = resp.json()
        except Exception as e:
            print(f"  ERRO na requisicao: {e}")
            time.sleep(RATE_LIMIT_S)
            continue
        time.sleep(RATE_LIMIT_S)

        if api_results:
            r = api_results[0]
            result = {
                "lat":        float(r["lat"]),
                "lon":        float(r["lon"]),
                "display":    r.get("display_name", ""),
                "query_used": query,
            }
            break

    cache[address] = result
    return result


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Baixando planilha 2026...")
    df = pd.read_csv(CSV_URL)
    df.columns = [c.strip() for c in df.columns]

    df["_endereco"] = df["Endereço"].fillna("").astype(str).str.strip()
    df["_dia"]      = df["Dia Entrega"].fillna("").astype(str).str.strip()
    df["_turno"]    = df["Turno"].fillna("").astype(str).str.strip()
    df["_nome"]     = df["Nome"].fillna("").astype(str).str.strip()

    df_entregas = df[
        ~df["_endereco"].apply(is_retirada) &
        ~df["_endereco"].apply(is_incompleto) &
        (df["_endereco"] != "") &
        (df["_dia"] != "")
    ].copy()

    df_entregas["_chave"] = df_entregas.apply(
        lambda r: f"{r['_dia']} · {r['_turno']}" if r["_turno"] else r["_dia"],
        axis=1,
    )

    enderecos_unicos = df_entregas["_endereco"].unique().tolist()
    print(f"{len(enderecos_unicos)} endereços únicos para geocodificar\n")

    # ── Geocodificação ────────────────────────────────────────────────────────
    cache = load_cache()
    novos = 0

    ORIGIN_KEY = "__origin__"
    if ORIGIN_KEY not in cache:
        print(f"  [req]    ORIGEM: {ORIGIN_ADDRESS} ... ", end="", flush=True)
        origin_result = geocode(ORIGIN_ADDRESS, {})
        if origin_result:
            cache[ORIGIN_KEY] = origin_result
            print(f"({origin_result['lat']:.5f}, {origin_result['lon']:.5f})")
        else:
            cache[ORIGIN_KEY] = {"lat": -19.4614, "lon": -45.6008, "display": ORIGIN_ADDRESS, "query_used": "fallback"}
            print("fallback usado")
        novos += 1

    origin_coord = cache[ORIGIN_KEY]

    for addr in enderecos_unicos:
        if addr in cache:
            print(f"  [cache]  {addr}")
            continue
        print(f"  [req]    {addr} ... ", end="", flush=True)
        result = geocode(addr, cache)
        if result:
            print(f"({result['lat']:.5f}, {result['lon']:.5f})")
        else:
            print("SEM RESULTADO")
        novos += 1

    if novos:
        save_cache(cache)
        print(f"\nCache atualizado: {novos} novo(s) -> {CACHE_PATH}")
    else:
        print("\nNenhuma requisicao nova (tudo em cache).")

    # ── Monta routes.json ─────────────────────────────────────────────────────
    chaves = sorted(df_entregas["_chave"].unique().tolist(), key=route_sort_key)
    routes: dict = {}

    for chave in chaves:
        sub = df_entregas[df_entregas["_chave"] == chave]

        # Agrupa por endereço
        grupos: dict = {}
        for _, row in sub.iterrows():
            addr         = row["_endereco"]
            coord        = cache.get(addr)
            pedido_num   = row.get("Pedido", "")
            faltante_raw = str(row.get("Faltante", "") or "").strip()
            faltante_num = parse_faltante(faltante_raw)
            ordem = {
                "pedido":       str(int(pedido_num)) if str(pedido_num).replace(".0", "").isdigit() else str(pedido_num or ""),
                "nome":         row["_nome"],
                "recheio":      str(row.get("Recheio", "") or ""),
                "tipo":         str(row.get("Tipo", "") or ""),
                "obs":          str(row.get("Observação", "") or ""),
                "faltante":     faltante_raw if faltante_raw and faltante_raw != "nan" else "R$ 0,00",
                "faltante_num": faltante_num,
            }
            if addr not in grupos:
                grupos[addr] = {
                    "endereco": addr,
                    "lat":      coord["lat"] if coord else None,
                    "lon":      coord["lon"] if coord else None,
                    "geocoded": coord is not None,
                    "ordens":   [],
                }
            grupos[addr]["ordens"].append(ordem)

        # Mescla coordenadas idênticas
        coord_map: dict = {}
        no_coord_list: list = []
        for entry in grupos.values():
            if entry["geocoded"]:
                key = (entry["lat"], entry["lon"])
                if key in coord_map:
                    coord_map[key]["ordens"].extend(entry["ordens"])
                    if entry["endereco"] not in coord_map[key]["endereco"]:
                        coord_map[key]["endereco"] += f" / {entry['endereco']}"
                else:
                    coord_map[key] = entry
            else:
                no_coord_list.append(entry)

        pedidos = list(coord_map.values()) + no_coord_list

        # Calcula total a receber por parada
        for p in pedidos:
            p["faltante_parada"] = round(sum(o.get("faltante_num", 0) for o in p["ordens"]), 2)

        # Ordena por número de pedido
        pedidos.sort(key=pedido_sort_key)

        ok     = sum(1 for p in pedidos if p["geocoded"])
        falhou = sum(1 for p in pedidos if not p["geocoded"])
        total_ordens   = sum(len(p["ordens"]) for p in pedidos)
        faltante_total = round(sum(p.get("faltante_parada", 0) for p in pedidos), 2)

        routes[chave] = {
            "origin":          {"lat": origin_coord["lat"], "lon": origin_coord["lon"], "endereco": ORIGIN_ADDRESS},
            "pedidos":         pedidos,
            "total_paradas":   len(pedidos),
            "total_ordens":    total_ordens,
            "geocoded_ok":     ok,
            "geocoded_falhou": falhou,
            "faltante_total":  faltante_total,
        }

        status = f"{ok} OK" + (f", {falhou} sem coord" if falhou else "")
        print(f"  {chave:<28} {len(pedidos)} entrega(s) ({status})")

    # ── Salva ─────────────────────────────────────────────────────────────────
    output = {
        "last_updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "routes": routes,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(ROUTES_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_ok = sum(r["geocoded_ok"] for r in routes.values())
    print(f"  last_updated_utc: {output['last_updated_utc']}")
    print(f"\nroutes.json salvo: {total_ok} pontos geocodificados -> {ROUTES_PATH}")


if __name__ == "__main__":
    main()
