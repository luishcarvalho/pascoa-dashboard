"""
build_prediction.py
Gera dist/data/prediction.json com predição bayesiana de ingredientes para Páscoa 2026.
Combina histórico de 2024/2025 com dados atuais via regressão beta ponderada + Monte Carlo.
"""

import json
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SHEET_ID     = "1UqiFtW_E0OFiLaoInoEa-UQeR6iswc2Zs0Bg-IR8RA0"
SHEET_NAME   = "Encomendas"
CSV_URL_2026 = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

CSV_2024 = os.path.join("data", "historico", "pascoa_2024.csv")
CSV_2025 = os.path.join("data", "historico", "pascoa_2025.csv")

N_SIM   = 10_000
TARGETS = list(range(0, 310, 10))   # 0, 10, …, 300

# ── ALIASES DE RECHEIO ────────────────────────────────────────────────────────
# Normaliza variações históricas para nomes canônicos
RECHEIO_ALIASES: dict[str, str | None] = {
    # 2024
    "ninho c/ nutella":              "Ninho com Nutella",
    "brigadeiro c/ nutella":         "Brigadeiro",
    # 2025
    "brigadeiro 70%":                "Brigadeiro",
    "ninho com brigadeiro":          "Ninho",
    "prestígio e ninho com nutella": None,   # ambíguo → ignorar
    # canônicos
    "brigadeiro":                    "Brigadeiro",
    "ferrero rocher":                "Ferrero Rocher",
    "kids":                          "Kids",
    "ninho kids":                    "Kids",
    "maracujá":                      "Maracujá",
    "maracuja":                      "Maracujá",
    "ninho":                         "Ninho",
    "ninho com morango":             "Ninho",
    "ninho com nutella":             "Ninho com Nutella",
    "prestígio":                     "Prestígio",
    "prestigio":                     "Prestígio",
}

# Ordem fixa (define colunas dos arrays numpy)
RECHEIOS = [
    "Brigadeiro",
    "Ferrero Rocher",
    "Kids",
    "Maracujá",
    "Ninho",
    "Ninho com Nutella",
    "Prestígio",
]

# Receita e flag Nutella por recheio
RECHEIO_CONFIG = {
    "Brigadeiro":       {"receita": "Brigadeiro", "nutella": False},
    "Ferrero Rocher":   {"receita": "Brigadeiro", "nutella": True},
    "Kids":             {"receita": "Brigadeiro", "nutella": False},
    "Maracujá":         {"receita": "Maracujá",   "nutella": False},
    "Ninho":            {"receita": "Ninho",       "nutella": False},
    "Ninho com Nutella":{"receita": "Ninho",       "nutella": True},
    "Prestígio":        {"receita": "Coco",        "nutella": False},
}

# Ingredientes por receita (Colher = 3 ovos/receita, Trufado = 4 ovos/receita)
RECEITA_INGREDIENTES = {
    "Brigadeiro": {"Leite Condensado": 1, "Creme de Leite": 2, "Chocolate em Pó": 3},
    "Ninho":      {"Leite Condensado": 1, "Creme de Leite": 2, "Leite em Pó": 3},
    "Maracujá":   {"Leite Condensado": 1, "Creme de Leite": 2, "Pó de Maracujá": 1},
    "Coco":       {"Leite Condensado": 1, "Creme de Leite": 2, "Coco Ralado": 1},
}

INGREDIENTES = [
    "Leite Condensado",
    "Creme de Leite",
    "Chocolate em Pó",
    "Leite em Pó",
    "Pó de Maracujá",
    "Coco Ralado",
    "Nutella (g)",
]

NUTELLA_G_POR_OVO = 60

