# -*- coding: utf-8 -*-
"""Grava os tutoriais do manual como GIFs animados: abre o app de demonstração (app_demo.py) no Chrome, executa
cada passo, tira capturas de tela e junta com legendas (Pillow). Uso: python gravar.py <cena|todas>
Requer: playwright (pip), Google Chrome instalado e o app_demo rodando em DEMO_URL (veja LEIA-ME)."""
import io
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

URL = os.environ.get("DEMO_URL", "http://localhost:8599")
CENA_ARQ = Path(os.environ["DEMO_CENA_ARQ"])
SAIDA = Path(__file__).resolve().parents[2] / "videos"
LARG, ALT = 1100, 760
ESCALA = 0.82
KYC_TXT = [
    "Nome: Carlos Eduardo Mendes", "Idade: 42 anos", "Cidade/Estado: Foz do Iguaçu/PR",
    "Profissão informada: Comerciante", "Registro profissional: sem registro profissional",
    "Renda presumida: R$ 3.500,00",
    "Registro societário: sócio de empresa do ramo de Serviços Combinados de Escritório",
    "Mora em região de fronteira, divisa com o Paraguai",
    "PEP relacionado: irmão de vereador, carência até 2027",
    "Mídia negativa: contrabando, G1, 10/03/2025",
    "Reporte ao COAF em 2024 por movimentação atípica",
    "Conta cancelada por fraude em 2023",
    "Compartilha dispositivo com outra conta",
]
MOV_TXT = [
    "Período de 01/01/2026 até 30/06/2026. Total de créditos R$ 450.000,00 e total de débitos R$ 430.000,00.",
    "Diversas contrapartes de crédito, pessoas físicas de renda baixa, em cidades diferentes, nomes aleatórios. Uma delas é PEP.",
    "2 contrapartes de débito, empresas de ramos diferentes, nomes aleatórios.",
    "Saques de R$ 15.000,00, boletos de R$ 8.500,00, gastos no cartão de crédito de R$ 12.000,00 e empréstimo de R$ 20.000,00.",
]
COMP_TXT = [
    "Fragmentação nos créditos. Diversas transações arredondadas em R$ 1.000,00 e R$ 2.000,00.",
    'Pix com mensagens "pagamento mercadoria" e "ajuda". Rápida evasão dos valores recebidos.',
    "Houve mudança de comportamento.",
]


def _fonte(tam):
    for c in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if Path(c).exists():
            return ImageFont.truetype(c, tam)
    return ImageFont.load_default()


class Gravador:
    def __init__(self, page, aviso_ia=False):
        self.page, self.quadros, self.aviso_ia = page, [], aviso_ia

    def snap(self, legenda, seg=1.6):
        self.page.wait_for_timeout(700)
        img = Image.open(io.BytesIO(self.page.screenshot())).convert("RGB")
        img = img.resize((int(img.width * ESCALA), int(img.height * ESCALA)), Image.LANCZOS)
        barra = 64
        quadro = Image.new("RGB", (img.width, img.height + barra), (62, 42, 99))
        quadro.paste(img, (0, 0))
        d = ImageDraw.Draw(quadro)
        tam = 20
        while tam > 12 and d.textlength(legenda, font=_fonte(tam)) > img.width - 32:
            tam -= 1  # reduz a fonte até a legenda caber
        d.text((16, img.height + 10), legenda, fill=(255, 255, 255), font=_fonte(tam))
        if self.aviso_ia:
            d.text((16, img.height + 38), "Demonstração: a resposta da IA é simulada neste vídeo.",
                   fill=(201, 167, 107), font=_fonte(14))
        self.quadros.append((quadro, int(seg * 1000)))

    def salvar(self, nome):
        SAIDA.mkdir(exist_ok=True)
        pal = [q.convert("P", palette=Image.ADAPTIVE, colors=128) for q, _ in self.quadros]
        pal[0].save(SAIDA / nome, save_all=True, append_images=pal[1:], duration=[d for _, d in self.quadros],
                    loop=0, optimize=True)
        print(nome, len(pal), "quadros", round((SAIDA / nome).stat().st_size / 1e6, 1), "MB")


