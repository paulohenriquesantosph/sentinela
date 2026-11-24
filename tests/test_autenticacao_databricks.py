# -*- coding: utf-8 -*-
"""Seleção de credencial e contrato SQL com SDK mockado, sem acesso ao Databricks.

Rodar, da raiz do projeto:
    python -m unittest tests.test_autenticacao_databricks -v

Todas as credenciais abaixo são fictícias. O ambiente é isolado e nenhum
WorkspaceClient real é criado, mesmo nos testes de falha de autenticação.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout, StatementState

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gravacao_sql as g  # noqa: E402


HOST = "https://workspace-de-teste.invalid"
WAREHOUSE = "warehouse-ficticio"
TOKEN = "token-ficticio-sem-validade"
PERFIL = "perfil-de-teste"
ENV_TOKEN = "SENTINELA_DATABRICKS_TOKEN"


class TestAutenticacaoDatabricks(unittest.TestCase):
    def setUp(self):
        g.executor_databricks.cache_clear()
        self.addCleanup(g.executor_databricks.cache_clear)

        ambiente = mock.patch.dict(os.environ, {"DATABRICKS_HOST": HOST}, clear=True)
        ambiente.start()
        self.addCleanup(ambiente.stop)

        workspace = mock.patch("databricks.sdk.WorkspaceClient")
        self.workspace = workspace.start()
        self.addCleanup(workspace.stop)
        self.cliente = self.workspace.return_value
        self.executar_statement = self.cliente.statement_execution.execute_statement
        self.executar_statement.return_value = SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None)
        )

    def _ativar_pat(self):
        os.environ[ENV_TOKEN] = TOKEN

    def _confirmar_cliente_pat(self):
        self.workspace.assert_called_once_with(host=HOST, token=TOKEN, auth_type="pat")

    def test_pat_explicito_prevalece_sobre_perfil_e_oauth_do_ambiente(self):
        os.environ.update({
            ENV_TOKEN: TOKEN,
            "DATABRICKS_CLIENT_ID": "cliente-oauth-ficticio",
            "DATABRICKS_CLIENT_SECRET": "segredo-oauth-ficticio",
            "DATABRICKS_AUTH_TYPE": "oauth-m2m",
        })

        executar = g.executor_databricks(WAREHOUSE, PERFIL)

        self.assertTrue(callable(executar))
        self._confirmar_cliente_pat()
        self.executar_statement.assert_not_called()

    def test_token_lido_do_segredo_pelo_service_principal(self):
        import base64
        os.environ["SENTINELA_TOKEN_SECRET"] = "scope-ficticio/chave-ficticia"
        self.cliente.secrets.get_secret.return_value = SimpleNamespace(
            value=base64.b64encode(TOKEN.encode()).decode())

        executar = g.executor_databricks(WAREHOUSE)

        self.assertTrue(callable(executar))
        self.cliente.secrets.get_secret.assert_called_once_with(scope="scope-ficticio", key="chave-ficticia")
        self.assertEqual(self.workspace.call_args_list,
                         [mock.call(), mock.call(host=HOST, token=TOKEN, auth_type="pat")])

    def test_perfil_explicito_sem_token(self):
        executar = g.executor_databricks(WAREHOUSE, PERFIL)

        self.assertTrue(callable(executar))
        self.workspace.assert_called_once_with(profile=PERFIL)
        self.executar_statement.assert_not_called()

    def test_perfil_explicito_com_token_em_branco(self):
        os.environ[ENV_TOKEN] = " \t\n "

        g.executor_databricks(WAREHOUSE, PERFIL)

        self.workspace.assert_called_once_with(profile=PERFIL)

    def test_sem_token_nem_perfil_falha_sem_criar_cliente(self):
        with self.assertRaises(RuntimeError):
            g.executor_databricks(WAREHOUSE)

        self.workspace.assert_not_called()
        self.executar_statement.assert_not_called()

    def test_token_em_branco_sem_perfil_falha_sem_criar_cliente(self):
        os.environ[ENV_TOKEN] = " \t\n "

        with self.assertRaises(RuntimeError):
            g.executor_databricks(WAREHOUSE)

        self.workspace.assert_not_called()
        self.executar_statement.assert_not_called()

    def test_pat_invalido_ao_criar_cliente_nao_tenta_perfil(self):
        self._ativar_pat()
        erro = RuntimeError("Credencial de teste rejeitada")
        self.workspace.side_effect = erro

        with self.assertRaises(RuntimeError) as ctx:
            g.executor_databricks(WAREHOUSE, PERFIL)

        self.assertIs(ctx.exception, erro)
        self._confirmar_cliente_pat()
        self.executar_statement.assert_not_called()

    def test_pat_rejeitado_na_execucao_nao_tenta_perfil(self):
        self._ativar_pat()
        executar = g.executor_databricks(WAREHOUSE, PERFIL)
        erro = RuntimeError("HTTP 401 simulado")
        self.executar_statement.side_effect = erro

        with self.assertRaises(RuntimeError) as ctx:
            executar("SELECT :valor", [{"name": "valor", "value": "teste"}])

        self.assertIs(ctx.exception, erro)
        self._confirmar_cliente_pat()
        self.executar_statement.assert_called_once()

    def test_preserva_warehouse_sql_parametros_e_timeout_do_sdk(self):
        self._ativar_pat()
        executar = g.executor_databricks(WAREHOUSE)
        sql = "SELECT :texto, :quantidade"
        parametros = [
            {"name": "texto", "value": "Texto sintético com 'aspas'"},
            {"name": "quantidade", "value": "2", "type": "INT"},
        ]

        executar(sql, parametros)

        self._confirmar_cliente_pat()
        self.executar_statement.assert_called_once()
        args, kwargs = self.executar_statement.call_args
        self.assertEqual(args, ())
        self.assertEqual(kwargs["warehouse_id"], WAREHOUSE)
        self.assertEqual(kwargs["statement"], sql)
        self.assertEqual(kwargs["wait_timeout"], "50s")
        self.assertEqual(kwargs["on_wait_timeout"], ExecuteStatementRequestOnWaitTimeout.CANCEL)
        self.assertEqual(
            [(p.name, p.value, p.type) for p in kwargs["parameters"]],
            [("texto", "Texto sintético com 'aspas'", "STRING"), ("quantidade", "2", "INT")],
        )
        self.assertNotIn("type", parametros[0])  # A conversão não modifica a entrada.

    def test_lista_vazia_de_parametros_continua_enviada_como_none(self):
        self._ativar_pat()
        executar = g.executor_databricks(WAREHOUSE)

        executar("SELECT 1", [])

        self.executar_statement.assert_called_once()
        self.assertIsNone(self.executar_statement.call_args.kwargs["parameters"])


if __name__ == "__main__":
    unittest.main()
