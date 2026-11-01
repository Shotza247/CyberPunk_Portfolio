// Theme toggle with saved visitor preference
  const themeToggle = document.getElementById('theme-toggle');
  const savedTheme = localStorage.getItem('jn_portfolio_theme');
  const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;

  function applyTheme(theme) {
    const isLight = theme === 'light';
    document.body.classList.toggle('theme-light', isLight);
    themeToggle?.setAttribute('aria-pressed', String(isLight));
    themeToggle?.setAttribute('aria-label', isLight ? 'Switch to dark theme' : 'Switch to light theme');
    themeToggle?.setAttribute('title', isLight ? 'Switch to dark theme' : 'Switch to light theme');
  }

  applyTheme(savedTheme || (prefersLight ? 'light' : 'dark'));

  themeToggle?.addEventListener('click', () => {
    const nextTheme = document.body.classList.contains('theme-light') ? 'dark' : 'light';
    localStorage.setItem('jn_portfolio_theme', nextTheme);
    applyTheme(nextTheme);
  });

  // Intersection Observer for fade-up animations
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.classList.add('visible');
          // Animate skill bars if present
          const fills = entry.target.querySelectorAll('.skill-fill[data-w]');
          fills.forEach(fill => {
            fill.style.width = fill.dataset.w + '%';
          });
        }, i * 80);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.fade-up').forEach(el => observer.observe(el));

  // Also animate skill bars on section scroll
  const skillObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.querySelectorAll('.skill-fill[data-w]').forEach(fill => {
          fill.style.width = fill.dataset.w + '%';
        });
        skillObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.2 });

  document.querySelectorAll('.skill-cluster').forEach(el => skillObserver.observe(el));

  // Active nav link highlight
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-links a');

  const navObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(link => {
          link.style.color = '';
          if (link.getAttribute('href') === '#' + entry.target.id) {
            link.style.color = 'var(--cyan)';
          }
        });
      }
    });
  }, { threshold: 0.4 });

  sections.forEach(s => navObserver.observe(s));
