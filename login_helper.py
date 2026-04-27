import asyncio
from playwright.async_api import async_playwright

async def run_login():
    async with async_playwright() as p:
        # Modo Invisível Total
        context = await p.chromium.launch_persistent_context(
            user_data_dir=r"./playwright_session", 
            headless=False,
            # Ignoramos a flag que avisa o site que é automação
            ignore_default_args=["--enable-automation"],
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage"
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        
        # Injeta um script para esconder o WebDriver em todas as abas
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Cria as abas iniciais
        page1 = context.pages[0]
        await page1.goto("https://gemini.google.com/u/1/app?pageId=none")
        
        page2 = await context.new_page()
        await page2.goto("https://www.perplexity.ai/")
        
        page3 = await context.new_page()
        await page3.goto("https://chatgpt.com/?temporary-chat=true")
        
        print("\n" + "="*50)
        print("MODO DE LOGIN ATIVO")
        print("="*50)
        print("1. Faça login manualmente nas 3 abas abertas.")
        print("2. Verifique se as contas estão ativas.")
        print("3. FECHE O NAVEGADOR quando terminar para salvar a sessão.")
        print("="*50)

        # Mantém aberto até o contexto ser fechado (navegador fechado pelo usuário)
        while len(context.pages) > 0:
            await asyncio.sleep(1)
            try:
                # Tenta acessar as abas; se der erro, é porque fechou
                _ = context.pages[0].url
            except:
                break
        
        print("\nSessão salva com sucesso! Agora você pode rodar o debate_orchestrator.py")

if __name__ == "__main__":
    asyncio.run(run_login())
