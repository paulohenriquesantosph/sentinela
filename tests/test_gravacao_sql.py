# -*- coding: utf-8 -*-
"""Gravação do dossiê gerado nas tabelas (gravacao_sql.py), com um executor falso: não acessa o Databricks.

Rodar, da raiz do projeto:
    ./venv/bin/python -m unittest tests.test_gravacao_sql -v
"""
import json
import os
import random
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import esquema_sql  # noqa: E402
import gravacao_sql as g  # noqa: E402

PROIBIDO = "NÃO DEVE SER GRAVADO"


def caso_completo(tipo="Cripto") -> core.Caso:
    c = core.Caso(numero_caso="2026-TESTE1", tipo_caso=tipo, fator_gerador="Alerta 'x'", data_alerta="15/06/2026",
                  sentenca="Texto com ' aspa; e DROP TABLE usr.sentinela_aml.casos; --\nlinha 2",
                  nome_cliente="Marina Costa", genero="F", idade="31", renda_presumida="R$3.000,00",
                  mov_periodo="01/04/2026 até 30/06/2026", mov_total_credito="R$100.000,00",
                  mov_total_debito="R$90.000,00", comp_evasao="Evasão Parcial (Pequena Parcela nos Débitos)",
                  comp_evasao_cripto="Só Créditos (Sem Débitos)", outras_info="Exchange: Binance",
                  # Resolução e Avaliação preenchidas de propósito: nada disso pode ser gravado
                  parecer_final=PROIBIDO, alineas=PROIBIDO, anexos=PROIBIDO, diligencia="Reportar",
                  scorecard_feedback=PROIBIDO, scorecard_tipo="AML Nupag", scorecard_salvo_em="2026-10-04T10:00:00",
                  resolucao_bloqueada_em="2026-10-04T10:00:00")
    c.contrapartes_credito = [core.ContraparteMovimentacao(nome="João O'Neil", porcentagem="25%", valor="R$25.000,00",
                                                           pep="Sim", pep_detalhe="Vereador"),
                              core.ContraparteMovimentacao(tipo="Pessoa Jurídica", nome="ACME",
                                                           faturamento_presumido="R$80.000,00")]
    c.contrapartes_debito = [core.ContraparteMovimentacao(nome="Beto", porcentagem="100%")]
    c.socios = [core.Socio(nome="Ana", renda_presumida="R$2.000,00", patrimonio="R$10.000,00")]
    c.outras_movimentacoes = [core.OutraMovimentacao(tipo="Criptomoedas", info="Enviou R$200.000,00"),
                              core.OutraMovimentacao(tipo="Saques", info="sem valor")]
    c.arredondamento_itens = [core.ItemArredondamento(quantidade="43 transações", valor="R$1.000,00")]
    c.pix_itens = [core.MensagemPix(cred_deb="Débitos", quantidade="5", mensagem="pagamento")]
    core.aplicar_timeline_ao_caso(c, random.Random(1))
    core.aplicar_timeline_cripto_ao_caso(c, random.Random(1))
    c.jurisprudencias_selecionadas = [PROIBIDO]
    c.razoes_clear_selecionadas = [PROIBIDO]
    c.scorecard_drivers_marcados = [PROIBIDO]
    c.resolucao_salva_em = {"parecer": "2026-10-04T10:00:00"}
    return c


class ExecutorFalso:
    def __init__(self, falhar_em=None):
        self.comandos = []
        self.falhar_em = falhar_em
        self._trava = threading.Lock()

    def __call__(self, sql, parametros):
        with self._trava:
            self.comandos.append((sql, parametros))
        if self.falhar_em and self.falhar_em in sql:
            raise g.ErroGravacao(f"falhou {self.falhar_em}")


