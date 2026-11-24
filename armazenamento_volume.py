# -*- coding: utf-8 -*-
"""
Sentinela PLD - Banco de Dossiês em um Volume do Unity Catalog, pela API de arquivos
====================================================================================

O Databricks Apps não enxerga `/Volumes/...` como pasta comum, então o Banco de Dossiês não pode usar
`ArmazenamentoLocal` apontando para o Volume. Esta classe tem a mesma interface, mas grava e lê pela API de
arquivos do Databricks SDK (`WorkspaceClient().files`).

Layout, dentro do Volume (`SENTINELA_VOLUME_DOSSIES`, ex.: `/Volumes/usr/sentinela_aml/dossies`):
    casos/<numero>.json          o caso completo
    pdfs/dossie_<numero>.pdf     o PDF mais recente
    indice/<numero>.json         uma linha do índice por caso (nome, tipo, diligência, datas)

Não há índice único nem trava: cada caso escreve só os próprios arquivos, então dois analistas salvando ao
mesmo tempo não se atropelam. A lista dos casos é montada lendo as linhas de `indice/` (guardada em memória por
poucos segundos e renovada a cada gravação).

Ativação: `criar_armazenamento()` usa o Volume só se `SENTINELA_VOLUME_DOSSIES` estiver definida e uma gravação
de teste funcionar. Se faltar permissão ou a API falhar, volta para `ArmazenamentoLocal` (pasta
`SENTINELA_DATA_DIR`) e devolve o motivo, para o app mostrar o aviso em vez de cair.
"""
from __future__ import annotations

import concurrent.futures
import io
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core import ArmazenamentoLocal, Caso, numero_caso_valido

ENV_VOLUME = "SENTINELA_VOLUME_DOSSIES"
ENV_PERFIL = "SENTINELA_SQL_PERFIL"  # o mesmo perfil de CLI usado na gravação SQL (só fora do Databricks Apps)
VALIDADE_LISTA_S = 15.0
log = logging.getLogger("sentinela.armazenamento")


def _nao_encontrado(erro: Exception) -> bool:
    from databricks.sdk.errors import NotFound
    return isinstance(erro, (NotFound, FileNotFoundError))


