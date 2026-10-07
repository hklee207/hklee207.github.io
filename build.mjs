// Builds the static site from content/ into plain HTML files GitHub Pages serves as-is.
// Usage: node build.mjs
import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = new URL('.', import.meta.url).pathname;
const site = JSON.parse(readFileSync(join(ROOT, 'content/site.json'), 'utf8'));

// ---------- markdown ----------
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function inline(s) {
  return esc(s)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, u) =>
      `<a href="${u}"${/^https?:/.test(u) ? ' target="_blank" rel="noopener"' : ''}>${t}</a>`)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

// A paragraph made only of images becomes a photo row: ![alt](src "caption")
const IMG = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g;
// Width/height of a JPEG, read from its SOF marker, so rows can size photos without cropping.
function jpegSize(rel) {
  try {
    const b = readFileSync(join(ROOT, rel));
    for (let i = 2; i < b.length;) {
      const marker = b[i + 1], len = b.readUInt16BE(i + 2);
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker))
        return { w: b.readUInt16BE(i + 7), h: b.readUInt16BE(i + 5) };
      i += 2 + len;
    }
  } catch {}
  return { w: 4, h: 3 };
}

function photos(line, base) {
  const imgs = [...line.matchAll(IMG)];
  return `<div class="photos n${imgs.length}">${imgs.map(([, alt, src, cap]) => {
    const { w, h } = jpegSize(src);
    return `<figure style="flex:${(w / h).toFixed(3)}"><img src="${base}${src}" alt="${esc(alt)}" width="${w}" height="${h}" loading="lazy">${cap ? `<figcaption>${inline(cap)}</figcaption>` : ''}</figure>`;
  }).join('')}</div>`;
}

function markdown(src, base = '') {
  const out = [];
  let para = [], list = null, quote = [];
  const flushPara = () => {
    if (!para.length) return;
    const text = para.join(' ');
    out.push(text.replace(IMG, '').trim() === '' ? photos(text, base) : `<p>${inline(text)}</p>`);
    para = [];
  };
  const flushList = () => { if (list) out.push(`<${list.tag}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`); list = null; };
  const flushQuote = () => { if (quote.length) out.push(`<blockquote>${markdown(quote.join('\n'))}</blockquote>`); quote = []; };
  const flush = () => { flushPara(); flushList(); flushQuote(); };

  for (const raw of src.split('\n')) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { flush(); continue; }
    if ((m = line.match(/^>\s?(.*)$/))) { flushPara(); flushList(); quote.push(m[1]); continue; }
    flushQuote();
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { flush(); const l = Math.min(m[1].length + 1, 4); out.push(`<h${l}>${inline(m[2])}</h${l}>`); continue; }
    if (/^(-{3,}|\*{3,})$/.test(line)) { flush(); out.push('<hr>'); continue; }
    if ((m = line.match(/^\s*[-*]\s+(.*)$/)) || (m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      const tag = /^\s*\d/.test(line) ? 'ol' : 'ul';
      flushPara();
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push(m[1]); continue;
    }
    if (list && /^\s{2,}\S/.test(raw)) { list.items[list.items.length - 1] += ' ' + line.trim(); continue; }
    flushList();
    para.push(line.trim());
  }
  flush();
  return out.join('\n');
}