def esperar(page, ms=900):
    page.wait_for_timeout(ms)


def clicar(page, nome):
    page.get_by_role("button", name=re.compile(nome, re.I)).first.click()
    esperar(page)


def digitar(page, rotulo, texto, area=False, exato=False):
    alvo = page.get_by_label(rotulo, exact=exato).first
    alvo.fill(texto)
    alvo.press("Tab")
    esperar(page, 600)


def aparece(page, texto, ms=30000):
    page.get_by_text(re.compile(texto, re.I)).first.wait_for(timeout=ms)


def ate_tela_ia(page, g=None):
    page.goto(URL)
    aparece(page, "Iniciar novo caso", 20000)
    if g:
        g.snap("Na home, clique em Iniciar novo caso.")
    clicar(page, "Iniciar novo caso")
    if g:
        g.snap("Etapa 1: escolha o tipo de caso (PF, PJ, Cripto, NuInvest ou Under 18).")
    clicar(page, "Pessoa Física")
    if g:
        g.snap("Etapa 2: escolha Preencher com instruções (automático).")
    clicar(page, "Preencher com instruções")


def alerta(page, g=None):
    digitar(page, "Nome do alerta", "Transfer In")
    digitar(page, "Sentença", "Cliente recebeu valores incompatíveis com a renda declarada.", area=True)
    if g:
        g.snap("Preencha Nome do alerta, Data e Sentença: o automático nunca os altera.")


def escrever(page, g, chave, linhas, legenda_fn):
    acumulado = []
    for i, linha in enumerate(linhas):
        acumulado.append(linha)
        digitar(page, chave, "\n".join(acumulado), area=True)
        if i in legenda_fn:
            g.snap(legenda_fn[i], 1.8)
    return acumulado


def rolar_ate(page, texto, extra=0):
    page.get_by_text(texto, exact=False).first.scroll_into_view_if_needed()
    if extra:
        page.mouse.wheel(0, extra)
    esperar(page, 800)


def cena_inicio(p):
    page = p.new_page()
    g = Gravador(page)
    ate_tela_ia(page, g)
    alerta(page, g)
    g.snap("Depois escreva as informações nas três caixas: KYC, Movimentações e Comportamentos.", 2.2)
    g.salvar("01_iniciar_caso.gif")


def cena_kyc(p):
    CENA_ARQ.write_text("kyc")
    page = p.new_page()
    g = Gravador(page, aviso_ia=True)
    ate_tela_ia(page)
    alerta(page)
    page.get_by_label("Informações do KYC do cliente").scroll_into_view_if_needed()
    esperar(page, 500)
    escrever(page, g, "Informações do KYC do cliente", KYC_TXT, {
        0: "KYC: escreva uma informação por linha. Cada dado vai para o seu campo.",
        5: "Nome, idade, cidade, profissão, registro profissional e renda: cada um no seu campo.",
        6: "Registro societário: cite o ramo da empresa.",
        7: "Região de fronteira, garimpo ou extração mineral: marca Região de Risco = Sim.",
        8: "PEP, mídia negativa, COAF e fraude: marcam Sim e levam o texto para o detalhe.",
        12: "Qualquer outra informação vai para Outras informações relevantes.",
    })
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "Razão social.*aleatoriamente")
    esperar(page, 800)
    g.snap("O Sentinela pergunta só o que faltou. Aqui, os dados da empresa do registro societário.", 2.4)
    for k in ("Razão social", "Data de abertura", "Situação cadastral"):
        page.get_by_text(re.compile(f"{k}.*aleatoriamente")).first.click()
        esperar(page, 800)
    g.snap('Marque "pode preencher aleatoriamente" para o Sentinela criar esses dados, ou digite os seus.', 2.4)
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "KYC - Know Your Customer")
    rolar_ate(page, "KYC - Know Your Customer")
    g.snap("O formulário abre preenchido: revise o Bloco 2 (KYC).", 2.2)
    for legenda in ("Cidade/Estado, profissão, renda e registro societário nos campos próprios.",
                    "Região de Risco, PEP, mídia negativa, histórico de PLD e de fraude com o texto de cada um.",
                    "Outras informações relevantes recebe o que não tem campo."):
        page.mouse.wheel(0, 400)
        g.snap(legenda, 2.4)
    g.salvar("02_kyc.gif")


