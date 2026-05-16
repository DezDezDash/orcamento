"""
Consolida os JSONs gerados pelos 20 jobs do scraper em um único estoque.json
que cobre TODOS os produtos do xlsx — mesmo os sem estoque encontrado.

Saída (estoque.json):
{
  "last_update": "16/05/2026 22:34",
  "lojas": ["CAM", "CAV", "CAX", "SLM"],
  "produtos": [
    {
      "codigo": "8246",
      "descricao": "ABAFADOR RUIDOS CONCHA ARV100 VONDER",
      "linha": "EPI",
      "linha_pai": "Ferramentas",
      "fornecedor": "OSTEN",
      "estoque": {"CAM": 3.0, "CAV": null, "CAX": 1.0, "SLM": null},
      "preco":   {"CAM": 25.90, "CAV": null, "CAX": 25.90, "SLM": null}
    },
    ...
  ]
}
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd


# Mapeamento da string da empresa (vinda do scraper) -> código curto da loja
EMPRESA_TO_LOJA = {
    "Comercial Dezdez Camaragibe":     "CAM",
    "Comercial Dezdez Cavaleiro":      "CAV",
    "Comercial Dezdez Caxangá":        "CAX",
    "Comercial DezDez São Lourenço":   "SLM",
}
LOJAS = ["CAM", "CAV", "CAX", "SLM"]


def empresa_to_loja(nome: str) -> str:
    """Resolve nome da empresa pro código curto, tolerante a variações."""
    if not nome:
        return ""
    # match exato primeiro
    if nome in EMPRESA_TO_LOJA:
        return EMPRESA_TO_LOJA[nome]
    # match por substring
    low = nome.lower()
    if "camaragibe" in low: return "CAM"
    if "cavaleiro"  in low: return "CAV"
    if "caxang"     in low: return "CAX"   # cobre Caxangá com/sem acento
    if "lourenço"   in low or "lourenco" in low or "são lou" in low: return "SLM"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs",   required=True, type=Path, help="pasta com JSONs dos jobs")
    ap.add_argument("--produtos", required=True, type=Path, help="produtos.xlsx (catálogo completo)")
    ap.add_argument("--saida",    required=True, type=Path, help="caminho do estoque.json")
    args = ap.parse_args()

    # 1) Carrega o catálogo completo (todos os 9871 produtos, mesmo sem estoque)
    df = pd.read_excel(args.produtos, dtype=str)
    df = df.fillna("")
    df["CODIGO"] = df["CODIGO"].astype(str).str.replace(".0", "", regex=False).str.strip()
    print(f"Catálogo: {len(df)} produtos")

    produtos = {}
    for _, row in df.iterrows():
        cod = row["CODIGO"]
        if not cod:
            continue
        produtos[cod] = {
            "codigo":     cod,
            "descricao":  row.get("DESCRICAO", "").strip(),
            "linha":      row.get("LINHA", "").strip(),
            "linha_pai":  row.get("LINHA_PAI", "").strip(),
            "fornecedor": row.get("FORNECEDOR", "").strip(),
            "estoque":    {l: None for l in LOJAS},
            "preco":      {l: None for l in LOJAS},
        }

    # 2) Lê todos os JSONs dos jobs e mescla
    jsons = sorted(args.inputs.rglob("*.json"))
    print(f"Encontrados {len(jsons)} JSONs em {args.inputs}")

    total_registros = 0
    for jf in jsons:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  Falha lendo {jf}: {e}")
            continue

        registros = data.get("data", [])
        for r in registros:
            cod = str(r.get("codigo", "")).replace(".0", "").strip()
            if not cod:
                continue
            loja = empresa_to_loja(r.get("empresa", ""))
            if not loja:
                continue

            # Se o produto não existe no catálogo (códigos órfãos), cria entrada mínima
            if cod not in produtos:
                produtos[cod] = {
                    "codigo":     cod,
                    "descricao":  r.get("descricao", "").strip(),
                    "linha":      r.get("linha", "").strip(),
                    "linha_pai":  "",
                    "fornecedor": "",
                    "estoque":    {l: None for l in LOJAS},
                    "preco":      {l: None for l in LOJAS},
                }

            produtos[cod]["estoque"][loja] = r.get("estoque")  # já vem float ou None
            produtos[cod]["preco"][loja]   = r.get("preco")

            # Completa descrição/linha se o catálogo estava vazio
            if not produtos[cod]["descricao"] and r.get("descricao"):
                produtos[cod]["descricao"] = r["descricao"].strip()
            if not produtos[cod]["linha"] and r.get("linha"):
                produtos[cod]["linha"] = r["linha"].strip()

            total_registros += 1

    print(f"Total de registros mesclados: {total_registros}")

    # 3) Estatísticas pra log do workflow
    com_estoque = sum(1 for p in produtos.values() if any(v is not None for v in p["estoque"].values()))
    sem_estoque = len(produtos) - com_estoque
    por_loja = {l: sum(1 for p in produtos.values() if p["estoque"][l] is not None) for l in LOJAS}
    print(f"Produtos com algum estoque coletado: {com_estoque}")
    print(f"Produtos sem nenhum dado coletado:   {sem_estoque}")
    print(f"Cobertura por loja: {por_loja}")

    # 4) Grava saída ordenada por código numérico quando possível
    def sort_key(p):
        try:
            return (0, int(p["codigo"]))
        except Exception:
            return (1, p["codigo"])

    payload = {
        "last_update": datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M"),
        "lojas": LOJAS,
        "total_produtos": len(produtos),
        "com_estoque": com_estoque,
        "cobertura_por_loja": por_loja,
        "produtos": sorted(produtos.values(), key=sort_key),
    }

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Gerado: {args.saida}")


if __name__ == "__main__":
    main()
