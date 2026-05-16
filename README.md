# DezDez — Orçamento com estoque atualizado nightly

Sistema de orçamento de balcão pra equipe DezDez, hospedado no **GitHub Pages**, com `estoque.json` regenerado automaticamente todas as noites às **22:00 horário de Brasília** via **20 jobs paralelos** consultando o webapp Trivia.

## Estrutura

```
.
├── index.html                   # orçamento (era seu orcamento.html)
├── estoque.json                 # 9871 produtos — ATUALIZADO toda noite, NÃO editar manualmente
├── scraper/
│   ├── scraper.py               # seu script original (intocado)
│   ├── produtos.xlsx            # catálogo completo (9871 produtos)
│   ├── consolidar.py            # junta os 20 JSONs em estoque.json
│   └── requirements.txt
└── .github/workflows/
    └── estoque.yml              # cron 22h BRT, 4 lojas × 5 chunks = 20 jobs
```

## Como funciona

1. **Vendedor** abre `https://<seu-usuario>.github.io/<repo>/` no celular ou desktop
2. Faz login (usuários hardcoded no `index.html`: rafael / elany / thais)
3. App faz `fetch('estoque.json')` e popula o catálogo de 9871 produtos
4. Header mostra "estoque: dd/mm/aaaa hh:mm" pra saber qual a última atualização
5. Cada produto na busca mostra **chips de estoque das 4 lojas** (CAM CAV CAX SLM) com cores:
   - 🟢 verde = tem estoque
   - 🟡 amarelo = zerado
   - ⚪ cinza = sem dado coletado
   - destaque no chip da loja atual (selecionada no dropdown)
6. **Preço se ajusta à loja selecionada** — trocou de loja, todos os preços do catálogo e do carrinho recalculam automaticamente
7. Toda noite às 22h BRT, o GitHub Actions roda 20 jobs em paralelo, atualiza o `estoque.json` e commita no repo

## Setup inicial (uma vez só)

### 1. Cria o repositório no GitHub
Pode ser público (mais simples, dado que você já optou por aceitar o risco das senhas no source).

### 2. Sobe todos os arquivos deste pacote
Faz push pra branch `main`.

### 3. Configura secrets do scraper
**Settings → Secrets and variables → Actions → New repository secret:**

| Nome              | Valor                              |
|-------------------|------------------------------------|
| `WEBAPP_USERNAME` | seu login do webapp.comercialdezdez |
| `WEBAPP_PASSWORD` | sua senha                          |

### 4. Permite que o workflow commite no repo
**Settings → Actions → General → Workflow permissions** → marca **"Read and write permissions"** → Save.

> Isso dispensa o PAT. Não precisa daquele `GH_PAT` com escopo `workflow` que estava te dando trabalho nos outros projetos.

### 5. Ativa o GitHub Pages
**Settings → Pages → Source: Deploy from a branch** → `main` / `/ (root)` → Save.
URL final: `https://<seu-usuario>.github.io/<nome-do-repo>/`

### 6. Roda manualmente pela primeira vez
**Actions → Atualizar Estoque DezDez → Run workflow**.

Acompanha pra confirmar que o login no Trivia funciona em headless e que o `estoque.json` é commitado de volta.

A partir daí, o cron das 22h roda sozinho.

## O `estoque.json` placeholder

O arquivo que vem neste pacote já tem os 9871 produtos com `estoque: null` em tudo — então o orçamento **funciona desde o minuto zero do deploy**, mesmo antes do primeiro scrape:

- Vendedor já consegue buscar produtos
- Chips aparecem todos cinza (sem dado)
- Preços aparecem como "s/ preço"

Depois da primeira execução do workflow, o `estoque.json` é sobrescrito com os dados reais.

## Paralelismo: 20 jobs

- Matrix: `4 lojas × 5 chunks = 20`
- Cada job processa **1/5 dos 9871 códigos** numa única loja (~1974 produtos)
- Divisão: `codigos[batch::total]` — interleaved (job 0 pega códigos 0, 5, 10…; job 1 pega 1, 6, 11…). Balanceia naturalmente.
- Estimativa: **~2,7h por job** (1974 × ~5s)
- Timeout configurado: 6h (teto do GitHub Free)

