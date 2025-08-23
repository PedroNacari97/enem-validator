from pydantic import BaseModel


class StartBody(BaseModel):
    chave: str