function parse(file) {
  const text = readFileSync(file, 'utf8');
  const m = text.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  const meta = {};
  if (m) for (const l of m[1].split('\n')) {
    const i = l.indexOf(':');
    if (i > 0) meta[l.slice(0, i).trim()] = l.slice(i + 1).trim().replace(/^["']|["']$/g, '');
  }
  return { meta, body: m ? m[2] : text };
}

function collection(dir) {
  const path = join(ROOT, 'content', dir);
  if (!existsSync(path)) return [];
  return readdirSync(path)
    .filter(f => f.endsWith('.md') && !f.startsWith('_'))
    .map(f => ({ slug: f.replace(/\.md$/, ''), ...parse(join(path, f)) }))
    .sort((a, b) => (b.meta.date || '').localeCompare(a.meta.date || ''));
}

// ---------- layout ----------
const fmtDate = d => {
  if (!d) return '';
  const [y, mo, da] = d.split('-').map(Number);
  return new Date(Date.UTC(y, mo - 1, da || 1)).toLocaleDateString('en-US',
    { month: 'long', ...(da ? { day: 'numeric' } : {}), year: 'numeric', timeZone: 'UTC' });
};
const minutes = body => Math.max(1, Math.round(body.split(/\s+/).length / 220));

function page({ title, description, depth = 0, body, nav = true }) {
  const up = '../'.repeat(depth);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description || site.tagline)}">
<link rel="stylesheet" href="${up}style.css">
<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}catch(e){}</script>
</head>
<body>
<main>
${nav ? `<nav class="top"><a href="${up}index.html" class="home">${esc(site.name)}</a><span><a href="${up}journey/index.html">Journey</a><a href="${up}writing/index.html">Writing</a><a href="${up}worldview/index.html">Worldview</a><a href="${up}projects/index.html">Projects</a><button id="theme" aria-label="Toggle theme">◐</button></span></nav>` : ''}
${body}
<footer>
<span>${site.links.map(l => `<a href="${l.url}"${/^https?:/.test(l.url) ? ' target="_blank" rel="noopener"' : ''}>${esc(l.label)}</a>`).join('')}</span>
<span class="muted">© ${new Date().getFullYear()} ${esc(site.name)}</span>
</footer>
</main>
<script>document.getElementById('theme')?.addEventListener('click',()=>{const r=document.documentElement,d=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;r.dataset.theme=d?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme)}catch(e){}})</script>
</body>
</html>
`;
}

const ext = u => /^https?:/.test(u) ? ' target="_blank" rel="noopener"' : '';
const rows = (items, depth) => `<ul class="rows">${items.map(i =>
  `<li><a href="${i.href}"${ext(i.href)}><span class="t">${esc(i.title)}${/^https?:/.test(i.href) ? ' <span class="arrow">↗</span>' : ''}</span><span class="d">${esc(i.right || '')}</span></a></li>`).join('')}</ul>`;

const writing = collection('writing');
const worldview = collection('worldview');
const intro = existsSync(join(ROOT, 'content/worldview/_intro.md')) ? parse(join(ROOT, 'content/worldview/_intro.md')) : { meta: {}, body: '' };

const writingRows = (depth) => [
  ...writing.map(p => ({ title: p.meta.title, href: `${depth ? '' : 'writing/'}${p.slug}.html`, right: fmtDate(p.meta.date) })),
  ...site.archive.map(a => ({ title: a.title, href: `${'../'.repeat(depth)}${a.href}`, right: a.date })),
];

function write(rel, html) {
  const full = join(ROOT, rel);
  mkdirSync(join(full, '..'), { recursive: true });
  writeFileSync(full, html);
}

// ---------- pages ----------
const projectList = (depth) => `<ul class="projects">${site.projects.map(p => {
  const href = p.url || (p.post ? '../'.repeat(depth) + p.post : null);
  return `<li>${href ? `<a href="${href}"${ext(href)}>${esc(p.name)}${p.url ? ' <span class="arrow">↗</span>' : ''}</a>` : `<span>${esc(p.name)}</span>`}<p>${inline(p.description)}</p>${p.note ? `<p class="muted small">${inline(p.note)}</p>` : ''}</li>`;
}).join('')}</ul>`;

write('index.html', page({
  title: `${site.name}`,
  body: `<header class="hero">
<div class="hero-text"><h1>${esc(site.name)}${site.hanja ? ` <span class="hanja" lang="ko">${esc(site.hanja)}</span>` : ''}</h1><p class="muted role">${esc(site.role)}</p><div class="prose">${markdown(site.bio)}</div></div>
<figure class="portrait"><img src="assets/portrait.jpg" alt="${esc(site.name)} on a street in Seoul" width="1000" height="1321"></figure>
</header>

