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
        self.max_safe_rounds = 20 # Teto para evitar crash do navegador

    async def setup(self):
        print("[*] Inicializando navegador (Modo Dialético Blindado)...")
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
            print(f"[*] Abrindo aba: {name}...")
            self.pages[name] = await self.context.new_page()
            try:
                await self.pages[name].goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"[!] Aviso: Problema ao carregar {name} (tentando prosseguir): {e}")

    async def interact(self, page_key, prompt):
        print(f"[*] {page_key.upper()} processando...")
        page = self.pages[page_key]
        
        # Seletores e Botões de Envio
        config = {
            'gemini': {
                'input': ".ql-editor",
                'btn': "button.send-button, button[aria-label*='Enviar']",
                'res': ".message-content, .model-response-text"
            },
            'perplexity': {
                'input': "#ask-input",
                'btn': "button[aria-label*='Submit'], button.bg-button-bg",
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

        # Tratamento especial ChatGPT (Modais)
        if page_key == 'chatgpt':
            try:
                for btn_text in ["Entendi", "Got it", "Okay", "Continuar"]:
                    btn = await page.get_by_role("button", name=btn_text).element_handle()
                    if btn: await btn.click()
            except: pass

        try:
            await page.wait_for_selector(cfg['input'], timeout=20000)
            await page.click(cfg['input'])
            
            # Limpa e digita
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.type(cfg['input'], prompt, delay=2)
            
            await asyncio.sleep(1)
            
            # Tenta clicar no botão de enviar primeiro, se não der, vai de Enter
            try:
                send_btn = await page.query_selector(cfg['btn'])
                if send_btn and await send_btn.is_enabled():
                    await send_btn.click()
                else:
                    await page.keyboard.press("Enter")
            except:
                await page.keyboard.press("Enter")
            
            # Espera resposta estabilizar
            last_text = ""
            stable_count = 0
            for _ in range(60):
                await asyncio.sleep(2)
                elements = await page.query_selector_all(cfg['res'])
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    if len(current) > 30 and current == last_text:
                        stable_count += 1
                        if stable_count >= 3: return current
                    else:
                        stable_count = 0
                        last_text = current
            return last_text
        except Exception as e:
            return f"ERRO: {str(e)}"

    async def start_debate(self, tema):
        print(f"\n🚀 DEBATE DIALÉTICO (LIMITE SEGURO: {self.max_safe_rounds} RODADAS): {tema}\n" + "="*50)
        
        current_thesis = await self.interact('gemini_proposer', f"TEMA: {tema}\n[PAPEL: PROPOSITOR] Crie uma tese técnica e robusta.")
        if "ERRO" in current_thesis:
             print(f"❌ Falha ao iniciar: {current_thesis}")
             return

        self.debate_history['teses'].append(current_thesis)
        
        round_num = 0
        while round_num < self.max_safe_rounds:
            round_num += 1
            print(f"\n--- RODADA {round_num} ---")
            
            tasks = [
                self.interact('perplexity', f"Critique esta tese: {current_thesis}"),
                self.interact('chatgpt', f"Aponte falhas lógicas nesta tese: {current_thesis}")
            ]
            criticas = await asyncio.gather(*tasks)
            perp_crit, gpt_crit = criticas
            
            if "ERRO" in perp_crit or "ERRO" in gpt_crit:
                print("⚠️ Uma das IAs críticas falhou. Tentando prosseguir com o que temos.")

            self.debate_history['perplexity'].append(perp_crit)
            self.debate_history['chatgpt'].append(gpt_crit)

            # Moderação do Juiz
            convergence_instr = ""
            if round_num >= 5:
                convergence_instr = "\n[URGENTE]: Estamos na rodada {round_num}. Pressione por um veredito final ou encerramento."

            judge_prompt = f"""
            VOCÊ É O JUIZ SUPREMO.
            TEMA: {tema}
            TESE ATUAL: {current_thesis}
            CRÍTICA PERP: {perp_crit}
            CRÍTICA GPT: {gpt_crit}
            
            REGRAS:
            1. 'VEREDITO: CONSENSO' se as críticas foram mínimas ou aceitas.
            2. 'VEREDITO: DIVERGÊNCIA' se ainda houver conflito técnico.
            3. Identifique o PONTO DE DISCORDÂNCIA.
            {convergence_instr}
            """
            
            veredito = await self.interact('gemini_judge', judge_prompt)
            print(f"[JUIZ]: {veredito}")
            
            if "CONSENSO" in veredito.upper():
                print(f"\n✅ CONSENSO ALCANÇADO!")
                break
            
            # Refinamento
            tese = await self.interact('gemini_proposer', f"Ajuste sua tese com base no Juiz:\n{veredito}")
            if "ERRO" in tese: break
            current_thesis = tese
            self.debate_history['teses'].append(current_thesis)

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
