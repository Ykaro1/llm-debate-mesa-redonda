import asyncio
import time
from playwright.async_api import async_playwright

class DebateOrchestrator:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.pages = {}
        # Armazena o histórico completo do debate
        self.debate_history = {
            'teses': [],
            'perplexity': [],
            'chatgpt': [],
            'vereditos': []
        }

    async def setup(self):
        print("[*] Inicializando navegador (Modo Dialético Contínuo)...")
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=r"./playwright_session", 
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        await self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Canais de debate
        urls = {
            'gemini_proposer': "https://gemini.google.com/u/1/app?temporary=true",
            'gemini_judge': "https://gemini.google.com/app?temporary=true",
            'perplexity': "https://www.perplexity.ai/?incognito=true",
            'chatgpt': "https://chatgpt.com/?temporary-chat=true"
        }
        
        for name, url in urls.items():
            self.pages[name] = await self.context.new_page()
            await self.pages[name].goto(url)

    async def interact(self, page_key, prompt):
        print(f"[*] {page_key.upper()} processando...")
        page = self.pages[page_key]
        
        if 'gemini' in page_key:
            selector = ".ql-editor"
            res_sel = ".message-content, .model-response-text"
        elif 'perplexity' in page_key:
            selector = "#ask-input"
            res_sel = ".prose"
        else:
            selector = "#prompt-textarea"
            res_sel = '[data-message-author-role="assistant"]'
            try:
                for btn_text in ["Entendi", "Got it", "Okay"]:
                    btn = await page.get_by_role("button", name=btn_text).element_handle()
                    if btn: await btn.click()
            except: pass

        try:
            await page.wait_for_selector(selector, timeout=15000)
            await page.click(selector)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.type(selector, prompt, delay=5)
            await page.keyboard.press("Enter")
            
            last_text = ""
            stable_count = 0
            for _ in range(50):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(res_sel)
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    if len(current) > 20 and current == last_text:
                        stable_count += 1
                        if stable_count >= 3: return current
                    else:
                        stable_count = 0
                        last_text = current
            return last_text
        except Exception as e:
            return f"ERRO: {str(e)}"

    async def start_debate(self, tema):
        print(f"\n🚀 DEBATE DIALÉTICO INICIADO: {tema}\n" + "="*50)
        
        # Tese Inicial
        current_thesis = await self.interact('gemini_proposer', f"TEMA: {tema}\n[PAPEL: PROPOSITOR] Crie uma tese técnica e robusta.")
        self.debate_history['teses'].append(current_thesis)
        
        round_num = 0
        while True:
            round_num += 1
            print(f"\n--- RODADA {round_num} ---")
            
            # Críticas
            tasks = [
                self.interact('perplexity', f"Critique esta tese considerando novos dados: {current_thesis}"),
                self.interact('chatgpt', f"Analise a lógica e aponte falhas nesta tese: {current_thesis}")
            ]
            perp_crit, gpt_crit = await asyncio.gather(*tasks)
            
            self.debate_history['perplexity'].append(perp_crit)
            self.debate_history['chatgpt'].append(gpt_crit)

            # PROMPT DE MODERAÇÃO ATIVA (O CÉREBRO DO PROCESSO)
            history_summary = "\n".join([f"R{i+1}: {t[:100]}..." for i, t in enumerate(self.debate_history['teses'])])
            
            convergence_instr = ""
            if round_num >= 5:
                convergence_instr = "\n[AVISO DE CONVERGÊNCIA]: Pressione o Proponente a ceder ou integrar as críticas para encerrar o debate agora."

            judge_prompt = f"""
            VOCÊ É O JUIZ SUPREMO DE UM DEBATE TÉCNICO.
            
            TEMA: {tema}
            TESE ATUAL: {current_thesis}
            HISTÓRICO DE TESES: {history_summary}
            
            CRÍTICA PERPLEXITY: {perp_crit}
            CRÍTICA CHATGPT: {gpt_crit}
            
            SUAS REGRAS DE MODERAÇÃO:
            1. Se houver acordo total, responda: 'VEREDITO: CONSENSO'.
            2. Se uma IA repetiu pontos técnicos das rodadas anteriores sem novos dados, emita um 'AVISO DE REPETIÇÃO'.
            3. Se a postura não mudou após 2 rodadas, pergunte: 'Este é o seu argumento final?'.
            4. Identifique o 'PONTO DE DISCORDÂNCIA TÉCNICA' exato que impede o consenso.
            5. {convergence_instr}
            
            RESPONDA APENAS O VEREDITO E A ANÁLISE DE MODERAÇÃO.
            """
            
            veredito = await self.interact('gemini_judge', judge_prompt)
            self.debate_history['vereditos'].append(veredito)
            print(f"[JUIZ]: {veredito}")
            
            if "VEREDITO: CONSENSO" in veredito.upper():
                print(f"\n✅ CONSENSO ALCANÇADO APÓS {round_num} RODADAS!")
                break
            
            # Refinamento
            print("[*] Refinando tese com base na moderação do Juiz...")
            refine_prompt = f"""
            [PAPEL: PROPOSITOR] Ajuste sua tese.
            CRÍTICAS: 
            1. {perp_crit}
            2. {gpt_crit}
            
            ORIENTAÇÃO DO JUIZ: {veredito}
            """
            current_thesis = await self.interact('gemini_proposer', refine_prompt)
            self.debate_history['teses'].append(current_thesis)

        print("\n🏁 PROCESSO DIALÉTICO FINALIZADO.")

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
