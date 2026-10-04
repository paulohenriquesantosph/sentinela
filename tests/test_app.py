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
    def caso_gerado(self, indice_tipo=0):
        at = self.app()
        self.ir_para_formulario(at, indice_tipo)
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

    def test_botoes_de_salvar_e_pdf_ficam_depois_da_diligencia_em_todos_os_tipos(self):
        for indice, tipo in ((0, "PF"), (2, "Cripto"), (3, "NuInvest")):
            with self.subTest(tipo=tipo):
                at, n = self.caso_gerado(indice)
                chaves = [b.key for b in at.button]
                self.assertLess(chaves.index(f"salvar_{n}_diligencia"), chaves.index(f"salvar_caso_{n}"))
                self.assertLess(chaves.index(f"salvar_{n}_diligencia"), chaves.index(f"dl_res_off_{n}"))
                # Voltar ao Sentinela fica no fim da página: depois dos botões de salvar/PDF e da avaliação
                self.assertLess(chaves.index(f"dl_res_off_{n}"), chaves.index("dossie_voltar_btn"))
                self.assertLess(chaves.index(f"salvar_av_{n}"), chaves.index("dossie_voltar_btn"))
                self.assertEqual(chaves[-1], "dossie_voltar_btn")
                # a Diligência é a última seção de resolução
                secoes = [k.split("_", 2)[2] for k in chaves if k.startswith(f"salvar_{n}_")]
                self.assertEqual(secoes[-1], "diligencia")

    def test_anexos_so_no_caso_cripto(self):
        at, n = self.caso_gerado(0)
        self.assertNotIn(f"res_{n}_anexos", [w.key for w in at.text_area])
        self.assertNotIn("Anexos", _html(at))
        at, n = self.caso_gerado(2)
        self.assertEqual(self.store.carregar_caso(n).tipo_caso, "Cripto")
        self.assertIn("Anexos", _html(at))
        campo = at.text_area(key=f"res_{n}_anexos")
        self.assertIn("Informe se você irá anexar algum documento e qual para este caso "
                      "(apenas a descrição e um anexo por linha)", campo.placeholder)
        chaves = [b.key for b in at.button]
        self.assertLess(chaves.index(f"salvar_{n}_razoes_cancelamento"), chaves.index(f"salvar_{n}_anexos"))
        self.assertLess(chaves.index(f"salvar_{n}_anexos"), chaves.index(f"salvar_{n}_diligencia"))

    def test_anexos_salvar_travar_editar_e_pdf(self):
        at, n = self.caso_gerado(2)
        at.text_area(key=f"res_{n}_anexos").set_value("Extrato da exchange\nComprovante de residência\n\n").run()
        self.clicar(at, f"salvar_{n}_anexos")
        c = self.store.carregar_caso(n)
        self.assertEqual(c.lista_anexos(), ["Extrato da exchange", "Comprovante de residência"])
        self.assertIn("anexos", c.resolucao_salva_em)
        self.assertTrue(at.text_area(key=f"res_{n}_anexos").disabled)
        self.assertIn("2 anexo(s)", _html(at))
        self.clicar(at, f"editar_{n}_anexos")
        self.assertNotIn("anexos", self.store.carregar_caso(n).resolucao_salva_em)
        self.clicar(at, f"salvar_caso_{n}")
        c = self.store.carregar_caso(n)
        self.assertTrue(c.resolucao_travada())
        self.assertEqual(set(c.resolucao_salva_em), {"parecer", "alineas", "jurisprudencias", "razoes_clear",
                                                     "razoes_cancelamento", "anexos", "diligencia"})
        self.assertTrue(self.store.carregar_pdf(n).startswith(b"%PDF"))


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


class TestHome(BaseApp):
    def test_home_tem_links_do_manual_e_do_feedback(self):
        at = self.app()
        links = [(e.proto.label, e.proto.url) for e in at.get("link_button")]
        self.assertEqual(links, [("Formulário de Feedback e Sugestões", "https://forms.gle/z6sdUZawYvgf4fn3A")])
        self.assertIn("home_manual", [b.key for b in at.button])


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


