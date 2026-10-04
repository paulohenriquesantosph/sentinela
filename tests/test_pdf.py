# -*- coding: utf-8 -*-
"""Testes do PDF do dossiê (pdf_dossie.py).

Rodar:  ./venv/bin/python -m unittest tests.test_pdf -v

Se o pypdf estiver instalado, o conteúdo do PDF é conferido pelo texto extraído;
sem ele, os testes validam só que o PDF é gerado (cabeçalho %PDF e tamanho).
Para salvar os PDFs gerados (inspeção visual), defina SENTINELA_PDF_OUT=<pasta>.
"""
import os
import sys
import unittest
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import pdf_dossie  # noqa: E402
from core import (  # noqa: E402
    Caso, ContraparteMovimentacao, OutraMovimentacao, ItemArredondamento, MensagemPix, Socio,
)

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def texto_pdf(pdf: bytes) -> str:
    if PdfReader is None:
        return ""
    r = PdfReader(BytesIO(pdf))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def n_paginas(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages) if PdfReader else 0


def _cp(nome, pct, valor, trans, idade, cidade, renda, reg):
    return ContraparteMovimentacao(
        tipo="Pessoa Física", nome=nome, porcentagem=pct, valor=valor, num_transacoes=trans,
        idade=idade, cidade_estado=cidade, renda_presumida=renda, registro_profissional=reg)


def caso_joao() -> Caso:
    c = Caso(numero_caso="2026-8058FB", tipo_caso="Pessoa Física (PF)")
    c.fator_gerador = "Transfer In"
    c.data_alerta = "01/10/2026"
    c.sentenca = ("Alerta disparado por volume de créditos recebidos incompatível com a renda "
                  "presumida do cliente, com indícios de fragmentação e rápida evasão dos recursos.")
    c.nome_cliente = "João Paulo Carvalho Dias"
    c.genero = "M"
    c.idade = "28"
    c.cidade_estado = "São Paulo/SP"
    c.ultima_atualizacao_cadastral = "15/03/2026"
    c.profissao_informada = "Auxiliar administrativo"
    c.renda_presumida = "R$1.200,00"
    c.registro_profissional = "Sem registros profissionais"
    c.outras_info = "Sem redes sociais vinculadas; não foram localizados processos judiciais."
    c.mov_periodo = "01/04/2026 até 30/09/2026"
    c.mov_total_credito = "R$500.000,00"
    c.mov_total_contrapartes_credito = "63"
    c.mov_total_debito = "R$500.000,00"
    c.mov_total_contrapartes_debito = "52"
    c.contrapartes_credito = [
        _cp("Marcos Vinícius Andrade", "14%", "R$70.000,00", "23", "34", "Belo Horizonte/MG", "R$2.100,00", "Pedreiro, sem registro profissional"),
        _cp("Fernanda Lopes Ribeiro", "11%", "R$55.000,00", "18", "41", "Contagem/MG", "R$1.600,00", "Auxiliar de limpeza, sem registro profissional"),
        _cp("Rafael Souza Nunes", "9%", "R$45.000,00", "15", "26", "Betim/MG", "R$1.900,00", "Motoboy, sem registro profissional"),
        _cp("Camila Teixeira Rocha", "7%", "R$35.000,00", "12", "30", "Ribeirão das Neves/MG", "R$1.450,00", "Atendente de lanchonete, sem registro profissional"),
        _cp("Anderson Pires Moura", "6%", "R$30.000,00", "10", "45", "Sete Lagoas/MG", "R$1.750,00", "Porteiro, sem registro profissional"),
    ]
    c.contrapartes_debito = [
        _cp("Diego Henrique Martins", "16%", "R$80.000,00", "20", "29", "São Paulo/SP", "R$1.800,00", "Ajudante geral"),
        _cp("Patrícia Gomes Silva", "12%", "R$60.000,00", "16", "37", "Guarulhos/SP", "R$1.500,00", "Diarista"),
        _cp("Lucas Ferreira Alves", "10%", "R$50.000,00", "14", "24", "Osasco/SP", "R$1.700,00", "Repositor"),
        _cp("Juliana Costa Pereira", "8%", "R$40.000,00", "11", "33", "Santo André/SP", "R$2.000,00", "Cabeleireira"),
        _cp("Thiago Ramos Oliveira", "6%", "R$30.000,00", "9", "31", "São Bernardo do Campo/SP", "R$1.650,00", "Garçom"),
    ]
    c.outras_movimentacoes = [OutraMovimentacao(
        tipo="Saques",
        info="R$90.000,00 em 38 saques fragmentados (R$1.500,00 a R$3.000,00) em terminais de 9 localidades.")]
    c.comp_arredondamento = "Sim"
    c.arredondamento_itens = [
        ItemArredondamento("Créditos", "84", "R$1.000,00"), ItemArredondamento("Créditos", "41", "R$2.000,00"),
        ItemArredondamento("Créditos", "17", "R$5.000,00"), ItemArredondamento("Débitos", "62", "R$1.000,00"),
        ItemArredondamento("Débitos", "35", "R$2.000,00"), ItemArredondamento("Débitos", "14", "R$5.000,00"),
    ]
    c.comp_pix = "Sim"
    c.pix_itens = [MensagemPix("Créditos", "12", "pagamento")]
    c.comp_evasao = "Rápida Evasão"
    core.aplicar_timeline_ao_caso(c)
    c.comp_mudanca_comportamento = core.gerar_narrativa_mudanca_comportamento(c.mov_periodo, "R$160.000,00")
    c.comp_data_abertura_ultimo_reporte = "10/01/2026"
    return c


