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
            'gemini_proposer': "https://gemini.google.com/u/1/app?pageId=none",
            'perplexity': "https://www.perplexity.ai/",
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
            await self.activate_anonymous_modes()
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

    async def activate_anonymous_modes(self):
        """Ativa modos anonimos/temporarios clicando nos toggles REAIS da UI.
        Executado UMA VEZ apos abrir todas as abas."""
        print("[*] Ativando modos anonimos...")

        # --- GEMINI: Clicar no toggle de conversa momentanea ---
        # Usa Playwright .click() nativo (simula mouse real) em vez de JS .click() que Angular ignora
        try:
            page = self.pages.get('gemini_proposer')
            if page:
                print("  [Gemini] Aguardando pagina carregar...")
                await asyncio.sleep(3.0)
                
                clicked = False
                
                # Estrategia 1: Clica no mat-slide-toggle usando locator nativo do Playwright
                try:
                    toggle = page.locator('mat-slide-toggle').first
                    if await toggle.count() > 0:
                        is_checked = await toggle.evaluate('el => el.classList.contains("mat-mdc-slide-toggle-checked")')
                        if not is_checked:
                            await toggle.click(force=True)
                            clicked = True
                            print("  [Gemini] Clicou no mat-slide-toggle (Playwright click)")
                        else:
                            clicked = True
                            print("  [Gemini] Toggle ja estava ativo")
                except Exception as e1:
                    logging.debug(f"Gemini estrategia 1 falhou: {e1}")
                
                # Estrategia 2: Clica no button[role="switch"] 
                if not clicked:
                    try:
                        switch_btn = page.locator('button[role="switch"]').first
                        if await switch_btn.count() > 0:
                            aria = await switch_btn.get_attribute('aria-checked')
                            if aria != 'true':
                                await switch_btn.click(force=True)
                                clicked = True
                                print("  [Gemini] Clicou no button[role=switch] (Playwright click)")
                            else:
                                clicked = True
                                print("  [Gemini] Switch ja estava ativo")
                    except Exception as e2:
                        logging.debug(f"Gemini estrategia 2 falhou: {e2}")
                
                # Estrategia 3: Clica diretamente no span.mat-mdc-button-touch-target
                if not clicked:
                    try:
                        touch = page.locator('span.mat-mdc-button-touch-target').first
                        if await touch.count() > 0:
                            await touch.click(force=True)
                            clicked = True
                            print("  [Gemini] Clicou no span.mat-mdc-button-touch-target (Playwright click)")
                    except Exception as e3:
                        logging.debug(f"Gemini estrategia 3 falhou: {e3}")
                
                # Estrategia 4: Busca por texto 'momentânea' e clica no elemento mais proximo
                if not clicked:
                    try:
                        label = page.get_by_text('momentânea', exact=False).first
                        if await label.count() > 0:
                            await label.click(force=True)
                            clicked = True
                            print("  [Gemini] Clicou no texto 'momentanea' (Playwright click)")
                    except Exception as e4:
                        logging.debug(f"Gemini estrategia 4 falhou: {e4}")
                
                if clicked:
                    logging.info("Gemini: modo temporario ativado com sucesso")
                    await asyncio.sleep(1.5)
                else:
                    logging.warning("Gemini: NENHUMA estrategia conseguiu clicar no toggle")
                    print("  [Gemini] AVISO: Nenhuma estrategia funcionou para o toggle")
        except Exception as exc:
            logging.warning(f"Erro ao ativar modo temporario no Gemini: {exc}")
            print(f"  [Gemini] ERRO: {exc}")

        # --- PERPLEXITY: Clicar no toggle de modo incognito ---
        # Elemento: div.absolute.inset-0.flex.items-center.justify-center (indicador do toggle)
        try:
            page = self.pages.get('perplexity')
            if page:
                # Espera o toggle aparecer no DOM (ate 10s).
                print("  [Perplexity] Aguardando toggle de incognito...")
                try:
                    await page.wait_for_selector(
                        'div.absolute.inset-0, [role="switch"], button:has-text("incognito")',
                        timeout=10000
                    )
                except Exception:
                    logging.warning("Perplexity: timeout esperando toggle aparecer.")
                    print("  [Perplexity] AVISO: Toggle nao apareceu em 10s.")
                await asyncio.sleep(0.5)
                toggled = await page.evaluate("""() => {
                    // Estrategia 1: Encontra o div indicador e clica no toggle pai.
                    const indicator = document.querySelector('div.absolute.inset-0.flex.items-center.justify-center');
                    if (indicator) {
                        // O toggle clicavel e o pai ou avo do indicador.
                        const clickable = indicator.closest('button') || 
                                          indicator.closest('[role="switch"]') ||
                                          indicator.closest('label') ||
                                          indicator.parentElement?.closest('button') ||
                                          indicator.parentElement;
                        if (clickable) {
                            clickable.click();
                            return 'indicator_parent_clicked';
                        }
                    }
                    
                    // Estrategia 2: Busca toggles/switches genericos.
                    const switches = document.querySelectorAll('[role="switch"], input[type="checkbox"]');
                    for (const sw of switches) {
                        const label = sw.closest('label') || sw.parentElement;
                        const txt = (label?.innerText || label?.textContent || 
                                     sw.getAttribute('aria-label') || '').toLowerCase();
                        if (txt.includes('incognito') || txt.includes('anon') || txt.includes('private')) {
                            sw.click();
                            return 'switch_clicked';
                        }
                    }
                    
                    // Estrategia 3: Busca botoes com texto de incognito.
                    const buttons = document.querySelectorAll('button, [role="button"]');
                    for (const b of buttons) {
                        const txt = (b.innerText || b.textContent || '').toLowerCase();
                        if (txt.includes('incognito') || txt.includes('anônimo') || txt.includes('anonimo')) {
                            b.click();
                            return 'button_clicked';
                        }
                    }
                    
                    return null;
                }""")
                if toggled:
                    logging.info(f"Perplexity modo anonimo: {toggled}")
                    print(f"  [Perplexity] Modo anonimo: {toggled}")
                    await asyncio.sleep(1.5)
                else:
                    logging.warning("Perplexity: toggle de incognito NAO encontrado.")
                    print("  [Perplexity] AVISO: Toggle incognito nao encontrado.")
        except Exception as exc:
            logging.warning(f"Erro ao ativar modo anonimo no Perplexity: {exc}")
            print(f"  [Perplexity] ERRO: {exc}")

        # --- CHATGPT: URL ?temporary-chat=true ja funciona ---
        logging.info("ChatGPT: modo temporary-chat ativo via URL.")
        print("  [ChatGPT] Modo temporario ativo.")
        print("[*] Modos anonimos configurados.")

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
        await self.activate_anonymous_modes()

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

    async def ensure_gemini_correct_mode(self, page):
        """Garante que o Gemini esta no modo 'Raciocínio' e NAO em um Gem especializado.
        Usa o pill/dropdown real da UI (data-test-id='logo-pill-label-container').
        Selecionar 'Raciocínio' automaticamente sai de qualquer Gem ativo."""
        try:
            current_url = page.url
            logging.info(f"Gemini URL atual: {current_url}")

            # Verifica se a URL aponta para um Gem (redirecionamento forcado).
            url_lower = current_url.lower()
            if '/gem/' in url_lower or '/gems/' in url_lower or '/app/g/' in url_lower:
                logging.warning(f"URL de Gem detectada: {current_url}. Redirecionando...")
                await page.goto(self.urls["gemini_proposer"], wait_until="domcontentloaded")
                await asyncio.sleep(2.5)

            # Verifica o modo atual no pill da UI.
            pill = await page.query_selector('[data-test-id="logo-pill-label-container"]')
            if not pill:
                logging.warning("Pill de modo nao encontrado. Tentando seletores alternativos...")
                pill = await page.query_selector('.logo-pill-label-container, .input-area-switch-label')

            if not pill:
                logging.warning("Nenhum seletor de modo encontrado na pagina.")
                return False

            pill_text = (await pill.inner_text()).strip().lower()
            logging.info(f"Gemini modo atual no pill: '{pill_text}'")

            # Se ja esta em Raciocinio, nada a fazer.
            if 'raciocínio' in pill_text or 'raciocinio' in pill_text or 'thinking' in pill_text:
                logging.info("Modo Raciocinio ja esta ativo.")
                return True

            # Precisa trocar: clica no pill para abrir o dropdown.
            logging.info(f"Modo atual '{pill_text}' nao e Raciocinio. Abrindo dropdown...")
            await pill.click()
            await asyncio.sleep(1.0)

            # Procura e clica na opcao "Raciocínio" no dropdown aberto.
            selected = await page.evaluate("""() => {
                const candidates = ['Raciocínio', 'Raciocinio', 'Thinking'];
                // Procura em todos os elementos clicaveis do dropdown.
                const selectors = [
                    '[role="option"]',
                    '[role="menuitem"]',
                    '[role="menuitemradio"]',
                    '[role="listbox"] > *',
                    'button',
                    'div[role="button"]',
                    'mat-option',
                    '.mat-mdc-menu-item',
                    '.mdc-list-item',
                    '[class*="option"]',
                    '[class*="menu-item"]'
                ];
                const allNodes = [];
                for (const sel of selectors) {
                    allNodes.push(...document.querySelectorAll(sel));
                }
                // Deduplica.
                const unique = [...new Set(allNodes)];
                for (const node of unique) {
                    const txt = (node.innerText || node.textContent || '').trim();
                    if (candidates.some(c => txt.includes(c))) {
                        node.click();
                        return txt;
                    }
                }
                return null;
            }""")

            if selected:
                await asyncio.sleep(1.0)
                logging.info(f"Modo Raciocinio selecionado: '{selected}'")
                return True
            else:
                logging.warning("Opcao 'Raciocinio' nao encontrada no dropdown.")
                # Fecha o dropdown clicando fora.
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                return False

        except Exception as exc:
            logging.warning(f"Falha ao configurar modo do Gemini: {exc}")
            return False

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
            if page_key == "gemini_proposer":
                reasoning_on = await self.ensure_gemini_correct_mode(page)
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

    async def start_debate(self, ideia):
        print(f"\n[MESA REDONDA] IDEIA: {ideia}\n" + "="*60)
        self.append_run_log({"event": "planning_start", "ideia": ideia})

        # Threshold de consenso: 90% para planos de app é suficiente.
        consensus_threshold = 90

        # =====================================================================
        # 1. GEMINI (Arquiteto Técnico) — Propõe o plano inicial
        # =====================================================================
        print("[*] 🏗️  Gemini (Arquiteto Técnico) criando plano inicial...")
        prompt_arquiteto = (
            f"IDEIA DE APLICATIVO: {ideia}\n\n"
            "Você é um ARQUITETO TÉCNICO SÊNIOR. Seu trabalho é transformar essa ideia "
            "em um plano de execução concreto e viável. Responda com:\n\n"
            "1. RESUMO DO PRODUTO — O que o app faz em 2-3 frases. Qual problema resolve.\n"
            "2. MVP (Produto Mínimo Viável) — Liste APENAS as funcionalidades essenciais "
            "para a primeira versão. Seja enxuto: o que pode ser cortado, corte.\n"
            "3. STACK TECNOLÓGICA — Recomende tecnologias específicas (linguagem, framework, "
            "banco de dados, hospedagem). Justifique cada escolha considerando:\n"
            "   - Custo (priorize opções gratuitas ou baratas)\n"
            "   - Velocidade de desenvolvimento (prototipagem rápida)\n"
            "   - Escalabilidade futura\n"
            "4. ARQUITETURA — Descreva a arquitetura básica (monolito vs microsserviços, "
            "API REST vs GraphQL, etc.) e por quê.\n"
            "5. ESTIMATIVA DE CUSTO — Quanto custaria para prototipar (hospedagem, domínio, "
            "APIs de terceiros, etc.). Dê valores reais.\n"
            "6. CRONOGRAMA — Estime tempo para o MVP considerando 1 desenvolvedor.\n"
            "7. RISCOS TÉCNICOS — Liste os 3 maiores riscos e como mitigá-los.\n\n"
            "Seja prático e realista. Pense como alguém que vai CONSTRUIR isso, não só planejar."
        )
        current_gemini_res = await self.interact('gemini_proposer', prompt_arquiteto)
        if not self.register_agent_result("gemini_proposer", current_gemini_res):
            print("[ERRO] Falhas no Gemini. Encerrando.")
            return

        for r in range(1, self.max_safe_rounds + 1):
            round_start = asyncio.get_event_loop().time()
            print(f"\n--- RODADA {r} ---")

            # =================================================================
            # 2. PERPLEXITY (Pesquisador de Mercado) — Valida com dados reais
            # =================================================================
            print("[*] 🔍 Perplexity (Pesquisador) validando plano...")
            if r <= 4:
                # Fase de análise crítica com pesquisa
                prompt_pesquisador = (
                    f"Um Arquiteto Técnico propôs o seguinte plano para o app: \"{ideia}\"\n\n"
                    f"---\n{current_gemini_res}\n---\n\n"
                    "Você é um PESQUISADOR DE MERCADO E TECNOLOGIA. Use sua capacidade de busca "
                    "para validar e melhorar este plano:\n\n"
                    "1. CONCORRENTES — Pesquise apps similares que já existem. "
                    "Como eles funcionam? Quanto cobram? Qual stack usam?\n"
                    "2. VALIDAÇÃO DE CUSTOS — Os custos estimados estão realistas? "
                    "Pesquise preços REAIS de hospedagem, APIs, domínios.\n"
                    "3. ALTERNATIVAS TÉCNICAS — Existem ferramentas, frameworks ou serviços "
                    "mais baratos ou rápidos que o proposto? (ex: no-code, BaaS, templates)\n"
                    "4. VIABILIDADE — O cronograma é realista? O MVP está realmente mínimo?\n"
                    "5. SUGESTÕES CONCRETAS — Proponha melhorias específicas ao plano, "
                    "sempre com justificativa baseada em dados.\n\n"
                    "Cite fontes e dados reais. Seja construtivo mas rigoroso."
                )
            else:
                # Fase de convergência
                prompt_pesquisador = (
                    f"Estamos refinando o plano para o app: \"{ideia}\"\n\n"
                    f"---\n{current_gemini_res}\n---\n\n"
                    "Estamos na fase de CONVERGÊNCIA. Sua tarefa:\n"
                    "1. PONTOS ACORDADOS — Liste as decisões técnicas onde já há consenso.\n"
                    "2. GAPS RESTANTES — O que ainda falta definir ou resolver?\n"
                    "3. PROPOSTA FINAL — Sugira a versão consolidada do plano incorporando "
                    "o melhor de ambas as análises.\n\n"
                    "Foque em fechar o plano, não em abrir novas discussões."
                )
            res_perp = await self.interact('perplexity', prompt_pesquisador)
            if not self.register_agent_result("perplexity", res_perp):
                print("[ERRO] Falhas no Perplexity. Encerrando.")
                return

            # =================================================================
            # 3. CHATGPT (Juiz Imparcial) — Avalia consenso do plano
            # =================================================================
            print("[*] ⚖️  ChatGPT (Juiz) avaliando consenso...")
            judge_prompt = (
                "Você é o JUIZ IMPARCIAL deste debate entre duas IAs sobre planejamento de app. "
                "Analise as duas respostas e determine o grau de consenso.\n\n"
                f"=== ARQUITETO TÉCNICO (Gemini) ===\n{current_gemini_res}\n\n"
                f"=== PESQUISADOR DE MERCADO (Perplexity) ===\n{res_perp}\n\n"
                "CRITÉRIOS DE AVALIAÇÃO:\n"
                "- Consenso NÃO exige texto idêntico. Exige que as RECOMENDAÇÕES TÉCNICAS "
                "e DECISÕES DE PRODUTO apontem na mesma direção.\n"
                "- Diferenças de ênfase ou formulação NÃO são divergências.\n"
                "- Divergências REAIS são: stack incompatível, escopo radicalmente diferente, "
                "custos discordantes por ordem de grandeza, ou lógica incompatível.\n\n"
                "RESPONDA EXCLUSIVAMENTE em JSON válido (sem markdown, sem ```json):\n"
                "{\n"
                '  "consenso": true ou false,\n'
                '  "confianca": número de 0 a 100,\n'
                '  "stack_acordada": "stack tecnológica onde concordaram",\n'
                '  "mvp_features": ["lista", "de", "features", "do", "MVP"],\n'
                '  "custo_estimado": "faixa de custo consolidada",\n'
                '  "cronograma": "tempo estimado consolidado",\n'
                '  "pendencias": "o que ainda falta resolver (vazio se nenhuma)",\n'
                '  "plano_executivo": "resumo do plano final pronto para execução se confiança >= 90",\n'
                '  "proximos_passos": ["passo 1", "passo 2", "passo 3"]\n'
                "}"
            )
            res_chatgpt = await self.interact('chatgpt', judge_prompt)
            if not self.register_agent_result("chatgpt", res_chatgpt):
                print("[ERRO] Falhas no ChatGPT Juiz. Encerrando.")
                return

            print(f"\n[VEREDITO DO JUIZ]:\n{res_chatgpt}\n")
            verdict_data = self.parse_json_verdict(res_chatgpt)

            self.append_run_log({
                "event": "judge_verdict",
                "round": r,
                "consenso": verdict_data.get("consenso"),
                "confianca": verdict_data.get("confianca"),
                "plano_executivo": verdict_data.get("plano_executivo")
            })

            # Verifica consenso
            confianca = verdict_data.get("confianca", 0)
            if verdict_data.get("consenso") == True and confianca >= consensus_threshold:
                print(f"\n{'='*60}")
                print(f"✅ PLANO APROVADO! Consenso de {confianca}% na rodada {r}!")
                print(f"{'='*60}")
                print(f"\n📦 Stack: {verdict_data.get('stack_acordada', 'N/A')}")
                print(f"📋 MVP Features: {verdict_data.get('mvp_features', 'N/A')}")
                print(f"💰 Custo: {verdict_data.get('custo_estimado', 'N/A')}")
                print(f"📅 Cronograma: {verdict_data.get('cronograma', 'N/A')}")
                print(f"\n🎯 Plano Executivo:\n{verdict_data.get('plano_executivo', 'N/A')}")
                print(f"\n🚀 Próximos Passos:")
                for i, passo in enumerate(verdict_data.get('proximos_passos', []), 1):
                    print(f"   {i}. {passo}")
                self.append_run_log({"event": "plan_approved", "round": r, "data": verdict_data})
                break
            
            print(f"[*] Plano ainda não consolidado ({confianca}% < {consensus_threshold}%). Refinando...")

            # =================================================================
            # 4. GEMINI (Arquiteto) — Refina plano com feedback do Pesquisador
            # =================================================================
            if r <= 4:
                # Fase de refinamento ativo
                prompt_refinamento = (
                    f"O Pesquisador de Mercado (Perplexity, com acesso a dados reais) "
                    f"analisou seu plano para o app \"{ideia}\":\n\n"
                    f"---\n{res_perp}\n---\n\n"
                    "E o Product Manager avaliou:\n"
                    f"Confiança: {confianca}% | Pendências: {verdict_data.get('pendencias', 'N/A')}\n\n"
                    "REFINE seu plano:\n"
                    "1. ACEITO — Quais sugestões do Pesquisador você incorpora e por quê?\n"
                    "2. CONTRAPONTO — Quais sugestões você rejeita e por quê? "
                    "(dê argumentos técnicos concretos)\n"
                    "3. PLANO ATUALIZADO — Reescreva o plano completo com as mudanças incorporadas. "
                    "Inclua: stack, MVP, arquitetura, custos, cronograma.\n\n"
                    "Seja objetivo. O objetivo é chegar num plano que ambos aceitem."
                )
            else:
                # Fase de convergência final
                prompt_refinamento = (
                    f"O Pesquisador finalizou sua análise:\n\n"
                    f"---\n{res_perp}\n---\n\n"
                    "Estamos fechando o plano. Sua tarefa:\n"
                    "1. Aceite os pontos de acordo.\n"
                    "2. Para cada pendência, proponha uma decisão final.\n"
                    "3. Apresente o PLANO EXECUTIVO FINAL com todos os detalhes:\n"
                    "   - Stack completa\n"
                    "   - Lista de features do MVP\n"
                    "   - Arquitetura\n"
                    "   - Custos detalhados\n"
                    "   - Cronograma semana a semana\n"
                    "   - Primeiros 3 passos para começar a construir\n\n"
                    "O objetivo é FECHAR o plano, não continuar debatendo."
                )
            current_gemini_res = await self.interact('gemini_proposer', prompt_refinamento)
            if not self.register_agent_result("gemini_proposer", current_gemini_res):
                print("[ERRO] Falhas no refinamento do Gemini. Encerrando.")
                return

            self.append_run_log({
                "event": "round_end",
                "round": r,
                "consenso": verdict_data.get("consenso"),
                "confianca": verdict_data.get("confianca")
            })

        print("\n[FIM] Mesa redonda encerrada.")
        self.append_run_log({"event": "planning_end"})

async def main():
    print("="*60)
    print("  🚀 MESA REDONDA DE PLANEJAMENTO DE APPS")
    print("  3 IAs colaboram para criar seu plano de execução")
    print("="*60)
    print("\n  🏗️  Gemini     → Arquiteto Técnico")
    print("  🔍 Perplexity → Pesquisador de Mercado")
    print("  ⚖️  ChatGPT    → Juiz Imparcial\n")
    ideia = input("💡 Descreva sua ideia de app: ")
    orchestrator = DebateOrchestrator()
    await orchestrator.setup()
    try:
        await orchestrator.start_debate(ideia)
    finally:
        if orchestrator.context: await orchestrator.context.close()
        if orchestrator.playwright: await orchestrator.playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