class TestTimelineBancariaNoFormulario(BaseApp):
    def _formulario(self, indice_tipo=0):
        at = self.app()
        self.ir_para_formulario(at, indice_tipo)
        if indice_tipo == 1:  # PJ
            self.preencher(at, f_empresa="Padaria Estrela Ltda", f_emp_fat="R$80.000,00")
        else:
            self.preencher(at, f_nome="Pedro Henrique Lima", f_idade="31", f_renda="R$3.000,00")
        self.preencher(at, f_periodo="01/04/2026 até 30/06/2026", f_tot_cred="R$500.000,00", f_tot_deb="R$40.000,00",
                       f_tot_cp_cred="63", f_tot_cp_deb="52")
        return at

    def test_opcoes_em_todos_os_tipos(self):
        esperadas = ["—", "Rápida Evasão", "Sem Rápida Evasão", "Só Créditos (Sem Débitos)",
                     "Só Débitos (Sem Créditos)", "Evasão Parcial (Pequena Parcela nos Débitos)"]
        for indice in range(5):
            at = self._formulario(indice)
            self.assertEqual(at.selectbox(key="f_evasao").options, esperadas, indice)

    def test_modos_desenham_so_o_que_existe(self):
        casos = (("Só Créditos (Sem Débitos)", 500000, 0), ("Só Débitos (Sem Créditos)", 0, 40000),
                 ("Evasão Parcial (Pequena Parcela nos Débitos)", 500000, 40000))
        for modo, esp_c, esp_d in casos:
            with self.subTest(modo=modo):
                at = self._formulario()
                at.selectbox(key="f_evasao").set_value(modo).run()
                self.clicar(at, "gerar_grafico")
                tl = at.session_state.timeline
                self.assertEqual((round(sum(tl["cred"])), round(sum(tl["deb"]))), (esp_c, esp_d))
                self.clicar(at, "gerar_dossie")
                caso = self.store.carregar_caso(at.session_state.gerado_numero)
                self.assertEqual(caso.comp_evasao, modo)
                self.assertEqual((round(sum(caso.timeline_creditos)), round(sum(caso.timeline_debitos))), (esp_c, esp_d))
                bloco = _html(at).split("Timeline de Transferências")[1]
                for proibido in ("Só Créditos", "Só Débitos", "Evasão Parcial"):
                    self.assertNotIn(proibido, bloco)

    def test_aviso_quando_a_parcela_nao_e_pequena(self):
        at = self._formulario()
        self.preencher(at, f_tot_deb="R$400.000,00")
        at.selectbox(key="f_evasao").set_value("Evasão Parcial (Pequena Parcela nos Débitos)").run()
        self.assertIn("parcela pequena dos créditos", _html(at))


