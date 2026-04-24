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
    filemode='w'
)

class DebateOrchestrator:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.pages = {}
        self.debate_history = {'teses': [], 'perplexity': [], 'chatgpt': [], 'vereditos': []}
        self.urls = {
            'gemini_proposer': "https://gemini.google.com/u/1/app?temporary=true",
            'gemini_judge': "https://gemini.google.com/app?temporary=true",
            'perplexity': "https://www.perplexity.ai/?incognito=true",
            'chatgpt': "https://chatgpt.com/?temporary-chat=true"
        }
        self.max_safe_rounds = 20

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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            for name, url in self.urls.items():
                logging.info(f"Abrindo aba: {name}")
                page = await self.context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                self.pages[name] = page
        except Exception as e:
            logging.error(f"Erro no setup: {e}")
            raise

    async def check_and_recover_page(self, name):
        if name not in self.pages or self.pages[name].is_closed():
            self.pages[name] = await self.context.new_page()
            await self.pages[name].goto(self.urls[name], wait_until="domcontentloaded")

    async def interact(self, page_key, prompt):
        logging.info(f"Interagindo com {page_key}")
        await self.check_and_recover_page(page_key)
        page = self.pages[page_key]
        
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
            # Modo Temporário Gemini
            if 'gemini' in page_key:
                try:
                    temp = await page.query_selector("button:has-text('Conversa momentânea'), [aria-label*='momentânea']")
                    if temp and (await temp.get_attribute("aria-checked")) != "true":
                        await temp.click()
                        await asyncio.sleep(2)
                except: pass

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
                await page.fill(cfg['input'], prompt)
            
            await asyncio.sleep(1)

            # Envio Persistente
            logging.info(f"Enviando mensagem em {page_key}...")
            for attempt in range(5):
                sent = await page.evaluate(f"""() => {{
                    let btns = Array.from(document.querySelectorAll('button'));
                    let sendBtn = btns.find(b => 
                        (b.getAttribute('aria-label') && b.getAttribute('aria-label').includes('Enviar')) || 
                        b.querySelector('mat-icon[stringid="send"]') || b.classList.contains('send-button')
                    );
                    if (sendBtn) {{ sendBtn.click(); return true; }}
                    return false;
                }}""")
                if not sent: await page.keyboard.press("Enter")
                await asyncio.sleep(2)
                
                content = await page.evaluate(f"(sel) => document.querySelector(sel) ? document.querySelector(sel).innerText.trim() : ''", cfg['input'])
                if not content or len(content) < 2: break
                
                btn = await page.query_selector(cfg['btn'])
                if btn: await btn.click(force=True)
                await page.keyboard.press("Enter")

            # Aguarda Resposta
            logging.info(f"Aguardando resposta de {page_key}...")
            for _ in range(90):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(cfg['res'])
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    if "interrompeu a resposta" in current:
                        await page.reload()
                        return "ERRO: Interrupção"
                    btn = await page.query_selector(cfg['btn'])
                    if btn and await btn.is_enabled(): return current
            
            return "ERRO: Timeout"
        except Exception as e:
            logging.error(f"Erro em {page_key}: {e}")
            return f"ERRO: {e}"

    async def start_debate(self, tema):
        print(f"\n[DEBATE] TEMA: {tema}\n" + "="*50)
        current_thesis = await self.interact('gemini_proposer', f"TEMA: {tema}\nCrie uma tese técnica.")
        for r in range(1, self.max_safe_rounds + 1):
            print(f"\n--- RODADA {r} ---")
            p_crit = await self.interact('perplexity', f"Critique: {current_thesis}")
            c_crit = await self.interact('chatgpt', f"Critique: {current_thesis}")
            judge_prompt = f"Analise o consenso.\nTESE: {current_thesis}\nPERP: {p_crit}\nGPT: {c_crit}"
            veredito = await self.interact('gemini_judge', judge_prompt)
            print(f"[JUIZ]: {veredito[:150]}...")
            if "CONSENSO" in veredito.upper(): break
            current_thesis = await self.interact('gemini_proposer', f"Refine: {veredito}")
        print("\n[FIM] Debate encerrado.")

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
