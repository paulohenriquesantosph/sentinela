# -*- coding: utf-8 -*-
"""Testes do núcleo (core.py): nota de qualidade, risco, narrativa, gráfico, validação e Banco de Dossiês.

Rodar, da raiz do projeto:
    ./venv/bin/python -m unittest tests.test_core -v
"""
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
from core import (  # noqa: E402
    ArmazenamentoLocal, Caso, ContraparteMovimentacao, OutraMovimentacao, Socio,
    calcular_nota_scorecard, faixa_nota, formatar_nota, gerar_narrativa_mudanca_comportamento,
    gerar_series_timeline, parse_valor_br, periodo_padrao, validar_caso, inferir_genero,
    percentual_restante, estilo_diligencia, grafico_do_caso, aplicar_timeline_ao_caso,
)
from opcoes import SCORECARD_NUPAG, SCORECARD_NUINVEST, DILIGENCIAS  # noqa: E402


def caso_joao(numero="2026-ABC123") -> Caso:
    c = Caso(numero_caso=numero, tipo_caso="Pessoa Física (PF)")
    c.fator_gerador, c.data_alerta = "Transfer In", "01/10/2026"
    c.sentenca = "Alerta por volume incompatível com a renda."
    c.nome_cliente, c.genero, c.idade, c.cidade_estado = "João Paulo Carvalho Dias", "M", "28", "São Paulo/SP"
    c.renda_presumida = "R$1.200,00"
    c.mov_periodo = "01/04/2026 até 30/09/2026"
    c.mov_total_credito = c.mov_total_debito = "R$500.000,00"
    c.mov_total_contrapartes_credito, c.mov_total_contrapartes_debito = "63", "52"
    c.contrapartes_credito = [ContraparteMovimentacao(nome=f"C{i}", porcentagem=f"{p}%", valor="R$1,00")
                              for i, p in enumerate((14, 11, 9, 7, 6))]
    c.outras_movimentacoes = [OutraMovimentacao(tipo="Saques", info="R$90.000,00 em 38 saques")]
    c.comp_evasao = "Rápida Evasão"
    c.comp_arredondamento = "Sim"
    return c


def nomes(tipo, categoria, n):
    """Primeiros n critérios de uma categoria da rubrica."""
    rubrica = SCORECARD_NUINVEST if tipo == "AML NuInvest" else SCORECARD_NUPAG
    cat = next(c for c in rubrica if c["categoria"] == categoria)
    return [d["nome"] for d in cat["drivers"][:n]]


class TestScorecard(unittest.TestCase):
    def test_contagem_de_criterios_do_manual(self):
        for rubrica, esperado in ((SCORECARD_NUPAG, (15, 10, 6, 9)), (SCORECARD_NUINVEST, (16, 12, 6, 9))):
            self.assertEqual(tuple(len(c["drivers"]) for c in rubrica), esperado)

    def test_sem_marcacao_100(self):
        self.assertEqual(calcular_nota_scorecard("AML Nupag", []), 100)

    def test_desconto_por_categoria_nao_por_criterio(self):
        # 3 critérios de Customer Critical descontam 15%, não 45%
        self.assertEqual(calcular_nota_scorecard("AML Nupag", nomes("AML Nupag", "Customer Critical", 3)), 85)

    def test_exemplo_do_manual_70(self):
        marcados = nomes("AML Nupag", "Customer Critical", 2) + nomes("AML Nupag", "Business Critical", 1) \
            + nomes("AML Nupag", "Business Intelligence", 1)
        self.assertEqual(calcular_nota_scorecard("AML Nupag", marcados), 70)

    def test_regulatory_zera(self):
        self.assertEqual(calcular_nota_scorecard("AML Nupag", nomes("AML Nupag", "Regulatory Critical", 1)), 0)

    def test_business_intelligence_nao_desconta(self):
        self.assertEqual(calcular_nota_scorecard("AML Nupag", nomes("AML Nupag", "Business Intelligence", 9)), 100)

    def test_faixas_de_cor(self):
        self.assertEqual([faixa_nota(n) for n in (100, 90, 89, 70, 69, 0)],
                         ["verde", "verde", "ambar", "ambar", "vermelho", "vermelho"])
        self.assertEqual(formatar_nota(70.0), "70%")

    def test_rubrica_segue_o_tipo_do_caso(self):
        self.assertEqual(Caso("1", "NuInvest").rubrica(), "AML NuInvest")
        for tipo in ("Pessoa Física (PF)", "Pessoa Jurídica (PJ)", "Cripto", "Under 18"):
            self.assertEqual(Caso("1", tipo).rubrica(), "AML Nupag")

    def test_diligencias_e_cores(self):
        self.assertEqual(DILIGENCIAS, ["Clear (arquivar)", "Reportar", "Reportar e Cancelar", "Cancelar"])
        self.assertEqual([estilo_diligencia(d) for d in DILIGENCIAS], ["verde", "ambar", "vermelho", "neutro"])
        self.assertEqual(estilo_diligencia(""), "pendente")