class TestTimelineCriptoNoFormulario(BaseApp):
    def _formulario(self, indice_tipo):
        at = self.app()
        self.ir_para_formulario(at, indice_tipo)
        self.preencher(at, f_nome="Pedro Henrique Lima", f_idade="31", f_renda="R$3.000,00")
        self.preencher(at, f_periodo="01/04/2026 até 30/06/2026", f_tot_cred="R$500.000,00", f_tot_deb="R$500.000,00",
                       f_tot_cp_cred="63", f_tot_cp_deb="52")
        return at

    def _add_cripto(self, at, info):
        self.clicar(at, "add_om")
        rid = at.session_state["L_om"][0]
        at.selectbox(key=f"r_om_{rid}_tipo").set_value("Criptomoedas")
        at.text_area(key=f"r_om_{rid}_info").set_value(info).run()

    def test_so_aparece_no_cripto_e_com_montante(self):
        at = self._formulario(2)  # Cripto
        self.assertNotIn("f_evasao_cripto", [w.key for w in at.selectbox])
        self.assertIn("adicione em Outras movimentações", _html(at))
        self._add_cripto(at, "Enviou R$200.000,00 para exchange")
        self.assertIn("f_evasao_cripto", [w.key for w in at.selectbox])
        self.assertEqual(at.selectbox(key="f_evasao_cripto").options,
                         ["—", "Rápida Evasão", "Sem Rápida Evasão", "Só Créditos (Sem Débitos)",
                          "Só Débitos (Sem Créditos)"])
        # PF e NuInvest não têm o campo, mesmo com cripto em Outras movimentações
        for indice in (0, 3):
            at2 = self._formulario(indice)
            self._add_cripto(at2, "Enviou R$200.000,00 para exchange")
            self.assertNotIn("f_evasao_cripto", [w.key for w in at2.selectbox], indice)

    def test_sem_montante_na_descricao_nao_habilita(self):
        at = self._formulario(2)
        self._add_cripto(at, "Enviou para exchange, sem valor")
        self.assertNotIn("f_evasao_cripto", [w.key for w in at.selectbox])

    def test_gera_grafico_e_o_dossie_guarda_a_serie(self):
        at = self._formulario(2)
        self._add_cripto(at, "Enviou R$200.000,00 para exchange")
        at.selectbox(key="f_evasao_cripto").set_value("Rápida Evasão").run()
        self.clicar(at, "gerar_grafico_cripto")
        self.assertEqual(round(sum(at.session_state.timeline_cripto["cred"])), 200000)
        self.clicar(at, "gerar_dossie")
        numero = at.session_state.gerado_numero
        self.assertTrue(numero, at.session_state.erros_form)
        caso = self.store.carregar_caso(numero)
        self.assertEqual(caso.comp_evasao_cripto, "Rápida Evasão")
        self.assertEqual(round(sum(caso.timeline_cripto_creditos)), 200000)
        self.assertIn("Timeline de Transferências — Criptomoedas", _html(at))
        self.assertNotIn("Rápida Evasão", _html(at).split("Timeline de Transferências — Criptomoedas")[1])

    def test_modos_de_um_lado_so_desenham_o_lado_escolhido(self):
        for modo, lado_cheio, lado_vazio in (("Só Créditos (Sem Débitos)", "cred", "deb"),
                                             ("Só Débitos (Sem Créditos)", "deb", "cred")):
            with self.subTest(modo=modo):
                at = self._formulario(2)
                self._add_cripto(at, "Enviou R$200.000,00 para exchange")
                at.selectbox(key="f_evasao_cripto").set_value(modo).run()
                self.clicar(at, "gerar_grafico_cripto")
                tl = at.session_state.timeline_cripto
                self.assertEqual(round(sum(tl[lado_cheio])), 200000)
                self.assertEqual(sum(tl[lado_vazio]), 0)
                self.clicar(at, "gerar_dossie")
                caso = self.store.carregar_caso(at.session_state.gerado_numero)
                self.assertEqual(caso.comp_evasao_cripto, modo)
                cheio = caso.timeline_cripto_creditos if lado_cheio == "cred" else caso.timeline_cripto_debitos
                vazio = caso.timeline_cripto_debitos if lado_cheio == "cred" else caso.timeline_cripto_creditos
                self.assertEqual((round(sum(cheio)), sum(vazio)), (200000, 0))
                html = _html(at)
                self.assertNotIn("Só Créditos", html.split("Timeline de Transferências — Criptomoedas")[1])
                self.assertNotIn("Só Débitos", html.split("Timeline de Transferências — Criptomoedas")[1])


    def test_automatico_marca_a_evasao_pelo_texto(self):
        d = {"kyc": {"nome": "Ana Lima"}, "movimentacoes": {"periodo": "01/04/2026 até 30/06/2026",
                                                              "totalCredito": "R$1.000,00"},
             "outrasMovimentacoes": [{"tipo": "Criptomoedas", "info": "Recebeu R$300.000,00 em cripto e enviou em seguida"}]}
        with mock.patch("ia.extrair_dados_do_texto", return_value=d):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_2")
            self.clicar(at, "modo_auto")
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta.")
            at.text_area(key="ia_resumo").set_value("Cliente cripto.")
            at.text_area(key="ia_outras").set_value("Cripto: R$300.000,00, enviou em seguida.")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
            self.assertEqual(at.selectbox(key="f_evasao_cripto").value, "Rápida Evasão")


