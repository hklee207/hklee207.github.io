# hklee207.github.io

Personal site of Aiden Lee. Plain static HTML, served by GitHub Pages.

## Edit
- Bio, Now, projects, footer links: `content/site.json`
- Life story with photos: `content/journey.md` (photos in `assets/journey/`; a paragraph of only `![alt](src "caption")` images becomes a photo row)
- Writing (talk and article reviews, essays): `content/writing/<slug>.md`
- Worldview (notes from conversations with my dad): `content/worldview/<date>-<slug>.md`, intro in `_intro.md`

Each post starts with frontmatter (`title`, `date: YYYY-MM-DD`, `summary`, `kind`, optional `source`, `source_url`, `themes`), then simple Markdown.

## Build
```bash
node build.mjs     # regenerates index.html, writing/, worldview/, projects/
git add -A && git commit -m "..." && git push
```
Older pages in `posts/` (notebooks, project write-ups) are hand-written HTML and use `legacy-style.css`.
