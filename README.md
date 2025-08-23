# ENEM Validator

Serviço FastAPI que automatiza a verificação de resultados do ENEM diretamente no portal do INEP.

## Como funciona
- Inicializa um navegador Chromium via Playwright.
- Abre a página de autenticidade do INEP e, se possível, pré-preenche a *chave de acesso*.
- O usuário resolve o CAPTCHA manualmente na interface própria.
- O servidor captura o HTML do resultado oficial, extrai nome, ano e notas e compara o CPF mascarado com o CPF da sessão.
- Uma imagem da página é mantida em memória para auditoria.

## Estrutura dos módulos
- `app.py`: ponto de entrada do FastAPI e registro das rotas/eventos.
- `browser.py`: inicialização do Playwright, gerenciamento de sessões e coleta de resultados.
- `config.py`: variáveis de ambiente e logger.
- `helpers.py`: utilitários para parsing e formatação.
- `models.py`: modelos Pydantic usados pelas rotas.
- `routes.py`: endpoints HTTP e renderização de templates.

## Executando localmente
```bash
pip install -r requirements.txt
playwright install chromium
# Linux: playwright install-deps chromium  # se necessário
uvicorn app:app --host 127.0.0.1 --port 8001
```

## Variáveis de ambiente
- `SESSION_CPF`: CPF da sessão utilizado para validar o CPF mascarado (padrão: `39847351899`).
- `HEADLESS`: "0" para ver o navegador, outro valor para modo headless (padrão: `1`).
- `NAV_TIMEOUT_MS`: tempo máximo de navegação em milissegundos (padrão: `45000`).

## Endpoints
- `POST /v1/enem/start` – inicia uma verificação com o corpo `{ "chave": "..." }` e retorna `verification_id`.
- `GET /v1/enem/status/{verification_id}` – consulta o status e, quando disponível, o resultado final.