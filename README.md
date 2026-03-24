# Páscoa Dashboard

Dashboard de acompanhamento de encomendas de ovos de Páscoa, com predição bayesiana de ingredientes.

## Páginas

| Página | Descrição |
|---|---|
| `index.html` | Métricas em tempo real: pedidos, recheios, chocolates, cascas, docinhos, ingredientes |
| `predicao.html` | Predição de ingredientes por meta de ovos, com modelo bayesiano e Monte Carlo |

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11 · pandas · numpy |
| Frontend | HTML + CSS + JS vanilla (sem framework) |
| Fontes | DM Sans + DM Mono (Google Fonts) |
| CI/CD | GitHub Actions (cron a cada 10 min) |
| Hospedagem | GitHub Pages |
| Trigger manual | Cloudflare Worker (`pascoa-dispatch`) |

## Estrutura

```
pascoa-dashboard/
├── site/                   # Fonte do site (copiada para dist/ no build)
│   ├── index.html          # Aba Métricas
│   ├── predicao.html       # Aba Predição
│   ├── app.js              # JS da aba Métricas
│   ├── predicao.js         # JS da aba Predição
│   └── styles.css          # Estilos compartilhados (dark/light mode)
├── scripts/
│   ├── build_metrics.py    # Lê CSV da Sheets → dist/data/metrics.json
│   └── build_prediction.py # Modelo bayesiano + Monte Carlo → dist/data/prediction.json
├── data/
│   └── historico/
│       ├── pascoa_2024.csv # Encomendas históricas 2024
│       └── pascoa_2025.csv # Encomendas históricas 2025
├── .github/workflows/
│   └── pages.yml           # Build & deploy automático
└── requirements.txt
```

## Fluxo de dados

```
Google Sheets (2026) ──┐
pascoa_2024.csv ───────┼─→ build_metrics.py   → dist/data/metrics.json
pascoa_2025.csv ───────┘      │
                               └─→ build_prediction.py → dist/data/prediction.json
                                                               │
                              GitHub Actions (cron 10min) ────┘
                                        │
                                   GitHub Pages
                                        │
                              index.html + predicao.html
```

## Modelo de predição

O modelo usa **Beta bayesiano com pesos temporais** para estimar a distribuição de recheios a partir dos históricos de 2024, 2025 e 2026.

**Pesos temporais:**
```
w(t) = exp(1.5 × (t − 2026))
  2024 → 0.050
  2025 → 0.223
  2026 → 1.000
```

**Beta por recheio** (prior uniforme + dados ponderados):
```
α_r = 1 + Σ w_t × contagem_r_t
β_r = 1 + Σ w_t × (total_t − contagem_r_t)
```

**Monte Carlo** (10 000 iterações, pre-computado no build):
- Sorteia proporções de cada recheio a partir das distribuições Beta
- Normaliza para somar 1 (aproximação Dirichlet)
- Sorteia proporção Colher/Trufado de outro Beta
- Aplica frações de receita: Colher = 1/3 ovo/receita, Trufado = 1/4
- Acumula ingredientes e salva percentis P50/P75/P90/P95 por cenário

Os cenários cobrem metas de **85 a 300 ovos** (passo 5). O browser apenas interpola/exibe — zero simulação no cliente.

## Normalização de recheios históricos

Variações entre anos são mapeadas para nomes canônicos:

| Valor original | Canônico |
|---|---|
| Ninho c/ Nutella | Ninho com Nutella |
| Brigadeiro c/ Nutella | Ferrero Rocher |
| Brigadeiro 70% | Brigadeiro |
| Ninho com brigadeiro | Ninho |
| Prestígio e Ninho com Nutella | *(ignorado — ambíguo)* |

## Desenvolvimento local

```bash
# Instalar dependências
pip install -r requirements.txt

# Gerar métricas (requer acesso à Google Sheets)
python scripts/build_metrics.py

# Gerar predição
python scripts/build_prediction.py

# Servir o site localmente
python -m http.server 8000 --directory dist
```

Os JSONs são gerados em `dist/data/`. Para visualizar o site, abra `http://localhost:8000`.
