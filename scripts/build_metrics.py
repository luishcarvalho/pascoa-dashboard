import json
from datetime import datetime, timezone
import pandas as pd

SHEET_ID = "14d8qkw1bD1m2k1M6IMZudDQ63dLhoxqhPUJy2qdxXLE"
SHEET_NAME = "Encomendas"

CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

# Regras do seu ipynb
TOPPINGS = {
    "Ninho": {"Ninho": 7},
    "Ferrero Rocher": {"Brigadeiro": 4, "Ferrero": 2},
    "Brigadeiro e morangos": {"Brigadeiro": 6, "Morango": 3},
    "Brigadeiro": {"Brigadeiro": 7},
    "Kids": {"Brigadeiro": 2},
    "Ninho e Brigadeiros": {"Brigadeiro": 3, "Ninho": 4},
    "Morangos": {"Morango": 5},
    "Ninho e morangos": {"Ninho": 4, "Morango": 3},
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


def safe_value_counts(df: pd.DataFrame, col: str):
    if col not in df.columns:
        return {}
    return df[col].fillna("").astype(str).replace("nan", "").value_counts().to_dict()


def main():
    df = pd.read_csv(CSV_URL)

    # Normalizar nomes (evita dor de cabeça com espaços)
    df.columns = [c.strip() for c in df.columns]

    # Métricas simples
    metrics = {}
    metrics["last_updated_utc"] = datetime.now(timezone.utc).isoformat()
    metrics["n_rows"] = int(len(df))
    metrics["counts"] = {
        "Tipo": safe_value_counts(df, "Tipo"),
        "Chocolate": safe_value_counts(df, "Chocolate"),
        "Casca": safe_value_counts(df, "Casca"),
        "Recheio": safe_value_counts(df, "Recheio"),
        "Docinho": safe_value_counts(df, "Docinho"),
        "Criança?": safe_value_counts(df, "Criança?"),
        "Dia Entrega": safe_value_counts(df, "Dia Entrega"),  # se existir
    }

    # Tipo x Recheio (como no ipynb)
    if "Tipo" in df.columns and "Recheio" in df.columns:
        tipo_recheio = (
            df[["Tipo", "Recheio"]]
            .value_counts(dropna=False)
            .reset_index(name="quantidade")
        )
        metrics["tipo_recheio"] = tipo_recheio.to_dict(orient="records")
    else:
        metrics["tipo_recheio"] = []

    # Cascas por combinação (Casca, Chocolate) com regra do Trufado=2
    if {"Tipo", "Casca", "Chocolate"}.issubset(df.columns):
        tmp = df.copy()
        tmp["cascas_ajustadas"] = tmp["Tipo"].fillna("").astype(str).str.lower().apply(
            lambda x: 2 if x == "trufado" else 1
        )
        cascas_por = (
            tmp.groupby(["Casca", "Chocolate"], dropna=False)["cascas_ajustadas"]
            .sum()
            .reset_index(name="Quantidade de cascas")
            .sort_values(by="Quantidade de cascas", ascending=False)
        )
        metrics["cascas_por_combinacao"] = cascas_por.to_dict(orient="records")
    else:
        metrics["cascas_por_combinacao"] = []

    # Tipo x Chocolate (contagem)
    if {"Tipo", "Chocolate"}.issubset(df.columns):
        tipo_choc = (
            df[["Tipo", "Chocolate"]]
            .value_counts(dropna=False)
            .reset_index(name="quantidade")
        )
        metrics["tipo_chocolate"] = tipo_choc.to_dict(orient="records")
    else:
        metrics["tipo_chocolate"] = []

    # Gasto por chocolate (peso total por Chocolate)
    if {"Tipo", "Chocolate"}.issubset(df.columns):
        def peso_tipo(t):
            t = str(t)
            return PESOS.get(t, 0)

        gasto = df.groupby("Chocolate")["Tipo"].apply(lambda s: int(sum(peso_tipo(x) for x in s)))
        metrics["gasto_por_chocolate_gramas"] = gasto.to_dict()
    else:
        metrics["gasto_por_chocolate_gramas"] = {}

    # Contagem de docinhos por topping (igual seu ipynb)
    docinhos = {"Morango": 0, "Brigadeiro": 0, "Ninho": 0, "Ferrero": 0}
    if "Docinho" in df.columns:
        for valor in df["Docinho"].fillna("").astype(str):
            if valor in TOPPINGS:
                for tipo, qtd in TOPPINGS[valor].items():
                    docinhos[tipo] += qtd
    metrics["docinhos_totais"] = docinhos

    # Ingredientes totais (Brigadeiro/Ninho)
    ingredientes = {
        "Leite Condensado": 0.0,
        "Leite em Pó (Colher)": 0.0,
        "Chocolate em Pó (Colher)": 0.0,
        "Margarina (Colher)": 0.0,
    }
    for tipo, qtd in docinhos.items():
        if tipo in RECEITAS_DOCINHOS:
            proporcao = qtd / DOCINHOS_POR_RECEITA
            for ing, base in RECEITAS_DOCINHOS[tipo].items():
                ingredientes[ing] += base * proporcao
    metrics["ingredientes_docinhos_total"] = {k: round(v, 2) for k, v in ingredientes.items()}

    # Salvar no site
    out_path = "dist/data/metrics.json"
    import os
    os.makedirs("dist/data", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(f"OK: gerado {out_path}")


if __name__ == "__main__":
    main()
