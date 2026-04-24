import asyncio
import time
import logging
import traceback
from playwright.async_api import async_playwright

# Configuração de Log
logging.basicConfig(
    filename='debate.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w' # Sobrescreve o log a cada nova execução
)

class DebateOrchestrator:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.pages = {}
        self.debate_history = {
            'teses': [],
            'perplexity': [],
            'chatgpt': [],
            'vereditos': []
        }
        self.urls = {
            'gemini_proposer': "https://gemini.google.com/u/1/app?temporary=true",
            'gemini_judge': "https://gemini.google.com/app?temporary=true",
            'perplexity': "https://www.perplexity.ai/?incognito=true",
            'chatgpt': "https://chatgpt.com/?temporary-chat=true"
        }
        self.max_safe_rounds = 20

    async def setup(self):
        logging.info("Iniciando setup do navegador...")
        print("[*] Inicializando navegador (Com Logs ativos)...")
        try:
            self.playwright = await async_playwright().start()
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=r"./playwright_session", 
                headless=False,
                ignore_default_args=["--enable-automation"],
                args=[
                    "--start-maximized", 
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            
            for name, url in self.urls.items():
                logging.info(f"Abrindo aba: {name} -> {url}")
                page = await self.context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                self.pages[name] = page
        except Exception as e:
            logging.error(f"Erro fatal no setup: {str(e)}")
            logging.error(traceback.format_exc())
            raise

    async def check_and_recover_page(self, name):
        if name not in self.pages or self.pages[name].is_closed():
            logging.warning(f"Aba {name} fechada. Tentando recuperar...")
            self.pages[name] = await self.context.new_page()
            await self.pages[name].goto(self.urls[name], wait_until="domcontentloaded")

    async def interact(self, page_key, prompt):
        logging.info(f"Iniciando interação com {page_key}")
        await self.check_and_recover_page(page_key)
        page = self.pages[page_key]
        
        config = {
            'gemini': {
                'input': 'div.ql-editor[contenteditable="true"], .ql-editor, [data-placeholder*="Momentânea"]',
                'btn': "button.send-button, [aria-label*='Enviar'], button:has(mat-icon[stringid='send']), .send-button-container button",
                'res': ".message-content, .model-response-text"
            },
            'perplexity': {
                'input': "#ask-input",
                'btn': "button[aria-label*='Submit']",
                'res': ".prose"
            },
            'chatgpt': {
                'input': "#prompt-textarea",
                'btn': "[data-testid='send-button'], button:has(svg)",
                'res': '[data-message-author-role="assistant"]'
            }
        }

        key = 'gemini' if 'gemini' in page_key else page_key
        cfg = config[key]

        try:
            # Ativação de Modo Temporário (Gemini)
            if 'gemini' in page_key:
                try:
                    temp_toggle = await page.query_selector("button:has-text('Conversa momentânea'), [aria-label*='momentânea']")
                    if temp_toggle:
                        is_active = await temp_toggle.get_attribute("aria-checked")
                        if is_active != "true":
                            logging.info(f"Ativando modo temporário no {page_key}")
                            await temp_toggle.click()
                            await asyncio.sleep(2)
                except: pass

                # Espera o Gemini estar pronto
                for _ in range(20):
                    btn = await page.query_selector(cfg['btn'])
                    if btn and await btn.is_enabled(): break
                    await asyncio.sleep(2)

            await page.wait_for_selector(cfg['input'], timeout=20000)
            
            # Injeção Atômica para Gemini, Fill para os outros
            if 'gemini' in page_key:
                logging.info(f"Injetando JS no {page_key}")
                # Passa argumentos como uma lista [sel, val]
                await page.evaluate(f"""([sel, val]) => {{
                    let el = document.querySelector(sel);
                    if (el) {{
                        el.innerText = val;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}""", [cfg['input'], prompt])
            else:
                await page.fill(cfg['input'], prompt)
            
            await asyncio.sleep(1)
            
            # Clique no Enviar
            try:
                btn = await page.wait_for_selector(cfg['btn'], state="visible", timeout=10000)
                await btn.click()
                logging.info(f"Botão enviar clicado em {page_key}")
            except Exception as e:
                logging.warning(f"Botão não clicável em {page_key}, tentando Enter: {e}")
                await page.keyboard.press("Enter")
            
            # Espera Resposta
            logging.info(f"Aguardando resposta de {page_key}...")
            for _ in range(90):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(cfg['res'])
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    if "interrompeu a resposta" in current:
                        logging.error(f"Interrupção detectada em {page_key}")
                        await page.reload()
                        return "ERRO: Interrupção detectada."
                    
                    btn = await page.query_selector(cfg['btn'])
                    if btn and await btn.is_enabled():
                        logging.info(f"Resposta concluída em {page_key}")
                        return current
            
            logging.warning(f"Timeout atingido em {page_key}")
            return "ERRO: Timeout"
        except Exception as e:
            logging.error(f"Erro na interação com {page_key}: {str(e)}")
            logging.error(traceback.format_exc())
            return f"ERRO: {str(e)}"

    async def start_debate(self, tema):
        logging.info(f"INICIANDO DEBATE: {tema}")
        print(f"\n🚀 DEBATE INICIADO: {tema}\n" + "="*50)
        
        current_thesis = await self.interact('gemini_proposer', f"TEMA: {tema}\nCrie uma tese técnica.")
        
        round_num = 0
        while round_num < self.max_safe_rounds:
            round_num += 1
            logging.info(f"--- RODADA {round_num} ---")
            print(f"\n--- RODADA {round_num} ---")
            
            perp_crit = await self.interact('perplexity', f"Critique: {current_thesis}")
            gpt_crit = await self.interact('chatgpt', f"Critique: {current_thesis}")
            
            judge_prompt = f"Analise o consenso.\nTESE: {current_thesis}\nPERP: {perp_crit}\nGPT: {gpt_crit}"
            veredito = await self.interact('gemini_judge', judge_prompt)
            print(f"[JUIZ]: {veredito[:100]}...")
            
            if "CONSENSO" in veredito.upper():
                logging.info("Consenso alcançado!")
                break
            
            current_thesis = await self.interact('gemini_proposer', f"Refine: {veredito}")

        logging.info("Fim do debate.")

async def main():
    tema = input("Digite o tema do debate: ")
    orchestrator = DebateOrchestrator()
    await orchestrator.setup()
    try:
        await orchestrator.start_debate(tema)
    finally:
        try:
            if orchestrator.context: await orchestrator.context.close()
            if orchestrator.playwright: await orchestrator.playwright.stop()
        except: pass

if __name__ == "__main__":
    asyncio.run(main())
