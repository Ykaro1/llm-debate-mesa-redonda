import asyncio
import time
from playwright.async_api import async_playwright

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

    async def setup(self):
        print("[*] Inicializando navegador (Modo Resiliência Máxima)...")
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=r"./playwright_session", 
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=[
                "--start-maximized", 
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage", # Evita crash de memória no Windows/Linux
                "--no-sandbox"
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        
        for name, url in self.urls.items():
            print(f"[*] Preparando aba: {name}...")
            page = await self.context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            self.pages[name] = page

    async def check_and_recover_page(self, name):
        """Verifica se a aba ainda está viva, se não, recria."""
        if name not in self.pages or self.pages[name].is_closed():
            print(f"[!] Aba {name} estava fechada. Recuperando...")
            self.pages[name] = await self.context.new_page()
            await self.pages[name].goto(self.urls[name], wait_until="domcontentloaded")

    async def interact(self, page_key, prompt):
        await self.check_and_recover_page(page_key)
        print(f"[*] {page_key.upper()} processando...")
        page = self.pages[page_key]
        
        config = {
            'gemini': {
                'input': ".ql-editor",
                'btn': "button.send-button, button[aria-label*='Enviar']",
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
            # ESPERA O GEMINI TERMINAR QUALQUER PROCESSO ANTERIOR
            if 'gemini' in page_key:
                try:
                    # Espera o ícone de "Gerando..." ou botão "Parar" sumir
                    for _ in range(10): 
                        stop_btn = await page.query_selector("button[aria-label*='Parar'], button[aria-label*='Stop']")
                        if not stop_btn: break
                        await asyncio.sleep(2)
                except: pass

            await page.wait_for_selector(cfg['input'], timeout=20000)
            await page.click(cfg['input'])
            
            # Limpeza e Digitação com pausa
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(1)
            await page.type(cfg['input'], prompt, delay=5)
            await asyncio.sleep(1)
            
            # ENVIO SEGURO
            try:
                # No Gemini, o botão de enviar só fica habilitado quando termina de processar
                await page.wait_for_function("() => {
                    let btn = document.querySelector(\"button.send-button, button[aria-label*='Enviar']\");
                    return btn && !btn.disabled;
                }", timeout=10000)
                btn = await page.query_selector(cfg['btn'])
                await btn.click()
            except:
                await page.keyboard.press("Enter")
            
            # Espera resposta estabilizar E o botão de enviar voltar
            last_text = ""
            for _ in range(60):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(cfg['res'])
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    # Se o texto é longo, estável e o botão de enviar voltou
                    if len(current) > 50 and current == last_text:
                        # Checa se o botão de enviar está visível e ativo de novo
                        is_ready = await page.query_selector(cfg['btn'])
                        if is_ready and await is_ready.is_enabled():
                            return current
                    last_text = current
            return last_text
        except Exception as e:
            return f"ERRO: {str(e)}"

    async def start_debate(self, tema):
        print(f"\n🚀 DEBATE RESILIENTE: {tema}\n" + "="*50)
        
        current_thesis = await self.interact('gemini_proposer', f"TEMA: {tema}\n[PROPOSITOR] Crie uma tese técnica.")
        if "ERRO" in current_thesis: return

        round_num = 0
        while round_num < 15:
            round_num += 1
            print(f"\n--- RODADA {round_num} ---")
            
            # SEQUENCIAL (Mais lento, porém indestrutível)
            perp_crit = await self.interact('perplexity', f"Critique: {current_thesis}")
            gpt_crit = await self.interact('chatgpt', f"Critique: {current_thesis}")
            
            judge_prompt = f"TESE: {current_thesis}\n\nPERP: {perp_crit}\n\nGPT: {gpt_crit}\n\nResponda 'VEREDITO: CONSENSO' ou 'VEREDITO: DIVERGÊNCIA'."
            veredito = await self.interact('gemini_judge', judge_prompt)
            print(f"[JUIZ]: {veredito}")
            
            if "CONSENSO" in veredito.upper():
                print("\n✅ CONSENSO ALCANÇADO!")
                break
            
            current_thesis = await self.interact('gemini_proposer', f"Refine com base no Juiz: {veredito}")

        print("\n🏁 FIM DO DEBATE.")

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
