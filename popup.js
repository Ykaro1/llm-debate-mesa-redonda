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
            const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${GEMINI_API_KEY}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    contents: [{ parts: [{ text: prompt }] }]
                })
            });
            const data = await response.json();
            if (data.candidates && data.candidates[0].content.parts[0].text) {
                return data.candidates[0].content.parts[0].text;
            }
        } catch (e) {
            console.warn(`Falha no modelo ${model}, tentando o próximo...`);
        }
    }
    throw new Error("Todos os modelos da API falharam.");
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
        addMessage("system", "🚨 ERRO: Debate abortado. Esta lógica exige as TRÊS abas abertas (Gemini, Perplexity e ChatGPT).");
        setDotsStatus('error');
        state.isDebating = false;
        return;
    }

    addMessage("system", "🚀 Iniciando Debate Circular (Contra-Argumento Ativo)");
    setDotsStatus('thinking'); 
    
    // 2. PROPOSTA INICIAL (RODADA 0)
    addMessage("system", "✍️ [Rodada 0] Gemini formulando a Tese Inicial...");
    const initialPrompt = `[PAPEL: PROPOSITOR] Crie uma tese inicial técnica e detalhada sobre o tema abaixo. Sua tese será desafiada por outros especialistas, então seja robusto.\n\nTEMA: "${prompt}"`;
    
    let currentThesis = (await interactWithLLM(tabs.gemini, initialPrompt, "", "gemini")).content;
    addMessage("gemini", `<b>Tese Inicial:</b><br>${currentThesis}`);
    
    let consensusReached = false;
    let rounds = 0;

    // 3. LOOP DE AVALIAÇÃO (DEBATE CIRCULAR)
    while (!consensusReached && rounds < CONFIG.maxRounds) {
        rounds++;
        addMessage("system", `⚖️ [Rodada ${rounds}] Enviando tese para avaliação crítica...`);
        
        // Avaliação em Paralelo (Perplexity e ChatGPT)
        const [perpEval, gptEval] = await Promise.all([
            interactWithLLM(tabs.perplexity, `[PAPEL: CRÍTICO] Analise a tese abaixo. Busque falhas factuais ou omissões. Se concordar 100%, diga CONSENSO. Se tiver críticas, exponha-as claramente.\n\nTESE:\n${currentThesis}`, "", "perplexity"),
            interactWithLLM(tabs.chatgpt, `[PAPEL: CRÍTICO] Analise a tese abaixo. Busque falhas de lógica ou melhorias. Se concordar 100%, diga CONSENSO. Se tiver críticas, exponha-as claramente.\n\nTESE:\n${currentThesis}`, "", "chatgpt")
        ]);

        addMessage("perplexity", `<b>Crítica Factual:</b><br>${perpEval.content}`);
        addMessage("chatgpt", `<b>Crítica Lógica:</b><br>${gptEval.content}`);

        // 4. O JUIZ (API) ANALISA AS DISCORDÂNCIAS
        addMessage("system", "🤖 Juiz Supremo (API) analisando vereditos...");
        const judgePrompt = `Você é o Juiz de um debate técnico. Analise se houve consenso total entre os participantes.
        
        TESE ATUAL: ${currentThesis}
        CRÍTICA PERPLEXITY: ${perpEval.content}
        CRÍTICA CHATGPT: ${gptEval.content}

        REGRAS:
        - Se ambos concordarem com a tese, retorne apenas: "VEREDITO: CONSENSO".
        - Se houver qualquer discordância, resuma o ponto principal do conflito e retorne: "VEREDITO: DIVERGÊNCIA. Motivo: [resumo curto]".`;

        const verdict = await callGeminiAPI(judgePrompt);
        addMessage("system", verdict);

        if (verdict.includes("VEREDITO: CONSENSO")) {
            consensusReached = true;
            addMessage("system", "✅ CONSENSO ALCANÇADO! O debate foi encerrado com sucesso.");
        } else {
            // 5. TRATAMENTO DA DIVERGÊNCIA (DEFESA DO GEMINI)
            const motivo = verdict.split("Motivo:")[1] || "Discordância geral nos argumentos.";
            addMessage("system", `🔄 [Reação] Devolvendo críticas para o Gemini ajustar a tese...`);
            
            const defensePrompt = `[PAPEL: DEFENSOR] Sua tese foi criticada. O Juiz apontou a seguinte divergência central: "${motivo}". 
            Analise as críticas do Perplexity e ChatGPT abaixo e formule uma NOVA versão da tese, defendendo seus pontos ou corrigindo as falhas.
            
            CRÍTICAS:
            Perplexity: ${perpEval.content}
            ChatGPT: ${gptEval.content}
            
            SUA NOVA TESE AJUSTADA:`;

            currentThesis = (await interactWithLLM(tabs.gemini, defensePrompt, "", "gemini")).content;
            addMessage("gemini", `<b>Tese Refinada:</b><br>${currentThesis}`);
        }
    }

    if (!consensusReached) {
        addMessage("system", "⚠️ Limite de rodadas atingido. O debate terminou em divergência construtiva.");
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
        // Acorda a aba para o DOM renderizar o streaming de texto corretamente
        await chrome.tabs.update(tabId, { active: true });
        
        const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: automationScript,
            args: [fullPrompt, provider]
        });

        if (!results || !results[0]) throw new Error("Sem resposta do script");
        return { provider, content: results[0].result };
    } catch (e) {
        return { provider, content: "ERRO: Não consegui interagir com esta aba. Verifique se ela está carregada." };
    }
}

