"""
analyze_addresses.py
Analisa os endereços de entrega da planilha de 2026 e gera um relatório
no terminal + salva dist/data/addresses_report.json
"""

import json
import os
import re

import pandas as pd

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID   = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME = "Encomendas"
CSV_URL    = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

# Padrões que indicam retirada (não entrega)
RETIRADA_PATTERNS = re.compile(r"retirada|retira|pickup|buscar", re.IGNORECASE)

# Padrões que indicam endereço potencialmente incompleto
INCOMPLETO_PATTERNS = re.compile(
    r"^(casa|vizinho|perto|próximo|ao lado|condomínio|cond\.?|apt?\.?\s*\d|bloco|ap\b)",
    re.IGNORECASE,
)

DAY_ORDER = ["qua", "qui", "sex", "sab", "dom", "seg"]


def day_sort_key(s: str) -> int:
    prefix = str(s).split()[0].lower() if s else ""
    try:
        return DAY_ORDER.index(prefix)
    except ValueError:
        return 99


def classify(addr: str) -> str:
    """Retorna 'retirada', 'incompleto' ou 'ok'."""
    a = str(addr).strip()
    if not a or a.lower() in ("nan", ""):
        return "vazio"
    if RETIRADA_PATTERNS.search(a):
        return "retirada"
    if INCOMPLETO_PATTERNS.search(a):
        return "incompleto"
    # Heurística: endereço razoável tem pelo menos número + palavra
    if len(a) < 8 or not re.search(r"\d", a):
        return "incompleto"
    return "ok"


def main() -> None:
    print("Baixando planilha 2026…")
    df = pd.read_csv(CSV_URL)
    df.columns = [c.strip() for c in df.columns]

    print(f"Total de linhas: {len(df)}\n")

    # Normaliza campos
    df["_endereco"]    = df["Endereço"].fillna("").astype(str).str.strip()
    df["_dia"]         = df["Dia Entrega"].fillna("").astype(str).str.strip()
    df["_nome"]        = df["Nome"].fillna("").astype(str).str.strip()
    df["_classificado"] = df["_endereco"].apply(classify)

    # ── Resumo geral ──────────────────────────────────────────────────────────
    counts = df["_classificado"].value_counts()
    print("=" * 52)
    print("RESUMO GERAL")
    print("=" * 52)
    for cat, n in counts.items():
        print(f"  {cat:<15} {n:>4} pedidos")
    print()

    # ── Por dia ───────────────────────────────────────────────────────────────
    dias = sorted(df["_dia"].unique(), key=day_sort_key)

    print("=" * 52)
    print("PEDIDOS DE ENTREGA POR DIA (excluindo retirada)")
    print("=" * 52)

    report_days = {}

    for dia in dias:
        sub = df[df["_dia"] == dia]
        entregas = sub[sub["_classificado"] != "retirada"]

        if entregas.empty:
            continue

        ok         = entregas[entregas["_classificado"] == "ok"]
        incompleto = entregas[entregas["_classificado"] == "incompleto"]
        vazio      = entregas[entregas["_classificado"] == "vazio"]

        print(f"\n  {dia}  ({len(entregas)} entregas, {len(sub)} total no dia)")
        print(f"  {'─'*46}")

        pedidos_dia = []
        for _, row in entregas.iterrows():
            status = row["_classificado"]
            icon   = "✓" if status == "ok" else "?" if status == "incompleto" else "✗"
            print(f"  [{icon}] {row['_nome']:<28} {row['_endereco']}")
            pedidos_dia.append({
                "nome":      row["_nome"],
                "endereco":  row["_endereco"],
                "status":    status,
                "recheio":   row.get("Recheio", ""),
                "tipo":      row.get("Tipo", ""),
                "obs":       row.get("Observação", ""),
            })

        print(f"\n       ✓ prontos p/ geocodificar : {len(ok)}")
        if not incompleto.empty:
            print(f"       ? endereços incompletos  : {len(incompleto)}")
        if not vazio.empty:
            print(f"       ✗ sem endereço           : {len(vazio)}")

        report_days[dia] = {
            "total_dia":   int(len(sub)),
            "entregas":    int(len(entregas)),
            "ok":          int(len(ok)),
            "incompleto":  int(len(incompleto)),
            "vazio":       int(len(vazio)),
            "pedidos":     pedidos_dia,
        }

    # ── Endereços únicos prontos para geocodificar ────────────────────────────
    prontos = df[df["_classificado"] == "ok"]["_endereco"].unique().tolist()
    print()
    print("=" * 52)
    print(f"ENDEREÇOS ÚNICOS PRONTOS PARA GEOCODIFICAR: {len(prontos)}")
    print("=" * 52)
    for e in sorted(prontos):
        print(f"  • {e}")

    # ── Endereços incompletos (precisam revisão) ───────────────────────────────
    incompletos = df[df["_classificado"] == "incompleto"][["_nome", "_endereco", "_dia"]].drop_duplicates()
    if not incompletos.empty:
        print()
        print("=" * 52)
        print("ENDEREÇOS INCOMPLETOS (precisam revisão na planilha)")
        print("=" * 52)
        for _, row in incompletos.iterrows():
            print(f"  {row['_dia']:<14} {row['_nome']:<28} \"{row['_endereco']}\"")

    # ── Salva JSON ────────────────────────────────────────────────────────────
    out_dir  = os.path.join("dist", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "addresses_report.json")

    report = {
        "total_pedidos":        int(len(df)),
        "total_entregas_ok":    int((df["_classificado"] == "ok").sum()),
        "total_incompletos":    int((df["_classificado"] == "incompleto").sum()),
        "total_retiradas":      int((df["_classificado"] == "retirada").sum()),
        "enderecos_unicos_ok":  prontos,
        "por_dia":              report_days,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nRelatório salvo em: {out_path}")


if __name__ == "__main__":
    main()