# ── ALIASES DE DOCINHO ────────────────────────────────────────────────────────
# Normaliza variações históricas para tipos canônicos de docinho
# None = pedido sem docinho (ignorar na contagem de docinhos)
DOCINHO_ALIASES: dict[str, str | None] = {
    # sem docinho
    "não":                       None,
    "nao":                       None,
    "-":                         None,
    # brigadeiro e variantes
    "brigadeiro":                "Brigadeiro",
    "brigadeiro e morangos":     "Brigadeiro com Morango",
    "brigadeiro e coco":         "Brigadeiro com Coco",
    "brigadeiro e côco":         "Brigadeiro com Coco",
    "brigadeiro e confeti":      "Brigadeiro com Confeti",
    "brigadeiros e confeti":     "Brigadeiro com Confeti",
    "brigadeiro e ninho":        "Brigadeiro com Ninho",
    "brigadeiro/ninho/confeti":  "Brigadeiro com Ninho",
    # ninho e variantes
    "ninho":                     "Ninho",
    "ninho e morangos":          "Ninho com Morango",
    "ninho e brigadeiros":       "Ninho com Brigadeiro",
    "ninho e confeti":           "Ninho com Confeti",
    "ninho e confeti":           "Ninho com Confeti",
    # outros
    "ferrero rocher":            "Ferrero Rocher",
    "kids":                      "Kids",
    "morangos":                  "Morango",
    "morango":                   "Morango",
}

# Tipos canônicos de docinho (ordem fixa para numpy)
DOCINHO_TIPOS = [
    "Brigadeiro",
    "Brigadeiro com Morango",
    "Brigadeiro com Coco",
    "Brigadeiro com Confeti",
    "Brigadeiro com Ninho",
    "Ninho",
    "Ninho com Morango",
    "Ninho com Brigadeiro",
    "Ninho com Confeti",
    "Ferrero Rocher",
    "Kids",
    "Morango",
]

# Docinhos individuais (Brigadeiro/Ninho) por pedido de cada tipo
# Baseado em TOPPINGS de build_metrics.py — apenas Brigadeiro/Ninho têm receita
TOPPINGS_ING: dict[str, dict[str, int]] = {
    "Brigadeiro":           {"Brigadeiro": 7, "Ninho": 0},
    "Brigadeiro com Morango": {"Brigadeiro": 6, "Ninho": 0},
    "Brigadeiro com Coco":  {"Brigadeiro": 7, "Ninho": 0},
    "Brigadeiro com Confeti": {"Brigadeiro": 5, "Ninho": 0},
    "Brigadeiro com Ninho": {"Brigadeiro": 3, "Ninho": 4},
    "Ninho":                {"Brigadeiro": 0, "Ninho": 7},
    "Ninho com Morango":    {"Brigadeiro": 0, "Ninho": 4},
    "Ninho com Brigadeiro": {"Brigadeiro": 3, "Ninho": 4},
    "Ninho com Confeti":    {"Brigadeiro": 0, "Ninho": 5},
    "Ferrero Rocher":       {"Brigadeiro": 4, "Ninho": 0},
    "Kids":                 {"Brigadeiro": 2, "Ninho": 0},
    "Morango":              {"Brigadeiro": 0, "Ninho": 0},
}

# Ingredientes por receita de docinho (1 receita = DOCINHOS_POR_RECEITA unidades)
RECEITAS_DOCINHOS: dict[str, dict[str, int]] = {
    "Brigadeiro": {"Leite Condensado": 1, "Margarina": 1, "Chocolate em Pó": 2},
    "Ninho":      {"Leite Condensado": 1, "Margarina": 1, "Leite em Pó": 2},
}

DOCINHOS_POR_RECEITA = 20  # consistente com build_metrics.py

INGREDIENTES_DOCINHOS = ["Leite Condensado", "Margarina", "Chocolate em Pó", "Leite em Pó"]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def normalize_recheio(s: str) -> str | None:
    return RECHEIO_ALIASES.get(str(s).strip().lower())


def normalize_docinho(s: str) -> str | None:
    """Normaliza string de docinho para tipo canônico; None = sem docinho."""
    key = str(s).strip().lower()
    if key in DOCINHO_ALIASES:
        return DOCINHO_ALIASES[key]
    # Tenta match parcial para variações não mapeadas
    return None


def load_csv(path_or_url: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path_or_url, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path_or_url, encoding="cp1252")
    df.columns = [c.strip() for c in df.columns]
    return df