class TestMudancaComportamento(unittest.TestCase):
    def test_igual_ao_print_do_manual(self):
        t = gerar_narrativa_mudanca_comportamento("01/04/2026 até 30/09/2026", "R$160.000,00")
        self.assertEqual(t.splitlines(), [
            "Novembro R$1.000,00", "Dezembro R$1.500,00", "Janeiro R$2.000,00",
            "Fevereiro R$0,00", "Março R$0,10", "Abril R$160.000,00"])

    def test_pico_vai_para_o_primeiro_mes_do_periodo(self):
        t = gerar_narrativa_mudanca_comportamento("01/08/2026 até 30/09/2026", "160000")
        self.assertTrue(t.splitlines()[-1].startswith("Agosto R$160.000,00"))

    def test_periodo_ausente_usa_o_padrao(self):
        hoje = date(2026, 10, 3)
        self.assertEqual(periodo_padrao(hoje), "01/07/2026 até 01/09/2026")
        t = gerar_narrativa_mudanca_comportamento("", "R$10,00", hoje)
        self.assertTrue(t.splitlines()[-1].startswith("Julho "))


class TestValores(unittest.TestCase):
    def test_parse(self):
        for txt, v in (("R$1.234,56", 1234.56), ("R$500.000,00", 500000), ("500 mil", 500000),
                       ("1,5 milhão", 1500000), ("1.200", 1200), ("", 0), ("sem valor", 0)):
            self.assertAlmostEqual(parse_valor_br(txt), v, msg=txt)

    def test_percentual_restante(self):
        c = caso_joao()
        self.assertEqual(percentual_restante(c.contrapartes_credito), 53)
        self.assertIsNone(percentual_restante([]))


class TestTimeline(unittest.TestCase):
    def test_soma_bate_com_os_totais(self):
        for evasao in ("Rápida Evasão", "Sem Rápida Evasão"):
            ini, cred, deb = gerar_series_timeline("01/04/2026 até 30/09/2026", 500000, 500000, evasao,
                                                   random.Random(1))
            self.assertEqual(ini, "01/04/2026")
            self.assertEqual(len(cred), 183)
            self.assertAlmostEqual(sum(cred), 500000, places=2)
            self.assertAlmostEqual(sum(deb), 500000, places=2)

    def test_rapida_evasao_usa_os_mesmos_pesos(self):
        _, cred, deb = gerar_series_timeline("01/04/2026 até 30/04/2026", 1000, 1000, "Rápida Evasão", random.Random(2))
        self.assertTrue(all(abs(c - d) < 0.02 for c, d in zip(cred, deb)))

    def test_sem_rapida_evasao_alterna_dias(self):
        _, cred, deb = gerar_series_timeline("01/04/2026 até 30/04/2026", 1000, 1000, "Sem Rápida Evasão",
                                             random.Random(3))
        self.assertTrue(all((c == 0 or d == 0) for c, d in zip(cred, deb)))

    def test_png(self):
        c = caso_joao()
        self.assertTrue(aplicar_timeline_ao_caso(c))
        png = grafico_do_caso(c)
        self.assertTrue(png.startswith(b"\x89PNG"))
        c.comp_evasao = ""
        self.assertFalse(aplicar_timeline_ao_caso(Caso("1", "Cripto")))