<figure class="shot" id="shot"><img src="${site.gallery[0].src}" alt="${esc(site.gallery[0].caption)}"><figcaption>${esc(site.gallery[0].caption)}</figcaption></figure>
<script>(function(){var g=${JSON.stringify(site.gallery)},p=g[Math.floor(Math.random()*g.length)],f=document.getElementById('shot');f.querySelector('img').src=p.src;f.querySelector('img').alt=p.caption;f.querySelector('figcaption').textContent=p.caption})()</script>

<section><h2>Now</h2><div class="prose">${markdown(site.now)}</div></section>

<section><h2>Worldview</h2>
<p class="muted">${inline(site.worldviewBlurb)}</p>
${rows(worldview.slice(0, 4).map(p => ({ title: p.meta.title, href: `worldview/${p.slug}.html`, right: fmtDate(p.meta.date) })))}
<p class="more"><a href="worldview/index.html">All notes →</a></p></section>

<section><h2>Writing</h2>
${rows(writingRows(0).slice(0, 8))}
<p class="more"><a href="writing/index.html">All writing →</a></p></section>

<section><h2>Projects</h2>${projectList(0)}</section>
`,
}));

write('writing/index.html', page({
  title: `Writing · ${site.name}`, depth: 1,
  body: `<h1>Writing</h1><p class="muted">Reviews of talks I attended and articles that changed how I see things, plus older research notes.</p>${rows(writingRows(1), 1)}`,
}));

for (const p of writing) {
  write(`writing/${p.slug}.html`, page({
    title: `${p.meta.title} · ${site.name}`, description: p.meta.summary, depth: 1,
    body: `<article>
<h1>${esc(p.meta.title)}</h1>
<p class="meta">${fmtDate(p.meta.date)} · ${minutes(p.body)} min read${p.meta.source ? ` · ${p.meta.source_url ? `<a href="${p.meta.source_url}" target="_blank" rel="noopener">${esc(p.meta.source)}</a>` : esc(p.meta.source)}` : ''}</p>
<div class="prose">${markdown(p.body)}</div>
</article>
<p class="more"><a href="index.html">← All writing</a></p>`,
  }));
}

write('worldview/index.html', page({
  title: `Worldview · ${site.name}`, depth: 1, description: intro.meta.summary,
  body: `<h1>${esc(intro.meta.title || 'Worldview')}</h1>
<div class="prose">${markdown(intro.body)}</div>
<section><h2>Notes</h2>${rows(worldview.map(p => ({ title: p.meta.title, href: `${p.slug}.html`, right: fmtDate(p.meta.date) })), 1)}</section>`,
}));

worldview.forEach((p, i) => {
  const newer = worldview[i - 1], older = worldview[i + 1];
  write(`worldview/${p.slug}.html`, page({
    title: `${p.meta.title} · ${site.name}`, description: p.meta.summary, depth: 1,
    body: `<article>
<p class="kicker">Worldview${p.meta.themes ? ` · ${esc(p.meta.themes)}` : ''}</p>
<h1>${esc(p.meta.title)}</h1>
<p class="meta">${fmtDate(p.meta.date)} · ${minutes(p.body)} min read</p>
<div class="prose">${markdown(p.body)}</div>
</article>
<nav class="pager">${older ? `<a href="${older.slug}.html">← ${esc(older.meta.title)}</a>` : '<span></span>'}${newer ? `<a href="${newer.slug}.html">${esc(newer.meta.title)} →</a>` : ''}</nav>`,
  }));
});

write('projects/index.html', page({
  title: `Projects · ${site.name}`, depth: 1,
  body: `<h1>Projects</h1><p class="muted">Things I've built, mostly to answer a question I had.</p>${projectList(1)}`,
}));

const journey = parse(join(ROOT, 'content/journey.md'));
write('journey/index.html', page({
  title: `${journey.meta.title} · ${site.name}`, description: journey.meta.summary, depth: 1,
  body: `<article class="journey">
<h1>${esc(journey.meta.title)}</h1>
<p class="meta">${esc(journey.meta.summary)}</p>
<div class="prose">${markdown(journey.body, '../')}</div>
</article>`,
}));

console.log(`built: journey, home, ${writing.length} writing, ${worldview.length} worldview, ${site.projects.length} projects`);
