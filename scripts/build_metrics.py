import json
import math
import os
from datetime import datetime, timezone

import pandas as pd

SHEET_ID = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME = "Encomendas"

CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

# Regras do seu ipynb
TOPPINGS = {
    "Ninho": {"Ninho": 7},
    "Ferrero Rocher": {"Brigadeiro": 4, "Ferrero": 2},
    "Brigadeiro e morangos": {"Brigadeiro": 6, "Morango": 3},
    "Brigadeiro": {"Brigadeiro": 7},
    "Kids": {"Brigadeiro": 2, "Tortuguita": 1, "Fini": 2, "Marshmallow": 2},
    "Ninho e morangos": {"Ninho": 4, "Morango": 2},
    "Ninho e Brigadeiros": {"Brigadeiro": 3, "Ninho": 4},
    "Morangos": {"Morango": 5},
    "Ninho e Confeti": {"Ninho": 5},
    "Brigadeiros e Confeti": {"Brigadeiro": 5},
}

PESOS = {"Trufado": 400, "Colher": 175}  # gramas por unidade

RECEITAS_DOCINHOS = {
    "Brigadeiro": {
        "Leite Condensado": 1,
        "Margarina (Colher)": 1,
        "Chocolate em Pó (Colher)": 2,
    },
    "Ninho": {
        "Leite Condensado": 1,
        "Margarina (Colher)": 1,
        "Leite em Pó (Colher)": 2,
    },
}
DOCINHOS_POR_RECEITA = 20

# Ingredientes por 1 receita de recheio
RECEITAS_RECHEIOS = {
    "Brigadeiro": {
        "Leite Condensado": 1,
        "Creme de Leite": 2,
        "Chocolate em Pó (Colher)": 3,
    },
    "Ninho": {
        "Leite Condensado": 1,
        "Creme de Leite": 2,
        "Leite em Pó (Colher)": 3,
    },
    "Maracujá": {
        "Leite Condensado": 1,
        "Creme de Leite": 2,
        "Pó de Sobremesa de Maracujá (Colher)": 1,
        "Suco Concentrado (ml)": 60,
    },
    "Coco": {
        "Leite Condensado": 1,
        "Creme de Leite": 2,
        "Coco Ralado Menina (Pacote)": 1,
    },
}

