# Páscoa Dashboard

Dashboard de gestão de encomendas de ovos de Páscoa com **predição bayesiana de ingredientes** — construído para resolver um problema real de planejamento de produção artesanal.

> Pipeline completo: Google Sheets → Python (pandas + numpy) → GitHub Actions → GitHub Pages. Zero banco de dados, zero servidor, zero custo.

---

## O problema

Produção artesanal de ovos de Páscoa envolve compra antecipada de ingredientes sem saber a demanda exata. Comprar de menos = perder vendas. Comprar demais = desperdício e prejuízo.

A solução foi um modelo que combina **histórico de dois anos** com os pedidos em aberto de 2026 para estimar, por cenário de meta, quanto de cada ingrediente comprar — e com qual margem de segurança.

---

## Funcionalidades

| Página | O que faz |
|---|---|
| **Métricas** | Pedidos em tempo real: recheios, chocolates, cascas, docinhos, ingredientes acumulados |
| **Predição** | Simulação bayesiana: dado uma meta de ovos, quanto de cada ingrediente comprar nos percentis P50 / P75 / P90 / P95 |

---

## Stack

| Camada | Tecnologia | Decisão |
|---|---|---|
| Backend | Python 3.11 · pandas · numpy | Processamento leve, sem overhead de framework |
| Frontend | HTML + CSS + JS vanilla | Sem bundle, sem build step no cliente — carrega em < 1s |
| CI/CD | GitHub Actions (cron diário) | Deploy automático sem infra própria |
| Hospedagem | GitHub Pages | Gratuito, CDN global, zero manutenção |
| Trigger manual | Cloudflare Worker (`pascoa-dispatch`) | Atualização sob demanda sem expor credenciais |
| Fonte de dados | Google Sheets (CSV export) | Interface de entrada acessível para usuários não-técnicos |

---

## Arquitetura

```
Google Sheets (2026) ──┐
pascoa_2024.csv ───────┼──→  build_metrics.py    →  dist/data/metrics.json
pascoa_2025.csv ───────┘          │
                                  └──→  build_prediction.py  →  dist/data/    prediction.json
                                                                        │
                                   GitHub Actions (cron diário) ────────┘
                                             │
                                        GitHub Pages
                                             │
                               index.html + predicao.html
                         (browser apenas lê JSON — zero simulação no cliente)
```

**Decisão de arquitetura:** toda a computação pesada (10 000 iterações Monte Carlo) roda no build. O browser só interpola e exibe — sem WebWorkers, sem WASM, sem latência de cálculo no cliente. O foco aqui era ser algo de acesso rápido e fácil seja pelo computador ou celular para acompanhar a venda.

---

## Estrutura do repositório

```
pascoa-dashboard/
├── site/
│   ├── index.html          # Aba Métricas
│   ├── predicao.html       # Aba Predição
│   ├── app.js              # Lógica de métricas
│   ├── predicao.js         # Interpolação e renderização da predição
│   └── styles.css          # Dark/light mode · design system consistente
├── scripts/
│   ├── build_metrics.py    # Lê CSV da Sheets → dist/data/metrics.json
│   └── build_prediction.py # Modelo bayesiano + Monte Carlo → dist/data/prediction.json
├── data/
│   └── historico/          # Dados de outros anos de venda
│       ├── pascoa_2024.csv
│       └── pascoa_2025.csv
├── .github/workflows/
│   └── pages.yml           # Build & deploy automático
└── requirements.txt
```

---

## Modelo de predição

### Por que Bayesiano?

Com apenas dois anos de histórico, um modelo frequentista seria instável — qualquer flutuação pontual distorceria a estimativa. A abordagem Beta bayesiana permite incorporar **incerteza estrutural**: o prior uniforme (`α = β = 1`) evita que recheios sem histórico sejam zerados, e os pesos temporais garantem que dados mais recentes tenham maior influência.

### Pesos temporais

```
w(t) = exp(1.5 × (t − 2026))

  2024 → 0.050   (sinal fraco — padrão pode ter mudado)
  2025 → 0.223   (contexto relevante)
  2026 → 1.000   (pedidos reais em aberto — máxima confiança)
```

O fator 1.5 foi calibrado para que o ano corrente domine sem ignorar completamente o histórico.

### Distribuição Beta por recheio

Prior uniforme atualizado com os dados ponderados de cada ano:

```
α_r = 1 + Σ  w_t × contagem_r_t
β_r = 1 + Σ  w_t × (total_t − contagem_r_t)
```

Isso produz uma distribuição de probabilidade para a *proporção esperada* de cada recheio — não um número fixo, mas uma curva de incerteza.

### Monte Carlo (10 000 iterações, pré-computado no build)

Para cada meta de ovos (0 a 300, passo 10):

1. Sorteia proporções de cada recheio a partir das distribuições Beta individuais
2. Normaliza para somar 1 (aproximação Dirichlet via marginalização)
3. Sorteia proporção Colher/Trufado de outro Beta independente
4. Aplica frações de receita: Colher = 1/3 ovo/receita · Trufado = 1/4
5. Acumula ingredientes e salva **P50 / P75 / P90 / P95** por cenário

O resultado é um JSON de cenários que o browser apenas lê e interpola — sem nenhum cálculo no cliente.

---

## Desenvolvimento local

```bash
# Instalar dependências
pip install -r requirements.txt

# Gerar métricas (requer acesso à Google Sheets pública ou CSV local)
python scripts/build_metrics.py

# Gerar predição
python scripts/build_prediction.py

# Servir o site localmente
python -m http.server 8000 --directory dist
# → http://localhost:8000
```

Os JSONs são gerados em `dist/data/`. O site é estático — qualquer servidor HTTP funciona.

---

## Sobre o projeto

Este foi um projeto pessoal, desenvolvido com o objetivo principal de explorar técnicas de análise de dados e modelagem probabilística aplicadas a um problema real. O foco esteve concentrado na construção do pipeline analítico, demonstração e extração de insights e no desenvolvimento dos modelos e simulações pra suporte à tomada de decisão.

As camadas de interface e grande parte da implementação do frontend não foram o foco central do projeto. Essas etapas foram desenvolvidas com o apoio do Claude Code, também como um experimento prático para avaliar as capacidades da ferramenta na geração de código, organização de interfaces e aceleração de desenvolvimento.