class ArmazenamentoVolume:
    """Mesma interface pública de `ArmazenamentoLocal`: salvar_caso, carregar_caso, carregar_pdf,
    listar_indice e buscar_por_numero."""

    def __init__(self, base: str, cliente: Any):
        self.base = base.rstrip("/")
        self._files = cliente.files
        self._lock = threading.Lock()
        self._lista: Optional[List[Dict[str, Any]]] = None
        self._lista_em = 0.0

    # -- caminhos --------------------------------------------------------
    def _caminho(self, pasta: str, nome: str) -> str:
        return f"{self.base}/{pasta}/{nome}"

    def _caso_path(self, numero_caso: str) -> str:
        if not numero_caso_valido(numero_caso):
            raise ValueError(f"Número de caso inválido: {numero_caso!r}")
        return self._caminho("casos", f"{numero_caso}.json")

    def _pdf_path(self, numero_caso: str) -> str:
        if not numero_caso_valido(numero_caso):
            raise ValueError(f"Número de caso inválido: {numero_caso!r}")
        return self._caminho("pdfs", f"dossie_{numero_caso}.pdf")

    def _indice_path(self, numero_caso: str) -> str:
        return self._caminho("indice", f"{numero_caso}.json")

    # -- arquivos --------------------------------------------------------
    def _escrever(self, path: str, dados: bytes) -> None:
        self._files.upload(path, io.BytesIO(dados), overwrite=True)

    def _ler(self, path: str) -> Optional[bytes]:
        try:
            return self._files.download(path).contents.read()
        except Exception as e:  # noqa: BLE001
            if _nao_encontrado(e):
                return None
            raise

    def verificar(self) -> None:
        """Grava e apaga um arquivo de teste; levanta exceção se o Volume não estiver acessível."""
        caminho = self._caminho("indice", ".teste_escrita")
        self._escrever(caminho, b"ok")
        self._files.delete(caminho)

    # -- API pública -----------------------------------------------------
    def salvar_caso(self, caso: Caso, pdf_bytes: Optional[bytes] = None) -> None:
        caso.atualizado_em = datetime.now().isoformat()
        self._escrever(self._caso_path(caso.numero_caso),
                       json.dumps(caso.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"))
        if pdf_bytes:
            self._escrever(self._pdf_path(caso.numero_caso), pdf_bytes)
        entrada = ArmazenamentoLocal._entrada_indice(caso)
        self._escrever(self._indice_path(caso.numero_caso), json.dumps(entrada, ensure_ascii=False).encode("utf-8"))
        with self._lock:
            self._lista = None  # a próxima consulta lê de novo

    def carregar_caso(self, numero_caso: str) -> Optional[Caso]:
        if not numero_caso_valido(numero_caso):
            return None
        dados = self._ler(self._caso_path(numero_caso))
        return Caso.from_dict(json.loads(dados.decode("utf-8"))) if dados is not None else None

    def carregar_pdf(self, numero_caso: str) -> Optional[bytes]:
        if not numero_caso_valido(numero_caso):
            return None
        return self._ler(self._pdf_path(numero_caso))

    def _ler_entrada(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            dados = self._ler(path)
            entrada = json.loads(dados.decode("utf-8")) if dados is not None else None
        except Exception:  # noqa: BLE001 - uma entrada ruim não derruba a lista
            return None
        return entrada if isinstance(entrada, dict) and entrada.get("numero_caso") else None

    def listar_indice(self) -> List[Dict[str, Any]]:
        """Todos os dossiês, do mais recente para o mais antigo."""
        with self._lock:
            if self._lista is not None and time.time() - self._lista_em < VALIDADE_LISTA_S:
                return list(self._lista)
        pasta = f"{self.base}/indice"
        try:
            caminhos = [e.path or f"{pasta}/{e.name}" for e in self._files.list_directory_contents(pasta)
                        if not e.is_directory and (e.name or "").endswith(".json")]
        except Exception as e:  # noqa: BLE001
            if not _nao_encontrado(e):
                raise
            caminhos = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            entradas = [x for x in pool.map(self._ler_entrada, caminhos) if x]
        entradas.sort(key=lambda e: e.get("criado_em", ""), reverse=True)
        with self._lock:
            self._lista, self._lista_em = entradas, time.time()
        return list(entradas)

    def buscar_por_numero(self, termo: str) -> List[Dict[str, Any]]:
        """Casos cujo número contém o trecho digitado (maiúsculas e minúsculas não importam)."""
        termo = (termo or "").strip().lower()
        if not termo:
            return []
        return [i for i in self.listar_indice() if termo in str(i.get("numero_caso", "")).lower()]


def _cliente(perfil: Optional[str]) -> Any:
    """Cliente do Databricks com a credencial do próprio app (service principal); fora do Databricks Apps,
    use um perfil do CLI. Não usa o token do segredo: o acesso ao Volume é do service principal."""
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(profile=perfil) if perfil else WorkspaceClient()


def criar_armazenamento() -> Tuple[Any, str]:
    """Devolve (armazenamento, aviso). Usa o Volume se `SENTINELA_VOLUME_DOSSIES` estiver definida e acessível;
    senão, a pasta local (`SENTINELA_DATA_DIR`), com o motivo no aviso (vazio quando a pasta local é o esperado)."""
    base = os.environ.get(ENV_VOLUME, "").strip()
    if not base:
        return ArmazenamentoLocal(), ""
    try:
        armazenamento = ArmazenamentoVolume(base, _cliente(os.environ.get(ENV_PERFIL) or None))
        armazenamento.verificar()
        log.warning("Banco de Dossiês: usando o Volume %s", base)
        return armazenamento, ""
    except Exception as e:  # noqa: BLE001 - sem acesso ao Volume, o app segue com a pasta local
        motivo = " ".join(str(e).split())[:160] or type(e).__name__
        log.error("Banco de Dossiês: Volume %s inacessível (%s: %s); usando a pasta local", base, type(e).__name__, motivo)
        return ArmazenamentoLocal(), (f"Não foi possível acessar o Volume {base} ({motivo}). Os dossiês estão sendo "
                                      "salvos na pasta local do app, que é apagada quando o app reinicia.")