class TestIAPerguntasKYC(BaseApp):
    def _dados(self):
        return {"kyc": {"nome": "Ana Lima", "idade": "30", "cidadeEstado": "",
                        "regiaoRisco": "Sim", "pep": "Sim", "tipoPep": "PEP Titular", "midiaNegativa": "Sim"},
                "movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$1.000,00",
                                  "totalDebito": "R$900,00"}}

    def test_pergunta_o_que_faltou_e_preenche_o_formulario(self):
        with mock.patch("ia.extrair_dados_do_texto", return_value=self._dados()):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_0")
            self.clicar(at, "modo_auto")
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta.")
            at.text_area(key="ia_resumo").set_value("Ana, região de risco, PEP e mídia negativa.")
            at.run()
            self.clicar(at, "ia_preencher")
            # ficou na tela, perguntando só o que faltou (o tipo de PEP já veio)
            self.assertEqual(at.session_state.tela, "preenchimento_ia")
            chaves = [w.key for w in at.text_input if w.key.startswith("ia_kyc_")]
            self.assertEqual(sorted(chaves), ["ia_kyc_cidade_estado", "ia_kyc_descricao_pep",
                                              "ia_kyc_midia_negativa_detalhe"])
            self.assertEqual([w.key for w in at.selectbox if w.key.startswith("ia_kyc_")],
                             ["ia_kyc_tipo_regiao_risco"])
            # sem responder, não avança
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "preenchimento_ia")
            self.assertIn("Cidade/Estado", at.session_state.ia_erro)
            at.text_input(key="ia_kyc_cidade_estado").set_value("Tabatinga/AM")
            at.selectbox(key="ia_kyc_tipo_regiao_risco").set_value("Região de Fronteira")
            at.text_input(key="ia_kyc_descricao_pep").set_value("Vereadora, carência até 2028")
            at.text_input(key="ia_kyc_midia_negativa_detalhe").set_value("g1.com/x, 10/05/2026, G1")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
            self.assertEqual(at.text_input(key="f_cidade").value, "Tabatinga/AM")
            self.assertEqual(at.selectbox(key="f_regiao").value, "Sim")
            self.assertEqual(at.selectbox(key="f_tipo_regiao").value, "Região de Fronteira")
            self.assertEqual(at.selectbox(key="f_pep").value, "Sim")
            self.assertEqual(at.text_input(key="f_desc_pep").value, "Vereadora, carência até 2028")
            self.assertEqual(at.text_input(key="f_midia_d").value, "g1.com/x, 10/05/2026, G1")

    def test_pergunta_detalhes_das_contrapartes(self):
        d = {"kyc": {"nome": "Ana Lima", "idade": "30"},
             "movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$1.000,00",
                               "totalDebito": "R$900,00",
                               "contrapartesCredito": [
                                   {"tipo": "Pessoa Física", "nome": "João", "porcentagem": "20%", "pep": "Sim"},
                                   {"tipo": "Pessoa Física", "nome": "", "porcentagem": "10%", "pep": "Sim"}]}}
        with mock.patch("ia.extrair_dados_do_texto", return_value=d):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_0")
            self.clicar(at, "modo_auto")
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta.")
            at.text_area(key="ia_resumo").set_value("Duas contrapartes de crédito são PEP.")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "preenchimento_ia")
            self.assertEqual(sorted(w.key for w in at.text_input if w.key.startswith("ia_kyc_")),
                             ["ia_kyc_cp__cred__0__pep_detalhe", "ia_kyc_cp__cred__1__pep_detalhe"])
            at.text_input(key="ia_kyc_cp__cred__0__pep_detalhe").set_value("Vereador, carência até 2028")
            at.text_input(key="ia_kyc_cp__cred__1__pep_detalhe").set_value("Secretária estadual")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
            rids = at.session_state["L_cred"]
            self.assertEqual(len(rids), 2)
            self.assertEqual(at.text_input(key=f"r_cred_{rids[0]}_pep_d").value, "Vereador, carência até 2028")
            self.assertEqual(at.text_input(key=f"r_cred_{rids[1]}_pep_d").value, "Secretária estadual")


    def test_pj_pede_dados_da_empresa_e_pergunta_socios(self):
        d = {"kyc": {"nomeEmpresa": "Padaria Estrela", "dataAbertura": "01/02/2020", "ramoAtividade": "Padaria",
                     "porte": "ME", "faturamentoPresumido": "R$80.000,00", "endereco": "Rua A, 10",
                     "presencaOnline": "Sim", "fachadaEmpresa": "Sim",
                     "socios": [{"nome": "Maria", "pep": "Sim", "tipoPep": "PEP Titular"},
                                {"nome": "", "pep": "Sim", "tipoPep": "PEP Titular", "descricaoPep": "Prefeito"}]},
             "movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$1.000,00",
                               "totalDebito": "R$900,00"}}
        with mock.patch("ia.extrair_dados_do_texto", return_value=d):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_1")
            self.clicar(at, "modo_auto")
            self.assertIn("Presença Online", _html(at))  # instrução com os dados da PJ
            self.assertIn("Caso PJ — dados do sócio", _html(at))  # e com os dados do sócio
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta.")
            at.text_area(key="ia_resumo").set_value("Padaria, dois sócios PEP.")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "preenchimento_ia")
            self.assertEqual([w.key for w in at.text_input if w.key.startswith("ia_kyc_")],
                             ["ia_kyc_so__0__descricao_pep"])
            at.text_input(key="ia_kyc_so__0__descricao_pep").set_value("Vereadora")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
            self.assertEqual(at.selectbox(key="f_pres_online").value, "Sim")
            self.assertEqual(at.selectbox(key="f_fachada").value, "Sim")
            self.assertFalse([w for w in at.text_input if w.key in ("f_pres_online_d", "f_fachada_d")])
            rids = at.session_state["L_so"]
            self.assertEqual(at.text_input(key=f"r_so_{rids[0]}_desc_pep").value, "Vereadora")
            self.assertEqual(at.text_input(key=f"r_so_{rids[1]}_desc_pep").value, "Prefeito")


    def test_perguntas_e_mudanca_em_todos_os_tipos_de_caso(self):
        d = {"kyc": {"nome": "Ana Lima", "idade": "30", "cidadeEstado": "Fortaleza/CE", "nomeEmpresa": "Padaria Estrela"},
             "movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$1.000,00",
                               "totalDebito": "R$900,00",
                               "contrapartesCredito": [{"tipo": "Pessoa Física", "nome": "João", "porcentagem": "20%",
                                                        "pep": "Sim"}]}}
        for indice in range(5):  # PF, PJ, Cripto, NuInvest, Under 18
            with self.subTest(tipo=indice), mock.patch("ia.extrair_dados_do_texto", return_value=d):
                at = self.app()
                self.clicar(at, "home_novo")
                self.clicar(at, f"tipo_{indice}")
                self.clicar(at, "modo_auto")
                at.text_input(key="ia_fator").set_value("Transfer In")
                at.text_area(key="ia_sentenca").set_value("Alerta.")
                at.text_area(key="ia_resumo").set_value("Contraparte PEP. Houve mudança de comportamento.")
                at.run()
                # a mudança de comportamento pergunta valor e data de abertura/último reporte, em qualquer tipo
                self.assertEqual(sorted(w.key for w in at.text_input if w.key.startswith("ia_mc_")),
                                 ["ia_mc_conta", "ia_mc_valor"])
                at.text_input(key="ia_mc_conta").set_value("10/01/2025")
                at.text_input(key="ia_data").set_value("15/06/2026")
                at.run()
                self.clicar(at, "ia_preencher")
                self.assertEqual(at.session_state.tela, "preenchimento_ia", at.session_state.ia_erro)
                self.assertEqual([w.key for w in at.text_input if w.key.startswith("ia_kyc_")],
                                 ["ia_kyc_cp__cred__0__pep_detalhe"])
                at.text_input(key="ia_kyc_cp__cred__0__pep_detalhe").set_value("Vereador")
                at.run()
                self.clicar(at, "ia_preencher")
                self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
                self.assertEqual(len(at.text_area(key="f_mudanca").value.splitlines()), 6)


    def test_instrucoes_por_tipo_de_caso(self):
        esperado = {0: [], 1: ["dados da empresa", "dados do sócio"], 2: [], 3: [], 4: ["dados do responsável legal"]}
        for indice, trechos in esperado.items():
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, f"tipo_{indice}")
            self.clicar(at, "modo_auto")
            html = _html(at)
            for t in ("dados da empresa", "dados do sócio", "dados do responsável legal"):
                (self.assertIn if t in trechos else self.assertNotIn)(t, html, f"tipo {indice}: {t}")
            if indice == 4:
                self.assertIn("Registro Societário, Histórico de PLD e Histórico de Fraude", html)


    def test_automatico_com_dados_minimos_gera_dossie_sem_marcadores(self):
        d = {"kyc": {}, "movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$1.000,00"}}
        with mock.patch("ia.extrair_dados_do_texto", return_value=d):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_0")
            self.clicar(at, "modo_auto")
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta.")
            at.text_area(key="ia_resumo").set_value("Movimentou R$1.000,00. Preencha apenas o que eu informei.")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)
            self.assertEqual(at.text_input(key="f_nome").value, "")  # sem marcador "Não informado"
            self.assertEqual(at.text_input(key="f_renda").value, "")
            self.clicar(at, "gerar_dossie")
            numero = at.session_state.gerado_numero
            self.assertTrue(numero, at.session_state.erros_form)  # a geração não é barrada por campos em branco
            caso = self.store.carregar_caso(numero)
            self.assertEqual((caso.nome_cliente, caso.renda_presumida, caso.mov_total_debito), ("", "", ""))
            html = _html(at)
            for proibido in ("Não informado", "Sem nome", "R$ 0,00"):
                self.assertNotIn(proibido, html)
            self.assertTrue(self.store.carregar_pdf(numero).startswith(b"%PDF"))


    def test_sem_faltas_vai_direto_ao_formulario(self):
        d = self._dados()
        d["kyc"].update({"cidadeEstado": "Tabatinga/AM", "tipoRegiaoRisco": "Região de Fronteira",
                         "descricaoPep": "Vereadora", "midiaNegativaDetalhe": "G1, 10/05/2026"})
        with mock.patch("ia.extrair_dados_do_texto", return_value=d):
            at = self.app()
            self.clicar(at, "home_novo")
            self.clicar(at, "tipo_0")
            self.clicar(at, "modo_auto")
            at.text_input(key="ia_fator").set_value("Transfer In")
            at.text_area(key="ia_sentenca").set_value("Alerta.")
            at.text_area(key="ia_resumo").set_value("Ana, tudo informado.")
            at.run()
            self.clicar(at, "ia_preencher")
            self.assertEqual(at.session_state.tela, "formulario", at.session_state.ia_erro)


if __name__ == "__main__":
    unittest.main()