class TestLinhas(unittest.TestCase):
    def setUp(self):
        self.caso = caso_completo()
        self.linhas = g.linhas_do_caso(self.caso)

    def test_resolucao_e_avaliacao_nunca_vao_para_as_tabelas(self):
        texto = json.dumps(self.linhas, ensure_ascii=False)
        self.assertNotIn(PROIBIDO, texto)
        caso = self.linhas["casos"][0]
        for coluna in esquema_sql.EXCLUIDOS_CASOS:
            self.assertNotIn(coluna, caso, coluna)
        sem = json.loads(caso["caso_json"])
        self.assertEqual((sem["parecer_final"], sem["diligencia"], sem["anexos"], sem["scorecard_feedback"],
                          sem["scorecard_tipo"], sem["jurisprudencias_selecionadas"], sem["resolucao_salva_em"],
                          sem["scorecard_drivers_marcados"], sem["resolucao_bloqueada_em"]),
                         ("", "", "", "", "", [], {}, [], ""))
        self.assertEqual(sem["nome_cliente"], "Marina Costa")  # o dossiê continua completo

    def test_nao_altera_o_caso_original(self):
        g.linhas_do_caso(self.caso)
        self.assertEqual((self.caso.parecer_final, self.caso.diligencia, self.caso.jurisprudencias_selecionadas),
                         (PROIBIDO, "Reportar", [PROIBIDO]))

    def test_caso_e_derivadas(self):
        c = self.linhas["casos"][0]
        self.assertEqual((c["numero_caso"], c["tipo_caso"], c["schema_version"]), ("2026-TESTE1", "Cripto", 2))
        self.assertEqual((c["data_alerta"], c["data_alerta_dt"]), ("15/06/2026", "2026-06-15"))
        self.assertEqual((c["mov_periodo_inicio"], c["mov_periodo_fim"]), ("2026-04-01", "2026-06-30"))
        self.assertEqual((c["mov_total_credito_valor"], c["mov_total_debito_valor"]), (100000.0, 90000.0))
        self.assertEqual((c["renda_presumida_valor"], c["montante_cripto_valor"]), (3000.0, 200000.0))
        self.assertIsNone(c["faturamento_presumido_valor"])  # vazio vira NULL
        self.assertIsNone(c["profissao_informada"])
        self.assertTrue(c["criado_em"] and c["gravado_em"])
        self.assertEqual(c["sentenca"], self.caso.sentenca)  # texto livre guardado literalmente

    def test_filhas_levam_tipo_caso_e_valores_numericos(self):
        for tabela in esquema_sql.TABELAS[1:]:
            for linha in self.linhas[tabela]:
                self.assertEqual((linha["numero_caso"], linha["tipo_caso"]), ("2026-TESTE1", "Cripto"), tabela)
        cps = self.linhas["contrapartes"]
        self.assertEqual([(l["lado"], l["ordem"], l["nome"]) for l in cps],
                         [("credito", 0, "João O'Neil"), ("credito", 1, "ACME"), ("debito", 0, "Beto")])
        self.assertEqual((cps[0]["porcentagem_valor"], cps[0]["valor_valor"], cps[0]["pep"]), (25.0, 25000.0, "Sim"))
        self.assertEqual(cps[1]["faturamento_presumido_valor"], 80000.0)
        self.assertEqual(self.linhas["socios"][0]["patrimonio_valor"], 10000.0)
        om = self.linhas["outras_movimentacoes"]
        self.assertEqual((om[0]["montante_valor"], om[1]["montante_valor"]), (200000.0, None))
        self.assertEqual((self.linhas["arredondamentos"][0]["quantidade_valor"],
                          self.linhas["arredondamentos"][0]["valor_valor"]), (43, 1000.0))
        self.assertEqual(self.linhas["mensagens_pix"][0]["quantidade_valor"], 5)

    def test_timeline_diaria_das_duas_timelines(self):
        tl = self.linhas["timeline_diaria"]
        bancaria = [l for l in tl if l["timeline"] == "bancaria"]
        cripto = [l for l in tl if l["timeline"] == "cripto"]
        self.assertEqual((len(bancaria), len(cripto)), (91, 91))
        self.assertEqual((bancaria[0]["data"], bancaria[-1]["data"]), ("2026-04-01", "2026-06-30"))
        self.assertAlmostEqual(sum(l["creditos"] for l in bancaria), 100000.0, places=2)
        self.assertEqual(sum(l["debitos"] for l in cripto), 0)  # modo "só créditos"

    def test_colunas_batem_com_o_esquema(self):
        esq = esquema_sql.definir_esquema()
        for tabela, linhas in self.linhas.items():
            nomes = {c.nome for c in esq[tabela]}
            for linha in linhas:
                self.assertEqual(set(linha), nomes, tabela)

    def test_caso_sem_nada_so_gera_a_linha_de_casos(self):
        vazio = g.linhas_do_caso(core.Caso(numero_caso="2026-VAZIO", tipo_caso="Pessoa Física (PF)"))
        self.assertEqual({t: len(v) for t, v in vazio.items()},
                         {"casos": 1, **{t: 0 for t in esquema_sql.TABELAS[1:]}})
        self.assertIsNone(vazio["casos"][0]["data_alerta_dt"])


