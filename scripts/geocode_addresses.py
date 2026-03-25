"""
geocode_addresses.py
Geocodifica os endereços de entrega de 2026 via Nominatim (OpenStreetMap).
- Cacheia resultados em dist/data/geocache.json (não regeocodifica endereços já conhecidos)
- Gera dist/data/routes.json com pedidos agrupados por dia + coordenadas
"""

import json
import math
import os
import re
import time

import pandas as pd
import requests

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID   = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME = "Encomendas"
CSV_URL    = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

# Nominatim: adiciona cidade para melhorar precisão
CITY_SUFFIX  = ", Dores do Indaiá, Minas Gerais, Brasil"
ORIGIN_ADDRESS = "Rua Espírito Santo 811, Dores do Indaiá, Minas Gerais, Brasil"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Obrigatório: identificar a aplicação no User-Agent
USER_AGENT   = "pascoa-dashboard/1.0 (luishenriquescarvalho@gmail.com)"
RATE_LIMIT_S = 1.1   # Nominatim exige >= 1s entre requisições

OUT_DIR      = os.path.join("dist", "data")
CACHE_PATH   = os.path.join("data", "geocache.json")
ROUTES_PATH  = os.path.join(OUT_DIR, "routes.json")

DAY_ORDER    = ["qua", "qui", "sex", "sab", "dom", "seg"]
TURNO_ORDER  = ["Manhã", "Tarde", "Noite"]

RETIRADA_RE  = re.compile(r"retirada|retira|pickup|buscar", re.IGNORECASE)
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
    """Ordena chaves 'Dia · Turno' por dia e depois por turno."""
    parts = key.split(" · ")
    dia   = parts[0] if parts else key
    turno = parts[1] if len(parts) > 1 else ""
    t_idx = TURNO_ORDER.index(turno) if turno in TURNO_ORDER else 99
    return (day_sort_key(dia), t_idx)


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
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def clean_for_geocoding(address: str) -> str:
    """Remove prefixos de estabelecimento e sufixos descritivos."""
    # Remove texto antes de "Rua|Beco|Avenida|..." se houver prefixo de nome
    cleaned = re.sub(
        r"^[^,]+?\s+((?:Rua|R\.|Beco|Av\.?|Avenida|Travessa|Alameda)\b)",
        r"\1",
        address,
        flags=re.IGNORECASE,
    )
    # Remove sufixos como "(fundo)", "perto de...", "ao lado de..."
    cleaned = re.sub(r"\s*[\(\[].+?[\)\]]", "", cleaned)
    cleaned = re.sub(r",?\s*(perto|próximo|ao lado|em frente).+$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(",")


def geocode(address: str, cache: dict) -> dict | None:
    """Retorna {'lat': float, 'lon': float, 'display': str} ou None."""
    if address in cache:
        return cache[address]

    # Tenta o endereço original; se falhar, tenta versão limpa
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
                "lat":     float(r["lat"]),
                "lon":     float(r["lon"]),
                "display": r.get("display_name", ""),
                "query_used": query,
            }
            break

    cache[address] = result
    return result


# ── OTIMIZAÇÃO DE ROTA ────────────────────────────────────────────────────────

OSRM_TABLE_URL = "https://routing.openstreetmap.de/routed-foot/table/v1/driving/{coords}?annotations=distance"
OSRM_RATE_S    = 0.5


def haversine(a: dict, b: dict) -> float:
    """Distância em km entre dois pontos {lat, lon}."""
    R = 6371.0
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(h))


def osrm_distance_matrix(points: list) -> list | None:
    """
    Chama OSRM Table API e retorna matriz de distâncias em km.
    points: lista de dicts {'lat', 'lon'} — origem no índice 0.
    Retorna None se falhar.
    """
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in points)
    url = OSRM_TABLE_URL.format(coords=coords)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            print(f"  OSRM Table: code={data.get('code')}")
            return None
        return [[d / 1000.0 for d in row] for row in data["distances"]]
    except Exception as e:
        print(f"  OSRM Table falhou: {e}")
        return None


def _total_dist_matrix(order: list, matrix: list) -> float:
    """Distância total (com retorno à origem=0) usando matriz."""
    full = [0] + order + [0]
    return sum(matrix[full[i]][full[i + 1]] for i in range(len(full) - 1))


def _nn_from(start: int, n: int, matrix: list) -> list:
    """Nearest neighbor partindo de `start`. Retorna índices dos stops (1..n-1)."""
    unvisited = list(range(1, n))
    if start != 0:
        unvisited.remove(start)
    route, current = ([] if start == 0 else [start]), start
    while unvisited:
        nxt = min(unvisited, key=lambda i: matrix[current][i])
        route.append(nxt)
        current = nxt
        unvisited.remove(nxt)
    return route