class TestTimelineBancariaModos(unittest.TestCase):
    PER = "01/04/2026 até 30/06/2026"

    def _series(self, modo, cred=500000.0, deb=40000.0, seed=3):
        return gerar_series_timeline(self.PER, cred, deb, modo, random.Random(seed))

    def test_so_creditos_nao_tem_debitos_mesmo_com_total_de_debitos(self):
        _, c, d = self._series(core.SO_CREDITOS)
        self.assertAlmostEqual(sum(c), 500000, places=2)
        self.assertEqual(sum(d), 0)
        self.assertEqual(len(c), len(d))

    def test_so_debitos_nao_tem_creditos_mesmo_com_total_de_creditos(self):
        _, c, d = self._series(core.SO_DEBITOS)
        self.assertEqual(sum(c), 0)
        self.assertAlmostEqual(sum(d), 40000, places=2)

    def test_evasao_parcial_usa_os_dois_totais(self):
        for seed in range(30):
            _, c, d = self._series(core.EVASAO_PARCIAL, 500000.0, 40000.0, seed)
            self.assertAlmostEqual(sum(c), 500000, places=2)  # recebeu tudo, ao longo do período
            self.assertAlmostEqual(sum(d), 40000, places=2)    # evadiu só a parcela pequena
            dias_c, dias_d = sum(1 for x in c if x), sum(1 for x in d if x)
            self.assertGreater(dias_c, 80)                      # créditos espalhados
            self.assertLess(dias_d, dias_c)                     # débitos concentrados em poucos dias
            self.assertEqual(d[0], 0)                           # nenhum débito antes de receber (1º dia)

    def test_evasao_parcial_com_um_dia_so(self):
        _, c, d = gerar_series_timeline("15/06/2026 até 15/06/2026", 100.0, 10.0, core.EVASAO_PARCIAL)
        self.assertEqual((c, d), ([100.0], [10.0]))

    def test_modos_antigos_nao_mudam(self):
        _, c, d = gerar_series_timeline(self.PER, 1000, 1000, "Rápida Evasão", random.Random(2))
        self.assertTrue(all(abs(a - b) < 0.02 for a, b in zip(c, d)))
        _, c, d = gerar_series_timeline(self.PER, 1000, 1000, "Sem Rápida Evasão", random.Random(3))
        self.assertTrue(all((a == 0 or b == 0) for a, b in zip(c, d)))

    def test_lados_da_timeline(self):
        self.assertEqual(core.lados_da_timeline(core.SO_CREDITOS), (True, False))
        self.assertEqual(core.lados_da_timeline(core.SO_DEBITOS), (False, True))
        for modo in ("", "Rápida Evasão", "Sem Rápida Evasão", core.EVASAO_PARCIAL):
            self.assertEqual(core.lados_da_timeline(modo), (True, True))

    def test_aplica_ao_caso_e_desenha_o_grafico(self):
        for modo in core.OPCOES_EVASAO[1:]:
            c = caso_joao()
            c.comp_evasao = modo
            c.mov_total_credito, c.mov_total_debito = "R$500.000,00", "R$40.000,00"
            self.assertTrue(aplicar_timeline_ao_caso(c, random.Random(1)), modo)
            self.assertTrue(grafico_do_caso(c).startswith(b"\x89PNG"), modo)
        c = caso_joao()
        c.comp_evasao, c.mov_total_credito, c.mov_total_debito = core.SO_CREDITOS, "R$500.000,00", "R$40.000,00"
        aplicar_timeline_ao_caso(c)
        self.assertEqual(sum(c.timeline_debitos), 0)


