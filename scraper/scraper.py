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

# Nome da empresa -> código curto da loja (para nomear arquivos)
EMPRESA_TO_LOJA = {
    "camaragibe": "CAM",
    "cavaleiro":  "CAV",
    "caxang":     "CAX",
    "lourenço":   "SLM",
    "lourenco":   "SLM",
    "são lou":    "SLM",
}


def log(x): print(time.strftime("%H:%M:%S"), "|", x, flush=True)
def nap(s=0.30): time.sleep(s)


def loja_codigo(nome):
    low = (nome or "").lower()
    for chave, cod in EMPRESA_TO_LOJA.items():
        if chave in low:
            return cod
    return re.sub(r"[^A-Za-z0-9]", "", nome)[:6].upper() or "LOJA"


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


def click_buscar(page):
    for s in ["xpath=//button[contains(.,'Buscar')]", "css=button:has-text('Buscar')", "role=button[name='Buscar']"]:
        try: page.locator(s).first.click(timeout=2000); return True
        except: pass
    return False


def exportar_excel(page, out_path: Path):
    """Clica no botão de exportar Excel da tabela e captura o arquivo baixado."""
    # Candidatos para o botão/ícone de export Excel do PrimeFaces.
    # A tela mostra um ícone verde de planilha acima da tabela.
    candidatos = [
        "css=img[src*='excel']",
        "css=img[src*='xls']",
        "css=a[id*='xls'] img, a[id*='excel'] img",
        "css=button[id*='xls'], button[id*='excel'], a[id*='xls'], a[id*='excel']",
        "css=[title*='Excel'], [title*='excel'], [title*='xcel']",
        "css=[onclick*='xls'], [onclick*='excel']",
        "xpath=//*[contains(@id,'xls') or contains(@id,'excel')]",
        "css=.ui-datatable img[src*='.png']",  # fallback: ícone clicável acima da tabela
    ]

    alvo = None
    usado = None
    for sel in candidatos:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                alvo = loc
                usado = sel
                break
        except:
            continue

    if alvo is None:
        raise RuntimeError("Botão de exportar Excel não encontrado na tela.")

    log(f"Botão de exportar localizado via: {usado}")
    try:
        alvo.scroll_into_view_if_needed()
    except:
        pass

    with page.expect_download(timeout=120000) as dl_info:
        alvo.click(timeout=5000)
    download = dl_info.value
    download.save_as(str(out_path))
    log(f"Excel baixado: {out_path}")


def estoque_num(s):
    if s is None: return None
    s = str(s).strip()
    if not s or s.upper() == "N/D": return None
    m = re.findall(r"[\d\.,]+", s)
    if not m: return None
    x = m[0].replace(".", "").replace(",", ".")
    try:
        return float(x)
    except:
        return None


def preco_num(s):
    if s is None: return None
    s = str(s).strip()
    if not s: return None
    m = re.findall(r"[\d\.,]+", s)
    if not m: return None
    x = m[0].replace(".", "").replace(",", ".")
    try:
        return float(x)
    except:
        return None


def _achar_coluna(cols, *palavras):
    """Acha o nome da coluna que contém alguma das palavras (case-insensitive)."""
    for c in cols:
        low = str(c).lower()
        for p in palavras:
            if p in low:
                return c
    return None


def xlsx_para_registros(xlsx_path: Path, empresa: str):
    """Lê o Excel exportado e devolve lista de registros no formato do consolidar."""
    df = pd.read_excel(xlsx_path, dtype=str).fillna("")
    cols = list(df.columns)
    log(f"Colunas do Excel ({loja_codigo(empresa)}): {cols}")

    c_cod  = _achar_coluna(cols, "cód", "cod")
    c_lin  = _achar_coluna(cols, "linha")
    c_desc = _achar_coluna(cols, "desc")
    c_est  = _achar_coluna(cols, "estoque", "saldo", "qtd", "quant")
    c_pre  = _achar_coluna(cols, "preç", "prec", "valor")

    if c_cod is None:
        raise RuntimeError(f"Coluna de código não encontrada em {cols}")

    registros = []
    for _, row in df.iterrows():
        cod = str(row.get(c_cod, "")).replace(".0", "").strip()
        if not cod:
            continue
        registros.append({
            "empresa":   empresa,
            "codigo":    cod,
            "descricao": str(row.get(c_desc, "")).strip() if c_desc else "",
            "linha":     str(row.get(c_lin, "")).strip() if c_lin else "",
            "estoque":   estoque_num(row.get(c_est, "")) if c_est else None,
            "preco":     preco_num(row.get(c_pre, "")) if c_pre else None,
        })
    log(f"{loja_codigo(empresa)}: {len(registros)} produtos lidos do Excel")
    return registros


def write_json(registros, json_path: Path):
    payload = {
        "last_update": datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M"),
        "data": registros,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"JSON gerado: {json_path} ({len(registros)} registros)")


def run(saida_dir: Path, username: str, password: str, headful: bool, empresa: str = ""):
    saida_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
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
            cod = loja_codigo(loja)
            try:
                go_to_produtos(page)
                select_company(page, loja)
                # Lista o catálogo completo da loja (busca sem filtros)
                clear_filters(page)
                click_buscar(page)
                pf_idle(page, timeout=20000)
                nap(0.5)

                xlsx_path = saida_dir / f"raw_{cod}.xlsx"
                exportar_excel(page, xlsx_path)

                registros = xlsx_para_registros(xlsx_path, loja)
                write_json(registros, saida_dir / f"json_{cod}.json")
            except Exception as e:
                log(f"[{loja}] ERRO: {e}")
                # Grava JSON vazio pra não travar a consolidação
                write_json([], saida_dir / f"json_{cod}.json")

        ctx.close()
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida-dir", dest="saida_dir", type=Path, default=Path("resultados"),
                    help="Pasta onde salvar os JSONs/Excels por loja")
    ap.add_argument("--username", default=os.getenv("WEBAPP_USERNAME", ""))
    ap.add_argument("--password", default=os.getenv("WEBAPP_PASSWORD", ""))
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--empresa", default="", help="Coletar apenas esta empresa (substring do nome)")
    a = ap.parse_args()
    run(a.saida_dir, a.username, a.password, a.headful, a.empresa)


if __name__ == "__main__":
    main()