def _two_opt_matrix(order: list, matrix: list) -> list:
    best, improved = order[:], True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 2, len(best)):
                candidate = best[:i + 1] + best[i + 1:j + 1][::-1] + best[j + 1:]
                if _total_dist_matrix(candidate, matrix) < _total_dist_matrix(best, matrix):
                    best, improved = candidate, True
    return best


def _or_opt_matrix(order: list, matrix: list) -> list:
    """Tenta reposicionar cada nó na posição mais vantajosa (elimina desvios)."""
    best, improved = order[:], True
    while improved:
        improved = False
        for i in range(len(best)):
            node = best[i]
            rest = best[:i] + best[i + 1:]
            for j in range(len(rest) + 1):
                candidate = rest[:j] + [node] + rest[j:]
                if _total_dist_matrix(candidate, matrix) < _total_dist_matrix(best, matrix):
                    best, improved = candidate, True
                    break
            if improved:
                break
    return best


def _best_nn_matrix(n: int, matrix: list) -> list:
    """Testa NN a partir de todos os pontos e retorna o melhor resultado após 2-opt + Or-opt."""
    best_order, best_dist = None, float("inf")
    for start in range(n):
        order = _nn_from(start, n, matrix)
        order = _two_opt_matrix(order, matrix)
        order = _or_opt_matrix(order, matrix)
        d = _total_dist_matrix(order, matrix)
        if d < best_dist:
            best_dist, best_order = d, order
    return best_order


def _nearest_neighbor_haversine(points: list, origin: dict) -> list:
    unvisited = list(range(len(points)))
    route, current = [], origin
    while unvisited:
        nearest = min(unvisited, key=lambda i: haversine(current, points[i]))
        route.append(nearest)
        current = points[nearest]
        unvisited.remove(nearest)
    return route


def _two_opt_haversine(points: list, order: list) -> list:
    def total(o):
        return sum(haversine(points[o[i]], points[o[i + 1]]) for i in range(len(o) - 1))
    best, improved = order[:], True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 2, len(best)):
                candidate = best[:i + 1] + best[i + 1:j + 1][::-1] + best[j + 1:]
                if total(candidate) < total(best):
                    best, improved = candidate, True
    return best