def com_resolucao_e_avaliacao(c: Caso) -> Caso:
    c.parecer_final = ("Cliente com renda presumida de R$1.200,00 movimentou R$500.000,00 em créditos e "
                       "R$500.000,00 em débitos no período, de forma totalmente incompatível com sua "
                       "capacidade financeira.")
    c.alineas = "Movimentação incompatível com a capacidade financeira; fragmentação de valores."
    c.jurisprudencias_selecionadas = [
        "Ausência de Resposta ao EDD",
        "Movimentação Expressiva com Comportamento Suspeito e sem Fundamentação Econômico Financeira Identificada",
    ]
    c.razoes_cancelamento_selecionadas = ["Cancelamento de Conta Investimento (NuInvest)"]
    c.diligencia = "Reportar e Cancelar"
    c.resolucao_salva_em = {k: "2026-10-03T19:07:08" for k in c.secoes_resolucao()}
    c.resolucao_bloqueada_em = "2026-10-03T19:07:08"
    c.scorecard_drivers_marcados = [
        "Foi suprimida informação ou movimentação relevante",
        "Faltou incluir macro e/ou processo de alertas específicos",
        "Não foi aberto alerta manual para encerramento de conta vinculada",
        "Processo interno insuficiente",
    ]
    c.scorecard_feedback = "Boa análise de capacidade financeira. Faltou detalhar a cronologia dos saques."
    c.scorecard_salvo_em = "2026-10-03T19:07:09"
    return c


def salvar_para_inspecao(nome: str, pdf: bytes) -> None:
    pasta = os.environ.get("SENTINELA_PDF_OUT")
    if pasta:
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, nome), "wb") as f:
            f.write(pdf)


