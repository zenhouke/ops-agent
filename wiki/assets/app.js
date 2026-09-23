const menu = document.querySelector('#menu');
menu.addEventListener('click', () => {
  const open = document.body.classList.toggle('nav-open');
  menu.setAttribute('aria-expanded', String(open));
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    document.body.classList.remove('nav-open');
    menu.setAttribute('aria-expanded', 'false');
  }
});
document.querySelector('.language').addEventListener('click', event => {
  event.currentTarget.href = event.currentTarget.pathname + location.hash;
});
const lang = document.documentElement.lang;
const input = document.querySelector('#search');
const results = document.querySelector('#results');
let searchData;
let searchSequence = 0;
input.addEventListener('input', async () => {
  const sequence = ++searchSequence;
  const query = input.value.trim().toLocaleLowerCase();
  results.replaceChildren();
  if (!query) return;
  try {
    searchData ??= fetch('/assets/search.json').then(response => {
      if (!response.ok) throw new Error('Search unavailable');
      return response.json();
    });
    const all = await searchData;
    if (sequence !== searchSequence) return;
    const matches = all[lang].filter(page => (page.title + ' ' + page.text).toLocaleLowerCase().includes(query));
    if (!matches.length) results.textContent = lang === 'zh' ? '没有找到相关内容' : 'No matching topics';
    for (const page of matches) {
      const link = document.createElement('a');
      link.href = `/${lang}/${page.id}.html`;
      link.textContent = page.title;
      results.append(link);
    }
  } catch {
    searchData = undefined;
    if (sequence === searchSequence) results.textContent = lang === 'zh' ? '搜索暂时不可用，请使用目录' : 'Search unavailable; use the navigation';
  }
});
let version;
setInterval(async () => {
  if (document.hidden) return;
  try {
    const response = await fetch('/__version');
    if (!response.ok) return;
    const next = (await response.json()).version;
    if (version && version !== next) location.reload();
    version = next;
  } catch { /* Static hosting does not require the development reload endpoint. */ }
}, 3000);
