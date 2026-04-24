// Configurações das LLMs
const GEMINI_API_KEY = "AIzaSyDLoVyY8S_JcqVmdZWB2zTRkvzfD35tVoc";
const GEMINI_MODELS = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"];

const CONFIG = {
    perplexity: { url: "perplexity.ai", name: "Perplexity" },
    gemini: { url: "gemini.google.com", name: "Gemini" },
    chatgpt: { url: "chatgpt.com", name: "ChatGPT" },
    maxRounds: 3
};

// Função para chamar a API do Gemini com Fallback de modelos
async function callGeminiAPI(prompt) {
    for (const model of GEMINI_MODELS) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 20000); // 20 segundos

            const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${GEMINI_API_KEY}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                signal: controller.signal,
                body: JSON.stringify({
                    contents: [{ parts: [{ text: prompt }] }]
                })
            });
            
            clearTimeout(timeoutId);
            const data = await response.json();
            if (data.candidates && data.candidates[0].content.parts[0].text) {
                return data.candidates[0].content.parts[0].text;
            }
        } catch (e) {
            console.warn(`Falha no modelo ${model}: ${e.message}`);
        }
    }
    return "VEREDITO: DIVERGÊNCIA. Motivo: Falha técnica na comunicação com o Juiz Supremo.";
}

let state = { rounds: 0, isDebating: false };

const chatDisplay = document.getElementById('chatDisplay');
const startBtn = document.getElementById('startBtn');
const userInput = document.getElementById('userInput');
const clearBtn = document.getElementById('clearBtn');

// Listener para limpar o histórico manualmente
clearBtn.addEventListener('click', () => {
    if (confirm("Deseja limpar todo o histórico do debate?")) {
        resetDebate();
        addMessage("system", "Histórico limpo pelo usuário.");
    }
});

// OS ELEMENTOS VISUAIS (Que eu havia apagado por acidente!)
const dots = {
    perplexity: document.querySelector('#llm-a .dot'),
    gemini: document.querySelector('#llm-b .dot'),
    chatgpt: document.querySelector('#llm-c .dot')
};

// Verifica o status das abas imediatamente
checkTabsStatus();

async function checkTabsStatus() {
    const tabs = await findRequiredTabs();
    
    // Atualiza os dots visualmente
    Object.keys(CONFIG).forEach(key => {
        if (key === 'maxRounds') return;
        const dot = dots[key];
        if (dot) {
            if (tabs[key]) {
                dot.className = 'dot ok'; // Verde se achou
            } else {
                dot.className = 'dot error'; // Vermelho se não achou
            }
        }
    });
    
    return tabs;
}

startBtn.addEventListener('click', async () => {
    if (state.isDebating) return;
    const prompt = userInput.value.trim();
    
    if (!prompt) {
        addMessage("system", "⚠️ Digite um tema para o debate antes de enviar.");
        return;
    }

    resetDebate();
    await startMesaRedonda(prompt);
});