class TestEscopos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caso = com_resolucao_e_avaliacao(caso_joao())
        cls.completo = pdf_dossie.gerar_pdf(cls.caso, "completo")
        cls.resolucao = pdf_dossie.gerar_pdf(cls.caso, "resolucao")
        cls.avaliacao = pdf_dossie.gerar_pdf(cls.caso, "avaliacao")
        cls.info = pdf_dossie.gerar_pdf(cls.caso, "informacoes")
        salvar_para_inspecao("completo.pdf", cls.completo)
        salvar_para_inspecao("resolucao.pdf", cls.resolucao)
        salvar_para_inspecao("avaliacao.pdf", cls.avaliacao)

    def test_sao_pdfs_validos(self):
        for pdf in (self.completo, self.resolucao, self.avaliacao, self.info):
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertGreater(len(pdf), 2000)

    def test_escopo_invalido(self):
        with self.assertRaises(ValueError):
            pdf_dossie.gerar_pdf(self.caso, "xyz")

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_completo_tem_as_tres_abas(self):
        t = texto_pdf(self.completo)
        for trecho in [
            "2026-8058FB", "João Paulo Carvalho Dias",
            "Alerta / Sentença", "KYC - Know Your Customer", "Resumo de Movimentações", "Thundera - AML 360",
            "Marcos Vinícius Andrade", "53% restante é referente às demais contrapartes de crédito",
            "48% restante é referente às demais contrapartes de débito",
            "1. Saques:", "CRÉDITOS — VALOR 1", "DÉBITOS — VALOR 6", "Valores Movimentados por Mês",
            "Novembro R$1.000,00", "Abril R$160.000,00",
            # resolução
            "RESOLUÇÃO DO CASO", "REPORTAR E CANCELAR", "Parecer Final do Analista", "totalmente incompatível",
            "Ausência de Resposta ao EDD", "Comportamento Suspeito e sem Fundamentação",
            "Cancelamento de Conta Investimento (NuInvest)", "Diligência", "03/10/2026, 19:07:08",
            # avaliação
            "AVALIAÇÃO DE QUALIDADE", "Avaliação de Qualidade — AML Nupag", "70%",
            "Foi suprimida informação ou movimentação relevante",
            "Faltou incluir macro e/ou processo de alertas específicos",
            "Não foi aberto alerta manual para encerramento de conta vinculada",
            "Processo interno insuficiente", "Boa análise de capacidade financeira",
        ]:
            self.assertIn(trecho, t, f"faltou no PDF completo: {trecho!r}")

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_pdf_nao_classifica_risco_nem_diz_se_houve_mudanca(self):
        t = texto_pdf(self.completo)
        for proibido in ("RISCO ALTO", "Risco Geral", "Fatores", "Rápida evasão dos recursos", "Padrão",
                         "Mudança de Comportamento", "Sem mudança de comportamento"):
            self.assertNotIn(proibido, t, f"não deveria constar no PDF: {proibido!r}")

    def test_html_nao_classifica_risco_nem_diz_se_houve_mudanca(self):
        import dossie_html
        html = dossie_html.cabecalho_html(self.caso) + "".join(dossie_html.informacoes_html(self.caso))
        for proibido in ("Risco ALTO", "Risco MÉDIO", "Fatores considerados", "Padrão", "Mudança de Comportamento"):
            self.assertNotIn(proibido, html, f"não deveria constar no dossiê: {proibido!r}")
        self.assertIn("Valores Movimentados por Mês", html)
        self.assertIn("Abril R$160.000,00", html)

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_anexos_so_aparecem_no_caso_cripto(self):
        c = caso_joao()
        c.tipo_caso = "Cripto"
        c.anexos = "Extrato da exchange\nComprovante de residência"
        t = texto_pdf(pdf_dossie.gerar_pdf(c))
        for trecho in ("Anexos", "Extrato da exchange", "Comprovante de residência"):
            self.assertIn(trecho, t)
        c.anexos = ""
        self.assertIn("Nenhum anexo informado", texto_pdf(pdf_dossie.gerar_pdf(c)))
        c.tipo_caso = "Pessoa Física (PF)"
        self.assertNotIn("Nenhum anexo informado", texto_pdf(pdf_dossie.gerar_pdf(c)))


    def _caso_quase_vazio(self):
        c = Caso(numero_caso="2026-VAZIO1", tipo_caso="Pessoa Física (PF)")
        c.fator_gerador, c.data_alerta = "Transfer In", "15/06/2026"
        c.mov_periodo = "01/04/2026 até 30/06/2026"
        return c

    def test_html_esconde_campos_vazios(self):
        import dossie_html
        c = self._caso_quase_vazio()
        html = dossie_html.cabecalho_html(c) + "".join(dossie_html.informacoes_html(c))
        for proibido in ("Sem nome", "Não informado", "R$ 0,00", "R$0,00", "—", "Nenhuma contraparte",
                         "Descrição da Sentença", "Outras Informações Relevantes", "Outras Movimentações",
                         "Contrapartes Principais", "Informações Básicas do Cliente", "Cadastro e Registros"):
            self.assertNotIn(proibido, html, proibido)
        self.assertIn("Transfer In", html)  # o que foi informado continua aparecendo

    def test_sem_demais_contrapartes_nao_mostra_linha_de_restante(self):
        import dossie_html
        c = self._caso_quase_vazio()
        c.contrapartes_credito = [ContraparteMovimentacao(nome="Ana", porcentagem="100%", valor="R$10,00")]
        c.contrapartes_debito = [ContraparteMovimentacao(nome="Beto", porcentagem="30%", valor="R$3,00")]
        html = "".join(dossie_html.informacoes_html(c))
        self.assertNotIn('<div class="sx-resto">0% restante', html)
        self.assertNotIn("demais contrapartes de crédito", html)
        self.assertIn("70% restante é referente às demais contrapartes de débito", html)


    def _caso_cripto(self, tipo="Cripto"):
        import random as _r
        c = self._caso_quase_vazio()
        c.tipo_caso = tipo
        c.comp_evasao_cripto = "Rápida Evasão"
        c.outras_movimentacoes = [OutraMovimentacao(tipo="Criptomoedas", info="Enviou R$200.000,00 para exchange")]
        core.aplicar_timeline_cripto_ao_caso(c, _r.Random(3))
        return c

    def test_html_mostra_timeline_cripto_so_com_valor_e_grafico(self):
        import dossie_html
        html = "".join(dossie_html.informacoes_html(self._caso_cripto()))
        self.assertIn("Timeline de Transferências — Criptomoedas", html)
        self.assertIn("R$ 200.000,00", html)
        self.assertIn('alt="Timeline de Transferências — Criptomoedas"', html)
        self.assertNotIn("Rápida Evasão", html)  # o dossiê não diz se houve ou não rápida evasão
        for tipo in ("Pessoa Física (PF)", "NuInvest", "Under 18", "Pessoa Jurídica (PJ)"):
            outro = "".join(dossie_html.informacoes_html(self._caso_cripto(tipo)))
            self.assertNotIn("Timeline de Transferências — Criptomoedas", outro, tipo)
            self.assertNotIn("data:image/png", outro, tipo)

    def test_rotulo_do_valor_acompanha_o_lado_sem_dizer_o_modo(self):
        import dossie_html
        for modo, rotulo in (("Só Créditos (Sem Débitos)", "Créditos (criptomoedas)"),
                             ("Só Débitos (Sem Créditos)", "Débitos (criptomoedas)")):
            c = self._caso_cripto()
            c.comp_evasao_cripto = modo
            core.aplicar_timeline_cripto_ao_caso(c)
            html = "".join(dossie_html.informacoes_html(c))
            self.assertIn(rotulo, html)
            self.assertIn("R$ 200.000,00", html)
            for proibido in ("Só Créditos", "Só Débitos", "Sem Débitos", "Sem Créditos", "Rápida Evasão"):
                self.assertNotIn(proibido, html, proibido)
            self.assertTrue(pdf_dossie.gerar_pdf(c).startswith(b"%PDF"))


    def _caso_bancario(self, modo):
        import random as _r
        c = self._caso_quase_vazio()
        c.mov_total_credito, c.mov_total_debito = "R$500.000,00", "R$40.000,00"
        c.comp_evasao = modo
        core.aplicar_timeline_ao_caso(c, _r.Random(5))
        return c

    def test_so_o_lado_que_existe_aparece_acima_do_grafico(self):
        import dossie_html
        for modo, tem, nao_tem in ((core.SO_CREDITOS, "R$ 500.000,00", "R$ 40.000,00"),
                                   (core.SO_DEBITOS, "R$ 40.000,00", "R$ 500.000,00")):
            html = "".join(dossie_html.informacoes_html(self._caso_bancario(modo)))
            bloco = html.split("Timeline de Transferências", 1)[1]
            self.assertIn(tem, bloco, modo)
            self.assertNotIn(nao_tem, bloco, modo)
            for proibido in ("Só Créditos", "Só Débitos", "Sem Débitos", "Sem Créditos", "Evasão Parcial"):
                self.assertNotIn(proibido, html, proibido)
            self.assertTrue(pdf_dossie.gerar_pdf(self._caso_bancario(modo)).startswith(b"%PDF"))
        for modo in ("Rápida Evasão", core.EVASAO_PARCIAL):  # os dois totais aparecem
            bloco = "".join(dossie_html.informacoes_html(self._caso_bancario(modo))).split("Timeline de Transferências", 1)[1]
            self.assertIn("R$ 500.000,00", bloco)
            self.assertIn("R$ 40.000,00", bloco)
            self.assertNotIn("Evasão Parcial", bloco)


    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_pdf_mostra_timeline_cripto_so_no_caso_cripto(self):
        t = texto_pdf(pdf_dossie.gerar_pdf(self._caso_cripto()))
        self.assertIn("Timeline de Transferências — Criptomoedas", t)
        self.assertIn("R$200.000,00", t.replace(" ", ""))
        self.assertNotIn("Rápida Evasão", t)
        self.assertNotIn("Timeline de Transferências — Criptomoedas", texto_pdf(pdf_dossie.gerar_pdf(self._caso_cripto("NuInvest"))))


    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_pdf_esconde_campos_vazios(self):
        t = texto_pdf(pdf_dossie.gerar_pdf(self._caso_quase_vazio()))
        for proibido in ("Sem nome", "Não informado", "R$0,00", "Nenhuma contraparte", "Nenhuma outra movimentação",
                         "Descrição da Sentença", "Outras Informações Relevantes", "Contrapartes Principais",
                         "Informações Básicas do Cliente", "Cadastro e Registros"):
            self.assertNotIn(proibido, t, proibido)
        self.assertIn("Transfer In", t)

    def test_pdf_com_so_um_total_gera(self):
        c = self._caso_quase_vazio()
        c.mov_total_credito = "R$10.000,00"
        c.comp_evasao = "Rápida Evasão"
        self.assertTrue(pdf_dossie.gerar_pdf(c).startswith(b"%PDF"))


    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_resolucao_nao_tem_avaliacao(self):
        t = texto_pdf(self.resolucao)
        self.assertIn("Parecer Final do Analista", t)
        self.assertIn("KYC - Know Your Customer", t)
        self.assertIn("REPORTAR E CANCELAR", t)
        self.assertNotIn("NOTA FINAL", t)
        self.assertNotIn("Avaliação de Qualidade — AML", t)

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_avaliacao_so_tem_avaliacao(self):
        t = texto_pdf(self.avaliacao)
        self.assertIn("NOTA FINAL", t)
        self.assertIn("70%", t)
        self.assertIn("Business Intelligence", t)
        self.assertNotIn("KYC - Know Your Customer", t)
        self.assertNotIn("Parecer Final do Analista", t)
        self.assertNotIn("Resumo de Movimentações", t)
        self.assertLess(len(self.avaliacao), len(self.completo))

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_informacoes_nao_tem_resolucao_nem_avaliacao(self):
        t = texto_pdf(self.info)
        self.assertIn("Thundera - AML 360", t)
        self.assertNotIn("Parecer Final do Analista", t)
        self.assertNotIn("NOTA FINAL", t)

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_rodape_e_paginacao(self):
        t = texto_pdf(self.completo)
        self.assertIn("Uso interno e confidencial", t)
        self.assertIn("Página 1", t)
        self.assertGreater(n_paginas(self.completo), 3)

    def test_alias_de_compatibilidade(self):
        pdf = pdf_dossie.gerar_pdf_dossie(self.caso)
        self.assertTrue(pdf.startswith(b"%PDF"))
        png = core.grafico_do_caso(self.caso)
        pdf2 = pdf_dossie.gerar_pdf_dossie(self.caso, grafico_png=png)
        self.assertTrue(pdf2.startswith(b"%PDF"))


