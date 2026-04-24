# LLM Debate: Mesa Redonda (Versão Python + Playwright)

Este projeto automatiza um debate circular entre três grandes IAs (Gemini, Perplexity e ChatGPT) utilizando o Playwright para controle robótico do navegador.

## 🚀 Como Rodar

1. **Requisitos**:
   - Python 3.8+
   - Google Chrome instalado

2. **Instalação**:
   ```powershell
   pip install playwright requests
   playwright install chrome
   ```

3. **Execução**:
   ```powershell
   python debate_orchestrator.py
   ```

## 🧠 Como funciona a Mesa Redonda

1. **Rodada 0**: O **Gemini** recebe o tema e formula uma tese técnica inicial.
2. **Avaliação**: O **Perplexity** (Crítica Factual) e o **ChatGPT** (Crítica Lógica) analisam a tese simultaneamente.
3. **Juiz Supremo**: O motor do script consulta a API do Gemini para verificar se houve consenso entre as críticas.
4. **Refinamento**: Se houver divergência, o Gemini ajusta a tese com base nos feedbacks e o ciclo se repete até o consenso ou limite de rodadas.

## 🔑 Login e Sessões

Na primeira execução, o script abrirá o navegador. **Você deve fazer login manualmente** no Gemini, Perplexity e ChatGPT. A sessão ficará salva na pasta `./playwright_session`, então você não precisará logar novamente nas próximas vezes.

---
*Substituiu a antiga extensão de Chrome para garantir maior estabilidade e controle.*
