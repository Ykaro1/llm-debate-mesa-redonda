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
                'input': 'div.ql-editor[contenteditable="true"], .ql-editor, [data-placeholder*="Momentânea"]',
                'btn': "button.send-button, [aria-label*='Enviar'], button:has(mat-icon)",
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
            # ATIVAÇÃO DO MODO TEMPORÁRIO (GEMINI)
            if 'gemini' in page_key:
                try:
                    # Procura o botão/toggle de Conversa Momentânea
                    temp_toggle = await page.query_selector("button:has-text('Conversa momentânea'), [aria-label*='momentânea']")
                    if temp_toggle:
                        # Verifica se já está ativo (geralmente muda a cor ou o aria-checked)
                        is_active = await temp_toggle.get_attribute("aria-checked")
                        if is_active != "true":
                            print(f"[*] Ativando Modo Temporário em {page_key}...")
                            await temp_toggle.click()
                            await asyncio.sleep(2)
                except: pass

                await page.wait_for_selector(cfg['input'])
                # Espera o botão de enviar ficar habilitado (significa que não está gerando)
                for _ in range(30):
                    btn = await page.query_selector(cfg['btn'])
                    if btn and await btn.is_enabled():
                        break
                    await asyncio.sleep(2)

            await page.wait_for_selector(cfg['input'], timeout=20000)
            input_field = await page.query_selector(cfg['input'])
            await input_field.click()
            
            # Limpeza PROFUNDA antes de enviar
            await page.fill(cfg['input'], "")
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(1)
            
            # Preenchimento Atômico via JavaScript (Infalível para Gemini/Quill)
            if 'gemini' in page_key:
                # Injeta o texto e avisa o sistema que houve mudança
                await page.evaluate(f"""(sel, val) => {{
                    let el = document.querySelector(sel);
                    if (el) {{
                        el.innerText = val;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}""", cfg['input'], prompt)
            else:
                await page.fill(cfg['input'], prompt)
            
            await asyncio.sleep(1)
            
            # ENVIO SEGURO (Aguarda o botão estar pronto após a injeção)
            try:
                # No Gemini, esperamos o botão não estar mais desabilitado
                if 'gemini' in page_key:
                    await page.wait_for_function(f"""() => {{
                        let btn = document.querySelector("{cfg['btn']}");
                        return btn && !btn.disabled && btn.offsetParent !== null;
                    }}""", timeout=10000)
                
                btn = await page.query_selector(cfg['btn'])
                if btn:
                    await btn.click()
                else:
                    await page.keyboard.press("Enter")
            except:
                await page.keyboard.press("Enter")
            
            # ESPERA RESPOSTA FINAL (Garantindo que o botão de enviar volte a ficar azul)
            print(f"[*] Aguardando conclusão da resposta de {page_key}...")
            await asyncio.sleep(5) # Delay inicial para a IA começar a escrever
            
            for _ in range(90): # Até 3 minutos de espera para respostas longas
                await asyncio.sleep(2)
                elements = await page.query_selector_all(cfg['res'])
                if elements:
                    current = (await elements[-1].inner_text()).strip()
                    
                    # Se detectar erro de interrupção, recarrega a página
                    if "interrompeu a resposta" in current:
                        print(f"[!] Erro de interrupção detectado. Recarregando {page_key}...")
                        await page.reload()
                        await asyncio.sleep(5)
                        return "ERRO: Resposta interrompida pelo site."

                    # O segredo: A resposta só acabou quando o botão de enviar VOLTAR a estar habilitado
                    btn = await page.query_selector(cfg['btn'])
                    if btn and await btn.is_enabled():
                        # Espera mais 1 segundo para garantir que o DOM atualizou o texto final
                        await asyncio.sleep(1)
                        final_text = (await elements[-1].inner_text()).strip()
                        return final_text
            
            return "ERRO: Timeout aguardando resposta."
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
