// Runs before CSS: prevents a light/dark flash and validates stored preferences.
(() => {
  const root = document.documentElement;
  const read = (key, fallback) => {
    try { return JSON.parse(localStorage.getItem('qvs.' + key)) ?? fallback; } catch { return fallback; }
  };
  const choice = (key, values, fallback) => {
    const value = read(key, fallback);
    return values.includes(value) ? value : fallback;
  };
  const theme = choice('theme', ['system', 'dark', 'light'], 'system');
  root.dataset.theme = theme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : theme;
  root.dataset.font = choice('font', ['studio', 'editorial'], 'studio');
  root.dataset.scale = String(choice('scale', [100, 110, 120], 100));
  root.lang = choice('locale', ['zh-CN', 'en'], navigator.language.startsWith('zh') ? 'zh-CN' : 'en');
})();
