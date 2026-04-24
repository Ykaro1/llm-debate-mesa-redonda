import asyncio
import json
import logging
import re
from playwright.async_api import async_playwright

# Configuração de Log
logging.basicConfig(
    filename='debate.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)

class DebateOrchestrator:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.pages = {}
        self.debate_history = {'teses': [], 'perplexity': [], 'chatgpt': [], 'vereditos': []}
        self.urls = {
            'gemini_proposer': "https://gemini.google.com/u/1/app/new?temporary=true",
            'perplexity': "https://www.perplexity.ai/?incognito=true",
            'chatgpt': "https://chatgpt.com/?temporary-chat=true"
        }
        self.max_safe_rounds = 20
        self.max_consecutive_failures = 2
        self.failure_counts = {k: 0 for k in self.urls.keys()}
        self.run_log_path = "debate_runs.jsonl"

    def parse_json_verdict(self, text):
        """Tenta extrair e converter o JSON da resposta do ChatGPT."""
        try:
            # Tenta encontrar o bloco JSON na resposta
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                # Garante campos mínimos
                data["parsed_ok"] = True
                return data
        except Exception as e:
            logging.error(f"Erro ao parsear JSON do juiz: {e}")
        
        return {"parsed_ok": False, "consenso": False, "confianca": 0}

    def parse_fact_check_status(self, text):
        match = re.search(r"^\s*STATUS_FACTUAL\s*:\s*(OK|ALERTA_CRITICO)\s*$", text, re.IGNORECASE | re.MULTILINE)
        return match.group(1).upper() if match else None

    async def setup(self):
        logging.info("Iniciando setup do navegador...")
        print("[*] Inicializando navegador...")
        try:
            self.playwright = await async_playwright().start()
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=r"./playwright_session", 
                headless=False,
                ignore_default_args=["--enable-automation"],
                args=["--start-maximized", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--no-sandbox"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                handle_sigint=True,
                handle_sigterm=True
            )
            await self.open_all_pages()
        except Exception as e:
            logging.error(f"Erro no setup: {e}")
            if "Target page, context or browser has been closed" in str(e):
                print("\n[!] ERRO: O Chrome já está aberto ou travado. Feche todas as janelas do Chrome e tente novamente.\n")
            raise

    async def open_all_pages(self):
        self.pages = {}
        for name, url in self.urls.items():
            logging.info(f"Abrindo aba: {name}")
            page = await self.context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            self.pages[name] = page

    async def recover_browser_context(self, reason):
        logging.warning(f"Recuperando BrowserContext ({reason})...")
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=r"./playwright_session",
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=["--start-maximized", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--no-sandbox"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            handle_sigint=True,
            handle_sigterm=True
        )
        await self.open_all_pages()

    async def check_and_recover_page(self, name):
        try:
            if name not in self.pages or self.pages[name].is_closed():
                self.pages[name] = await self.context.new_page()
                await self.pages[name].goto(self.urls[name], wait_until="domcontentloaded")
        except Exception as exc:
            if "Target page, context or browser has been closed" in str(exc):
                await self.recover_browser_context("context closed em check_and_recover_page")
                return
            raise

    def register_agent_result(self, agent, response_text):
        is_error = isinstance(response_text, str) and response_text.startswith("ERRO:")
        self.failure_counts[agent] = self.failure_counts[agent] + 1 if is_error else 0
        return self.failure_counts[agent] < self.max_consecutive_failures

    def append_run_log(self, event):
        payload = {"ts": asyncio.get_event_loop().time(), **event}
        with open(self.run_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    async def ensure_perplexity_anonymous(self, page):
        # Reforca navegacao anonima na URL esperada do Perplexity.
        if "incognito=true" not in page.url:
            await page.goto(self.urls["perplexity"], wait_until="domcontentloaded")

    async def ensure_gemini_reasoning_mode(self, page):
        # Tenta alternar de "Rapido" para "Raciocinio" no proposer.
        try:
            switcher = await page.query_selector("""button:has-text('Rápido'),
                button:has-text('Rapido'),
                button:has-text('Flash'),
                [aria-label*='Rápido'],
                [aria-label*='Rapido'],
                [aria-label*='Flash']""")
            if switcher:
                await switcher.click()
                await asyncio.sleep(0.6)
                clicked = await page.evaluate("""() => {
                    const candidates = ['Raciocínio', 'Raciocinio', 'Thinking', 'Pro'];
                    const nodes = Array.from(document.querySelectorAll('button,[role="option"],div[role="button"]'));
                    const match = nodes.find(node => {
                        const txt = (node.innerText || node.textContent || '').trim();
                        return candidates.some(label => txt.includes(label));
                    });
                    if (!match) return false;
                    match.click();
                    return true;
                }""")

                if clicked:
                    await asyncio.sleep(0.8)
                    logging.info("Modo raciocinio ativado no Gemini proposer.")
                    return True
        except Exception as exc:
            logging.info(f"Nao foi possivel forcar modo raciocinio: {exc}")
        return False

    async def ensure_gemini_default_chat(self, page):
        # Sai de Gems especializados (ex.: Parceiro de Programacao) para o chat padrao.
        try:
            in_gem = await page.evaluate("""() => {
                const txt = (document.body?.innerText || '').toLowerCase();
                const href = (window.location?.href || '').toLowerCase();
                return (
                    txt.includes('parceiro de programacao') ||
                    txt.includes('de learnlm') ||
                    href.includes('/gem/') ||
                    href.includes('/gems/') ||
                    href.includes('/app/g/')
                );
            }""")
            if not in_gem:
                return

            # Tenta primeiro voltar para "Gemini" pelo link da marca no topo.
            home_link = await page.query_selector(
                "a[aria-label*='Gemini'], a:has-text('Gemini')"
            )
            if home_link:
                await home_link.click()
                await asyncio.sleep(1.0)

            new_chat = await page.query_selector(
                "a[aria-label*='Novo chat'], button[aria-label*='Novo chat'], a[aria-label*='New chat'], button[aria-label*='New chat']"
            )
            if new_chat:
                await new_chat.click()
                await asyncio.sleep(1.2)
                logging.info("Saiu de Gem especializado para chat padrao no proposer.")
                return

            await page.goto(self.urls["gemini_proposer"], wait_until="domcontentloaded")
            await asyncio.sleep(1.2)
            logging.info("Recarregou Gemini proposer para chat padrao.")
        except Exception as exc:
            logging.info(f"Nao foi possivel garantir chat padrao no Gemini proposer: {exc}")

    async def ensure_gemini_temporary_mode(self, page):
        # Garante conversa/mensagem temporaria para evitar memoria de chat.
        try:
            temp = await page.query_selector(
                "button:has-text('Conversa momentânea'), button:has-text('Conversa temporária'), [aria-label*='momentânea'], [aria-label*='temporária'], [aria-label*='Temporary']"
            )
            if temp:
                checked = await temp.get_attribute("aria-checked")
                if checked != "true":
                    await temp.click()
                    await asyncio.sleep(1.2)
        except Exception as exc:
            logging.info(f"Nao foi possivel reforcar modo temporario: {exc}")

    async def interact(self, page_key, prompt, retry_on_timeout=True):
        logging.info(f"Interagindo com {page_key}")
        config = {
            'gemini': {
                'input': 'div.ql-editor[contenteditable="true"], .ql-editor, [data-placeholder*="Momentânea"]',
                'btn': "button.send-button, [aria-label*='Enviar'], button:has(mat-icon[stringid='send'])",
                'res': ".message-content, .model-response-text"
            },
            'perplexity': {'input': "#ask-input", 'btn': "button[aria-label*='Submit']", 'res': ".prose"},
            'chatgpt': {'input': "#prompt-textarea", 'btn': "[data-testid='send-button']", 'res': '[data-message-author-role="assistant"]'}
        }
        cfg = config['gemini' if 'gemini' in page_key else page_key]

        try:
            await self.check_and_recover_page(page_key)
            page = self.pages[page_key]
            if page_key == "perplexity":
                await self.ensure_perplexity_anonymous(page)
            if "gemini" in page_key:
                await self.ensure_gemini_temporary_mode(page)
            if page_key == "gemini_proposer":
                await self.ensure_gemini_default_chat(page)
                reasoning_on = await self.ensure_gemini_reasoning_mode(page)
                if not reasoning_on:
                    prompt = (
                        "MODO OBRIGATORIO: RACIOCINIO.\n"
                        "Responda com analise detalhada e estruturada (passo a passo), sem modo rapido.\n\n"
                        f"{prompt}"
                    )

            # Captura quantas respostas já existiam para identificar a nova.
            previous_count = len(await page.query_selector_all(cfg['res']))

            # Inserção de Texto
            await page.wait_for_selector(cfg['input'], timeout=20000)
            if 'gemini' in page_key:
                await page.evaluate(f"""([sel, val]) => {{
                    let el = document.querySelector(sel);
                    if (el) {{
                        el.innerText = val;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}""", [cfg['input'], prompt])
            else:
                await page.click(cfg['input'])
                await page.fill(cfg['input'], prompt)
            
            await asyncio.sleep(1)

            # Envio Persistente
            logging.info(f"Enviando mensagem em {page_key}...")
            for attempt in range(5):
                sent = False
                try:
                    btn = await page.query_selector(cfg['btn'])
                    if btn and await btn.is_visible():
                        await btn.click(force=True)
                        sent = True
                except Exception:
                    pass

                if not sent:
                    await page.keyboard.press("Enter")

                await asyncio.sleep(2)
                
                content = await page.evaluate(f"(sel) => document.querySelector(sel) ? document.querySelector(sel).innerText.trim() : ''", cfg['input'])
                if not content or len(content) < 2: break
                
                btn = await page.query_selector(cfg['btn'])
                if btn:
                    await btn.click(force=True)
                await page.keyboard.press("Enter")

            # Aguarda Resposta (ate 60s). Se travar, tenta recarregar e reenviar 1 vez.
            logging.info(f"Aguardando resposta de {page_key}...")
            last_text = ""
            stable_reads = 0
            max_wait_seconds = 60
            poll_every_seconds = 2
            max_reads = max_wait_seconds // poll_every_seconds
            for _ in range(max_reads):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(cfg['res'])
                if len(elements) > previous_count:
                    current = (await elements[-1].inner_text()).strip()
                    if "interrompeu a resposta" in current:
                        if retry_on_timeout:
                            logging.info(f"{page_key}: resposta interrompida; recarregando e reenviando 1 vez.")
                            await page.reload(wait_until="domcontentloaded")
                            await asyncio.sleep(1.0)
                            return await self.interact(page_key, prompt, retry_on_timeout=False)
                        await page.reload(wait_until="domcontentloaded")
                        return "ERRO: Interrupção"
                    if current:
                        if current == last_text:
                            stable_reads += 1
                        else:
                            last_text = current
                            stable_reads = 0

                        # Retorna quando o texto estabiliza por algumas leituras.
                        if stable_reads >= 2:
                            return current
            
            if retry_on_timeout:
                logging.info(f"{page_key}: timeout de 60s; recarregando e reenviando 1 vez.")
                await page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(1.0)
                return await self.interact(page_key, prompt, retry_on_timeout=False)

            return "ERRO: Timeout (apos recarregar e reenviar)"
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                try:
                    await self.recover_browser_context(f"context closed em interact/{page_key}")
                    return await self.interact(page_key, prompt, retry_on_timeout=False)
                except Exception as recover_exc:
                    logging.error(f"Falha na recuperacao de contexto: {recover_exc}")
                    return f"ERRO: {recover_exc}"
            logging.error(f"Erro em {page_key}: {e}")
            return f"ERRO: {e}"

    async def start_debate(self, tema):
        print(f"\n[DEBATE] TEMA: {tema}\n" + "="*50)
        self.append_run_log({"event": "debate_start", "tema": tema})

        # 1. Pergunta inicial diretamente para o Gemini
        print("[*] Gemini gerando tese inicial...")
        current_gemini_res = await self.interact(
            'gemini_proposer',
            f"TEMA: {tema}\nCrie uma tese técnica profunda, com raciocínio detalhado."
        )
        if not self.register_agent_result("gemini_proposer", current_gemini_res):
            print("[ERRO] Falhas no Gemini. Encerrando.")
            return

        for r in range(1, self.max_safe_rounds + 1):
            round_start = asyncio.get_event_loop().time()
            print(f"\n--- RODADA {r} ---")

            # 2. Resposta do Gemini enviada para o Perplexity
            print("[*] Perplexity analisando resposta do Gemini...")
            prompt_perp = (
                f"Você concorda com essa LLM?\n\nRESPOSTA DA LLM:\n{current_gemini_res}\n\n"
                "Preciso que tenha senso crítico para verificar se as respostas dela estão certas."
            )
            res_perp = await self.interact('perplexity', prompt_perp)
            if not self.register_agent_result("perplexity", res_perp):
                print("[ERRO] Falhas no Perplexity. Encerrando.")
                return

            # 3. ChatGPT Juiz: Verifica consenso
            print("[*] ChatGPT atuando como Juiz...")
            judge_prompt = (
                "Verifique se as duas respostas abaixo entraram em consenso absoluto (100%).\n\n"
                f"RESPOSTA GEMINI:\n{current_gemini_res}\n\n"
                f"RESPOSTA PERPLEXITY:\n{res_perp}\n\n"
                "RESPONDA OBRIGATORIAMENTE EM FORMATO JSON:\n"
                "{\n"
                '  "consenso": true/false,\n'
                '  "confianca": 0-100,\n'
                '  "analise": "breve explicação",\n'
                '  "veredito": "texto final se houver consenso"\n'
                "}"
            )
            res_chatgpt = await self.interact('chatgpt', judge_prompt)
            if not self.register_agent_result("chatgpt", res_chatgpt):
                print("[ERRO] Falhas no ChatGPT Juiz. Encerrando.")
                return

            print(f"\n[VEREDITO DO CHATGPT]:\n{res_chatgpt}\n")
            verdict_data = self.parse_json_verdict(res_chatgpt)

            # Verifica se houve consenso de 100%
            if verdict_data.get("consenso") == True and verdict_data.get("confianca", 0) >= 100:
                print(f"\n[SUCESSO] Consenso de 100% atingido na rodada {r}!")
                print(f"Análise: {verdict_data.get('analise')}")
                self.append_run_log({"event": "consensus_reached", "round": r, "data": verdict_data})
                break
            
            print(f"[*] Sem consenso total ({verdict_data.get('confianca', 0)}%). Iniciando rebate...")

            # 4. Rebate: Perplexity de volta para o Gemini
            prompt_rebate = (
                f"Essa AI (Perplexity) disse isso:\n\n{res_perp}\n\n"
                "Você concorda com ela? Tenha análise crítica ao que ela disse. Caso ela esteja errada, rebata."
            )
            current_gemini_res = await self.interact('gemini_proposer', prompt_rebate)
            if not self.register_agent_result("gemini_proposer", current_gemini_res):
                print("[ERRO] Falhas no rebate do Gemini. Encerrando.")
                return

            self.append_run_log({
                "event": "round_end",
                "round": r,
                "consenso": verdict_data.get("consenso"),
                "confianca": verdict_data.get("confianca")
            })

        print("\n[FIM] Debate encerrado.")
        self.append_run_log({"event": "debate_end"})

async def main():
    tema = input("Digite o tema: ")
    orchestrator = DebateOrchestrator()
    await orchestrator.setup()
    try:
        await orchestrator.start_debate(tema)
    finally:
        if orchestrator.context: await orchestrator.context.close()
        if orchestrator.playwright: await orchestrator.playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
