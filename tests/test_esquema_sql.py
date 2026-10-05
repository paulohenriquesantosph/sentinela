# -*- coding: utf-8 -*-
"""O esquema SQL (esquema_sql.py) precisa acompanhar o modelo do app (core.py).

Rodar, da raiz do projeto:
    ./venv/bin/python -m unittest tests.test_esquema_sql -v
Não acessa o Databricks: só confere o DDL gerado.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import esquema_sql  # noqa: E402


def _colunas(ddl: str) -> set:
    return set(re.findall(r"^\s{2}([a-z_0-9]+) (?:STRING|INT|DOUBLE|DATE|TIMESTAMP)\b", ddl, flags=re.M))


class TestEsquemaSql(unittest.TestCase):
    def setUp(self):
        self.ddl = {c.split("usr.sentinela_aml.")[1].split(" ")[0]: c for c in esquema_sql.gerar_ddl()}

    def test_sete_tabelas_na_ordem_certa(self):
        self.assertEqual(list(self.ddl), esquema_sql.TABELAS)
        self.assertEqual(len(esquema_sql.TABELAS), 7)
        self.assertEqual(esquema_sql.TABELAS[0], "casos")  # as filhas referenciam casos
        for comando in self.ddl.values():
            self.assertIn("CREATE TABLE IF NOT EXISTS usr.sentinela_aml.", comando)  # nunca apaga nem recria
            self.assertIn("USING DELTA", comando)

    def test_so_o_dossie_e_gravado_resolucao_e_avaliacao_ficam_de_fora(self):
        todas = set()
        for ddl in self.ddl.values():
            todas |= _colunas(ddl)
        for proibida in ("parecer_final", "alineas", "anexos", "diligencia", "resolucao_bloqueada_em",
                         "scorecard_tipo", "scorecard_feedback", "scorecard_salvo_em", "nota_qualidade",
                         "jurisprudencias_selecionadas", "razoes_clear_selecionadas", "driver", "secao"):
            self.assertNotIn(proibida, todas, proibida)
        for tabela in ("selecoes_resolucao", "avaliacao_drivers", "resolucao_secoes"):
            self.assertNotIn(tabela, self.ddl)

    def test_todo_campo_escalar_do_modelo_tem_coluna_ou_e_declarado_nao_gravado(self):
        for f in esquema_sql.campos_escalares(core.Caso):
            if f.name in esquema_sql.EXCLUIDOS_CASOS:
                self.assertNotIn(f.name, _colunas(self.ddl["casos"]), f.name)
            else:
                self.assertIn(f.name, _colunas(self.ddl["casos"]), f"Caso.{f.name} sem coluna em casos")
        pares = [(core.ContraparteMovimentacao, "contrapartes"), (core.Socio, "socios"),
                 (core.OutraMovimentacao, "outras_movimentacoes"), (core.ItemArredondamento, "arredondamentos"),
                 (core.MensagemPix, "mensagens_pix")]
        for classe, tabela in pares:
            for f in esquema_sql.campos_escalares(classe):
                self.assertIn(f.name, _colunas(self.ddl[tabela]), f"{classe.__name__}.{f.name} sem coluna em {tabela}")

    def test_toda_lista_do_caso_tem_destino_ou_e_declarada_nao_gravada(self):
        listas = set(esquema_sql.campos_de_lista(core.Caso))
        self.assertEqual(listas, set(esquema_sql.COBERTURA_LISTAS) | esquema_sql.NAO_GRAVADOS_LISTAS)
        self.assertFalse(set(esquema_sql.COBERTURA_LISTAS) & esquema_sql.NAO_GRAVADOS_LISTAS)
        for destino in esquema_sql.COBERTURA_LISTAS.values():
            self.assertIn(destino, esquema_sql.TABELAS)

    def test_chaves_tipo_caso_nas_filhas_e_colunas_derivadas(self):
        casos = self.ddl["casos"]
        self.assertIn("PRIMARY KEY (numero_caso)", casos)
        self.assertIn("numero_caso STRING NOT NULL", casos)
        for col in ("mov_total_credito_valor", "mov_periodo_inicio", "montante_cripto_valor", "caso_json",
                    "gravado_em", "comp_evasao_cripto", "criado_em", "tipo_caso"):
            self.assertIn(col, _colunas(casos), col)
        for filha in esquema_sql.TABELAS[1:]:
            self.assertIn("FOREIGN KEY (numero_caso) REFERENCES usr.sentinela_aml.casos (numero_caso)",
                          self.ddl[filha], filha)
            for col in ("numero_caso", "tipo_caso"):  # tipo_caso repetido: filtra por tipo sem JOIN
                self.assertIn(f"{col} STRING NOT NULL", self.ddl[filha], f"{filha}.{col}")

    def test_tipos_dos_campos_de_data_e_hora(self):
        casos = self.ddl["casos"]
        for campo in ("criado_em", "atualizado_em"):
            self.assertRegex(casos, rf"\b{campo} TIMESTAMP\b")
        self.assertRegex(casos, r"\bschema_version INT\b")
        self.assertRegex(casos, r"\bdata_alerta STRING\b")  # o texto original é mantido
        self.assertRegex(self.ddl["timeline_diaria"], r"\bdata DATE NOT NULL\b")

    def test_aspas_nos_comentarios_nao_quebram_o_sql(self):
        for nome, comando in list(self.ddl.items()) + [(f"view {i}", v) for i, v in enumerate(esquema_sql.gerar_views())]:
            for linha in comando.splitlines():
                if "COMMENT '" in linha:
                    texto = linha.split("COMMENT '", 1)[1].rstrip(",").rstrip()
                    self.assertTrue(texto.endswith("'"), f"{nome}: {linha}")
                    self.assertNotIn("'", texto[:-1].replace("''", ""), f"{nome}: {linha}")


class TestViewsPorTipo(unittest.TestCase):
    def setUp(self):
        self.views = {v.split("usr.sentinela_aml.")[1].split("\n")[0].strip(): v for v in esquema_sql.gerar_views()}
        self.casos = {c.nome for c in esquema_sql.definir_esquema()["casos"]}

    def _colunas_view(self, nome):
        corpo = self.views[nome].split("AS SELECT\n", 1)[1].split("\nFROM ", 1)[0]
        return [c.strip() for c in corpo.split(",\n")]

    def test_uma_view_por_tipo_de_caso(self):
        self.assertEqual(set(self.views), {"casos_pf", "casos_pj", "casos_cripto", "casos_nuinvest", "casos_under18"})
        filtros = {"casos_pf": "Pessoa Física (PF)", "casos_pj": "Pessoa Jurídica (PJ)", "casos_cripto": "Cripto",
                   "casos_nuinvest": "NuInvest", "casos_under18": "Under 18"}
        for nome, tipo in filtros.items():
            self.assertIn(f"WHERE tipo_caso = '{tipo}'", self.views[nome], nome)
            self.assertIn("CREATE OR REPLACE VIEW", self.views[nome])
        self.assertEqual(set(filtros.values()), set(core.TIPOS_CASO))  # nenhum tipo do app ficou sem view

    def test_colunas_de_cada_view_existem_em_casos(self):
        for nome in self.views:
            for col in self._colunas_view(nome):
                self.assertIn(col, self.casos, f"{nome}.{col}")
            self.assertNotIn("caso_json", self._colunas_view(nome))

    def test_so_as_colunas_do_tipo(self):
        pj, pf = self._colunas_view("casos_pj"), self._colunas_view("casos_pf")
        self.assertIn("nome_empresa", pj)
        self.assertNotIn("nome_cliente", pj)
        self.assertIn("nome_cliente", pf)
        self.assertNotIn("nome_empresa", pf)
        self.assertIn("comp_evasao_cripto", self._colunas_view("casos_cripto"))
        for outra in ("casos_pf", "casos_pj", "casos_nuinvest", "casos_under18"):
            self.assertNotIn("comp_evasao_cripto", self._colunas_view(outra), outra)
        self.assertIn("rep_nome", self._colunas_view("casos_under18"))
        self.assertNotIn("rep_nome", self._colunas_view("casos_nuinvest"))
        for nome in self.views:  # o que é comum a todos
            for col in ("numero_caso", "tipo_caso", "fator_gerador", "mov_total_credito", "outras_info", "criado_em"):
                self.assertIn(col, self._colunas_view(nome), f"{nome}.{col}")

    def test_toda_coluna_de_casos_esta_em_alguma_view_ou_e_tecnica(self):
        em_views = set()
        for nome in self.views:
            em_views |= set(self._colunas_view(nome))
        self.assertEqual(self.casos - em_views, set(esquema_sql.COLUNAS_TECNICAS))


if __name__ == "__main__":
    unittest.main()
