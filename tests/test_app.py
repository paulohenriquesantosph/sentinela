# -*- coding: utf-8 -*-
"""Testes da interface (app.py) com o AppTest do Streamlit — sem navegador.

Rodar, da raiz do projeto:
    ./venv/bin/python -m unittest tests.test_app -v
Cobre: navegação, os 5 tipos de caso, validação de obrigatórios, sócios (PJ), responsável legal
(Under 18), rubrica NuInvest, gênero ambíguo, preenchimento por IA (servidor fake) e o Banco.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from core import ArmazenamentoLocal, TIPOS_CASO  # noqa: E402
from tests.test_ia import FakeLLM  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app.py")


class BaseApp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sentinela_app_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        p = mock.patch.dict(os.environ, {"SENTINELA_DATA_DIR": self.dir})
        p.start()
        self.addCleanup(p.stop)
        st.cache_resource.clear()
        st.cache_data.clear()
        self.store = ArmazenamentoLocal(self.dir)

    def app(self) -> AppTest:
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        return at

    def clicar(self, at, key):
        at.button(key=key).click().run()
        self.assertFalse(at.exception, [e.value for e in at.exception])

    def ir_para_formulario(self, at, indice_tipo):
        self.clicar(at, "home_novo")
        self.clicar(at, f"tipo_{indice_tipo}")
        self.clicar(at, "modo_manual")
        self.assertEqual(at.session_state.tela, "formulario")

    @staticmethod
    def preencher(at, **campos):
        for chave, valor in campos.items():
            widget = next((w for w in (at.text_input, at.text_area, at.selectbox) if _tem(w, chave)), None)
            assert widget is not None, f"campo {chave} não encontrado"
            widget(key=chave).set_value(valor)
        at.run()

    def preencher_bloco3(self, at):
        self.preencher(at, f_periodo="01/04/2026 até 30/09/2026", f_tot_cred="R$500.000,00", f_tot_deb="R$500.000,00",
                       f_tot_cp_cred="63", f_tot_cp_deb="52")


def _html(at) -> str:
    """Todo o HTML emitido na tela, já sem escape (&quot; etc.)."""
    import html
    return html.unescape(" ".join(h.proto.body for h in at.get("html")))


def _tem(colecao, chave):
    try:
        colecao(key=chave)
        return True
    except KeyError:
        return False


class TestNavegacao(BaseApp):
    def test_home_tipo_modo_e_voltar(self):
        at = self.app()
        self.assertEqual(at.session_state.tela, "home")
        self.clicar(at, "home_novo")
        self.assertEqual(at.session_state.tela, "escolher_tipo")
        self.clicar(at, "tipo_voltar")
        self.assertEqual(at.session_state.tela, "home")
        self.clicar(at, "home_novo")
        self.clicar(at, "tipo_0")
        self.assertEqual(at.session_state.tela, "modo_preenchimento")
        self.assertEqual(at.session_state.tipo_caso_novo, "Pessoa Física (PF)")
        self.clicar(at, "modo_voltar")
        self.assertEqual(at.session_state.tela, "escolher_tipo")

    def test_banco_vazio_e_sem_resultado(self):
        at = self.app()
        self.clicar(at, "home_banco")
        self.assertEqual(at.session_state.tela, "banco")
        self.clicar(at, "banco_tudo")
        self.assertIn("Nenhum dossiê salvo", _html(at))
        at.text_input(key="banco_termo").set_value("CASO-00000000")
        self.clicar(at, "banco_buscar")
        self.assertIn('Nenhum caso encontrado com o número "CASO-00000000"', _html(at))


class TestGerarDossie(BaseApp):
    def gerar(self, at):
        self.clicar(at, "gerar_dossie")
        return at.session_state.gerado_numero

    def test_validacao_lista_o_que_falta(self):
        at = self.app()
        self.ir_para_formulario(at, 0)
        self.assertIsNone(self.gerar(at))
        faltando = " ".join(at.session_state.erros_form)
        for campo in ("Nome do Cliente", "Idade", "Renda Presumida", "Período", "Total de Créditos"):
            self.assertIn(campo, faltando)
        self.assertEqual(self.store.listar_indice(), [])

    def test_pf_gera_grava_e_abre_no_banco(self):
        at = self.app()
        self.ir_para_formulario(at, 0)
        self.preencher(at, f_fator="Transfer In", f_sentenca="Alerta por volume incompatível.",
                       f_nome="João Paulo Carvalho Dias", f_idade="28", f_cidade="São Paulo/SP", f_renda="R$1.200,00",
                       f_evasao="Rápida Evasão", f_data_conta="10/01/2026")
        self.preencher_bloco3(at)
        self.clicar(at, "add_cred")
        self.assertEqual(len(at.session_state["L_cred"]), 1)
        rid = at.session_state["L_cred"][0]
        self.preencher(at, **{f"r_cred_{rid}_nome": "Marcos Vinícius Andrade", f"r_cred_{rid}_pct": "14%",
                              f"r_cred_{rid}_valor": "R$70.000,00", f"r_cred_{rid}_ntrans": "23"})
        numero = self.gerar(at)
        self.assertTrue(numero and numero.startswith("2026-"), numero)
        caso = self.store.carregar_caso(numero)
        self.assertEqual(caso.nome_cliente, "João Paulo Carvalho Dias")
        self.assertEqual(caso.genero, "M")
        self.assertEqual(caso.contrapartes_credito[0].nome, "Marcos Vinícius Andrade")
        self.assertAlmostEqual(sum(caso.timeline_creditos), 500000, places=2)
        self.assertTrue(self.store.carregar_pdf(numero).startswith(b"%PDF"))
        # abrir pelo Banco
        self.clicar(at, "ver_dossie_gerado")
        self.assertEqual(at.session_state.tela, "dossie")
        self.assertEqual(len(at.tabs), 3)
        self.clicar(at, "dossie_voltar_btn")
        self.assertEqual(at.session_state.tela, "formulario")
        self.assertEqual(at.text_input(key="f_nome").value, "João Paulo Carvalho Dias")  # formulário restaurado

    def test_pj_com_socio(self):
        at = self.app()
        self.ir_para_formulario(at, 1)
        self.preencher(at, f_empresa="Padaria Estrela Ltda", f_emp_fat="R$80.000,00")
        self.preencher_bloco3(at)
        self.clicar(at, "add_so")
        rid = at.session_state["L_so"][0]
        self.preencher(at, **{f"r_so_{rid}_nome": "Maria Souza", f"r_so_{rid}_pep": "Sim"})
        numero = self.gerar(at)
        caso = self.store.carregar_caso(numero)
        self.assertTrue(caso.eh_pj())
        self.assertEqual(caso.socios[0].nome, "Maria Souza")
        self.assertEqual(caso.risco_geral(), "ALTO")

    def test_under18_e_nuinvest_e_cripto(self):
        for indice, tipo in ((2, "Cripto"), (3, "NuInvest"), (4, "Under 18")):
            at = self.app()
            self.ir_para_formulario(at, indice)
            self.preencher(at, f_nome="Pedro Henrique Lima", f_idade="16", f_renda="R$500,00")
            if tipo == "Under 18":
                self.preencher(at, f_rep_nome="Ana Lima", f_rep_renda="R$3.000,00")
            self.preencher_bloco3(at)
            numero = self.gerar(at)
            caso = self.store.carregar_caso(numero)
            self.assertEqual(caso.tipo_caso, tipo)
            self.assertEqual(caso.rubrica(), "AML NuInvest" if tipo == "NuInvest" else "AML Nupag")
            if tipo == "Under 18":
                self.assertEqual(caso.rep_nome, "Ana Lima")

    def test_genero_ambiguo_pede_resposta(self):
        at = self.app()
        self.ir_para_formulario(at, 0)
        self.preencher(at, f_nome="Alex Silva", f_idade="30", f_renda="R$2.000,00")
        self.preencher_bloco3(at)
        self.assertIsNone(self.gerar(at))
        self.assertIn("Gênero do cliente", " ".join(at.session_state.erros_form))
        at.selectbox(key="f_genero").set_value("Feminino").run()
        numero = self.gerar(at)
        self.assertEqual(self.store.carregar_caso(numero).genero, "F")


class TestResolucaoEAvaliacao(BaseApp):
    def caso_gerado(self):
        at = self.app()
        self.ir_para_formulario(at, 0)
        self.preencher(at, f_nome="João Paulo Carvalho Dias", f_idade="28", f_renda="R$1.200,00")
        self.preencher_bloco3(at)
        self.clicar(at, "gerar_dossie")
        numero = at.session_state.gerado_numero
        self.clicar(at, "ver_dossie_gerado")
        return at, numero

    def test_salvar_secoes_travar_e_persistir(self):
        at, n = self.caso_gerado()
        at.text_area(key=f"res_{n}_parecer").set_value("Parecer do analista.").run()
        self.clicar(at, f"salvar_{n}_parecer")
        c = self.store.carregar_caso(n)
        self.assertEqual(c.parecer_final, "Parecer do analista.")
        self.assertIn("parecer", c.resolucao_salva_em)
        self.assertTrue(at.text_area(key=f"res_{n}_parecer").disabled)
        at.selectbox(key=f"res_{n}_diligencia").set_value("Cancelar").run()
        self.clicar(at, f"salvar_caso_{n}")
        c = self.store.carregar_caso(n)
        self.assertEqual(c.diligencia, "Cancelar")
        self.assertTrue(c.resolucao_travada())
        self.assertEqual(set(c.resolucao_salva_em), {"parecer", "alineas", "jurisprudencias", "razoes_clear",
                                                     "razoes_cancelamento", "diligencia"})
        self.assertEqual(self.store.listar_indice()[0]["diligencia"], "Cancelar")
        self.clicar(at, f"reabrir_{n}")
        self.assertFalse(self.store.carregar_caso(n).resolucao_travada())

    def test_avaliacao_nota_por_categoria_e_persistencia(self):
        at, n = self.caso_gerado()
        from opcoes import SCORECARD_NUPAG
        cc, bc, bi = SCORECARD_NUPAG[0], SCORECARD_NUPAG[1], SCORECARD_NUPAG[3]
        for cat, qtd in ((cc, 2), (bc, 1), (bi, 1)):
            for i in range(qtd):
                at.checkbox(key=f"av_{n}_{cat['categoria']}_{i}").check()
        at.run()
        self.assertIn("70%", _html(at))
        at.text_area(key=f"av_{n}_feedback").set_value("Faltou detalhar os saques.").run()
        self.clicar(at, f"salvar_av_{n}")
        c = self.store.carregar_caso(n)
        self.assertEqual(c.nota_qualidade(), 70)
        self.assertEqual(len(c.scorecard_drivers_marcados), 4)
        self.assertEqual(c.scorecard_feedback, "Faltou detalhar os saques.")
        self.assertTrue(c.scorecard_salvo_em)


class TestIA(BaseApp):
    def test_preenchimento_automatico_leva_ao_formulario_com_dados(self):
        fake = FakeLLM()
        self.addCleanup(fake.fechar)
        env = {"ANTHROPIC_API_KEY": "x", "ANTHROPIC_BASE_URL": fake.url, "SENTINELA_LLM_FORMATO": "openai",
               "SENTINELA_LLM_MODELO": "fake"}
        with mock.patch.dict(os.environ, env):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_0")
            self.clicar(at, "modo_auto")
            # campos obrigatórios do analista
            self.clicar(at, "ia_preencher")
            self.assertIn("Preencha", at.session_state.ia_erro)
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta por volume incompatível.")
            at.text_area(key="ia_resumo").set_value("Cliente João, renda R$1.200,00, R$500 mil.")
            at.text_area(key="ia_outras").set_value("Saques de R$90.000,00 em 38 saques.")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
            # a IA nunca preenche os campos do analista: continuam os digitados
            self.assertEqual(at.text_input(key="f_fator").value, "Transfer In")
            self.assertEqual(at.text_input(key="f_nome").value, "João Paulo Carvalho Dias")
            self.assertEqual(len(at.session_state["L_cred"]), 5)
            self.assertEqual(len(at.session_state["L_deb"]), 5)
            self.assertEqual(len(at.session_state["L_ar"]), 6)
            self.assertEqual(len(at.session_state["L_om"]), 1)
            self.assertIn("Abril R$160.000,00", at.text_area(key="f_mudanca").value)
            self.clicar(at, "gerar_dossie")
            self.assertTrue(at.session_state.gerado_numero)

    def test_erro_da_ia_aparece_na_tela(self):
        fake = FakeLLM()
        self.addCleanup(fake.fechar)
        fake.roteiro = [(401, {"error": "nao autorizado"})]
        env = {"ANTHROPIC_API_KEY": "x", "ANTHROPIC_BASE_URL": fake.url, "SENTINELA_LLM_FORMATO": "openai"}
        with mock.patch.dict(os.environ, env):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_0")
            self.clicar(at, "modo_auto")
            at.text_input(key="ia_fator").set_value("A")
            at.text_area(key="ia_sentenca").set_value("B")
            at.text_area(key="ia_resumo").set_value("C")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "preenchimento_ia")
            self.assertIn("401", at.session_state.ia_erro)


if __name__ == "__main__":
    unittest.main()
