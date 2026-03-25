"""
build_metrics.py
Gera dist/data/metrics.json com métricas agregadas da planilha de Páscoa 2026:
totais de pedidos, distribuição por tipo/recheio/chocolate, ingredientes e docinhos.
"""

import json
import math
import os
from datetime import datetime, timezone

import pandas as pd

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID   = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME = "Encomendas"
CSV_URL    = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

TOPPINGS = {
    "Ninho":                  {"Ninho": 7},
    "Ferrero Rocher":         {"Brigadeiro": 4, "Ferrero": 2},
    "Brigadeiro e morangos":  {"Brigadeiro": 6, "Morango": 3},
    "Brigadeiro":             {"Brigadeiro": 7},
    "Kids":                   {"Brigadeiro": 2, "Tortuguita": 1, "Fini": 2, "Marshmallow": 2},
    "Ninho e morangos":       {"Ninho": 4, "Morango": 2},
    "Ninho e Brigadeiros":    {"Brigadeiro": 3, "Ninho": 4},
    "Morangos":               {"Morango": 5},
    "Ninho e Confeti":        {"Ninho": 5},
    "Brigadeiros e Confeti":  {"Brigadeiro": 5},
}

PESOS = {"Trufado": 400, "Colher": 175}  # gramas por unidade

RECEITAS_DOCINHOS = {
    "Brigadeiro": {
        "Leite Condensado":        1,
        "Margarina (Colher)":      1,
        "Chocolate em Pó (Colher)": 2,
    },
    "Ninho": {
        "Leite Condensado":    1,
        "Margarina (Colher)":  1,
        "Leite em Pó (Colher)": 2,
    },
}
DOCINHOS_POR_RECEITA = 20

# Ingredientes por 1 receita de recheio
RECEITAS_RECHEIOS = {
    "Brigadeiro": {
        "Leite Condensado":          1,
        "Creme de Leite":            2,
        "Chocolate em Pó (Colher)":  3,
    },
    "Ninho": {
        "Leite Condensado":    1,
        "Creme de Leite":      2,
        "Leite em Pó (Colher)": 3,
    },
    "Maracujá": {
        "Leite Condensado":                     1,
        "Creme de Leite":                       2,
        "Pó de Sobremesa de Maracujá (Colher)": 1,
        "Suco Concentrado (ml)":                60,
    },
    "Coco": {
        "Leite Condensado":          1,
        "Creme de Leite":            2,
        "Coco Ralado Menina (Pacote)": 1,
    },
}