## ⚠️ Risco de conflito de sessão

20 logins simultâneos no Trivia podem dar conflito (o sistema talvez derrube sessões). Se acontecer:

- **Sintoma**: vários jobs falham logo após o login, sem coletar nada
- **Solução A** (mais simples): reduz a matrix pra `chunk: [0]` no `estoque.yml` → 4 jobs (1 por loja). Mais lento, zero conflito.
- **Solução B**: cria 20 usuários separados no sistema e passa um por job (precisa mudar o workflow pra escolher credencial por matrix)

A primeira execução manual já te diz se aguenta os 20.

## Estrutura do estoque.json

```json
{
  "last_update": "16/05/2026 22:34",
  "lojas": ["CAM", "CAV", "CAX", "SLM"],
  "total_produtos": 9871,
  "com_estoque": 7234,
  "cobertura_por_loja": {"CAM": 9700, "CAV": 9650, "CAX": 9580, "SLM": 9710},
  "produtos": [
    {
      "codigo": "8246",
      "descricao": "ABAFADOR RUIDOS CONCHA ARV100 VONDER",
      "linha": "EPI",
      "linha_pai": "Ferramentas",
      "fornecedor": "OSTEN",
      "estoque": {"CAM": 3.0, "CAV": 7.0, "CAX": null, "SLM": 12.0},
      "preco":   {"CAM": 25.90, "CAV": 26.50, "CAX": null, "SLM": 25.90}
    }
  ]
}
```

**Todos os 9871 produtos sempre aparecem** mesmo sem estoque (campos `null`). Garante seu requisito: "que tenha disponível dentro do próprio orçamento mesmo que não haja estoque".

## Atualizando o catálogo de produtos

Quando o catálogo mudar:

1. Exporta novo `ProdutosDezDezRafael.xlsx` do sistema
2. Renomeia as colunas pro padrão do scraper:
   - `CODPRODUTO` → `CODIGO`
   - `DESCPRODUTO` → `DESCRICAO`
   - `DESCLINHAPRODUTO` → `LINHA`
   - `LINHAPRODUTOPAI` → `LINHA_PAI`
   - `NOMEFANTFORN` → `FORNECEDOR`
3. Substitui `scraper/produtos.xlsx` e commita
4. Próxima execução do cron já usa a nova lista

## Testando o scraper localmente

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium

# 1 loja, 1 chunk, browser visível
python scraper.py \
  --produtos produtos.xlsx \
  --saida saida.xlsx \
  --json saida.json \
  --empresa "Camaragibe" \
  --batch 0 --total 5 \
  --headful \
  --username "seu_login" --password "sua_senha"
```

## Testando o orçamento localmente

```bash
# Da raiz do repo:
python3 -m http.server 8000
# Abrir http://localhost:8000/
```

O `fetch('estoque.json')` precisa ser servido via HTTP (não `file://`). Qualquer servidor estático serve.

## Modificações feitas no orcamento.html original

Tudo cirúrgico, identidade visual e lógica do app preservadas. Modificações:

1. **Removido**: o `CATALOGO = [...]` gigante embarcado (~677 KB de produtos no JS)
2. **Removido**: feature "Carregar CSV de preços" — não faz mais sentido com `estoque.json` automático (CSS, HTML da caixa amarela, funções `carregarPrecosCSV` e `aplicarPrecosSalvos`, constante `PRECOS_KEY`)
3. **Adicionado**: `carregarCatalogo()` que faz fetch do `estoque.json` e mapeia pro formato `{c,d,l,f,p,e,precos}` que o app já usa
4. **Adicionado**: chips de estoque das 4 lojas em cada resultado de busca
5. **Adicionado**: troca de loja no dropdown agora recalcula preços do catálogo e carrinho dinamicamente
6. **Adicionado**: indicador "estoque: dd/mm hh:mm" no header (fica amarelo se estoque > 30h)
7. **Adicionado**: logo DezDez no canto superior esquerdo do PDF gerado (extraída em runtime do `<img class="logo-img">` embutido)
8. **Adicionado**: tratamento de produto sem preço — mostra "s/ preço" em vez de "R$ 0,00"

O arquivo final tem ~85 KB (era 760 KB com o catálogo embarcado).