class TestTimelineCripto(unittest.TestCase):
    def _caso(self, tipo="Cripto", evasao="Rápida Evasão", info="Enviou R$200.000,00 para uma exchange"):
        c = Caso("2026-CRIPTO", tipo)
        c.mov_periodo = "01/04/2026 até 30/06/2026"
        c.comp_evasao_cripto = evasao
        c.outras_movimentacoes = [core.OutraMovimentacao(tipo="Criptomoedas", info=info),
                                  core.OutraMovimentacao(tipo="Saques", info="R$9.000,00")]
        return c

    def test_extrair_montante(self):
        casos = {"Comprou R$ 120.000,00 em 15 transações de R$8.000,00": 120000.0, "R$120 mil": 120000.0,
                 "R$ 1,5 milhão": 1500000.0, "R$2 milhões": 2000000.0, "R$ 300k": 300000.0, "R$120000": 120000.0,
                 "sem valor": 0.0, "": 0.0}
        for texto, esperado in casos.items():
            self.assertEqual(core.extrair_montante(texto), esperado, texto)

    def test_montante_so_conta_linhas_de_criptomoedas(self):
        c = self._caso()
        self.assertEqual(core.montante_cripto(c), 200000.0)  # o saque de R$9.000 não entra
        c.outras_movimentacoes.append(core.OutraMovimentacao(tipo="Criptomoedas", info="Mais R$50.000,00"))
        self.assertEqual(core.montante_cripto(c), 250000.0)

    def test_racional_igual_ao_dos_repasses_rapidos(self):
        c = self._caso(evasao="Rápida Evasão")
        self.assertTrue(core.aplicar_timeline_cripto_ao_caso(c, random.Random(1)))
        self.assertEqual(round(sum(c.timeline_cripto_creditos), 2), 200000.0)
        self.assertEqual(round(sum(c.timeline_cripto_debitos), 2), 200000.0)
        self.assertEqual(c.timeline_cripto_creditos, c.timeline_cripto_debitos)  # entra e sai nos mesmos dias
        c = self._caso(evasao="Sem Rápida Evasão")
        self.assertTrue(core.aplicar_timeline_cripto_ao_caso(c, random.Random(1)))
        self.assertFalse(any(a and b for a, b in zip(c.timeline_cripto_creditos, c.timeline_cripto_debitos)))
        self.assertEqual(round(sum(c.timeline_cripto_creditos), 2), 200000.0)

    def test_modos_de_um_lado_so(self):
        for modo, cheio, vazio in ((core.CRIPTO_SO_CREDITOS, 0, 1), (core.CRIPTO_SO_DEBITOS, 1, 0)):
            c = self._caso(evasao=modo)
            self.assertTrue(core.aplicar_timeline_cripto_ao_caso(c, random.Random(4)))
            series = (c.timeline_cripto_creditos, c.timeline_cripto_debitos)
            self.assertEqual(round(sum(series[cheio]), 2), 200000.0, modo)
            self.assertEqual(sum(series[vazio]), 0, modo)
            self.assertEqual(len(series[0]), len(series[1]))
            self.assertTrue(core.grafico_cripto_do_caso(c).startswith(b"\x89PNG"))

    def test_opcoes_e_rotulo_do_valor(self):
        self.assertEqual(core.OPCOES_EVASAO_CRIPTO, ["", "Rápida Evasão", "Sem Rápida Evasão",
                                                    "Só Créditos (Sem Débitos)", "Só Débitos (Sem Créditos)"])
        # a timeline bancária tem também a evasão parcial (usa os totais de créditos e de débitos)
        self.assertEqual(core.OPCOES_EVASAO, core.OPCOES_EVASAO_CRIPTO + ["Evasão Parcial (Pequena Parcela nos Débitos)"])
        self.assertEqual(core.pilula_cripto(self._caso(evasao=core.CRIPTO_SO_CREDITOS)), ("Créditos (criptomoedas)", "verde"))
        self.assertEqual(core.pilula_cripto(self._caso(evasao=core.CRIPTO_SO_DEBITOS)), ("Débitos (criptomoedas)", "vermelho"))
        self.assertEqual(core.pilula_cripto(self._caso(evasao="Rápida Evasão")), ("Criptomoedas", "verde"))


    def test_so_para_casos_cripto_e_com_montante(self):
        for c in (self._caso(tipo="Pessoa Física (PF)"), self._caso(evasao=""), self._caso(info="sem valor")):
            self.assertFalse(core.aplicar_timeline_cripto_ao_caso(c))
            self.assertEqual(c.timeline_cripto_creditos, [])
        self.assertIsNone(core.grafico_cripto_do_caso(self._caso(tipo="Pessoa Física (PF)")))

    def test_grafico_e_persistencia(self):
        c = self._caso()
        core.aplicar_timeline_cripto_ao_caso(c, random.Random(2))
        self.assertTrue(core.grafico_cripto_do_caso(c).startswith(b"\x89PNG"))
        c2 = Caso.from_dict(json.loads(json.dumps(c.to_dict())))
        self.assertEqual((c2.comp_evasao_cripto, c2.timeline_cripto_creditos), ("Rápida Evasão", c.timeline_cripto_creditos))