# Ovos por receita de recheio:
# - brigadeiro/ninho de colher → 3 ovos/receita
# - maracujá de colher → 4 ovos/receita
# - qualquer trufado → 4 ovos/receita
RECHEIO_RULES = [
    # colher
    {"tipo": "colher", "recheio": "ferrero rocher",    "receita": "Brigadeiro", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "kids",              "receita": "Brigadeiro", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "brigadeiro",        "receita": "Brigadeiro", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "ninho com nutella", "receita": "Ninho",      "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "ninho com morango", "receita": "Ninho",      "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "ninho kids",        "receita": "Ninho",      "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "maracujá",          "receita": "Maracujá",   "ovos_por_receita": 4},
    {"tipo": "colher", "recheio": "maracuja",          "receita": "Maracujá",   "ovos_por_receita": 4},
    # trufado
    {"tipo": "trufado", "recheio": "brigadeiro",        "receita": "Brigadeiro", "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "ferrero rocher",    "receita": "Brigadeiro", "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "maracujá",          "receita": "Maracujá",   "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "maracuja",          "receita": "Maracujá",   "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "ninho com nutella", "receita": "Ninho",      "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "prestígio",         "receita": "Coco",       "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "prestigio",         "receita": "Coco",       "ovos_por_receita": 4},
]

RECHEIOS_COM_NUTELLA   = {"ninho com nutella", "ferrero rocher"}
NUTELLA_GRAMAS_POR_OVO = 60

DAY_ORDER = ["qua", "qui", "sex", "sab", "dom", "seg"]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def json_sanitize(x):
    """Converte NaN/Inf/None para None e estruturas aninhadas recursivamente."""
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


def safe_value_counts(df: pd.DataFrame, col: str) -> dict:
    """Retorna {valor: contagem} para a coluna, ignorando vazios."""
    if col not in df.columns:
        return {}
    s = df[col].fillna("").astype(str).str.strip().replace({"nan": "", "None": ""})
    s = s[s != ""]
    return {str(k): int(v) for k, v in s.value_counts().items()}


def normalize_text(s: str) -> str:
    return str(s).strip().lower()


def get_recheio_rule(tipo: str, recheio: str):
    tipo_n    = normalize_text(tipo)
    recheio_n = normalize_text(recheio)
    for rule in RECHEIO_RULES:
        if rule["tipo"] == tipo_n and rule["recheio"] == recheio_n:
            return rule
    return None


def peso_tipo(t) -> int:
    return PESOS.get(str(t).strip(), 0)


def day_sort_key(x) -> int:
    prefix = str(x).split()[0].lower()
    return DAY_ORDER.index(prefix) if prefix in DAY_ORDER else len(DAY_ORDER)


def normalize_day_value(x) -> str:
    return "" if pd.isna(x) else str(x).strip()


def compute_metrics(df: pd.DataFrame) -> dict:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    metrics = {}

    # total de pedidos = linhas com algum nome preenchido
    nomes_validos = df["Nome"].fillna("").astype(str).str.strip()
    metrics["n_rows"]        = int(len(df))
    metrics["total_pedidos"] = int((nomes_validos != "").sum())

    metrics["counts"] = {
        "Tipo":        safe_value_counts(df, "Tipo"),
        "Chocolate":   safe_value_counts(df, "Chocolate"),
        "Recheio":     safe_value_counts(df, "Recheio"),
        "Docinho":     safe_value_counts(df, "Docinho"),
        "Infantil":    safe_value_counts(df, "Infantil"),
        "Dia Entrega": safe_value_counts(df, "Dia Entrega"),
        "Turno":       safe_value_counts(df, "Turno"),
    }

    if {"Tipo", "Recheio"}.issubset(df.columns):
        tmp = df[["Tipo", "Recheio"]].fillna("").astype(str).apply(lambda x: x.str.strip())
        tmp = tmp[(tmp["Tipo"] != "") & (tmp["Recheio"] != "")]
        tipo_recheio = tmp.value_counts().reset_index(name="quantidade")
        tipo_recheio["quantidade"] = tipo_recheio["quantidade"].astype(int)
        metrics["tipo_recheio"] = tipo_recheio.to_dict(orient="records")
    else:
        metrics["tipo_recheio"] = []

    if {"Tipo", "Chocolate"}.issubset(df.columns):
        tmp = df.copy()
        tmp["qtd_cascas"] = tmp["Tipo"].fillna("").astype(str).str.strip().str.lower().apply(
            lambda x: 2 if x == "trufado" else 1 if x == "colher" else 0
        )
        cascas = (
            tmp.groupby("Chocolate", dropna=False)["qtd_cascas"]
            .sum()
            .reset_index(name="Quantidade de cascas")
            .sort_values(by="Quantidade de cascas", ascending=False)
        )
        cascas["Chocolate"] = cascas["Chocolate"].fillna("").astype(str).str.strip()
        cascas = cascas[(cascas["Chocolate"] != "") & (cascas["Quantidade de cascas"] > 0)]
        cascas["Quantidade de cascas"] = cascas["Quantidade de cascas"].astype(int)
        metrics["cascas_por_combinacao"] = cascas.to_dict(orient="records")
    else:
        metrics["cascas_por_combinacao"] = []

    if {"Tipo", "Chocolate"}.issubset(df.columns):
        tmp = df[["Tipo", "Chocolate"]].fillna("").astype(str).apply(lambda x: x.str.strip())
        tmp = tmp[(tmp["Tipo"] != "") & (tmp["Chocolate"] != "")]
        tipo_choc = tmp.value_counts().reset_index(name="quantidade")
        tipo_choc["quantidade"] = tipo_choc["quantidade"].astype(int)
        metrics["tipo_chocolate"] = tipo_choc.to_dict(orient="records")
    else:
        metrics["tipo_chocolate"] = []

    if {"Tipo", "Chocolate"}.issubset(df.columns):
        gasto = df.groupby("Chocolate")["Tipo"].apply(lambda s: int(sum(peso_tipo(x) for x in s)))
        metrics["gasto_por_chocolate_gramas"] = {str(k): int(v) for k, v in gasto.to_dict().items()}
    else:
        metrics["gasto_por_chocolate_gramas"] = {}

    docinhos: dict = {}
    if "Docinho" in df.columns:
        for valor in df["Docinho"].fillna("").astype(str).str.strip():
            if valor in TOPPINGS:
                for tipo, qtd in TOPPINGS[valor].items():
                    docinhos[tipo] = docinhos.get(tipo, 0) + int(qtd)
    metrics["docinhos_totais"] = docinhos

    metrics["receitas_docinhos_total"] = {
        tipo: round(qtd / DOCINHOS_POR_RECEITA, 2)
        for tipo, qtd in docinhos.items()
        if tipo in RECEITAS_DOCINHOS
    }

    ingredientes: dict = {
        "Leite Condensado":          0.0,
        "Leite em Pó (Colher)":      0.0,
        "Chocolate em Pó (Colher)":  0.0,
        "Margarina (Colher)":        0.0,
    }
    for tipo, qtd in docinhos.items():
        if tipo in RECEITAS_DOCINHOS:
            proporcao = qtd / DOCINHOS_POR_RECEITA
            for ing, base in RECEITAS_DOCINHOS[tipo].items():
                ingredientes[ing] += base * proporcao
    metrics["ingredientes_docinhos_total"] = {k: round(v, 2) for k, v in ingredientes.items()}

    receitas_recheios:     dict = {r: 0.0 for r in RECEITAS_RECHEIOS}
    ingredientes_recheios: dict = {
        "Leite Condensado":                     0.0,
        "Creme de Leite":                       0.0,
        "Chocolate em Pó (Colher)":             0.0,
        "Leite em Pó (Colher)":                 0.0,
        "Pó de Sobremesa de Maracujá (Colher)": 0.0,
        "Suco Concentrado (ml)":                0.0,
        "Coco Ralado Menina (Pacote)":          0.0,
        "Nutella (g)":                          0.0,
    }

    if {"Tipo", "Recheio"}.issubset(df.columns):
        for _, row in df.iterrows():
            tipo    = row.get("Tipo", "")
            recheio = row.get("Recheio", "")
            if pd.isna(tipo) or pd.isna(recheio):
                continue
            tipo    = str(tipo).strip()
            recheio = str(recheio).strip()
            if not tipo or not recheio:
                continue

            rule = get_recheio_rule(tipo, recheio)
            if not rule:
                continue

            proporcao = 1.0 / rule["ovos_por_receita"]
            receitas_recheios[rule["receita"]] += proporcao
            for ing, base in RECEITAS_RECHEIOS[rule["receita"]].items():
                ingredientes_recheios[ing] += base * proporcao
            if normalize_text(recheio) in RECHEIOS_COM_NUTELLA:
                ingredientes_recheios["Nutella (g)"] += NUTELLA_GRAMAS_POR_OVO

    metrics["receitas_recheios_total"]     = {k: round(v, 2) for k, v in receitas_recheios.items() if v > 0}
    metrics["ingredientes_recheios_total"] = {k: round(v, 2) for k, v in ingredientes_recheios.items() if v > 0}

    return metrics


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    df = pd.read_csv(CSV_URL)
    df.columns = [c.strip() for c in df.columns]

    payload = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "overall":          compute_metrics(df),
    }

    per_day: dict = {}
    if "Dia Entrega" in df.columns:
        tmp = df.copy()
        tmp["_day"] = tmp["Dia Entrega"].apply(normalize_day_value)
        tmp = tmp[tmp["_day"] != ""]
        for day_value, g in tmp.groupby("_day", dropna=False):
            per_day[str(day_value)] = compute_metrics(g.drop(columns=["_day"]))

    payload["per_day"]        = per_day
    payload["available_days"] = sorted(per_day.keys(), key=day_sort_key)
    payload = json_sanitize(payload)

    output_dir = os.path.join("dist", "data")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "metrics.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)

    print(f"OK: gerado {out_path}")


if __name__ == "__main__":
    main()
