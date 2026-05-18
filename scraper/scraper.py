import argparse
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

URL = "https://webapp.comercialdezdez.com.br"
DEFAULT_COMPANIES = [
    "Comercial Dezdez Camaragibe",
    "Comercial DezDez São Lourenço",
    "Comercial Dezdez Cavaleiro",
    "Comercial Dezdez Caxangá",
]


def log(x): print(time.strftime("%H:%M:%S"), "|", x, flush=True)
def nap(s=0.30): time.sleep(s)


def pf_idle(page, timeout=10000):
    try:
        page.wait_for_function("""() => {
            try {
              if (window.PrimeFaces && PrimeFaces.ajax && PrimeFaces.ajax.Queue) {
                return PrimeFaces.ajax.Queue.isEmpty();
              }
            } catch(e){}
            const overlays = Array.from(document.querySelectorAll('.ui-widget-overlay,.ui-blockui')).filter(el => el.offsetParent !== null);
            return overlays.length === 0;
        }""", timeout=timeout)
    except:
        pass


def do_login(page, username, password):
    log("Aguardando tela de login...")
    try:
        page.wait_for_selector(
            "input[type='password'], input[name='j_password'], input[id*='senha'], input[id*='password']",
            timeout=15000
        )
    except:
        log("Campo de senha não localizado, tentando mesmo assim...")

    for sel in [
        "input[name='j_username']",
        "input[id*='username']",
        "input[id*='login']",
        "input[id*='usuario']",
        "input[type='text']",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.fill(username, timeout=2000)
                log(f"Usuário preenchido ({sel})")
                break
        except:
            continue

    for sel in [
        "input[type='password']",
        "input[name='j_password']",
        "input[id*='senha']",
        "input[id*='password']",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.fill(password, timeout=2000)
                log("Senha preenchida")
                break
        except:
            continue

    nap(0.3)

    for sel in [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Entrar')",
        "button:has-text('Login')",
        "button:has-text('Acessar')",
        ".ui-commandbutton",
        "button",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.click(timeout=2000)
                log(f"Submit via {sel}")
                break
        except:
            continue

    nap(2)
    pf_idle(page, timeout=15000)
    log(f"Pós-login. URL: {page.url}")


def go_to_produtos(page):
    for s in ["button:has(svg)", ".fa-bars", ".navbar-toggle", ".fa.fa-bars", "[class*=bars]"]:
        try: page.locator(s).first.click(timeout=1200); break
        except: pass
    for s in ["text=Produto", "css=li >> text=Produto", "role=link[name='Produto']"]:
        try: page.locator(s).first.click(timeout=2500); break
        except: pass
    page.wait_for_selector("text=Pedido / Produto", timeout=30000)
    page.evaluate("window.scrollTo(0,0)")
    log("Na tela Produto. URL: " + page.url)


def open_dropdown(page):
    for xp in [
        "xpath=//div[contains(@id,':empresa') and contains(@class,'ui-selectonemenu')]//div[contains(@class,'trigger')]",
        "xpath=//label[contains(@id,'empresa_label')]",
        "xpath=//div[contains(@id,':empresa') and contains(@class,'ui-selectonemenu')]",
    ]:
        try: page.locator(xp).first.click(timeout=1200); nap(0.1); return True
        except: continue
    return False


def visible_empresa_panel(page):
    loc = page.locator("xpath=//div[contains(@id,':empresa_panel') and contains(@class,'ui-selectonemenu-panel') and not(contains(@style,'display: none'))]")
    if loc.count() > 0: return loc.first
    return page.locator("css=.ui-selectonemenu-panel:not([style*='display: none'])").first


def panel_items(panel): return panel.locator("xpath=.//li[not(contains(@class,'disabled'))]")


def get_companies(page):
    opts = []
    try:
        open_dropdown(page)
        pan = visible_empresa_panel(page)
        pan.wait_for(state="visible", timeout=2000)
        items = panel_items(pan)
        opts = [t.strip() for t in items.all_text_contents() if t.strip()]
        page.mouse.click(5, 5)
    except Exception:
        pass
    opts = [o for o in opts if o.lower().startswith("comercial")]
    if len(opts) < 2:
        opts = DEFAULT_COMPANIES
        log("Aviso: usando lista padrão de lojas.")
    log(f"Empresas detectadas ({len(opts)}): {opts}")
    return opts


def selected_company(page):
    try: return page.locator("xpath=//label[contains(@id,'empresa_label')]").inner_text().strip()
    except: return ""


def fuzzy_match(items, target):
    t = target.lower().strip()
    for i, x in enumerate(items):
        if x.lower().strip() == t: return i
    for i, x in enumerate(items):
        if x.lower().strip().startswith(t[:15]): return i
    for i, x in enumerate(items):
        if t in x.lower(): return i
    return None


def select_company(page, name, retries=3):
    last_err = None
    for attempt in range(retries + 1):
        try:
            page.evaluate("window.scrollTo(0,0)")
            open_dropdown(page)
            pan = visible_empresa_panel(page)
            pan.wait_for(state="visible", timeout=2500)
            items = panel_items(pan)
            texts = [t.strip() for t in items.all_text_contents() if t.strip()]
            idx = fuzzy_match(texts, name)
            if idx is None:
                raise RuntimeError(f"Loja '{name}' não encontrada no dropdown: {texts}")
            it = items.nth(idx)
            try: it.scroll_into_view_if_needed()
            except: pass
            it.click(timeout=2000)
            page.keyboard.press("Escape")
            pf_idle(page, timeout=8000)
            nap(0.4)
            sel = selected_company(page).strip()
            log(f"Empresa selecionada: {sel}")
            if sel == name.strip(): return
            last_err = RuntimeError(f"Esperado '{name}', obtido '{sel}'")
        except Exception as e:
            last_err = e
        try: page.mouse.click(5, 5)
        except: pass
        nap(0.3)
    raise last_err or RuntimeError("Falha ao selecionar empresa.")


def clear_filters(page):
    for xp in [
        "xpath=//input[contains(@id,':codigo') and @type='text' and not(@role='combobox')]",
        "xpath=//input[@id='formProdutoBuscar:descProdFilter']",
        "xpath=//input[contains(@placeholder,'Linha de Produto')]",
    ]:
        loc = page.locator(xp)
        if loc.count():
            try:
                loc.first.click(timeout=800)
                page.keyboard.press("Control+A"); page.keyboard.press("Delete")
            except:
                pass
    try:
        cb = page.locator("xpath=//label[contains(.,'Sem estoque')]/preceding::input[@type='checkbox'][1]")
        if cb.count() > 0 and cb.first.is_checked(): cb.first.click()
    except:
        pass


def find_code_input(page):
    for xp in [
        "xpath=//input[contains(@id,':codigo') and @type='text' and not(@role='combobox')]",
        "xpath=//input[contains(@name,':codigo') and @type='text' and not(@role='combobox')]",
        "xpath=(//input[contains(@placeholder,'Linha de Produto')]/preceding::input[@type='text' and not(@role='combobox')])[1]",
    ]:
        loc = page.locator(xp).first
        try:
            loc.wait_for(state="visible", timeout=1500)
            print(f"Campo de código: id='{loc.get_attribute('id')}'", flush=True)
            return loc
        except:
            continue
    loc = page.locator("css=input[type='text']:not([role='combobox'])").first
    loc.wait_for(state="visible", timeout=2500)
    print(f"Campo de código (fallback): id='{loc.get_attribute('id')}'", flush=True)
    return loc


def click_buscar(page):
    for s in ["xpath=//button[contains(.,'Buscar')]", "css=button:has-text('Buscar')", "role=button[name='Buscar']"]:
        try: page.locator(s).first.click(timeout=2000); return True
        except: pass
    return False


def wait_table_has_code(page, code, timeout=9000):
    end = time.time() + timeout / 1000.0
    xp = f"//table[.//th[contains(.,'Descrição')] and .//th[contains(.,'Estoque')]]//tbody//tr"
    while time.time() < end:
        try:
            rows = page.locator(f"xpath={xp}")
            n = rows.count()
            for i in range(n):
                r = rows.nth(i)
                c0 = r.locator("xpath=./td[1]").inner_text().strip().replace('\xa0', '')
                if c0 == str(code): return True
            if page.locator('text=Nenhum registro encontrado').count():
                return True
        except:
            pass
        nap(0.25)
    return False


def buscar_codigo(page, code):
    clear_filters(page)
    pf_idle(page, timeout=6000)
    inp = find_code_input(page)
    try:
        inp.click()
        page.keyboard.press("Control+A"); page.keyboard.press("Delete")
        inp.fill(str(code))
    except:
        try:
            el = inp.element_handle()
            page.evaluate("""(el, v) => { el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); el.value=v; el.dispatchEvent(new Event('input',{bubbles:true})); }""", el, str(code))
        except:
            pass
    nap(0.1)
    click_buscar(page)
    pf_idle(page, timeout=10000)
    wait_table_has_code(page, code, timeout=12000)


def ler_linha(page, code):
    xp = f"//table[.//th[contains(.,'Descrição')] and .//th[contains(.,'Estoque')]]//tbody//tr"
    rows = page.locator(f"xpath={xp}")
    try:
        n = rows.count()
    except:
        n = 0
    for i in range(n):
        r = rows.nth(i)
        try:
            c0 = r.locator("xpath=./td[1]").inner_text().strip().replace('\xa0', '')
            if c0 == str(code):
                linha = r.locator("xpath=./td[2]").inner_text().strip()
                desc = r.locator("xpath=./td[3]").inner_text().strip()
                est = r.locator("xpath=./td[4]").inner_text().strip()
                try:
                    preco = r.locator("xpath=./td[5]").inner_text().strip()
                except:
                    preco = ""
                return {"CODIGO": c0, "LINHA": linha, "DESCRICAO": desc, "ESTOQUE": est, "PRECO": preco}
        except:
            pass
    try:
        if page.locator("text=Nenhum registro encontrado").is_visible(): return None
    except:
        pass
    return None


def estoque_num(s):
    if not s or not isinstance(s, str): return None
    if s.strip().upper() == "N/D": return None
    m = re.findall(r"[\d\.,]+", s)
    if not m: return None
    x = m[0].replace(".", "").replace(",", ".")
    try:
        return float(x)
    except:
        return None


def preco_num(s):
    if not s or not isinstance(s, str): return None
    m = re.findall(r"[\d\.,]+", s)
    if not m: return None
    x = m[0].replace(".", "").replace(",", ".")
    try:
        return float(x)
    except:
        return None


def write_excel_with_matrix(df, out_path: Path):
    cols = ["EMPRESA", "CODIGO", "DESCRICAO", "ESTOQUE", "LINHA", "PRECO"]
    det = df[cols].copy()
    det.to_excel(out_path, index=False)
    tmp = df.copy()
    tmp["ESTOQUE_NUM"] = tmp["ESTOQUE"].apply(estoque_num)
    piv = tmp.pivot_table(index="CODIGO", columns="EMPRESA", values="ESTOQUE_NUM", aggfunc="first")
    desc_map = tmp.dropna(subset=["DESCRICAO"]).drop_duplicates("CODIGO").set_index("CODIGO")["DESCRICAO"]
    piv.insert(0, "DESCRICAO", desc_map.reindex(piv.index).fillna(""))
    with pd.ExcelWriter(out_path, mode="a", engine="openpyxl", if_sheet_exists="replace") as w:
        piv.to_excel(w, sheet_name="Matriz_Estoque")


def write_json(df, json_path: Path):
    records = []
    for _, row in df.iterrows():
        est = estoque_num(str(row.get("ESTOQUE", "")))
        preco = preco_num(str(row.get("PRECO", "")))
        records.append({
            "empresa": str(row["EMPRESA"]),
            "codigo": int(str(row["CODIGO"]).replace(".0", "").strip()) if str(row["CODIGO"]).replace(".0", "").strip().isdigit() else str(row["CODIGO"]),
            "descricao": str(row.get("DESCRICAO", "")),
            "linha": str(row.get("LINHA", "")),
            "estoque": est,
            "preco": preco,
        })
    payload = {
        "last_update": datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M"),
        "data": records,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"JSON gerado: {json_path} ({len(records)} registros)")


def run(produtos: Path, saida: Path, json_out, username: str, password: str, headful: bool, empresa: str = "", batch: int = 0, total: int = 1):
    df = pd.read_excel(produtos) if produtos.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(produtos)
    if "CODIGO" not in df.columns:
        for alt in ["Codigo", "CÓDIGO", "COD", "SKU", "Produto", "PRODUTO"]:
            if alt in df.columns:
                df = df.rename(columns={alt: "CODIGO"}); break
    df = df.dropna(subset=["CODIGO"]).copy()
    df["CODIGO"] = df["CODIGO"].astype(str).str.replace(".0", "", regex=False).str.strip()
    codigos = df["CODIGO"].tolist()
    if total > 1:
        codigos = codigos[batch::total]
        log(f"Batch {batch} de {total} — {len(codigos)} códigos")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.goto(URL, timeout=60000)

        if username and password:
            do_login(page, username, password)
        else:
            log("Credenciais não fornecidas. Faça login manualmente.")
            print("Quando a HOME carregar, volte ao terminal e pressione ENTER."); input()

        go_to_produtos(page)
        lojas = get_companies(page)

        if empresa:
            matched = [l for l in lojas if empresa.lower() in l.lower()]
            if not matched:
                raise ValueError(f"Empresa '{empresa}' não encontrada. Disponíveis: {lojas}")
            lojas = matched
            log(f"Filtrando para empresa: {lojas[0]}")

        for loja in lojas:
            go_to_produtos(page)
            select_company(page, loja)
            for code in codigos:
                try:
                    buscar_codigo(page, code)
                    data = ler_linha(page, code)
                    if data is None:
                        rows.append({"EMPRESA": loja, "CODIGO": code, "DESCRICAO": "", "ESTOQUE": "N/D", "LINHA": "", "PRECO": ""})
                    else:
                        data["EMPRESA"] = loja
                        rows.append(data)
                    log(f"[{loja}] {code} => {rows[-1]['ESTOQUE']}")
                except Exception as e:
                    rows.append({"EMPRESA": loja, "CODIGO": code, "DESCRICAO": "", "ESTOQUE": f"ERRO: {e}", "LINHA": "", "PRECO": ""})
                    log(f"[{loja}] {code} => ERRO {e}")

        saida.parent.mkdir(parents=True, exist_ok=True)
        df_out = pd.DataFrame(rows).sort_values(["EMPRESA", "CODIGO"])
        write_excel_with_matrix(df_out, saida)
        log(f"Excel gerado: {saida}")

        if json_out:
            write_json(df_out, Path(json_out))

        ctx.close()
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--produtos", type=Path, default=Path("scraper/produtos.csv"))
    ap.add_argument("--saida", type=Path, default=Path("scraper/saidas/estoque_por_loja.xlsx"))
    ap.add_argument("--json", dest="json_out", default=None, help="Caminho para data.json")
    ap.add_argument("--username", default=os.getenv("WEBAPP_USERNAME", ""))
    ap.add_argument("--password", default=os.getenv("WEBAPP_PASSWORD", ""))
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--empresa", default="", help="Scrape apenas esta empresa (substring do nome)")
    ap.add_argument("--batch", type=int, default=0, help="Índice deste batch (0..total-1)")
    ap.add_argument("--total", type=int, default=1, help="Quantos batches no total (1=sem fatia)")
    a = ap.parse_args()
    run(a.produtos, a.saida, a.json_out, a.username, a.password, a.headful, a.empresa, a.batch, a.total)


if __name__ == "__main__":
    main()
