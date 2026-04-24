import asyncio
import json
import time
import requests
from playwright.async_api import async_playwright

# CONFIGURAÇÕES
GEMINI_API_KEY = "AIzaSyDLoVyY8S_JcqVmdZWB2zTRkvzfD35tVoc"
USER_DATA_DIR = r"C:\Users\ynunes\AppData\Local\Google\Chrome\User Data\Default" # Ajuste se necessário
MAX_ROUNDS = 3

class DebateOrchestrator:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.pages = {}
        self.history = []

    async def setup(self):
        self.playwright = await async_playwright().start()
        # Usamos launch_persistent_context para manter os LOGINS do usuário
        self.context = await self.playwright.browser_type.launch_persistent_context(
            user_data_dir=r"./playwright_session", # Criará uma pasta local para não conflitar com o Chrome aberto
            headless=False,
            channel="chrome",
            args=["--start-maximized"]
        )
        
        # Abrir as abas necessárias
        self.pages['gemini'] = await self.context.new_page()
        await self.pages['gemini'].goto("https://gemini.google.com/app")
        
        self.pages['perplexity'] = await self.context.new_page()
        await self.pages['perplexity'].goto("https://www.perplexity.ai/")
        
        self.pages['chatgpt'] = await self.context.new_page()
        await self.pages['chatgpt'].goto("https://chatgpt.com/")

    async def interact_with_llm(self, provider, prompt):
        print(f"[*] Interagindo com {provider}...")
        page = self.pages[provider]
        
        try:
            if provider == 'gemini':
                # Seletor do Gemini (Quill Editor)
                selector = ".ql-editor"
                await page.wait_for_selector(selector)
                await page.fill(selector, prompt)
                await page.keyboard.press("Enter")
                
            elif provider == 'perplexity':
                selector = "#ask-input"
                await page.wait_for_selector(selector)
                await page.fill(selector, prompt)
                # No Perplexity, o Enter geralmente funciona ou clicamos no botão
                await page.keyboard.press("Enter")
                
            elif provider == 'chatgpt':
                selector = "#prompt-textarea"
                await page.wait_for_selector(selector)
                await page.fill(selector, prompt)
                await page.keyboard.press("Enter")

            # Aguardar a resposta estabilizar (Lógica de Polling)
            return await self.wait_for_response(provider)
        except Exception as e:
            return f"ERRO: {str(e)}"

    async def wait_for_response(self, provider):
        page = self.pages[provider]
        last_text = ""
        stable_count = 0
        
        # Seletores de resposta
        res_selectors = {
            'gemini': '.message-content, .model-response-text',
            'perplexity': '.prose',
            'chatgpt': '[data-message-author-role="assistant"]'
        }
        
        sel = res_selectors[provider]
        
        for _ in range(60): # Timeout de 60s
            await asyncio.sleep(2)
            elements = await page.query_selector_all(sel)
            if elements:
                current_text = await elements[-1].inner_text()
                current_text = current_text.strip()
                
                if len(current_text) > 10 and current_text == last_text:
                    stable_count += 1
                    if stable_count >= 3:
                        return self.clean_text(current_text)
                else:
                    stable_count = 0
                    last_text = current_text
        return last_text

    def clean_text(self, text):
        # Limpeza de lixo de interface
        junk = ["Abre em uma nova janela", "Conversa temporária", "Compartilhar", "Copiar"]
        for j in junk:
            text = text.replace(j, "")
        return text.strip()

    def call_gemini_judge(self, prompt):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            res = requests.post(url, json=payload, timeout=20)
            data = res.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        except:
            return "VEREDITO: DIVERGÊNCIA. Motivo: Falha na API do Juiz."

    async def start_debate(self, tema):
        print(f"\n🚀 INICIANDO DEBATE: {tema}\n" + "="*50)
        
        # Rodada 0: Tese Inicial
        tese = await self.interact_with_llm('gemini', f"Crie uma tese técnica sobre: {tema}")
        print(f"\n[GEMINI TESE]: {tese[:200]}...")
        
        round = 1
        consenso = False
        
        while not consenso and round <= MAX_ROUNDS:
            print(f"\n--- RODADA {round} ---")
            
            # Críticas em paralelo
            tasks = [
                self.interact_with_llm('perplexity', f"Critique esta tese: {tese}"),
                self.interact_with_llm('chatgpt', f"Critique esta tese: {tese}")
            ]
            criticas = await asyncio.gather(*tasks)
            perp_crit, gpt_crit = criticas
            
            print(f"[PERPLEXITY]: {perp_crit[:100]}...")
            print(f"[CHATGPT]: {gpt_crit[:100]}...")
            
            # Juiz
            print("[*] Consultando Juiz Supremo...")
            judge_prompt = f"Analise o consenso.\nTESE: {tese}\nPERP: {perp_crit}\nGPT: {gpt_crit}"
            veredito = self.call_gemini_judge(judge_prompt)
            print(f"[JUIZ]: {veredito}")
            
            if "CONSENSO" in veredito.upper():
                consenso = True
                print("\n✅ CONSENSO ALCANÇADO!")
            else:
                print("[*] Refinando tese...")
                tese = await self.interact_with_llm('gemini', f"Ajuste sua tese com base nas críticas:\n1. {perp_crit}\n2. {gpt_crit}")
                round += 1

        print("\n🏁 FIM DO DEBATE.")
        await self.context.close()
        await self.playwright.stop()

if __name__ == "__main__":
    tema = input("Digite o tema do debate: ")
    orchestrator = DebateOrchestrator()
    asyncio.run(orchestrator.setup())
    asyncio.run(orchestrator.start_debate(tema))