# Quantos ovos 1 receita recheia, por tipo/recheio
# Observação prática usada no código:
# - brigadeiro de colher: Ferrero Rocher, Kids e Brigadeiro -> 3 ovos/receita
# - ninho de colher: Ninho com Nutella, Ninho com morango e Ninho Kids -> 3 ovos/receita
# - maracujá de colher -> 4 ovos/receita
# - brigadeiro trufado: Brigadeiro e Ferrero Rocher -> 4 ovos/receita
# - ninho trufado: Ninho com Nutella -> 4 ovos/receita
# - maracujá trufado -> 4 ovos/receita
# - coco trufado: Prestígio -> 4 ovos/receita
RECHEIO_RULES = [
    # colher
    {"tipo": "colher", "recheio": "ferrero rocher", "receita": "Brigadeiro", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "kids", "receita": "Brigadeiro", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "brigadeiro", "receita": "Brigadeiro", "ovos_por_receita": 3},

    {"tipo": "colher", "recheio": "ninho com nutella", "receita": "Ninho", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "ninho com morango", "receita": "Ninho", "ovos_por_receita": 3},
    {"tipo": "colher", "recheio": "ninho kids", "receita": "Ninho", "ovos_por_receita": 3},

    {"tipo": "colher", "recheio": "maracujá", "receita": "Maracujá", "ovos_por_receita": 4},
    {"tipo": "colher", "recheio": "maracuja", "receita": "Maracujá", "ovos_por_receita": 4},

    # trufado
    {"tipo": "trufado", "recheio": "brigadeiro", "receita": "Brigadeiro", "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "ferrero rocher", "receita": "Brigadeiro", "ovos_por_receita": 4},

    {"tipo": "trufado", "recheio": "maracujá", "receita": "Maracujá", "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "maracuja", "receita": "Maracujá", "ovos_por_receita": 4},

    {"tipo": "trufado", "recheio": "ninho com nutella", "receita": "Ninho", "ovos_por_receita": 4},

    {"tipo": "trufado", "recheio": "prestígio", "receita": "Coco", "ovos_por_receita": 4},
    {"tipo": "trufado", "recheio": "prestigio", "receita": "Coco", "ovos_por_receita": 4},
]

# recheios que usam nutella
RECHEIOS_COM_NUTELLA = {
    "ninho com nutella",
    "ferrero rocher",
}
NUTELLA_GRAMAS_POR_OVO = 60


def json_sanitize(x):
    # pandas/numpy: NaN/NaT
    if x is None:
        return None

    # pega NaN/NaT de pandas/numpy
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass

    if isinstance(x, dict):
        return {str(k): json_sanitize(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_sanitize(v) for v in x]

    # inf/-inf
    if isinstance(x, (float, int)) and isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        return None

    return x


def safe_value_counts(df: pd.DataFrame, col: str):
    if col not in df.columns:
        return {}

    s = df[col].fillna("").astype(str).str.strip()
    s = s.replace({"nan": "", "None": ""})

    # remove valores vazios
    s = s[s != ""]

    vc = s.value_counts()
    return {str(k): int(v) for k, v in vc.items()}


def normalize_text(s: str) -> str:
    return str(s).strip().lower()


def get_recheio_rule(tipo: str, recheio: str):
    tipo_n = normalize_text(tipo)
    recheio_n = normalize_text(recheio)

    for rule in RECHEIO_RULES:
        if rule["tipo"] == tipo_n and rule["recheio"] == recheio_n:
            return rule

    return None


def compute_metrics(df: pd.DataFrame) -> dict:
    # Normalizar nomes (evita dor de cabeça com espaços)
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # total de pedidos = linhas com algum nome preenchido
    nomes_validos = (
        df["Nome"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    
    metrics["n_rows"] = int(len(df))  # compatibilidade
    metrics["total_pedidos"] = int((nomes_validos != "").sum())
    
    metrics["counts"] = {
        "Tipo": safe_value_counts(df, "Tipo"),
        "Chocolate": safe_value_counts(df, "Chocolate"),
        "Recheio": safe_value_counts(df, "Recheio"),
        "Docinho": safe_value_counts(df, "Docinho"),
        "Infantil": safe_value_counts(df, "Infantil"),
        "Dia Entrega": safe_value_counts(df, "Dia Entrega"),
        "Turno": safe_value_counts(df, "Turno"),
    }

    # Tipo x Recheio
    if {"Tipo", "Recheio"}.issubset(df.columns):
        tmp = df[["Tipo", "Recheio"]].fillna("").astype(str).apply(lambda x: x.str.strip())

        tmp = tmp[(tmp["Tipo"] != "") & (tmp["Recheio"] != "")]

        tipo_recheio = (
            tmp.value_counts()
            .reset_index(name="quantidade")
        )
        tipo_recheio["quantidade"] = tipo_recheio["quantidade"].astype(int)
        metrics["tipo_recheio"] = tipo_recheio.to_dict(orient="records")
    else:
        metrics["tipo_recheio"] = []

    # Quantidade de cascas por chocolate
    if {"Tipo", "Chocolate"}.issubset(df.columns):
        tmp = df.copy()

        tmp["qtd_cascas"] = tmp["Tipo"].fillna("").astype(str).str.strip().str.lower().apply(
            lambda x: 2 if x == "trufado" else 1 if x == "colher" else 0
        )

        cascas_por_chocolate = (
            tmp.groupby("Chocolate", dropna=False)["qtd_cascas"]
            .sum()
            .reset_index(name="Quantidade de cascas")
            .sort_values(by="Quantidade de cascas", ascending=False)
        )

        cascas_por_chocolate["Chocolate"] = cascas_por_chocolate["Chocolate"].fillna("").astype(str).str.strip()

        # remove chocolates vazios e quantidades zeradas
        cascas_por_chocolate = cascas_por_chocolate[
            (cascas_por_chocolate["Chocolate"] != "") &
            (cascas_por_chocolate["Quantidade de cascas"] > 0)
        ]

        cascas_por_chocolate["Quantidade de cascas"] = cascas_por_chocolate["Quantidade de cascas"].astype(int)

        metrics["cascas_por_combinacao"] = cascas_por_chocolate.to_dict(orient="records")
    else:
        metrics["cascas_por_combinacao"] = []

    # Tipo x Chocolate
    if {"Tipo", "Chocolate"}.issubset(df.columns):
        tmp = df[["Tipo", "Chocolate"]].fillna("").astype(str).apply(lambda x: x.str.strip())

        tmp = tmp[(tmp["Tipo"] != "") & (tmp["Chocolate"] != "")]

        tipo_choc = (
            tmp.value_counts()
            .reset_index(name="quantidade")
        )
        tipo_choc["quantidade"] = tipo_choc["quantidade"].astype(int)
        metrics["tipo_chocolate"] = tipo_choc.to_dict(orient="records")
    else:
        metrics["tipo_chocolate"] = []

    # Gasto por chocolate (peso total por Chocolate)
    if {"Tipo", "Chocolate"}.issubset(df.columns):
        def peso_tipo(t):
            t = str(t).strip()
            return PESOS.get(t, 0)

        gasto = df.groupby("Chocolate")["Tipo"].apply(lambda s: int(sum(peso_tipo(x) for x in s)))
        metrics["gasto_por_chocolate_gramas"] = {str(k): int(v) for k, v in gasto.to_dict().items()}
    else:
        metrics["gasto_por_chocolate_gramas"] = {}

    # Docinhos
    docinhos = {}
    if "Docinho" in df.columns:
        for valor in df["Docinho"].fillna("").astype(str).str.strip():
            if valor in TOPPINGS:
                for tipo, qtd in TOPPINGS[valor].items():
                    docinhos[tipo] = docinhos.get(tipo, 0) + int(qtd)
    metrics["docinhos_totais"] = docinhos

    # Quantidade de receitas de docinhos
    receitas_docinhos = {}
    
    for tipo, qtd in docinhos.items():
        if tipo in RECEITAS_DOCINHOS:
            receitas = float(qtd) / float(DOCINHOS_POR_RECEITA)
            receitas_docinhos[tipo] = round(receitas, 2)
    
    metrics["receitas_docinhos_total"] = receitas_docinhos

    # Ingredientes totais dos docinhos
    ingredientes = {
        "Leite Condensado": 0.0,
        "Leite em Pó (Colher)": 0.0,
        "Chocolate em Pó (Colher)": 0.0,
        "Margarina (Colher)": 0.0,
    }
    for tipo, qtd in docinhos.items():
        if tipo in RECEITAS_DOCINHOS:
            proporcao = float(qtd) / float(DOCINHOS_POR_RECEITA)
            for ing, base in RECEITAS_DOCINHOS[tipo].items():
                ingredientes[ing] += float(base) * proporcao
    metrics["ingredientes_docinhos_total"] = {k: round(v, 2) for k, v in ingredientes.items()}

    # Recheios
    receitas_recheios = {
        "Brigadeiro": 0.0,
        "Ninho": 0.0,
        "Maracujá": 0.0,
        "Coco": 0.0,
    }

    ingredientes_recheios = {
        "Leite Condensado": 0.0,
        "Creme de Leite": 0.0,
        "Chocolate em Pó (Colher)": 0.0,
        "Leite em Pó (Colher)": 0.0,
        "Pó de Sobremesa de Maracujá (Colher)": 0.0,
        "Suco Concentrado (ml)": 0.0,
        "Coco Ralado Menina (Pacote)": 0.0,
        "Nutella (g)": 0.0,
    }

    if {"Tipo", "Recheio"}.issubset(df.columns):
        for _, row in df.iterrows():
            tipo = row.get("Tipo", "")
            recheio = row.get("Recheio", "")

            if pd.isna(tipo) or pd.isna(recheio):
                continue

            tipo = str(tipo).strip()
            recheio = str(recheio).strip()

            if not tipo or not recheio:
                continue

            rule = get_recheio_rule(tipo, recheio)
            if not rule:
                continue

            receita_nome = rule["receita"]
            ovos_por_receita = float(rule["ovos_por_receita"])
            proporcao = 1.0 / ovos_por_receita

            receitas_recheios[receita_nome] += proporcao

            for ing, base in RECEITAS_RECHEIOS[receita_nome].items():
                ingredientes_recheios[ing] += float(base) * proporcao

            if normalize_text(recheio) in RECHEIOS_COM_NUTELLA:
                ingredientes_recheios["Nutella (g)"] += NUTELLA_GRAMAS_POR_OVO

    metrics["receitas_recheios_total"] = {k: round(v, 2) for k, v in receitas_recheios.items() if v > 0}
    metrics["ingredientes_recheios_total"] = {k: round(v, 2) for k, v in ingredientes_recheios.items() if v > 0}

    return metrics


def normalize_day_value(x) -> str:
    # garante chave consistente: "19", "20", etc.
    s = "" if pd.isna(x) else str(x).strip()
    return s


def main():
    df = pd.read_csv(CSV_URL)
    df.columns = [c.strip() for c in df.columns]

    payload = {}
    payload["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

    # ✅ Geral
    payload["overall"] = compute_metrics(df)

    # ✅ Por dia
    per_day = {}
    if "Dia Entrega" in df.columns:
        tmp = df.copy()
        tmp["_day"] = tmp["Dia Entrega"].apply(normalize_day_value)

        # remove vazios
        tmp = tmp[tmp["_day"] != ""]

        for day_value, g in tmp.groupby("_day", dropna=False):
            per_day[str(day_value)] = compute_metrics(g.drop(columns=["_day"]))

    payload["per_day"] = per_day
    payload["available_days"] = sorted(per_day.keys(), key=lambda x: (len(x), x))

    # sanitize + salvar
    payload = json_sanitize(payload)

    output_dir = os.path.join("dist", "data")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "metrics.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)

    print(f"OK: gerado {out_path}")


if __name__ == "__main__":
    main()
