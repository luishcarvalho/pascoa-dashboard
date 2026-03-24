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
    "brigadeiro c/ nutella":         "Ferrero Rocher",
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


# ── HELPERS ───────────────────────────────────────────────────────────────────

def normalize_recheio(s: str) -> str | None:
    return RECHEIO_ALIASES.get(str(s).strip().lower())


def load_csv(path_or_url: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path_or_url, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path_or_url, encoding="cp1252")
    df.columns = [c.strip() for c in df.columns]
    return df


def extract_counts(df: pd.DataFrame) -> tuple[int, dict, int]:
    """Retorna (total_válido, {recheio: contagem}, n_colher)."""
    df = df.copy()
    df["_recheio"] = df["Recheio"].fillna("").astype(str).apply(normalize_recheio)
    df["_tipo"]    = df["Tipo"].fillna("").astype(str).str.strip().str.lower()

    valid = df[df["_recheio"].notna() & df["_tipo"].isin(["colher", "trufado"])]

    counts   = {r: 0 for r in RECHEIOS}
    n_colher = int((valid["_tipo"] == "colher").sum())

    for r in valid["_recheio"]:
        if r in counts:
            counts[r] += 1

    return len(valid), counts, n_colher


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    rng = np.random.default_rng(42)

    # Carregar CSVs
    df24 = load_csv(CSV_2024)
    df25 = load_csv(CSV_2025)
    df26 = load_csv(CSV_URL_2026)

    years_order = [2024, 2025, 2026]
    dfs = {2024: df24, 2025: df25, 2026: df26}

    # Pesos temporais: w(t) = exp(1.5*(t - 2026))
    weights = {y: float(np.exp(1.5 * (y - 2026))) for y in years_order}

    # Contagens por ano
    year_stats = {}
    for y, df in dfs.items():
        total, counts, n_colher = extract_counts(df)
        year_stats[y] = {"total": total, "counts": counts, "n_colher": n_colher}

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

    # ── Monte Carlo (amostras únicas reutilizadas por target) ─────────────────
    alphas_arr = np.array([beta_params[r]["alpha"] for r in RECHEIOS])
    betas_arr  = np.array([beta_params[r]["beta"]  for r in RECHEIOS])

    # (N_SIM, n_recheios) — proporções normalizadas
    x_rec = rng.beta(alphas_arr, betas_arr, size=(N_SIM, len(RECHEIOS)))
    p_rec = x_rec / x_rec.sum(axis=1, keepdims=True)

    # (N_SIM,) — proporção Colher
    p_col = rng.beta(alpha_c, beta_c, size=N_SIM)

    scenarios: dict = {}

    for N in TARGETS:
        n_rec = p_rec * N   # ovos por recheio, (N_SIM, n_rec)

        acc = {ing: np.zeros(N_SIM) for ing in INGREDIENTES}

        for i, r in enumerate(RECHEIOS):
            cfg = RECHEIO_CONFIG[r]
            nr  = n_rec[:, i]
            nc  = nr * p_col          # colher
            nt  = nr * (1 - p_col)    # trufado

            receitas = nc / 3.0 + nt / 4.0

            for ing, qty in RECEITA_INGREDIENTES[cfg["receita"]].items():
                acc[ing] += receitas * qty

            if cfg["nutella"]:
                acc["Nutella (g)"] += nr * NUTELLA_G_POR_OVO

        sc: dict = {}
        for ing in INGREDIENTES:
            v = acc[ing]
            if v.max() == 0:
                continue
            sc[ing] = {
                "p50":  round(float(np.percentile(v, 50)), 1),
                "p75":  round(float(np.percentile(v, 75)), 1),
                "p90":  round(float(np.percentile(v, 90)), 1),
                "p95":  round(float(np.percentile(v, 95)), 1),
                "mean": round(float(np.mean(v)), 1),
                "std":  round(float(np.std(v)), 2),
            }

        # Histograma do Leite Condensado (20 bins)
        lc_vals = acc["Leite Condensado"]
        counts_h, edges_h = np.histogram(lc_vals, bins=20)
        sc["_histogram_lc"] = {
            "bins":   [round(float(e), 2) for e in edges_h],
            "counts": [int(c) for c in counts_h],
        }

        scenarios[str(N)] = sc

    # ── Payload ───────────────────────────────────────────────────────────────
    payload = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "model": {
            "weights":     {str(y): round(weights[y], 4) for y in years_order},
            "beta_params": beta_params,
            "p_colher":    round(p_colher_mean, 4),
            "historico":   historico,
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
