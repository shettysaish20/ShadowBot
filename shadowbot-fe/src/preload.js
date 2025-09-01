// // See the Electron documentation for details on how to use preload scripts:
// // https://www.electronjs.org/docs/latest/tutorial/process-model#preload-scripts

// // Global error & promise rejection logging injected by preload
// window.addEventListener('error', (e) => {
//   try { console.error('[GLOBAL ERROR]', e.message, e.error); } catch(_) {}
// });
// window.addEventListener('unhandledrejection', (e) => {
//   try { console.error('[UNHANDLED REJECTION]', e.reason); } catch(_) {}
// });

// try {
//   const banner = document.createElement('div');
//   banner.textContent = 'DEBUG: Preload loaded';
//   banner.style.position = 'fixed';
//   banner.style.bottom = '0';
//   banner.style.left = '0';
//   banner.style.width = '100vw';
//   banner.style.height = '32px';
//   banner.style.background = 'rgba(0,0,255,0.7)';
//   banner.style.color = '#fff';
//   banner.style.zIndex = '99999';
//   banner.style.fontSize = '18px';
//   banner.style.textAlign = 'center';
//   banner.style.lineHeight = '32px';
//   banner.style.pointerEvents = 'none';
//   document.body.appendChild(banner);
// } catch(e) {}