def cena_mov(p):
    CENA_ARQ.write_text("movimentacoes")
    page = p.new_page()
    g = Gravador(page, aviso_ia=True)
    ate_tela_ia(page)
    alerta(page)
    page.get_by_label("Informações das Movimentações do cliente").scroll_into_view_if_needed()
    esperar(page, 500)
    escrever(page, g, "Informações das Movimentações do cliente", MOV_TXT, {
        0: "Movimentações: informe o período e os totais de créditos e débitos.",
        1: 'Descreva as contrapartes: "diversas", renda baixa, cidades diferentes, nomes aleatórios.',
        2: "Contrapartes de débito: empresas de ramos diferentes. Sem menção, os sinais de KYC ficam Não.",
        3: "Outras movimentações: cite o tipo (saque, boleto, cartão, empréstimo) e o valor.",
    })
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "Contraparte de crédito 1")
    esperar(page, 600)
    g.snap('Como você disse que uma contraparte é PEP, o Sentinela pergunta o detalhe.', 2.4)
    digitar(page, re.compile(r"^PEP"), "PEP Titular: vereador de Recife, carência até 2028")
    g.snap("Escreva a informação no campo pequeno e clique em Continuar.", 2.0)
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "Resumo de movimentações")
    rolar_ate(page, "Resumo de movimentações")
    g.snap("Bloco 3: período e totais preenchidos.", 2.2)
    for legenda in ("Contrapartes de crédito com nomes, cidades e rendas diferentes. Só a PEP tem sinal Sim.",
                    "Contrapartes de débito: empresas com ramo, porte e faturamento."):
        page.mouse.wheel(0, 650)
        g.snap(legenda, 2.4)
    rolar_ate(page, "Outras movimentações (opcional)", 200)
    g.snap("Outras movimentações: uma linha por tipo, com o valor que você escreveu.", 3.0)
    g.salvar("03_movimentacoes.gif")


def cena_comp(p):
    CENA_ARQ.write_text("comportamentos")
    page = p.new_page()
    g = Gravador(page, aviso_ia=True)
    ate_tela_ia(page)
    alerta(page)
    page.get_by_label("Informações dos Comportamentos do cliente").scroll_into_view_if_needed()
    esperar(page, 500)
    escrever(page, g, "Informações dos Comportamentos do cliente", COMP_TXT, {
        0: "Comportamentos: fragmentação e transações arredondadas.",
        1: "Pix com mensagens e rápida evasão dos valores recebidos.",
        2: 'Escreva "houve mudança de comportamento" para o Sentinela montar a narrativa.',
    })
    aparece(page, "Abertura da conta", 15000)
    page.get_by_label("Abertura da conta").scroll_into_view_if_needed()
    esperar(page, 500)
    g.snap("Aparecem campos extras: informe a abertura da conta (antes da data do alerta).", 2.4)
    digitar(page, "Abertura da conta", "10/01/2025")
    g.snap("O valor do mês da mudança é opcional. Sem ele, o Sentinela cria um valor.", 2.0)
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "Resumo de movimentações")
    rolar_ate(page, "Thundera")
    g.snap("Bloco 4: Thundera / AML 360 preenchido.", 2.2)
    for legenda in ("Arredondamento: várias linhas, por valor e por lado.",
                    "Mensagens Pix e timeline de transferências (Rápida Evasão).",
                    "Mudança de comportamento: narrativa dos 6 meses e data de abertura da conta."):
        page.mouse.wheel(0, 650)
        g.snap(legenda, 2.4)
    g.salvar("04_comportamentos.gif")