def sc_stats(v: "np.ndarray") -> dict | None:
    """Retorna dict p50/p75/p90/p95/mean/std ou None se todos zeros."""
    if v.max() == 0:
        return None
    return {
        "p50":  round(float(np.percentile(v, 50)), 1),
        "p75":  round(float(np.percentile(v, 75)), 1),
        "p90":  round(float(np.percentile(v, 90)), 1),
        "p95":  round(float(np.percentile(v, 95)), 1),
        "mean": round(float(np.mean(v)), 1),
        "std":  round(float(np.std(v)), 2),
    }


def extract_counts(df: pd.DataFrame) -> tuple[int, dict, int, dict]:
    """Retorna (total_válido, {recheio: contagem}, n_colher, {docinho_tipo: contagem})."""
    df = df.copy()
    df["_recheio"] = df["Recheio"].fillna("").astype(str).apply(normalize_recheio)
    df["_tipo"]    = df["Tipo"].fillna("").astype(str).str.strip().str.lower()

    valid = df[df["_recheio"].notna() & df["_tipo"].isin(["colher", "trufado"])]

    counts   = {r: 0 for r in RECHEIOS}
    n_colher = int((valid["_tipo"] == "colher").sum())

    for r in valid["_recheio"]:
        if r in counts:
            counts[r] += 1

    # Contagem de docinhos (somente pedidos válidos)
    doc_counts = {t: 0 for t in DOCINHO_TIPOS}
    if "Docinho" in valid.columns:
        doc_series = valid["Docinho"].fillna("").astype(str).apply(normalize_docinho)
        for d in doc_series:
            if d is not None and d in doc_counts:
                doc_counts[d] += 1

    return len(valid), counts, n_colher, doc_counts


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    rng = np.random.default_rng(42)

    df24 = load_csv(CSV_2024)
    df25 = load_csv(CSV_2025)
    df26 = load_csv(CSV_URL_2026)

    years_order = [2024, 2025, 2026]
    dfs = {2024: df24, 2025: df25, 2026: df26}

    # Pesos temporais: w(t) = exp(1.5*(t - 2026))
    weights = {y: float(np.exp(1.5 * (y - 2026))) for y in years_order}

    year_stats = {}
    for y, df in dfs.items():
        total, counts, n_colher, doc_counts = extract_counts(df)
        year_stats[y] = {"total": total, "counts": counts, "n_colher": n_colher, "doc_counts": doc_counts}

    # ── Beta bayesiano por recheio ─────────────────────────────────────────────
    beta_params: dict = {}
    historico:   dict = {}

    for r in RECHEIOS:
        alpha, beta_ = 1.0, 1.0
        historico[r] = {}
        for y in years_order:
            stats = year_stats[y]
            w     = weights[y]
            cnt   = stats["counts"].get(r, 0)
            tot   = stats["total"]
            historico[r][str(y)] = round(cnt / tot * 100, 1) if tot else 0.0
            alpha  += w * cnt
            beta_  += w * (tot - cnt)
        mean = alpha / (alpha + beta_)
        var  = (alpha * beta_) / ((alpha + beta_) ** 2 * (alpha + beta_ + 1))
        beta_params[r] = {
            "alpha": round(alpha, 3),
            "beta":  round(beta_, 3),
            "mean":  round(mean, 4),
            "std":   round(math.sqrt(var), 4),
        }

    # ── Beta para proporção Colher ─────────────────────────────────────────────
    alpha_c, beta_c = 1.0, 1.0
    for y in years_order:
        stats   = year_stats[y]
        w       = weights[y]
        alpha_c += w * stats["n_colher"]
        beta_c  += w * (stats["total"] - stats["n_colher"])
    p_colher_mean = alpha_c / (alpha_c + beta_c)

    # ── Beta bayesiano por tipo de docinho ────────────────────────────────────
    beta_params_doc: dict = {}
    for t in DOCINHO_TIPOS:
        alpha_d, beta_d = 1.0, 1.0
        for y in years_order:
            stats  = year_stats[y]
            w      = weights[y]
            cnt    = stats["doc_counts"].get(t, 0)
            # total de docinhos pedidos (excluindo "sem docinho" / None)
            tot_doc = sum(stats["doc_counts"].values())
            alpha_d += w * cnt
            beta_d  += w * max(tot_doc - cnt, 0)
        mean_d = alpha_d / (alpha_d + beta_d)
        var_d  = (alpha_d * beta_d) / ((alpha_d + beta_d) ** 2 * (alpha_d + beta_d + 1))
        beta_params_doc[t] = {
            "alpha": round(alpha_d, 3),
            "beta":  round(beta_d,  3),
            "mean":  round(mean_d,  4),
            "std":   round(math.sqrt(var_d), 4),
        }

    # ── Monte Carlo (amostras únicas reutilizadas por target) ─────────────────
    alphas_arr = np.array([beta_params[r]["alpha"] for r in RECHEIOS])
    betas_arr  = np.array([beta_params[r]["beta"]  for r in RECHEIOS])

    # (N_SIM, n_recheios) — proporções normalizadas
    x_rec = rng.beta(alphas_arr, betas_arr, size=(N_SIM, len(RECHEIOS)))
    p_rec = x_rec / x_rec.sum(axis=1, keepdims=True)

    # (N_SIM,) — proporção Colher
    p_col = rng.beta(alpha_c, beta_c, size=N_SIM)

    # (N_SIM, n_tipos_docinho) — proporções normalizadas de docinhos
    alphas_doc = np.array([beta_params_doc[t]["alpha"] for t in DOCINHO_TIPOS])
    betas_doc  = np.array([beta_params_doc[t]["beta"]  for t in DOCINHO_TIPOS])
    x_doc = rng.beta(alphas_doc, betas_doc, size=(N_SIM, len(DOCINHO_TIPOS)))
    p_doc = x_doc / x_doc.sum(axis=1, keepdims=True)

    # Proporção histórica de pedidos COM docinho (qualquer tipo) — constante
    tot_doc_hist = sum(
        sum(year_stats[y]["doc_counts"].values()) for y in years_order
    )
    tot_ov_hist  = sum(year_stats[y]["total"] for y in years_order)
    p_tem_doc    = tot_doc_hist / max(tot_ov_hist, 1)

    scenarios: dict = {}

    for N in TARGETS:
        n_rec = p_rec * N   # ovos por recheio, (N_SIM, n_rec)

        acc = {ing: np.zeros(N_SIM) for ing in INGREDIENTES}
        acc_rec = {"Brigadeiro": np.zeros(N_SIM), "Ninho": np.zeros(N_SIM),
                   "Maracujá": np.zeros(N_SIM), "Coco": np.zeros(N_SIM)}

        for i, r in enumerate(RECHEIOS):
            cfg = RECHEIO_CONFIG[r]
            nr  = n_rec[:, i]
            nc  = nr * p_col          # colher
            nt  = nr * (1 - p_col)    # trufado

            receitas = nc / 3.0 + nt / 4.0
            acc_rec[cfg["receita"]] += receitas

            for ing, qty in RECEITA_INGREDIENTES[cfg["receita"]].items():
                acc[ing] += receitas * qty

            if cfg["nutella"]:
                acc["Nutella (g)"] += nr * NUTELLA_G_POR_OVO

        sc: dict = {}
        for ing in INGREDIENTES:
            stats_ing = sc_stats(acc[ing])
            if stats_ing is not None:
                sc[ing] = stats_ing

        # Histograma do Leite Condensado (20 bins)
        lc_vals = acc["Leite Condensado"]
        counts_h, edges_h = np.histogram(lc_vals, bins=20)
        sc["_histogram_lc"] = {
            "bins":   [round(float(e), 2) for e in edges_h],
            "counts": [int(c) for c in counts_h],
        }

        # ── Docinhos ─────────────────────────────────────────────────────────
        # Pedidos com docinho = N * p_tem_doc; proporção por tipo via p_doc
        n_doc_por_tipo = p_doc * (N * p_tem_doc)   # (N_SIM, n_tipos)

        acc_doc  = {ing: np.zeros(N_SIM) for ing in INGREDIENTES_DOCINHOS}
        acc_rdoc = {"Brigadeiro": np.zeros(N_SIM), "Ninho": np.zeros(N_SIM)}

        for j, t in enumerate(DOCINHO_TIPOS):
            nd   = n_doc_por_tipo[:, j]          # pedidos desse tipo
            tops = TOPPINGS_ING.get(t, {})
            n_brig = tops.get("Brigadeiro", 0)
            n_ninh = tops.get("Ninho", 0)

            # Receitas = total individual docinhos / DOCINHOS_POR_RECEITA
            receitas_brig = (nd * n_brig) / DOCINHOS_POR_RECEITA
            receitas_ninh = (nd * n_ninh) / DOCINHOS_POR_RECEITA
            acc_rdoc["Brigadeiro"] += receitas_brig
            acc_rdoc["Ninho"]      += receitas_ninh

            for ing, qty in RECEITAS_DOCINHOS["Brigadeiro"].items():
                acc_doc[ing] += receitas_brig * qty
            for ing, qty in RECEITAS_DOCINHOS["Ninho"].items():
                acc_doc[ing] += receitas_ninh * qty

        sc_doc: dict = {}
        for ing in INGREDIENTES_DOCINHOS:
            stats_ing = sc_stats(acc_doc[ing])
            if stats_ing is not None:
                sc_doc[ing] = stats_ing
        sc["_docinhos"] = sc_doc

        # ── Total combinado (recheio + docinhos) ─────────────────────────────
        # Ingredientes que somam: LC, Chocolate em Pó, Leite em Pó, Margarina, Nutella
        TOTAL_KEYS = [
            ("Leite Condensado",  "Leite Condensado",   "Leite Condensado"),
            ("Chocolate em Pó",   "Chocolate em Pó",    "Chocolate em Pó"),
            ("Leite em Pó",       "Leite em Pó",        "Leite em Pó"),
            ("Margarina",         None,                  "Margarina"),
            ("Nutella (g)",       "Nutella (g)",         None),
        ]
        sc_total: dict = {}
        for out_key, rec_key, doc_key in TOTAL_KEYS:
            v_rec = acc[rec_key]     if rec_key and rec_key in acc     else np.zeros(N_SIM)
            v_doc = acc_doc[doc_key] if doc_key and doc_key in acc_doc else np.zeros(N_SIM)
            v_tot = v_rec + v_doc
            stats_tot = sc_stats(v_tot)
            if stats_tot is not None:
                sc_total[out_key] = stats_tot
        sc["_total"] = sc_total

        # ── Receitas a produzir ───────────────────────────────────────────────
        RECEITA_TIPOS = ["Brigadeiro", "Ninho", "Maracujá", "Coco"]

        sc_rrec: dict = {}
        for rt in RECEITA_TIPOS:
            s = sc_stats(acc_rec[rt])
            if s:
                sc_rrec[rt] = s
        sc["_receitas_recheio"] = sc_rrec

        sc_rdoc: dict = {}
        for rt in ["Brigadeiro", "Ninho"]:
            s = sc_stats(acc_rdoc[rt])
            if s:
                sc_rdoc[rt] = s
        sc["_receitas_docinho"] = sc_rdoc

        sc_rtot: dict = {}
        for rt in RECEITA_TIPOS:
            v = acc_rec[rt] + acc_rdoc.get(rt, np.zeros(N_SIM))
            s = sc_stats(v)
            if s:
                sc_rtot[rt] = s
        sc["_receitas_total"] = sc_rtot

        scenarios[str(N)] = sc

    payload = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "model": {
            "weights":          {str(y): round(weights[y], 4) for y in years_order},
            "beta_params":      beta_params,
            "beta_params_doc":  beta_params_doc,
            "p_colher":         round(p_colher_mean, 4),
            "historico":        historico,
        },
        "scenarios": scenarios,
    }

    out_dir  = os.path.join("dist", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "prediction.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    size_kb = os.path.getsize(out_path) // 1024
    print(f"OK: {out_path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
