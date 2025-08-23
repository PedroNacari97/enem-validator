import os
import sys
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enem-validator")

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

SESSION_CPF = "39847351899"   # CPF chumbado para teste
HEADLESS = os.getenv("HEADLESS", "1") != "0"
INEP_URL = "https://enem.inep.gov.br/participante/#!/autenticidade"
NAV_TIMEOUT = int(os.getenv("NAV_TIMEOUT_MS", "45000"))
