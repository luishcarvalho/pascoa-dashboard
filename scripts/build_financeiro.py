"""
build_financeiro.py
Gera dist/data/financeiro.json com métricas financeiras da planilha de Páscoa 2026.

Fontes:
  - Aba "Encomendas": receita (coluna Total) e status de pagamento (coluna Pago)
  - Aba "Gastos":     despesas reais (coluna Valor Total) agrupadas por Categoria
"""

import json
import math
import os
import re
from datetime import datetime, timezone

import pandas as pd

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"


def csv_url(sheet_name):
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    )


# Tabela de custo teórico por unidade (R$)
CUSTOS = {
    ("Trufado", "premium"): 29.71,
    ("Trufado", "normal"):  23.72,
    ("Colher",  "premium"): 31.21,
    ("Colher",  "normal"):  22.98,
}
RECHEIOS_PREMIUM = {"ferrero rocher", "ninho com nutella", "geleia morango", "ninho"}

DAY_ORDER = ["qua", "qui", "sex", "sab", "dom", "seg"]

PAGO_TRUE = {"true", "sim", "1", "yes", "verdadeiro"}


# ── HELPERS ───────────────────────────────────────────────────────────────────

def parse_brl(s):
    """Converte 'R$ 1.234,56' ou '1234.56' para float."""
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return 0.0
    s = re.sub(r"[Rr]\$\s*", "", str(s).strip())
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def day_sort_key(x):
    prefix = str(x).split()[0].lower()
    return DAY_ORDER.index(prefix) if prefix in DAY_ORDER else len(DAY_ORDER)


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


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    df_enc = pd.read_csv(csv_url("Encomendas"))
    df_enc.columns = [c.strip() for c in df_enc.columns]

    df_gas = pd.read_csv(csv_url("Gastos"))
    df_gas.columns = [c.strip() for c in df_gas.columns]

    # ── Receita e pagamentos da aba Encomendas ────────────────────────────────
    # Colunas: Valor (preço do ovo), Recebido (pago), Faltante (a receber)
    receita_bruta = 0.0
    recebido      = 0.0
    faltante      = 0.0
    n_pedidos     = 0
    receita_por_dia: dict = {}

    nomes    = df_enc["Nome"].fillna("").astype(str).str.strip()
    df_valid = df_enc[nomes != ""].copy()

    n_pedidos = int(len(df_valid))

    n_pedidos_com_valor = 0

    if "Valor" in df_valid.columns:
        df_valid["_valor"] = df_valid["Valor"].apply(parse_brl)
        receita_bruta       = round(df_valid["_valor"].sum(), 2)
        n_pedidos_com_valor = int((df_valid["_valor"] > 0).sum())

    if "Recebido" in df_valid.columns:
        recebido = round(df_valid["Recebido"].apply(parse_brl).sum(), 2)

    if "Faltante" in df_valid.columns:
        faltante = round(df_valid["Faltante"].apply(parse_brl).sum(), 2)

    if "Dia Entrega" in df_valid.columns and "_valor" in df_valid.columns:
        tmp        = df_valid[["Dia Entrega", "_valor"]].copy()
        tmp["dia"] = tmp["Dia Entrega"].fillna("").astype(str).str.strip()
        tmp        = tmp[tmp["dia"] != ""]
        for dia, grp in tmp.groupby("dia"):
            receita_por_dia[str(dia)] = round(float(grp["_valor"].sum()), 2)
        receita_por_dia = {
            k: receita_por_dia[k]
            for k in sorted(receita_por_dia, key=day_sort_key)
        }

    ticket_medio = round(receita_bruta / n_pedidos_com_valor, 2) if n_pedidos_com_valor > 0 else 0.0

    # ── Gastos reais da aba Gastos ────────────────────────────────────────────
    gastos_por_categoria: dict = {}
    gastos_por_metodo:    dict = {}
    gastos_por_loja:      dict = {}
    gastos_total = 0.0

    if "Valor Total" in df_gas.columns:
        df_gas["_val"] = df_gas["Valor Total"].apply(parse_brl)
        df_gas_clean   = df_gas[df_gas["_val"] > 0].copy()
        gastos_total   = round(df_gas_clean["_val"].sum(), 2)

        if "Categoria" in df_gas.columns:
            for cat, grp in df_gas_clean.groupby("Categoria", dropna=True):
                cat_str = str(cat).strip()
                if cat_str and cat_str not in ("nan", "None"):
                    gastos_por_categoria[cat_str] = round(float(grp["_val"].sum()), 2)

        if "Método" in df_gas.columns:
            for met, grp in df_gas_clean.groupby("Método", dropna=True):
                met_str = str(met).strip()
                if met_str and met_str not in ("nan", "None"):
                    gastos_por_metodo[met_str] = round(float(grp["_val"].sum()), 2)

        if "Loja" in df_gas.columns:
            for loja, grp in df_gas_clean.groupby("Loja", dropna=True):
                loja_str = str(loja).strip()
                if loja_str and loja_str not in ("nan", "None"):
                    gastos_por_loja[loja_str] = round(float(grp["_val"].sum()), 2)

    # ── Custo teórico por tipo (tabela de preços) ─────────────────────────────
    custo_teorico_por_tipo: dict = {}
    custo_teorico_total = 0.0

    if {"Tipo", "Recheio", "Nome"}.issubset(df_enc.columns):
        nomes    = df_enc["Nome"].fillna("").astype(str).str.strip()
        df_valid = df_enc[nomes != ""].copy()

        for _, row in df_valid.iterrows():
            tipo    = str(row.get("Tipo", "")).strip()
            recheio = str(row.get("Recheio", "")).strip()
            if tipo not in ("Trufado", "Colher"):
                continue
            is_premium = any(r in recheio.lower() for r in RECHEIOS_PREMIUM)
            categoria  = "premium" if is_premium else "normal"
            custo      = CUSTOS.get((tipo, categoria), 0.0)
            custo_teorico_total += custo
            label = f"{tipo} {'Premium' if is_premium else 'Normal'}"
            custo_teorico_por_tipo[label] = custo_teorico_por_tipo.get(label, 0.0) + custo

    # ── Métricas derivadas ────────────────────────────────────────────────────
    lucro_bruto = receita_bruta - gastos_total
    margem_pct  = (lucro_bruto / receita_bruta * 100) if receita_bruta > 0 else 0.0

    payload = {
        "last_updated_utc":       datetime.now(timezone.utc).isoformat(),
        # Receita
        "receita_bruta":          receita_bruta,
        "recebido":               recebido,
        "faltante":               faltante,
        "n_pedidos":              n_pedidos,
        "ticket_medio":           ticket_medio,
        # Gastos reais
        "gastos_total":           gastos_total,
        "gastos_por_categoria":   {k: round(v, 2) for k, v in sorted(gastos_por_categoria.items(), key=lambda x: -x[1])},
        "gastos_por_metodo":      {k: round(v, 2) for k, v in sorted(gastos_por_metodo.items(), key=lambda x: -x[1])},
        "gastos_por_loja":        {k: round(v, 2) for k, v in sorted(gastos_por_loja.items(), key=lambda x: -x[1])},
        # Resultado
        "lucro_bruto":            round(lucro_bruto, 2),
        "margem_lucro_pct":       round(margem_pct, 2),
        # Custo teórico (para referência)
        "custo_teorico_total":    round(custo_teorico_total, 2),
        "custo_teorico_por_tipo": {k: round(v, 2) for k, v in sorted(custo_teorico_por_tipo.items())},
        # Por dia
        "receita_por_dia":        receita_por_dia,
    }

    payload = json_sanitize(payload)

    output_dir = os.path.join("dist", "data")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "financeiro.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)

    print(f"OK: gerado {out_path}")
    print(f"    Receita: R$ {receita_bruta:,.2f} | Gastos: R$ {gastos_total:,.2f} | Lucro: R$ {lucro_bruto:,.2f} ({margem_pct:.1f}%)")


if __name__ == "__main__":
    main()
