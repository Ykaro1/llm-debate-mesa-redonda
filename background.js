// Configura a extensão para abrir o Side Panel ao clicar no ícone da barra de ferramentas
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

// Log de inicialização do Service Worker
chrome.runtime.onInstalled.addListener(() => {
  console.log('LLM Debate: Mesa Redonda - Service Worker Instalado');
});
