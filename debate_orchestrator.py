import asyncio
import time
from playwright.async_api import async_playwright

class DebateOrchestrator:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.pages = {}

    async def setup(self):
        print("[*] Inicializando navegador (Modo 100% Site)...")
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=r"./playwright_session", 
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        await self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # ABA 1: GEMINI PROPONENTE (CONTA HERONET - MODO MOMENTÂNEO)
        self.pages['gemini_proposer'] = await self.context.new_page()
        await self.pages['gemini_proposer'].goto("https://gemini.google.com/u/1/app?temporary=true")
        
        # ABA 2: GEMINI JUIZ (CONTA PADRÃO YKARO YURI - MODO MOMENTÂNEO)
        self.pages['gemini_judge'] = await self.context.new_page()
        await self.pages['gemini_judge'].goto("https://gemini.google.com/app?temporary=true")
        
        # ABA 3: PERPLEXITY (MODO INCOGNITO)
        self.pages['perplexity'] = await self.context.new_page()
        await self.pages['perplexity'].goto("https://www.perplexity.ai/?incognito=true")
        
        # ABA 4: CHATGPT (MODO TEMPORÁRIO)
        self.pages['chatgpt'] = await self.context.new_page()
        await self.pages['chatgpt'].goto("https://chatgpt.com/?temporary-chat=true")

    async def interact(self, page_key, prompt):
        print(f"[*] Interagindo com {page_key}...")
        page = self.pages[page_key]
        
        # Seletores dinâmicos
        if 'gemini' in page_key:
            selector = ".ql-editor"
            res_sel = ".message-content, .model-response-text"
        elif 'perplexity' in page_key:
            selector = "#ask-input"
            res_sel = ".prose"
        else: # chatgpt
            selector = "#prompt-textarea"
            res_sel = '[data-message-author-role="assistant"]'

        try:
            await page.wait_for_selector(selector, timeout=10000)
            await page.fill(selector, prompt)
            await page.keyboard.press("Enter")
            
            # Espera resposta estabilizar
            last_text = ""
            stable_count = 0
            for _ in range(30):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(res_sel)
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    if len(current) > 10 and current == last_text:
                        stable_count += 1
                        if stable_count >= 2: return current
                    else:
                        stable_count = 0
                        last_text = current
            return last_text
        except Exception as e:
            return f"ERRO: {str(e)}"

    async def start_debate(self, tema):
        print(f"\n🚀 INICIANDO DEBATE 100% NAVEGADOR: {tema}\n" + "="*50)
        
        # 1. Tese Inicial
        tese = await self.interact('gemini_proposer', f"Crie uma tese técnica sobre: {tema}")
        print(f"\n[TESE INICIAL]: {tese[:150]}...")
        
        for round in range(1, 4):
            print(f"\n--- RODADA {round} ---")
            
            # 2. Críticas
            tasks = [
                self.interact('perplexity', f"Critique esta tese: {tese}"),
                self.interact('chatgpt', f"Critique esta tese: {tese}")
            ]
            perp_crit, gpt_crit = await asyncio.gather(*tasks)
            print(f"[PERPLEXITY]: {perp_crit[:80]}...")
            print(f"[CHATGPT]: {gpt_crit[:80]}...")
            
            # 3. Juiz no Site
            judge_prompt = f"VOCÊ É O JUIZ SUPREMO. Analise o consenso.\nTESE: {tese}\n\nPERP: {perp_crit}\n\nGPT: {gpt_crit}\n\nResponda APENAS 'VEREDITO: CONSENSO' ou 'VEREDITO: DIVERGÊNCIA'."
            veredito = await self.interact('gemini_judge', judge_prompt)
            print(f"[JUIZ]: {veredito}")
            
            if "CONSENSO" in veredito.upper():
                print("\n✅ CONSENSO ALCANÇADO NO SITE!")
                break
            else:
                print("[*] Refinando tese na aba do Proponente...")
                tese = await self.interact('gemini_proposer', f"Refine sua tese com base nestas críticas:\n1. {perp_crit}\n2. {gpt_crit}")

        print("\n🏁 FIM DO DEBATE.")

async def main():
    tema = input("Digite o tema do debate: ")
    orchestrator = DebateOrchestrator()
    await orchestrator.setup()
    try:
        await orchestrator.start_debate(tema)
    finally:
        if orchestrator.context: await orchestrator.context.close()
        if orchestrator.playwright: await orchestrator.playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