class TestComandos(unittest.TestCase):
    def test_texto_do_usuario_vai_como_parametro_e_nunca_dentro_do_sql(self):
        caso = caso_completo()
        sql, params = g.comando_insert("casos", g.linhas_do_caso(caso)["casos"])
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("Marina", sql)
        self.assertEqual([p["name"] for p in params], ["linhas"])
        self.assertIn("DROP TABLE usr.sentinela_aml.casos", params[0]["value"])  # viaja no parâmetro
        self.assertEqual(json.loads(params[0]["value"])[0]["sentenca"], caso.sentenca)
        self.assertIn("from_json(:linhas", sql)

    def test_insert_cobre_todas_as_colunas_com_casts(self):
        linhas = g.linhas_do_caso(caso_completo())
        for tabela in esquema_sql.TABELAS:
            sql, _ = g.comando_insert(tabela, linhas[tabela])
            self.assertTrue(sql.startswith(f"INSERT INTO usr.sentinela_aml.{tabela} ("))
            for c in esquema_sql.definir_esquema()[tabela]:
                self.assertIn(f"`{c.nome}`", sql, f"{tabela}.{c.nome}")
        sql, _ = g.comando_insert("casos", linhas["casos"])
        self.assertIn("CAST(r.`criado_em` AS TIMESTAMP)", sql)
        self.assertIn("CAST(r.`data_alerta_dt` AS DATE)", sql)
        self.assertIn("`mov_total_credito_valor`: DOUBLE", sql)
        self.assertIn("`schema_version`: INT", sql)

    def test_delete_por_numero_do_caso_com_parametro(self):
        sql, params = g.comando_delete("contrapartes", "2026-X'; DROP TABLE y; --")
        self.assertEqual(sql, "DELETE FROM usr.sentinela_aml.contrapartes WHERE numero_caso = :numero_caso")
        self.assertEqual(params, [{"name": "numero_caso", "value": "2026-X'; DROP TABLE y; --", "type": "STRING"}])


class TestGravarCaso(unittest.TestCase):
    def test_primeiro_o_caso_depois_as_filhas_so_as_que_tem_linhas(self):
        ex = ExecutorFalso()
        qtd = g.gravar_caso(caso_completo(), ex)
        self.assertIn("INTO usr.sentinela_aml.casos ", ex.comandos[0][0])
        tabelas = {c[0].split("usr.sentinela_aml.")[1].split(" ")[0] for c in ex.comandos}
        self.assertEqual(tabelas, set(esquema_sql.TABELAS))
        self.assertEqual(qtd["casos"], 1)
        self.assertEqual((qtd["contrapartes"], qtd["socios"], qtd["timeline_diaria"]), (3, 1, 182))
        self.assertFalse(any(c[0].startswith("DELETE") for c in ex.comandos))  # 1ª gravação: só INSERT

    def test_caso_simples_nao_gera_comando_para_tabela_vazia(self):
        ex = ExecutorFalso()
        g.gravar_caso(core.Caso(numero_caso="2026-VAZIO", tipo_caso="Pessoa Física (PF)"), ex)
        self.assertEqual(len(ex.comandos), 1)

    def test_nova_tentativa_apaga_antes_em_todas_as_tabelas(self):
        ex = ExecutorFalso()
        g.gravar_caso(caso_completo(), ex, limpar=True)
        deletes = [c for c in ex.comandos if c[0].startswith("DELETE")]
        self.assertEqual(len(deletes), len(esquema_sql.TABELAS))
        self.assertEqual(ex.comandos[: len(deletes)], deletes)  # primeiro os DELETE, depois os INSERT
        self.assertTrue(all(c[1][0]["value"] == "2026-TESTE1" for c in deletes))

    def test_falha_numa_filha_levanta_erro_com_a_tabela(self):
        ex = ExecutorFalso(falhar_em="usr.sentinela_aml.socios")
        with self.assertRaises(g.ErroGravacao) as ctx:
            g.gravar_caso(caso_completo(), ex)
        self.assertIn("socios", str(ctx.exception))

    def test_falha_no_caso_nao_tenta_as_filhas(self):
        ex = ExecutorFalso(falhar_em="INTO usr.sentinela_aml.casos ")
        with self.assertRaises(g.ErroGravacao):
            g.gravar_caso(caso_completo(), ex)
        self.assertEqual(len(ex.comandos), 1)

    def test_catalogo_e_schema_configuraveis(self):
        ex = ExecutorFalso()
        g.gravar_caso(core.Caso(numero_caso="2026-A", tipo_caso="Cripto"), ex, catalogo="meu_cat", schema="meu_sch")
        self.assertIn("INTO meu_cat.meu_sch.casos ", ex.comandos[0][0])


