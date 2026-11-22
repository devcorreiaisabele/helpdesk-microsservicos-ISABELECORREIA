"""Erros de negócio e seu mapeamento para HTTP."""


class ErroAplicacao(Exception):
    status_code = 500

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class NaoAutenticado(ErroAplicacao):
    status_code = 401


class SemPermissao(ErroAplicacao):
    status_code = 403


class NaoEncontrado(ErroAplicacao):
    status_code = 404


class RegraDeNegocio(ErroAplicacao):
    status_code = 400


class ServicoIndisponivel(ErroAplicacao):
    status_code = 503