class TestValidacao(unittest.TestCase):
    def test_validacao_pf(self):
        faltando = validar_caso(Caso("1", "Pessoa Física (PF)"))
        for campo in ("Nome do Cliente", "Idade", "Renda Presumida do Cliente", "Gênero do cliente", "Período",
                      "Total de Créditos", "Total de Débitos", "Total de Contrapartes (Crédito)",
                      "Total de Contrapartes (Débito)"):
            self.assertIn(campo, faltando)
        self.assertEqual(validar_caso(caso_joao()), [])

    def test_validacao_pj(self):
        faltando = validar_caso(Caso("1", "Pessoa Jurídica (PJ)"))
        self.assertIn("Nome da Empresa", faltando)
        self.assertIn("Faturamento Presumido", faltando)
        self.assertNotIn("Idade", faltando)
        self.assertNotIn("Gênero do cliente", faltando)

    def test_genero(self):
        self.assertEqual(inferir_genero("João Paulo"), "M")
        self.assertEqual(inferir_genero("Mariana Costa"), "F")
        self.assertIsNone(inferir_genero("Alex Silva"))
        self.assertIsNone(inferir_genero(""))


class TestBancoDeDossies(unittest.TestCase):
    """Item 5 do pedido: criar um caso, gravar, buscar, abrir e conferir."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sentinela_test_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = ArmazenamentoLocal(self.dir)

    def test_criar_gravar_buscar_abrir(self):
        caso = caso_joao()
        caso.parecer_final = "Parecer com acentuação: ç ã é ô."
        caso.diligencia = "Reportar e Cancelar"
        caso.jurisprudencias_selecionadas = ["Ausência de Resposta ao EDD"]
        caso.scorecard_drivers_marcados = nomes("AML Nupag", "Customer Critical", 2)
        aplicar_timeline_ao_caso(caso, random.Random(5))
        pdf = b"%PDF-1.4 teste"
        self.store.salvar_caso(caso, pdf)

        # arquivos no formato esperado
        self.assertTrue(os.path.exists(os.path.join(self.dir, "caso_2026-ABC123.json")))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "pdfs", "dossie_2026-ABC123.pdf")))

        # índice
        indice = self.store.listar_indice()
        self.assertEqual(len(indice), 1)
        self.assertEqual(indice[0]["numero_caso"], "2026-ABC123")
        self.assertEqual(indice[0]["nome_cliente"], "João Paulo Carvalho Dias")
        self.assertEqual(indice[0]["diligencia"], "Reportar e Cancelar")
        self.assertNotIn("risco", indice[0])  # o dossiê não classifica risco

        # busca: exata, por trecho, sem diferenciar caixa, vazia e inexistente
        self.assertEqual(len(self.store.buscar_por_numero("2026-ABC123")), 1)
        self.assertEqual(len(self.store.buscar_por_numero("abc")), 1)
        self.assertEqual(len(self.store.buscar_por_numero("  C123 ")), 1)
        self.assertEqual(self.store.buscar_por_numero(""), [])
        self.assertEqual(self.store.buscar_por_numero("CASO-00000000"), [])

        # abrir: tudo volta idêntico, inclusive resolução, avaliação e gráfico
        aberto = self.store.carregar_caso("2026-ABC123")
        self.assertEqual(aberto.to_dict(), caso.to_dict())
        self.assertEqual(aberto.parecer_final, "Parecer com acentuação: ç ã é ô.")
        self.assertEqual(aberto.nota_qualidade(), 85)
        self.assertEqual(len(aberto.timeline_creditos), 183)
        self.assertEqual(self.store.carregar_pdf("2026-ABC123"), pdf)
        self.assertIsNone(self.store.carregar_caso("2026-NAOEXISTE"))

    def test_regravar_substitui_sem_duplicar(self):
        caso = caso_joao()
        self.store.salvar_caso(caso)
        caso.diligencia = "Clear (arquivar)"
        self.store.salvar_caso(caso)
        self.assertEqual(len(self.store.listar_indice()), 1)
        self.assertEqual(self.store.listar_indice()[0]["diligencia"], "Clear (arquivar)")

    def test_ordem_mais_recente_primeiro(self):
        for i, quando in enumerate(("2026-10-01T10:00:00", "2026-10-03T10:00:00", "2026-10-02T10:00:00")):
            c = caso_joao(f"2026-NUM00{i}")
            c.criado_em = quando
            self.store.salvar_caso(c)
        self.assertEqual([i["numero_caso"] for i in self.store.listar_indice()],
                         ["2026-NUM001", "2026-NUM002", "2026-NUM000"])

    def test_numero_malformado_nao_vira_caminho(self):
        self.assertIsNone(self.store.carregar_caso("../../etc/passwd"))
        self.assertIsNone(self.store.carregar_pdf("../x"))
        with self.assertRaises(ValueError):
            self.store.salvar_caso(Caso("../fora", "Cripto"))

    def test_indice_corrompido_e_reconstruido(self):
        self.store.salvar_caso(caso_joao())
        with open(os.path.join(self.dir, "indice_dossies.json"), "w") as f:
            f.write("{quebrado")
        self.assertEqual([i["numero_caso"] for i in self.store.listar_indice()], ["2026-ABC123"])

    def test_gravacoes_simultaneas_nao_perdem_casos(self):
        def gravar(i):
            ArmazenamentoLocal(self.dir).salvar_caso(caso_joao(f"2026-PAR{i:03d}"))
        ts = [threading.Thread(target=gravar, args=(i,)) for i in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(self.store.listar_indice()), 12)
        self.assertEqual(len(self.store.reconstruir_indice()), 12)

    def test_caso_antigo_sem_campos_novos_ainda_abre(self):
        d = caso_joao().to_dict()
        for k in ("data_alerta", "genero", "timeline_creditos", "resolucao_salva_em", "schema_version"):
            d.pop(k)
        d["campo_de_versao_futura"] = 1
        with open(os.path.join(self.dir, "caso_2026-OLD001.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        c = self.store.carregar_caso("2026-OLD001")
        self.assertEqual(c.nome_cliente, "João Paulo Carvalho Dias")
        self.assertEqual(c.data_alerta, "")


if __name__ == "__main__":
    unittest.main()