async function automationScript(text, provider) {
    const selectors = {
        chatgpt: { input: '#prompt-textarea', btn: '[data-testid="send-button"]', response: '[data-message-author-role="assistant"]' },
        gemini: { input: 'div[role="textbox"], .ql-editor', btn: '.send-button, button[aria-label*="Enviar"]', response: '.message-content, .model-response-text, .content' },
        perplexity: { input: 'textarea[placeholder*="Ask"], textarea', btn: 'button[aria-label*="Submit"]', response: '.prose' }
    };

    const sel = selectors[provider];
    let inputField = document.querySelector(sel.input) || document.querySelector('div[contenteditable="true"], textarea');
    
    if (!inputField) return "ERRO: Campo de texto não encontrado.";

    // Dispara eventos nativos para acordar o framework da página
    inputField.focus();
    if (inputField.tagName === 'TEXTAREA') {
        inputField.value = text;
    } else {
        inputField.innerText = text;
    }
    inputField.dispatchEvent(new Event('input', { bubbles: true }));
    inputField.dispatchEvent(new Event('change', { bubbles: true }));
    
    await new Promise(r => setTimeout(r, 800));

    // Tenta clicar no botão de envio
    let btn = document.querySelector(sel.btn);
    if (btn && btn.getAttribute('aria-disabled') !== 'true' && !btn.disabled) {
        btn.click();
    } else {
        const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
        inputField.dispatchEvent(enterEvent);
    }

    // Loop de estabilidade para aguardar a IA redigir
    let previousText = "";
    let stableCount = 0;
    
    for (let i = 0; i < 45; i++) {
        await new Promise(r => setTimeout(r, 1000));
        
        const elements = document.querySelectorAll(sel.response);
        if (elements.length > 0) {
            const currentRes = elements[elements.length - 1].innerText.trim();
            
            if (currentRes.length > 15 && !currentRes.includes("Searching...")) {
                if (currentRes === previousText) {
                    stableCount++;
                    if (stableCount >= 3) return currentRes; // Terminou de gerar
                } else {
                    stableCount = 0; 
                    previousText = currentRes;
                }
            }
        }
    }
    return previousText || "ERRO: Timeout aguardando resposta.";
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
    chatDisplay.innerHTML = "";
    chatHistory = [];
    chrome.storage.local.set({ chatHistory: [] });
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
