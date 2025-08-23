# Servidor ENEM — Verificação via INEP (server-side)

Fluxo **sem extensão** e **blindado contra falsificação no cliente**:
- Backend abre a página do INEP (Playwright), captura a **imagem do CAPTCHA** e envia para sua UI.
- O **aluno digita o CAPTCHA na sua UI**.
- O backend **submete no INEP** e **lê o resultado oficial** diretamente do HTML.
- Compara **CPF mascarado** do INEP com o **CPF da sessão** e decide.

## Rodando localmente

1) Instale dependências:
```bash
pip install -r requirements.txt
playwright install chromium
# Linux: se necessário: playwright install-deps chromium
