class DomainError(Exception):
    def __init__(self, status: int, mensagem: str):
        self.status = status
        self.message = mensagem
        super().__init__(mensagem)
