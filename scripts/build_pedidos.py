"""
build_pedidos.py
Gera dist/data/pedidos.json com a lista completa de pedidos por dia.
Hierarquia: cidade → período → tipo (Entrega / Retirada)
"""

import json
import math
import os
import re
from datetime import datetime, timezone

import pandas as pd

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID   = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME = "Encomendas"
CSV_URL    = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

DAY_ORDER    = ["qua", "qui", "sex", "sab", "dom", "seg"]
TURNO_ORDER  = ["Manhã", "Tarde", "Noite"]
CIDADE_ORDER = ["Dores", "Divinópolis"]

RETIRADA_RE = re.compile(r"retirada|retira|pickup|buscar", re.IGNORECASE)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def json_sanitize(x):
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    if isinstance(x, dict):
        return {str(k): json_sanitize(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_sanitize(v) for v in x]
    if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        return None
    return x


def day_sort_key(s: str) -> int:
    prefix = str(s).split()[0].lower() if s else ""
    try:
        return DAY_ORDER.index(prefix)
    except ValueError:
        return 99


def turno_sort_key(t: str) -> int:
    try:
        return TURNO_ORDER.index(t)
    except ValueError:
        return 99


def cidade_sort_key(c: str) -> int:
    try:
        return CIDADE_ORDER.index(c)
    except ValueError:
        return 99


def is_retirada(endereco: str) -> bool:
    return bool(RETIRADA_RE.search(endereco)) or not endereco.strip()


def normalize_cidade(cidade: str) -> str:
    """Normaliza o valor da coluna Cidade para o nome canônico."""
    c = str(cidade).strip()
    if re.search(r"divin", c, re.IGNORECASE):
        return "Divinópolis"
    return "Dores"


def parse_pedido_num(s) -> int:
    try:
        clean = re.sub(r"[^\d]", "", str(s))
        return int(clean) if clean else 99999
    except (ValueError, TypeError):
        return 99999


def safe_str(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s


def sort_pedidos(pedidos: list) -> list:
    """Ordena por (menor pedido do grupo por nome, pedido individual).
    Pedidos do mesmo nome ficam agrupados e a posição do grupo é definida
    pelo menor número de pedido daquela pessoa.
    """
    nome_min: dict = {}
    for p in pedidos:
        nome = safe_str(p.get("nome")) or "__sem_nome__"
        num  = parse_pedido_num(p.get("pedido"))
        if nome not in nome_min or num < nome_min[nome]:
            nome_min[nome] = num

    return sorted(
        pedidos,
        key=lambda p: (
            nome_min.get(safe_str(p.get("nome")) or "__sem_nome__", 99999),
            parse_pedido_num(p.get("pedido")),
        ),
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    df = pd.read_csv(CSV_URL)
    df.columns = [c.strip() for c in df.columns]

    # Filtra linhas sem nome
    df["_nome"] = df["Nome"].fillna("").astype(str).str.strip()
    df = df[df["_nome"] != ""].copy()

    # Normaliza dia e turno
    df["_dia"]   = df["Dia Entrega"].fillna("").astype(str).str.strip()
    df["_turno"] = df["Turno"].fillna("").astype(str).str.strip()
    df = df[df["_dia"] != ""].copy()

    available_days = sorted(df["_dia"].unique().tolist(), key=day_sort_key)

    days_data: dict = {}

    for dia in available_days:
        df_dia = df[df["_dia"] == dia]

        # Estrutura: cidade → turno → tipo_entrega → [pedidos]
        cidades_data: dict = {}

        for _, row in df_dia.iterrows():
            endereco = safe_str(row.get("Endereço", ""))
            ret      = is_retirada(endereco)
            cidade   = normalize_cidade(row.get("Cidade", ""))  # coluna Cidade da planilha
            turno    = safe_str(row.get("Turno", "")) or "Sem turno"
            tipo_ent = "Retirada" if ret else "Entrega"

            pedido_raw = row.get("Pedido", "")
            pedido_str = ""
            try:
                num = float(pedido_raw)
                pedido_str = str(int(num)) if not math.isnan(num) else ""
            except (ValueError, TypeError):
                pedido_str = safe_str(pedido_raw)

            entry = {
                "pedido":    pedido_str,
                "nome":      safe_str(row.get("Nome", "")),
                "tipo":      safe_str(row.get("Tipo", "")),
                "recheio":   safe_str(row.get("Recheio", "")),
                "chocolate": safe_str(row.get("Chocolate", "")),
                "docinho":   safe_str(row.get("Docinho", "")),
                "infantil":  safe_str(row.get("Infantil", "")),
                "endereco":  endereco,
                "valor":     safe_str(row.get("Valor", "")),
                "entrega":   tipo_ent,
                "obs":       safe_str(row.get("Observação", "")),
                "recebido":  safe_str(row.get("Recebido", "")),
                "faltante":  safe_str(row.get("Faltante", "")),
            }

            cidades_data.setdefault(cidade, {})
            cidades_data[cidade].setdefault(turno, {"Entrega": [], "Retirada": []})
            cidades_data[cidade][turno][tipo_ent].append(entry)

        # Ordena pedidos dentro de cada bucket
        for cidade in cidades_data:
            for turno in cidades_data[cidade]:
                for tipo_ent in ("Entrega", "Retirada"):
                    lst = cidades_data[cidade][turno].get(tipo_ent, [])
                    cidades_data[cidade][turno][tipo_ent] = sort_pedidos(lst)
                # Remove tipo_entrega vazio
                cidades_data[cidade][turno] = {
                    k: v for k, v in cidades_data[cidade][turno].items() if v
                }

        # Remove cidades e turnos vazios
        cidades_data = {
            c: {t: v for t, v in turnos.items() if v}
            for c, turnos in cidades_data.items()
            if turnos
        }

        total = sum(
            len(lst)
            for turnos in cidades_data.values()
            for tipo_map in turnos.values()
            for lst in tipo_map.values()
        )

        days_data[dia] = {"cidades": cidades_data, "total": total}

    payload = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "available_days":   available_days,
        "days":             days_data,
    }
    payload = json_sanitize(payload)

    output_dir = os.path.join("dist", "data")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "pedidos.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)

    print(f"OK: gerado {out_path}")
    for dia in available_days:
        total = days_data[dia]["total"]
        print(f"  {dia}: {total} pedido(s)")


if __name__ == "__main__":
    main()