async function startMesaRedonda(prompt) {
    state.isDebating = true;
    
    // 1. VALIDAÇÃO ESTRITA
    const tabs = await checkTabsStatus();
    if (!tabs.gemini || !tabs.perplexity || !tabs.chatgpt) {
        addMessage("system", "🚨 ERRO: Debate abortado. Esta lógica exige as TRÊS abas abertas.");
        setDotsStatus('error');
        state.isDebating = false;
        return;
    }

    addMessage("system", "🚀 Iniciando Debate Circular (Contra-Argumento Ativo)");
    setDotsStatus('thinking'); 
    
    // 2. PROPOSTA INICIAL (RODADA 0)
    addMessage("system", "✍️ [Rodada 0] Gemini formulando a Tese Inicial...");
    const initialPrompt = `[PAPEL: PROPOSITOR] Crie uma tese inicial técnica e detalhada sobre o tema abaixo.\n\nTEMA: "${prompt}"`;
    
    let thesisResult = await interactWithLLM(tabs.gemini, initialPrompt, "", "gemini");
    
    if (thesisResult.content.startsWith("ERRO")) {
        addMessage("system", "⚠️ Gemini falhou. Tentando reconectar...");
        await new Promise(r => setTimeout(r, 2000));
        thesisResult = await interactWithLLM(tabs.gemini, initialPrompt, "", "gemini");
    }

    if (thesisResult.content.startsWith("ERRO")) {
        addMessage("system", "❌ ERRO CRÍTICO: O proponente (Gemini) falhou.");
        state.isDebating = false;
        return;
    }

    let currentThesis = thesisResult.content;
    addMessage("gemini", `<b>Tese Inicial:</b><br>${currentThesis}`);
    
    let consensusReached = false;
    let rounds = 0;

    // 3. LOOP DE AVALIAÇÃO
    while (!consensusReached && rounds < CONFIG.maxRounds) {
        rounds++;
        addMessage("system", `⚖️ [Rodada ${rounds}] Enviando tese para avaliação crítica...`);
        
        const [perpEval, gptEval] = await Promise.all([
            interactWithLLM(tabs.perplexity, `Analise a tese: ${currentThesis}`, "", "perplexity"),
            interactWithLLM(tabs.chatgpt, `Analise a tese: ${currentThesis}`, "", "chatgpt")
        ]);

        // VALIDAÇÃO ESTRITA: Se qualquer uma falhar, o debate para
        if (perpEval.content.startsWith("ERRO")) {
            addMessage("system", `🚨 DEBATE ABORTADO: O Perplexity não respondeu.`);
            state.isDebating = false;
            return;
        }
        if (gptEval.content.startsWith("ERRO")) {
            addMessage("system", `🚨 DEBATE ABORTADO: O ChatGPT não respondeu.`);
            state.isDebating = false;
            return;
        }

        addMessage("perplexity", `<b>Crítica Factual:</b><br>${perpEval.content}`);
        addMessage("chatgpt", `<b>Crítica Lógica:</b><br>${gptEval.content}`);

        addMessage("system", "🤖 Juiz Supremo (API) analisando vereditos...");
        
        const judgePrompt = `Você é o Juiz. Analise o consenso.\nTESE: ${currentThesis}\nPERPLEXITY: ${perpEval.content}\nCHATGPT: ${gptEval.content}`;

        const verdict = await callGeminiAPI(judgePrompt);
        addMessage("system", verdict);

        if (verdict.includes("VEREDITO: CONSENSO")) {
            consensusReached = true;
            addMessage("system", "✅ CONSENSO ALCANÇADO!");
        } else {
            addMessage("system", `🔄 [Reação] Refinando tese...`);
            const defensePrompt = `[PAPEL: DEFENSOR] Ajuste sua tese com base nas críticas:\n${perpEval.content}\n${gptEval.content}`;
            const defenseResult = await interactWithLLM(tabs.gemini, defensePrompt, "", "gemini");
            
            if (defenseResult.content.startsWith("ERRO")) {
                addMessage("system", "🚨 DEBATE ABORTADO: Gemini falhou ao refinar a tese.");
                state.isDebating = false;
                return;
            }
            
            currentThesis = defenseResult.content;
            addMessage("gemini", `<b>Tese Refinada:</b><br>${currentThesis}`);
        }
    }

    if (!consensusReached) {
        addMessage("system", "⚠️ Limite de rodadas atingido.");
    }

    addMessage("system", "🏁 Processo de Mesa Redonda Finalizado.");
    setDotsStatus('ok');
    state.isDebating = false;
}


async function findRequiredTabs() {
    const allTabs = await chrome.tabs.query({});
    const found = { allOpen: true, missing: [] };
    
    for (const [key, config] of Object.entries(CONFIG)) {
        if (key === 'maxRounds') continue;
        const tab = allTabs.find(t => t.url && t.url.includes(config.url));
        if (tab) {
            found[key] = tab.id;
        } else {
            found.allOpen = false;
            found.missing.push(config.name);
        }
    }
    return found;
}

async function interactWithLLM(tabId, prompt, feedback, provider) {
    const fullPrompt = feedback ? `FEEDBACK DOS OUTROS: ${feedback}\n\nPROMPT: ${prompt}` : prompt;
    
    try {
        const tab = await chrome.tabs.update(tabId, { active: true });
        
        // Espera a aba carregar 100% para evitar erro de política de script
        if (tab.status !== 'complete') {
            await new Promise(r => {
                const listener = (id, info) => {
                    if (id === tabId && info.status === 'complete') {
                        chrome.tabs.onUpdated.removeListener(listener);
                        r();
                    }
                };
                chrome.tabs.onUpdated.addListener(listener);
            });
        }
        
        const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: automationScript,
            args: [fullPrompt, provider]
        });

        if (!results || !results[0]) throw new Error("Sem resposta do script de automação.");
        const result = results[0].result;
        
        if (result.startsWith("ERRO:")) throw new Error(result);
        
        return { provider, content: result };
    } catch (e) {
        return { provider, content: `ERRO: ${e.message}` };
    }
}

