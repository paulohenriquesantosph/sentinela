# -*- coding: utf-8 -*-
"""Teste ponta a ponta no navegador real (Chrome) — Banco de Dossiês, Resolução e Avaliação.

NÃO faz parte do `requirements.txt`: precisa de `playwright` e `pypdf` num venv à parte, por exemplo
    python3 -m venv /tmp/e2e && /tmp/e2e/bin/pip install playwright pypdf
e roda a partir da raiz do projeto:
    /tmp/e2e/bin/python tests/e2e_playwright.py

O que ele faz:
  1. sobe um servidor de IA falso (tests.test_ia.FakeLLM) e o app (venv do projeto) com um diretório de dados novo;
  2. cria um caso pelo preenchimento automático e gera o dossiê;
  3. confere o JSON, o índice e o PDF gravados em disco;
  4. busca o caso no Banco (por trecho do número, sem diferenciar maiúsculas), abre e confere as 3 abas;
  5. preenche e salva a Resolução e a Avaliação (nota 70%), recarrega a página, reabre pelo Banco e
     confere que tudo foi persistido e que o PDF completo traz Resolução e Avaliação;
  6. confere busca sem resultado.
Sai com código 1 se algo falhar.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PY_PROJETO = os.path.join(RAIZ, "venv", "bin", "python")
PORTA = int(os.environ.get("E2E_PORT", "8611"))

from playwright.sync_api import sync_playwright  # noqa: E402
from pypdf import PdfReader  # noqa: E402

FALHAS = []


def confere(cond, msg):
    print(("  ok   " if cond else "  FALHOU ") + msg)
    if not cond:
        FALHAS.append(msg)


def fake_llm():
    """Sobe o FakeLLM em um processo filho (precisa do venv do projeto) e devolve (processo, url)."""
    codigo = ("import sys,time; sys.path.insert(0,%r); from tests.test_ia import FakeLLM; f=FakeLLM(); "
              "print(f.url, flush=True); time.sleep(3600)" % RAIZ)
    proc = subprocess.Popen([PY_PROJETO, "-c", codigo], stdout=subprocess.PIPE, text=True, cwd=RAIZ)
    return proc, proc.stdout.readline().strip()


def main():
    dados = tempfile.mkdtemp(prefix="sentinela_e2e_")
    llm, url_llm = fake_llm()
    env = dict(os.environ, SENTINELA_DATA_DIR=dados, ANTHROPIC_API_KEY="fake", ANTHROPIC_BASE_URL=url_llm,
               SENTINELA_LLM_FORMATO="openai", SENTINELA_LLM_MODELO="fake")
    app = subprocess.Popen([PY_PROJETO, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
                            "--server.port", str(PORTA), "--browser.gatherUsageStats", "false"],
                           cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://localhost:{PORTA}/_stcore/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True)
            pg = b.new_page(viewport={"width": 1280, "height": 4500})

            def abrir():
                pg.goto(f"http://localhost:{PORTA}/", wait_until="networkidle")
                pg.wait_for_timeout(1500)

            def clicar(nome, exato=False):
                pg.get_by_role("button", name=nome, exact=exato).first.click()
                pg.wait_for_timeout(1300)

            # ---- 1. criar o caso pela IA e gerar o dossiê
            print("1) Criar caso e gerar dossiê")
            abrir()
            clicar("Iniciar novo caso")
            clicar("Pessoa Física (PF)")
            clicar("Preencher com instruções")
            pg.get_by_label("Nome do alerta", exact=False).fill("Transfer In")
            pg.keyboard.press("Tab")
            pg.get_by_label("Sentença", exact=False).first.fill("Alerta por volume incompatível com a renda.")
            pg.keyboard.press("Control+Enter")
            pg.locator("textarea").nth(1).fill("Cliente João Paulo, 28 anos, renda R$1.200,00, R$500 mil em créditos e débitos.")
            pg.keyboard.press("Control+Enter")
            pg.wait_for_timeout(500)
            clicar("Preencher automaticamente")
            pg.wait_for_timeout(2500)
            confere("Revise o que a IA preencheu" in pg.inner_text("body") or "Bloco 1" in pg.inner_text("body").title()
                    or "BLOCO 1" in pg.inner_text("body").upper(), "formulário aberto com os dados da IA")
            clicar("Gerar dossiê do caso")
            pg.wait_for_timeout(3000)
            corpo = pg.inner_text("body")
            m = re.search(r"Dossiê (\d{4}-[0-9A-F]{6}) salvo no Banco de Dossiês", corpo)
            confere(bool(m), "tela confirma a gravação no Banco")
            numero = m.group(1) if m else ""

            # ---- 2. conferir o que foi gravado em disco
            print("2) Conferir arquivos gravados")
            caminho = os.path.join(dados, f"caso_{numero}.json")
            confere(os.path.exists(caminho), "caso_<número>.json existe")
            caso = json.load(open(caminho, encoding="utf-8"))
            confere(caso["nome_cliente"] == "João Paulo Carvalho Dias", "nome do cliente gravado")
            confere(caso["fator_gerador"] == "Transfer In" and caso["data_alerta"], "campos do analista preservados")
            confere(len(caso["contrapartes_credito"]) == 5 and len(caso["arredondamento_itens"]) == 6,
                    "contrapartes e arredondamento gravados")
            confere(abs(sum(caso["timeline_creditos"]) - 500000) < 0.01, "série do gráfico soma o total de créditos")
            indice = json.load(open(os.path.join(dados, "indice_dossies.json"), encoding="utf-8"))
            confere(any(i["numero_caso"] == numero for i in indice), "caso aparece no índice")
            pdf0 = os.path.join(dados, "pdfs", f"dossie_{numero}.pdf")
            confere(os.path.exists(pdf0), "PDF do dossiê gravado")

            # ---- 3. buscar no Banco, abrir e conferir
            print("3) Buscar e abrir pelo Banco")
            abrir()
            clicar("Banco de dossiês")
            pg.get_by_label("Consultar por número", exact=False).fill(numero[-4:].lower())
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(1500)
            confere(numero in pg.inner_text("body"), "busca por trecho (minúsculas) encontra o caso")
            pg.get_by_label("Consultar por número", exact=False).fill("ZZZZ-999999")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(1500)
            confere("Nenhum caso encontrado" in pg.inner_text("body"), "busca sem resultado mostra a mensagem")
            clicar("Consultar banco de dados completo")
            confere(numero in pg.inner_text("body"), "consulta completa lista o caso")
            pg.get_by_role("button", name=numero).first.click()
            pg.wait_for_timeout(2500)
            corpo = pg.inner_text("body")
            confere("João Paulo Carvalho Dias" in corpo and "Alerta / Sentença" in corpo, "dossiê abre com a aba Informações")
            confere("Abril R$160.000,00" in corpo, "mudança de comportamento atribui o pico ao 1º mês do período")

            # ---- 4. Resolução
            print("4) Resolução do caso")
            pg.get_by_role("tab", name="Resolução do Caso").click()
            pg.wait_for_timeout(1200)
            confere("DILIGÊNCIA PENDENTE" in pg.inner_text("body").upper(), "selo 'Diligência pendente'")
            pg.get_by_placeholder("Elaboração livre do parecer").fill("Cliente com renda de R$1.200,00 movimentou R$500.000,00.")
            pg.keyboard.press("Control+Enter")
            pg.wait_for_timeout(600)
            pg.get_by_role("button", name="Salvar", exact=True).first.click()
            pg.wait_for_timeout(2500)
            confere("preenchido e bloqueado" in pg.inner_text("body").lower(), "seção Parecer bloqueada após salvar")
            pg.get_by_placeholder("Insira as alíneas").fill("Movimentação incompatível; fragmentação.")
            pg.keyboard.press("Control+Enter")
            pg.wait_for_timeout(600)
            pg.get_by_text("Ausência de Resposta ao EDD").click()
            pg.get_by_text("Movimentação Expressiva Acompanhada por Fragmentação").click()
            pg.get_by_text("Cancelamento de Conta Investimento (NuInvest)").click()
            pg.wait_for_timeout(600)
            pg.get_by_role("combobox").last.click()
            pg.wait_for_timeout(500)
            pg.get_by_role("option", name="Reportar e Cancelar").click()
            pg.wait_for_timeout(800)
            pg.get_by_role("button", name="Salvar informações do caso").click()
            pg.wait_for_timeout(3000)
            corpo = pg.inner_text("body")
            confere("REPORTAR E CANCELAR" in corpo.upper() and "bloqueado" in corpo.lower(), "salvar o caso trava a aba e muda o selo")
            confere(pg.get_by_role("button", name="Baixar versão atualizada em PDF").first.is_enabled(), "PDF da Resolução liberado")

            # ---- 5. Avaliação
            print("5) Avaliação de qualidade")
            pg.get_by_role("tab", name="Avaliação de Qualidade").click()
            pg.wait_for_timeout(1200)
            confere("100%" in pg.inner_text("body"), "nota inicial 100%")
            for rotulo in ("Foi suprimida informação ou movimentação relevante",
                           "Faltou incluir macro e/ou processo de alertas específicos",
                           "Não foi aberto alerta manual para encerramento de conta vinculada",
                           "Processo interno insuficiente"):
                pg.get_by_text(rotulo, exact=True).click()
                pg.wait_for_timeout(500)
            pg.wait_for_timeout(800)
            confere("70%" in pg.inner_text("body"), "2 Customer + 1 Business + 1 BI = 70% (desconto por categoria)")
            pg.locator("textarea").last.fill("Boa análise de capacidade financeira. Faltou detalhar a cronologia dos saques.")
            pg.keyboard.press("Control+Enter")
            pg.wait_for_timeout(500)
            pg.get_by_role("button", name="Salvar avaliação").click()
            pg.wait_for_timeout(3000)
            confere("Avaliação salva em" in pg.inner_text("body"), "avaliação salva")

            # ---- 6. persistência: recarrega tudo e reabre
            print("6) Persistência após recarregar")
            salvo = json.load(open(caminho, encoding="utf-8"))
            confere(salvo["diligencia"] == "Reportar e Cancelar", "diligência gravada no JSON")
            confere("Parecer" not in salvo["parecer_final"] and "R$1.200,00" in salvo["parecer_final"], "parecer gravado no JSON")
            confere(len(salvo["jurisprudencias_selecionadas"]) == 2, "jurisprudências gravadas")
            confere(salvo["razoes_cancelamento_selecionadas"] == ["Cancelamento de Conta Investimento (NuInvest)"], "razão de cancelamento gravada")
            confere(len(salvo["scorecard_drivers_marcados"]) == 4 and salvo["scorecard_salvo_em"], "avaliação gravada")
            abrir()
            clicar("Banco de dossiês")
            clicar("Consultar banco de dados completo")
            pg.get_by_role("button", name=numero).first.click()
            pg.wait_for_timeout(2500)
            pg.get_by_role("tab", name="Resolução do Caso").click()
            pg.wait_for_timeout(1000)
            corpo = pg.inner_text("body")
            confere("REPORTAR E CANCELAR" in corpo.upper() and "movimentou R$500.000,00" in corpo or
                    pg.get_by_role("textbox").first.input_value() != "", "Resolução reaparece depois de recarregar")
            pg.get_by_role("tab", name="Avaliação de Qualidade").click()
            pg.wait_for_timeout(1000)
            confere("70%" in pg.inner_text("body") and "Avaliação salva em" in pg.inner_text("body"), "Avaliação reaparece com nota 70%")
            b.close()

        # ---- 7. PDF completo contém as 3 abas
        print("7) PDF completo")
        texto = "\n".join((pg_.extract_text() or "") for pg_ in PdfReader(pdf0).pages)
        for trecho, rotulo in (("Alerta / Sentença", "Informações"), ("resolu", "Resolução"),
                               ("R$1.200,00 movimentou", "parecer"), ("Ausência de Resposta ao EDD", "jurisprudência marcada"),
                               ("Cancelamento de Conta Investimento", "razão de cancelamento"),
                               ("Reportar e Cancelar", "diligência"), ("Avaliação de Qualidade", "Avaliação"),
                               ("70%", "nota 70%"), ("Foi suprimida informação", "critério marcado"),
                               ("cronologia dos saques", "feedback")):
            confere(trecho.lower() in texto.replace("\n", " ").lower(), f"PDF completo contém {rotulo}")
    finally:
        app.terminate()
        llm.terminate()
        shutil.rmtree(dados, ignore_errors=True)
    print("\n" + ("TUDO OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)"))
    sys.exit(1 if FALHAS else 0)


if __name__ == "__main__":
    main()
