(function() {
    try {
      const theme = localStorage.getItem('jn_portfolio_theme');
      const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
      if (theme === 'light' || (!theme && prefersLight)) document.body.classList.add('theme-light');
    } catch (e) {}
  })();
