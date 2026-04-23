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
    
    const tabs = await checkTabsStatus();
    
    if (!tabs.gemini || !tabs.perplexity) {
        addMessage("system", "🚨 ERRO: A nova lógica exige que o Gemini e o Perplexity estejam abertos.");
        setDotsStatus('error');
        state.isDebating = false;
        return;
    }

    addMessage("system", "🚀 Iniciando Mesa Redonda: Modo Hierárquico");
    setDotsStatus('thinking'); 
    
    // PASSO 1: O GEMINI FAZ A PROPOSIÇÃO INICIAL
    addMessage("system", "1️⃣ Extraindo proposta inicial do Gemini...");
    const geminiPrompt = `[INSTRUÇÃO DE SISTEMA: Você está em um debate. Dite a regra/proposta inicial para o seguinte tema. No final da sua resposta, escreva obrigatoriamente: "STATUS: [CONSENSO ou NÃO CONSENSO]"]\n\nTEMA: "${prompt}"`;
    
    let geminiResponse = await interactWithLLM(tabs.gemini, geminiPrompt, "", "gemini");
    addMessage("gemini", geminiResponse.content);
    
    let consensusReached = false;
    let rounds = 0;
    let currentProposal = geminiResponse.content;

    // PASSO 2: O LOOP DE CONSENSO (GEMINI VS PERPLEXITY)
    while (!consensusReached && rounds < CONFIG.maxRounds) {
        rounds++;
        addMessage("system", `🔄 Rodada ${rounds}: Perplexity verificando fatos...`);
        
        const perpPrompt = `[INSTRUÇÃO DE SISTEMA: Analise a proposta abaixo. Verifique a veracidade. No final da sua resposta, escreva obrigatoriamente: "STATUS: [CONSENSO ou NÃO CONSENSO]"]\n\nPROPOSTA DO GEMINI:\n${currentProposal}`;
        
        let perpResponse = await interactWithLLM(tabs.perplexity, perpPrompt, "", "perplexity");
        addMessage("perplexity", perpResponse.content);

        // A API ENTRA COMO JUIZ
        addMessage("system", "⚖️ API do Gemini julgando o nível de consenso...");
        const judgePrompt = `Analise a discussão abaixo. O Especialista (Gemini) e o Checador (Perplexity) chegaram a um acordo total sobre os fatos? Responda iniciando com "VEREDITO: SIM" ou "VEREDITO: NÃO" e justifique.\n\nPROPOSTA:\n${currentProposal}\n\nREVISÃO:\n${perpResponse.content}`;
        
        const judgeVerdict = await callGeminiAPI(judgePrompt);
        addMessage("system", `🤖 Juiz (API): ${judgeVerdict}`);

        if (judgeVerdict.toUpperCase().includes("VEREDITO: SIM")) {
            consensusReached = true;
            addMessage("system", "✅ Consenso Validado pela API!");
        } else {
            addMessage("system", "⚠️ API detectou que ainda há divergências. Refinando...");
            const geminiFeedbackPrompt = `[SISTEMA: A API de julgamento detectou que ainda não há consenso. Corrija sua proposta com base nestas críticas: ${perpResponse.content}]`;
            let newGeminiResponse = await interactWithLLM(tabs.gemini, geminiFeedbackPrompt, "", "gemini");
            currentProposal = newGeminiResponse.content;
            addMessage("gemini", currentProposal);
        }
    }

    // PASSO 3: O VEREDITO FINAL (CHATGPT)
    if (tabs.chatgpt) {
        addMessage("system", "3️⃣ Enviando consenso para o ChatGPT (Editor Final)...");
        const gptPrompt = `[INSTRUÇÃO DE SISTEMA: O Gemini e o Perplexity debateram e chegaram no consenso abaixo. Atue como Editor-Chefe: Melhore a fluidez, resuma os pontos chaves e dê o veredito final do debate.]\n\nCONSENSO:\n${currentProposal}`;
        
        let gptResponse = await interactWithLLM(tabs.chatgpt, gptPrompt, "", "chatgpt");
        addMessage("chatgpt", gptResponse.content);
    } else {
        addMessage("system", "⚠️ ChatGPT não está aberto. Finalizando debate sem o veredito final.");
    }

    addMessage("system", "🎯 Mesa Redonda Concluída!");
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
        chatgpt: { 
            input: '#prompt-textarea', 
            btn: 'button[data-testid="send-button"]', 
            response: '[data-message-author-role="assistant"]' 
        },
        gemini: { 
            input: 'div[role="textbox"], .ql-editor, div[aria-label*="pergunta"], div[aria-label*="Gemini"]', 
            btn: 'button[aria-label*="Enviar"], .send-button', 
            response: '.message-content, .model-response-text' 
        },
        perplexity: { 
            input: 'textarea[placeholder*="Ask"], textarea[placeholder*="pergunta"]', 
            btn: 'button[aria-label*="Submit"], button[aria-label*="enviar"]', 
            response: '.prose, .default-line-height' 
        }
    };

    const sel = selectors[provider];
    let inputField = document.querySelector(sel.input);
    
    if (!inputField) {
        inputField = document.querySelector('div[contenteditable="true"], textarea');
    }

    if (inputField) {
        inputField.focus();
        document.execCommand('insertText', false, text);
        
        await new Promise(r => setTimeout(r, 500));

        const btn = document.querySelector(sel.btn);
        if (btn && !btn.disabled) {
            btn.click();
        } else {
            // Injeção de Enter nível React/NextJS
            const enterDown = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
            const enterUp = new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
            inputField.dispatchEvent(enterDown);
            inputField.dispatchEvent(enterUp);
        }

        let response = "";
        for (let i = 0; i < 30; i++) { // Aumentado para 30s pois o loop é maior
            await new Promise(r => setTimeout(r, 1000));
            const elements = document.querySelectorAll(sel.response);
            if (elements.length > 0) {
                const lastRes = elements[elements.length - 1].innerText;
                // Ignorar estados de carregamento
                if (lastRes.length > 15 && lastRes !== response && !lastRes.includes("Searching...")) {
                    response = lastRes;
                    await new Promise(r => setTimeout(r, 2000)); // Espera ele terminar de redigir
                    return elements[elements.length - 1].innerText;
                }
            }
        }
        return response || "A IA não respondeu a tempo ou está carregando.";
    }
    return "Não encontrei o campo de texto nesta página.";
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