async function automationScript(text, provider) {
    const selectors = {
        chatgpt: { 
            input: '#prompt-textarea', 
            btn: '[data-testid="send-button"], button[aria-label*="Send"], button:has(svg)', 
            response: '[data-message-author-role="assistant"], .markdown' 
        },
        gemini: { 
            input: 'div[role="textbox"], .ql-editor', 
            btn: 'button[aria-label*="Enviar"], button[aria-label*="Send"], .send-button-container button, button:has(svg path[d*="M2"])', 
            response: '.message-content, .model-response-text, .content' 
        },
        perplexity: { 
            input: '#ask-input, [data-lexical-editor="true"]', 
            btn: 'button.bg-button-bg, button[aria-label*="Submit"], button[aria-label*="Enviar"]', 
            response: '.prose' 
        }
    };

    const sel = selectors[provider];
    const inputField = document.querySelector(sel.input) || document.querySelector('[contenteditable="true"], textarea');
    
    if (!inputField) return `ERRO: Campo de entrada não encontrado no ${provider}.`;

    inputField.focus();
    
    // Inserção robusta para Lexical/React
    try {
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, text);
    } catch(e) {
        inputField.innerText = text;
    }

    inputField.dispatchEvent(new Event('input', { bubbles: true }));
    inputField.dispatchEvent(new Event('change', { bubbles: true }));

    // Espera a UI reagir ao texto (importante para o Perplexity trocar o botão de voz para envio)
    await new Promise(r => setTimeout(r, 1500));

    // Busca o botão
    let sendBtn = document.querySelector(sel.btn);
    
    // Especial Perplexity: Se o botão ainda for o de "voz", espera um pouco mais
    if (provider === 'perplexity' && sendBtn && sendBtn.ariaLabel && sendBtn.ariaLabel.includes('voz')) {
        await new Promise(r => setTimeout(r, 500));
        sendBtn = document.querySelector(sel.btn); // tenta pegar de novo
    }

    if (sendBtn && !sendBtn.disabled) {
        sendBtn.click();
    } else {
        // Fallback: Teclado
        const events = ['keydown', 'keypress', 'keyup'];
        events.forEach(type => {
            inputField.dispatchEvent(new KeyboardEvent(type, {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true
            }));
        });
    }

    // Loop de resposta...
    let lastText = "";
    let stableSecs = 0;
    for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const msgs = document.querySelectorAll(sel.response);
        if (msgs.length > 0) {
            let current = msgs[msgs.length - 1].innerText.trim();
            
            // Limpa lixo do Gemini
            current = current.replace(/Abre em uma nova janela/g, '').replace(/Conversa temporária/g, '').replace(/Compartilhar/g, '').trim();

            if (current.length > 10 && !current.includes("Searching...")) {
                if (current === lastText) {
                    stableSecs++;
                    if (stableSecs >= 3) return current;
                } else {
                    stableSecs = 0;
                    lastText = current;
                }
            }
        }
    }
    return lastText || `ERRO: O ${provider} não gerou resposta a tempo.`;
}

let chatHistory = [];

function addMessage(type, text, save = true) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    const name = CONFIG[type] ? CONFIG[type].name : "Sistema";
    div.innerHTML = `<strong>${name}:</strong> ${text}`;
    chatDisplay.appendChild(div);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;

    if (save) {
        chatHistory.push({ type, text });
        chrome.storage.local.set({ chatHistory });
    }
}

function resetDebate() {
    state.rounds = 0;
    state.isDebating = false; // CHAVE: Força o desbloqueio da lógica da interface
    chatDisplay.innerHTML = "";
    chatHistory = [];
    chrome.storage.local.set({ chatHistory: [] });
    
    // Repõe o estado visual das bolinhas
    checkTabsStatus(); 
}

function setDotsStatus(status) {
    Object.values(dots).forEach(dot => {
        if(dot) dot.className = 'dot ' + status;
    });
}

// Salvar o que o usuário digita no rascunho
userInput.addEventListener('input', () => {
    chrome.storage.local.set({ savedInput: userInput.value });
});

// Carregar histórico e rascunho assim que abrir
chrome.storage.local.get(['chatHistory', 'savedInput'], (data) => {
    if (data.savedInput) {
        userInput.value = data.savedInput;
    }
    if (data.chatHistory && data.chatHistory.length > 0) {
        data.chatHistory.forEach(msg => addMessage(msg.type, msg.text, false));
        chatHistory = data.chatHistory;
    }
});