class TestNotaNoPdf(unittest.TestCase):
    def test_nota_por_categoria(self):
        c = com_resolucao_e_avaliacao(caso_joao())
        self.assertEqual(c.nota_qualidade(), 70.0)  # 100 - 15 (CC) - 15 (BC); BI não desconta

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_regulatory_zera(self):
        c = com_resolucao_e_avaliacao(caso_joao())
        c.scorecard_drivers_marcados.append("Caso deveria ter sido Clear")
        t = texto_pdf(pdf_dossie.gerar_pdf(c, "avaliacao"))
        self.assertIn("0%", t)
        self.assertIn("Caso deveria ter sido Clear", t)

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_avaliacao_sem_criterios(self):
        c = caso_joao()
        t = texto_pdf(pdf_dossie.gerar_pdf(c, "avaliacao"))
        self.assertIn("100%", t)
        self.assertIn("Nenhum critério marcado", t)
        self.assertIn("Avaliação ainda não salva", t)

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_rubrica_nuinvest(self):
        c = caso_joao()
        c.tipo_caso = "NuInvest"
        c.scorecard_drivers_marcados = ["Faltou incluir perfil Suitability ou incluiu incorretamente"]
        t = texto_pdf(pdf_dossie.gerar_pdf(c, "avaliacao"))
        self.assertIn("AML NuInvest", t)
        self.assertIn("85%", t)