class TestSeConfigurado(unittest.TestCase):
    def test_desativado_sem_a_variavel(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(g.ENV_WAREHOUSE, None)
            with mock.patch.object(g, "executor_databricks") as exe:
                self.assertEqual(g.gravar_se_configurado(caso_completo()), ("desativado", ""))
                exe.assert_not_called()

    def test_ok_e_usa_catalogo_e_schema_do_ambiente(self):
        ex = ExecutorFalso()
        env = {g.ENV_WAREHOUSE: "wh123", g.ENV_CATALOGO: "cat", g.ENV_SCHEMA: "sch", g.ENV_PERFIL: "perfil"}
        with mock.patch.dict(os.environ, env), mock.patch.object(g, "executor_databricks", return_value=ex) as exe:
            self.assertEqual(g.gravar_se_configurado(caso_completo()), ("ok", "cat.sch"))
            exe.assert_called_once_with("wh123", "perfil")
        self.assertIn("INTO cat.sch.casos ", ex.comandos[0][0])

    def test_erro_nunca_levanta_excecao(self):
        env = {g.ENV_WAREHOUSE: "wh123"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(g, "executor_databricks", return_value=ExecutorFalso(falhar_em="casos")):
            status, msg = g.gravar_se_configurado(caso_completo())
        self.assertEqual(status, "erro")
        self.assertIn("falhou", msg)
        with mock.patch.dict(os.environ, env), mock.patch.object(g, "executor_databricks", side_effect=RuntimeError("sem credencial")):
            self.assertEqual(g.gravar_se_configurado(caso_completo()), ("erro", "sem credencial"))


class TestMigracao(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        self.pasta = tempfile.mkdtemp(prefix="sentinela_migra_")
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.store = core.ArmazenamentoLocal(self.pasta)

    def _salvar(self, numero, tipo="Pessoa Física (PF)", **kw):
        c = core.Caso(numero_caso=numero, tipo_caso=tipo, nome_cliente="João Paulo", **kw)
        c.parecer_final = PROIBIDO
        c.diligencia = "Reportar"
        c.contrapartes_credito = [core.ContraparteMovimentacao(nome="Ana", cidade_estado="Não informado")]
        self.store.salvar_caso(c, b"%PDF-1.4")
        return c

    def test_normaliza_o_marcador_antigo_em_qualquer_nivel(self):
        c = self._salvar("2026-A", cidade_estado="Não informado", registro_profissional="Não informado",
                         idade="30")
        alterados = g.normalizar_caso_antigo(c)
        self.assertEqual(sorted(alterados), ["cidade_estado", "contrapartes_credito[0].cidade_estado",
                                             "registro_profissional"])
        self.assertEqual((c.cidade_estado, c.idade, c.contrapartes_credito[0].nome), ("", "30", "Ana"))
        self.assertEqual(g.normalizar_caso_antigo(c), [])

    def test_migra_todos_os_casos_sem_resolucao_e_sem_marcador(self):
        self._salvar("2026-A", cidade_estado="Não informado")
        self._salvar("2026-B", tipo="Cripto")
        ex = ExecutorFalso()
        rel = g.migrar_pasta(self.pasta, ex)
        self.assertEqual(sorted(r["numero_caso"] for r in rel), ["2026-A", "2026-B"])
        self.assertTrue(all(r["status"] == "ok" for r in rel))
        comandos = " ".join(json.dumps(p) for _, params in ex.comandos for p in params)
        self.assertNotIn(PROIBIDO, comandos)
        self.assertNotIn("Não informado", comandos)
        deletes = [c for c in ex.comandos if c[0].startswith("DELETE")]
        self.assertEqual(len(deletes), 2 * len(esquema_sql.TABELAS))  # idempotente: apaga antes de regravar

    def test_erro_num_caso_nao_impede_os_outros(self):
        self._salvar("2026-A")
        self._salvar("2026-B")
        ex = ExecutorFalso()
        original = ex.__call__

        def falha_no_a(sql, params):
            if any(p["value"].startswith('[{"numero_caso": "2026-A"') or p["value"] == "2026-A" for p in params):
                raise g.ErroGravacao("falhou A")
            original(sql, params)
        rel = {r["numero_caso"]: r for r in g.migrar_pasta(self.pasta, falha_no_a)}
        self.assertEqual((rel["2026-A"]["status"], rel["2026-B"]["status"]), ("erro", "ok"))
        self.assertIn("falhou A", rel["2026-A"]["erro"])


if __name__ == "__main__":
    unittest.main()
