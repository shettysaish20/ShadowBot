// Wire interactive bits and config-driven links
(function(){
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

  // Year
  const y = new Date().getFullYear();
  const yEl = $('#year'); if (yEl) yEl.textContent = y;

  // Smooth scroll
  $$('.nav a, .scroll-indicator').forEach(a => {
    a.addEventListener('click', e => {
      const target = a.getAttribute('data-scroll') || a.getAttribute('href');
      if (!target || !target.startsWith('#')) return;
      e.preventDefault();
      const el = $(target);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  // Typewriter rotate
  const tw = $('.typewriter');
  if (tw){
    let i = 0; const words = JSON.parse(tw.dataset.rotate || '[]');
    const swap = () => { i = (i+1) % words.length; tw.textContent = words[i]; };
    setInterval(swap, 2000);
  }

  // Carousel
  const track = $('.carousel-track');
  const slides = $$('.carousel-track img');
  let idx = 0;
  const setSlide = () => {
    track.style.transform = `translateX(-${idx*100}%)`;
  }
  $('.carousel .next')?.addEventListener('click', () => { idx = (idx+1)%slides.length; setSlide(); });
  $('.carousel .prev')?.addEventListener('click', () => { idx = (idx-1+slides.length)%slides.length; setSlide(); });

  // Video embed
  const videoWrap = $('#video-embed');
  const vId = (window.SHADOWBOT_CONFIG && window.SHADOWBOT_CONFIG.videoId) || '';
  if (videoWrap && vId){
    const play = $('.video-play', videoWrap);
    const makeIframe = () => {
      const iframe = document.createElement('iframe');
      iframe.width = '560';
      iframe.height = '315';
      iframe.src = `https://www.youtube.com/embed/${vId}?autoplay=1`;
      iframe.title = 'Shadowbot Demo Video';
      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
      iframe.referrerPolicy = 'strict-origin-when-cross-origin';
      iframe.allowFullscreen = true;
      return iframe;
    }
    play?.addEventListener('click', () => {
      videoWrap.innerHTML = '';
      videoWrap.appendChild(makeIframe());
    });
  } else if (videoWrap) {
    // no video id, show tooltip
    const play = $('.video-play', videoWrap);
    play?.addEventListener('click', () => alert('Demo video coming soon'));
  }

  // Download links & GitHub
  const cfg = window.SHADOWBOT_CONFIG || {};
  const setHref = (id, url) => { const el = $(id); if (el && url) el.setAttribute('href', url); };
  setHref('#dl-windows', cfg.downloads?.windows);
  setHref('#dl-mac', cfg.downloads?.mac);
  setHref('#github-link', cfg.github);
  setHref('#footer-github', cfg.github);

  // Mirror buttons in hero
  $('#btn-win')?.addEventListener('click', e => { const url = cfg.downloads?.windows; if (url) $('#dl-windows').click(); });
  $('#btn-mac')?.addEventListener('click', e => { const url = cfg.downloads?.mac; if (url) $('#dl-mac').click(); });
})();