class TestRobustez(unittest.TestCase):
    def test_caso_vazio(self):
        for escopo in pdf_dossie.ESCOPOS:
            pdf = pdf_dossie.gerar_pdf(Caso(numero_caso="2026-VAZIO1", tipo_caso="Pessoa Física (PF)"), escopo)
            self.assertTrue(pdf.startswith(b"%PDF"), escopo)

    @unittest.skipIf(PdfReader is None, "pypdf ausente")
    def test_caso_vazio_mostra_pendencias(self):
        t = texto_pdf(pdf_dossie.gerar_pdf(Caso(numero_caso="2026-VAZIO1", tipo_caso="Pessoa Física (PF)")))
        self.assertIn("DILIGÊNCIA PENDENTE", t)
        self.assertIn("PENDENTE — PREENCHER NA CALIBRAÇÃO DO TIME", t)
        self.assertIn("Nenhuma selecionada", t)

    def test_pj_com_socios(self):
        c = Caso(numero_caso="2026-PJ0001", tipo_caso="Pessoa Jurídica (PJ)")
        c.nome_empresa = "Padaria & Cia <Ltda> \"Pão Quente\""
        c.faturamento_presumido = "R$50.000,00"
        c.data_abertura = "01/01/2020"
        c.ramo_atividade = "Padaria"
        c.presenca_online = "Sim"
        c.socios = [Socio(nome="Fulano <script>", idade="40", pep="Sim", tipo_pep="PEP Titular",
                          descricao_pep="Vereador até 2022", regiao_risco="Sim", tipo_regiao_risco="Região de Fronteira"),
                    Socio(nome="Beltrana")]
        c.contrapartes_credito = [ContraparteMovimentacao(
            tipo="Pessoa Jurídica", nome="Empresa X", porcentagem="30%", valor="R$10,00", data_abertura="02/02/2019",
            ramo_atividade="Comércio", porte="ME", faturamento_presumido="R$1.000,00", pep="Sim", pep_detalhe="sócio PEP")]
        pdf = pdf_dossie.gerar_pdf(c)
        self.assertTrue(pdf.startswith(b"%PDF"))
        if PdfReader:
            t = texto_pdf(pdf)
            self.assertIn("Padaria & Cia <Ltda>", t)
            self.assertIn("Fulano <script>", t)
            self.assertIn("Empresa X", t)

    def test_under18_e_nuinvest(self):
        c = caso_joao()
        c.tipo_caso = "Under 18"
        c.rep_nome = "Maria Responsável"
        c.rep_renda_presumida = "R$3.000,00"
        c.rep_hist_pld = "Não"
        self.assertTrue(pdf_dossie.gerar_pdf(c).startswith(b"%PDF"))
        if PdfReader:
            self.assertIn("Maria Responsável", texto_pdf(pdf_dossie.gerar_pdf(c, "informacoes")))
        c.tipo_caso = "NuInvest"
        self.assertTrue(pdf_dossie.gerar_pdf(c).startswith(b"%PDF"))

    def test_caracteres_especiais_e_quebras(self):
        c = com_resolucao_e_avaliacao(caso_joao())
        c.parecer_final = "Linha 1 & <b>negrito?</b>\nLinha 2 com \"aspas\" e 'apóstrofo' > < &amp; \x00\x07 fim"
        c.scorecard_feedback = "Feedback <i>x</i> & y\n\nParágrafo"
        pdf = pdf_dossie.gerar_pdf(c)
        self.assertTrue(pdf.startswith(b"%PDF"))
        if PdfReader:
            t = texto_pdf(pdf)
            self.assertIn("<b>negrito?</b>", t)
            self.assertIn("&amp;", t)
            self.assertIn("Linha 2", t)

    def test_parecer_enorme(self):
        c = com_resolucao_e_avaliacao(caso_joao())
        c.parecer_final = ("O cliente movimentou valores incompatíveis com a sua capacidade financeira. " * 270)[:20000]
        c.alineas = "X" * 3000  # palavra gigante, sem espaços
        pdf = pdf_dossie.gerar_pdf(c, "resolucao")
        self.assertTrue(pdf.startswith(b"%PDF"))
        if PdfReader:
            self.assertGreater(n_paginas(pdf), 6)
            self.assertIn("capacidade financeira", texto_pdf(pdf))

    def test_listas_vazias_sem_grafico(self):
        c = caso_joao()
        c.contrapartes_credito = []
        c.contrapartes_debito = []
        c.outras_movimentacoes = []
        c.arredondamento_itens = []
        c.pix_itens = []
        c.comp_evasao = ""
        c.timeline_creditos, c.timeline_debitos = [], []
        c.comp_mudanca_comportamento = ""
        self.assertTrue(pdf_dossie.gerar_pdf(c).startswith(b"%PDF"))

    def test_sem_evasao_alterna_dias(self):
        c = caso_joao()
        c.comp_evasao = "Sem Rápida Evasão"
        core.aplicar_timeline_ao_caso(c)
        self.assertTrue(pdf_dossie.gerar_pdf(c).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