def cena_final(p):
    CENA_ARQ.write_text("completo")
    page = p.new_page()
    g = Gravador(page, aviso_ia=True)
    ate_tela_ia(page)
    alerta(page)
    digitar(page, "Informações do KYC do cliente", "\n".join(KYC_TXT), area=True)
    digitar(page, "Informações das Movimentações do cliente", "\n".join(MOV_TXT), area=True)
    digitar(page, "Informações dos Comportamentos do cliente", "\n".join(COMP_TXT), area=True)
    digitar(page, "Abertura da conta", "10/01/2025")
    page.get_by_label("Informações dos Comportamentos do cliente").scroll_into_view_if_needed()
    g.snap("Com as três caixas escritas, clique em Preencher automaticamente.", 2.4)
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "Razão social.*aleatoriamente")
    page.get_by_text(re.compile("Razão social.*aleatoriamente")).first.scroll_into_view_if_needed()
    g.snap("Responda as perguntas que o Sentinela fizer (ou aceite o preenchimento aleatório).", 2.4)
    for k in ("Razão social", "Data de abertura", "Situação cadastral"):
        page.get_by_text(re.compile(f"{k}.*aleatoriamente")).first.click()
        esperar(page, 700)
    digitar(page, re.compile(r"^PEP"), "PEP Titular: vereador de Recife, carência até 2028")
    clicar(page, "Preencher automaticamente|Continuar")
    aparece(page, "KYC - Know Your Customer")
    page.evaluate("window.scrollTo(0, 0)")
    esperar(page, 700)
    page.mouse.wheel(0, -30000)
    esperar(page, 800)
    g.snap("O formulário abre preenchido. Revise os Blocos 1 a 4 antes de gerar.", 2.4)
    page.get_by_role("button", name=re.compile("Gerar dossiê do caso", re.I)).first.scroll_into_view_if_needed()
    g.snap("Tudo certo? Clique em Gerar dossiê do caso.", 2.2)
    clicar(page, "Gerar dossiê do caso")
    aparece(page, "Clique aqui para ver o dossiê", 60000)
    page.get_by_text(re.compile("Clique aqui para ver o dossiê")).first.scroll_into_view_if_needed()
    esperar(page, 800)
    g.snap("O dossiê é salvo no Banco de Dossiês. Clique para abri-lo e baixe o PDF.", 2.6)
    clicar(page, "Clique aqui para ver o dossiê")
    aparece(page, "Resolução do Caso", 30000)
    page.mouse.wheel(0, -30000)
    esperar(page, 800)
    g.snap("O dossiê tem três abas: Informações, Resolução e Avaliação de Qualidade.", 2.8)
    page.get_by_role("tab", name=re.compile("Resolução do Caso")).click()
    esperar(page, 900)
    g.snap("Na Resolução, preencha o parecer e a diligência e use Salvar.", 2.4)
    page.goto(URL)
    aparece(page, "Banco de dossiês", 20000)
    clicar(page, "Banco de dossiês")
    clicar(page, "Consultar banco de dados completo")
    esperar(page, 1200)
    g.snap("Para reabrir um caso: Banco de dossiês, busca por número ou banco completo.", 3.0)
    g.salvar("05_gerar_dossie.gif")


CENAS = {"inicio": cena_inicio, "kyc": cena_kyc, "mov": cena_mov, "comp": cena_comp, "final": cena_final}

if __name__ == "__main__":
    nomes = list(CENAS) if sys.argv[1:] == ["todas"] else sys.argv[1:]
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(channel="chrome", headless=True)
        ctx = navegador.new_context(viewport={"width": LARG, "height": ALT})
        for n in nomes:
            CENAS[n](ctx)
        navegador.close()