def optimize_route(origin: dict, pedidos: list) -> tuple[list, float, str]:
    """
    Retorna (pedidos_otimizados, dist_km_total, route_type).
    route_type = "loop"  → rota circular (origin→...→origin)
    route_type = "star"  → ida-e-volta por parada (origin→s1→origin→s2→origin)
    Usa OSRM Table para distâncias reais; fallback para Haversine.
    """
    with_coord = [p for p in pedidos if p["geocoded"]]
    without    = [p for p in pedidos if not p["geocoded"]]

    if len(with_coord) == 0:
        return without, 0.0, "loop"
    if len(with_coord) == 1:
        p = with_coord[0]
        d = 2 * haversine(origin, {"lat": p["lat"], "lon": p["lon"]})
        return with_coord + without, round(d, 2), "loop"

    all_points = [origin] + [{"lat": p["lat"], "lon": p["lon"]} for p in with_coord]
    matrix = osrm_distance_matrix(all_points)
    time.sleep(OSRM_RATE_S)

    if matrix:
        n = len(all_points)

        # Opção A: loop otimizado
        loop_order = _best_nn_matrix(n, matrix)
        loop_dist  = _total_dist_matrix(loop_order, matrix)

        # Opção B: star (ida-e-volta independente por parada)
        star_dist  = sum(matrix[0][i] + matrix[i][0] for i in range(1, n))
        star_order = sorted(range(1, n), key=lambda i: matrix[0][i])  # mais próximo primeiro

        if star_dist < loop_dist:
            optimized = [with_coord[i - 1] for i in star_order]
            dist = round(star_dist, 2)
            route_type = "star"
            print(f"    [OSRM star]   distância real: {dist:.1f} km  (loop seria {loop_dist:.1f} km)")
        else:
            # Rotaciona o tour para começar pela parada mais próxima da origem
            closest = min(range(len(loop_order)), key=lambda i: matrix[0][loop_order[i]])
            loop_order = loop_order[closest:] + loop_order[:closest]
            optimized = [with_coord[i - 1] for i in loop_order]
            dist = round(loop_dist, 2)
            route_type = "loop"
            print(f"    [OSRM loop]   distância real: {dist:.1f} km  (star seria {star_dist:.1f} km)")
    else:
        points = [{"lat": p["lat"], "lon": p["lon"]} for p in with_coord]
        order  = _nearest_neighbor_haversine(points, origin)
        order  = _two_opt_haversine(points, order)
        optimized = [with_coord[i] for i in order]
        pts = [{"lat": p["lat"], "lon": p["lon"]} for p in optimized]
        dist = round(
            haversine(origin, pts[0]) +
            sum(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) +
            haversine(pts[-1], origin),
            2,
        )
        route_type = "loop"
        print(f"    [Haversine fallback] distância estimada: {dist:.1f} km")

    return optimized + without, dist, route_type


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Baixando planilha 2026...")
    df = pd.read_csv(CSV_URL)
    df.columns = [c.strip() for c in df.columns]

    df["_endereco"] = df["Endereço"].fillna("").astype(str).str.strip()
    df["_dia"]      = df["Dia Entrega"].fillna("").astype(str).str.strip()
    df["_turno"]    = df["Turno"].fillna("").astype(str).str.strip()
    df["_nome"]     = df["Nome"].fillna("").astype(str).str.strip()

    # Filtra apenas entregas com endereço utilizável e dia preenchido
    df_entregas = df[
        ~df["_endereco"].apply(is_retirada) &
        ~df["_endereco"].apply(is_incompleto) &
        (df["_endereco"] != "") &
        (df["_dia"] != "")
    ].copy()

    # Chave: "Dia · Turno"
    df_entregas["_chave"] = df_entregas.apply(
        lambda r: f"{r['_dia']} · {r['_turno']}" if r["_turno"] else r["_dia"],
        axis=1,
    )

    enderecos_unicos = df_entregas["_endereco"].unique().tolist()
    print(f"{len(enderecos_unicos)} endereços únicos para geocodificar\n")

    # ── Geocodificação ────────────────────────────────────────────────────────
    cache = load_cache()

    novos = 0

    # Geocodifica também a origem
    ORIGIN_KEY = "__origin__"
    if ORIGIN_KEY not in cache:
        print(f"  [req]    ORIGEM: {ORIGIN_ADDRESS} ... ", end="", flush=True)
        origin_result = geocode(ORIGIN_ADDRESS, {})
        if origin_result:
            cache[ORIGIN_KEY] = origin_result
            print(f"({origin_result['lat']:.5f}, {origin_result['lon']:.5f})")
        else:
            # Fallback manual aproximado do centro de Dores do Indaiá
            cache[ORIGIN_KEY] = {"lat": -19.4614, "lon": -45.6008, "display": ORIGIN_ADDRESS, "query_used": "fallback"}
            print("fallback usado")
        novos += 1

    origin_coord = cache[ORIGIN_KEY]

    for addr in enderecos_unicos:
        if addr in cache:
            status = "cache" if cache[addr] else "falhou (cache)"
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
    chaves = sorted(
        df_entregas["_chave"].unique().tolist(),
        key=route_sort_key,
    )

    routes: dict = {}

    for chave in chaves:
        sub = df_entregas[df_entregas["_chave"] == chave]

        # Agrupa por endereço — múltiplas entregas no mesmo local = 1 ponto
        grupos: dict = {}
        for _, row in sub.iterrows():
            addr  = row["_endereco"]
            coord = cache.get(addr)
            pedido_num = row.get("Pedido", "")
            ordem = {
                "pedido":  str(int(pedido_num)) if str(pedido_num).replace(".0","").isdigit() else str(pedido_num or ""),
                "nome":    row["_nome"],
                "recheio": str(row.get("Recheio", "") or ""),
                "tipo":    str(row.get("Tipo", "") or ""),
                "obs":     str(row.get("Observação", "") or ""),
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

        pedidos = list(grupos.values())

        ok     = sum(1 for p in pedidos if p["geocoded"])
        falhou = sum(1 for p in pedidos if not p["geocoded"])

        # Otimiza a rota (retorna pedidos + distância + tipo de rota)
        pedidos_otimizados, dist_total, route_type = optimize_route(origin_coord, pedidos)

        total_ordens = sum(len(p["ordens"]) for p in pedidos_otimizados)

        routes[chave] = {
            "origin":          {"lat": origin_coord["lat"], "lon": origin_coord["lon"], "endereco": ORIGIN_ADDRESS},
            "pedidos":         pedidos_otimizados,
            "total_paradas":   len(pedidos),
            "total_ordens":    total_ordens,
            "geocoded_ok":     ok,
            "geocoded_falhou": falhou,
            "dist_km_est":     round(dist_total, 2),
            "route_type":      route_type,
        }

        status = f"{ok} OK, {dist_total:.1f} km (ida+volta)" + (f", {falhou} sem coord" if falhou else "")
        print(f"  {chave:<28} {len(pedidos)} entrega(s) ({status})")

    # ── Salva ─────────────────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(ROUTES_PATH, "w", encoding="utf-8") as f:
        json.dump(routes, f, ensure_ascii=False, indent=2)

    total_ok = sum(r["geocoded_ok"] for r in routes.values())
    print(f"\nroutes.json salvo: {total_ok} pontos geocodificados -> {ROUTES_PATH}")


if __name__ == "__main__":
    main()
