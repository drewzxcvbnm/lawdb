const $ = (selector) => document.querySelector(selector);
const form = $('#search-form');
const keys = ['q', 'mode', 'court', 'process_type', 'instance', 'date_from', 'date_to', 'sort'];
let state = new URLSearchParams(location.search);
let searchController;
let readerController;
let currentDecision;
let readerOpener;
const formatNumber = (value) => new Intl.NumberFormat('en').format(value);
const formatDate = (value) => value ? new Intl.DateTimeFormat('en-GB', {day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value)) : 'Date unavailable';
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
async function api(url, signal) {
  const response = await fetch(url, {signal});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the search fields and try again.');
  return data;
}
function fillForm() {
  for (const key of keys) {
    const input = form.elements.namedItem(key);
    const value = state.get(key) || ({mode:'text',sort:'relevance'}[key] || '');
    if (input.tagName === 'SELECT' && value && ![...input.options].some(o => o.value === value)) input.add(new Option(value, value));
    input.value = value;
  }
}
function collectForm() {
  const params = new URLSearchParams();
  for (const key of keys) {
    const value = form.elements.namedItem(key).value.trim();
    if (value) params.set(key, value);
  }
  return params;
}
function updateUrl(replace = false) {
  const url = new URL(location.href);
  url.search = state.toString();
  history[replace ? 'replaceState' : 'pushState']({}, '', url);
}
function displayError(container, message, retry) {
  container.replaceChildren();
  const box = node('div', 'empty-state');
  box.append(node('h3', '', 'Something needs attention'), node('p', '', message));
  const button = node('button', 'secondary', 'Try again');
  button.type = 'button'; button.addEventListener('click', retry);
  box.append(button); container.append(box);
}
function renderSnippet(text) {
  const p = node('p', 'snippet'); p.lang = 'lv';
  // Never insert source text as HTML. Only our marker pairs create mark elements.
  for (const part of text.split(/(⟦[^⟧]*⟧)/g)) {
    p.append(part.startsWith('⟦') && part.endsWith('⟧') ? node('mark', '', part.slice(1,-1)) : document.createTextNode(part));
  }
  return p;
}
function renderCard(item) {
  const card = node('article', 'result-card');
  const top = node('div', 'result-top');
  top.append(node('span', 'category', item.process_type || 'Uncategorized'), node('span', 'result-date', `Registered ${formatDate(item.registration_date)}`));
  const title = node('h3', 'result-title');
  const titleButton = node('button', '', item.case_number || item.application_number || 'Court decision');
  titleButton.type = 'button'; titleButton.addEventListener('click', () => openReader(item.id, item.match_page, true, titleButton)); title.append(titleButton);
  const bottom = node('div', 'result-bottom');
  const readButton = node('button', 'read-link', `Read decision · p. ${item.match_page} →`);
  readButton.type = 'button'; readButton.addEventListener('click', () => openReader(item.id, item.match_page, true, readButton));
  bottom.append(node('span', 'document-kind', item.material_type || 'Published decision'), readButton);
  card.append(top, title, node('p', 'result-court', [item.court, item.court_instance].filter(Boolean).join(' · ')), renderSnippet(item.snippet), bottom);
  return card;
}
function renderFilters() {
  const labels = {court:'Court',process_type:'Category',instance:'Instance',date_from:'From',date_to:'To'};
  const chips = $('#active-filters'); chips.replaceChildren();
  for (const [key,label] of Object.entries(labels)) {
    if (!state.get(key)) continue;
    const chip = node('button', 'filter-chip', `${label}: ${state.get(key)} ×`);
    chip.type='button'; chip.setAttribute('aria-label', `Remove ${label} filter`);
    chip.addEventListener('click', () => { state.delete(key); state.delete('page'); fillForm(); updateUrl(); runSearch(); });
    chips.append(chip);
  }
}
async function runSearch() {
  searchController?.abort();
  const controller = searchController = new AbortController();
  const results = $('#results');
  results.setAttribute('aria-busy','true'); results.replaceChildren();
  $('#pagination').hidden = true;
  $('#results-heading').textContent = state.get('q') ? 'Search results' : 'Browse decisions';
  $('#results-meta').textContent = 'Searching your local collection…';
  renderFilters();
  for(let i=0;i<3;i++) { const card=node('div','result-card'); card.setAttribute('aria-hidden','true'); for(let j=0;j<4;j++)card.append(node('div','loading-line')); results.append(card); }
  try {
    const params = new URLSearchParams(state); params.delete('decision');params.delete('document_page');
    const data = await api(`/api/search?${params}`, controller.signal);
    if (controller.signal.aborted) return;
    results.replaceChildren();
    const first = (data.page - 1) * data.page_size + 1;
    $('#results-meta').textContent = data.items.length ? `Showing ${first}–${first + data.items.length - 1}${data.has_more ? ' · More results available' : ''} · ${(data.elapsed_ms/1000).toFixed(2)} s` : 'No matching decisions';
    if (data.items.length) results.append(...data.items.map(renderCard));
    else { const empty=node('div','empty-state');empty.append(node('h3','','No decisions found'),node('p','','Try fewer words, a different word ending, or a wider date range. Use identifier mode for an exact case number or ECLI.'));results.append(empty); }
    $('#page-label').textContent = `Page ${data.page}${data.page === data.page_limit ? ' · Refine filters to see more' : ''}`;
    $('#previous').disabled = data.page <= 1; $('#next').disabled = !data.has_more;
    $('#pagination').hidden = !data.items.length && data.page <= 1;
  } catch(error) {
    if(error.name !== 'AbortError') { $('#results-meta').textContent='Search could not complete';displayError(results,error.message,runSearch); }
  } finally { if (!controller.signal.aborted) results.setAttribute('aria-busy','false'); }
}
async function loadCatalog() {
  try {
    const data = await api('/api/catalog');
    const stats = $('#collection-stats');stats.replaceChildren();
    stats.append(node('strong','',formatNumber(data.searchable)), document.createTextNode(' searchable decisions'), node('span','separator','/'),document.createTextNode(`${formatNumber(data.courts.length)} courts · ${formatNumber(data.decisions - data.searchable)} without text`));
    for (const [key,values] of [['court',data.courts],['process_type',data.process_types],['instance',data.instances]]) {
      const input=form.elements.namedItem(key);const selected=input.value;const first=input.options[0].cloneNode(true);input.replaceChildren(first);
      for(const value of values) input.add(new Option(value,value));
      if(selected && !values.includes(selected))input.add(new Option(selected,selected));
      input.value=selected;
    }
  } catch(error) { $('#collection-stats').textContent='Collection details unavailable. Check the database and refresh.'; }
}
async function openReader(id, page = 1, writeUrl = true, opener = null) {
  readerController?.abort();const controller=readerController=new AbortController();
  if(opener) readerOpener=opener;
  const dialog=$('#reader');if(!dialog.open) dialog.showModal();
  if(writeUrl) {state.set('decision',id);state.set('document_page',page);updateUrl();}
  currentDecision=null;
  $('#reader-title').textContent='Loading decision…';$('#reader-meta').replaceChildren();$('#reader-text').textContent='Loading source text…';$('#reader-error').textContent='';
  $('#page-back').disabled=true;$('#page-forward').disabled=true;$('#pdf-link').hidden=true;$('#document-page').textContent='';
  try {
    const data=await api(`/api/decisions/${encodeURIComponent(id)}?page=${page}`,controller.signal);
    if(controller.signal.aborted)return;
    currentDecision=data;$('#reader-title').textContent=data.case_number || data.application_number || 'Court decision';
    const meta=node('p','reader-meta',[data.court,data.court_instance,data.process_type,`Registered ${formatDate(data.registration_date)}`,data.ecli].filter(Boolean).join(' · '));$('#reader-meta').append(meta);
    $('#reader-text').textContent=data.text || 'No extracted text is available for this decision.';
    $('#document-page').textContent=`Page ${data.page} of ${data.page_count}`;
    $('#page-back').disabled=data.page<=1;$('#page-forward').disabled=data.page>=data.page_count;
    $('#pdf-link').hidden=!data.pdf_available;$('#pdf-link').href=`/api/decisions/${data.id}/pdf#page=${data.page}`;
    if(!data.pdf_available)$('#reader-error').textContent='The original PDF is not available locally.';
    dialog.scrollTop=0;
  }catch(error){if(error.name!=='AbortError'){$('#reader-title').textContent='Unable to open decision';$('#reader-text').textContent='';$('#reader-error').textContent=error.message;}}
}
form.addEventListener('submit',(event)=>{event.preventDefault();state=collectForm();updateUrl();runSearch();});
$('#sort').addEventListener('change',()=>form.requestSubmit());
$('#reset').addEventListener('click',()=>{for(const key of ['court','process_type','instance','date_from','date_to'])state.delete(key);state.delete('page');fillForm();updateUrl();runSearch();});
for(const [selector,delta] of [['#previous',-1],['#next',1]])$(selector).addEventListener('click',()=>{state.set('page',Number(state.get('page')||1)+delta);updateUrl();runSearch();$('#results-heading').scrollIntoView({block:'start'});});
$('#close-reader').addEventListener('click',()=>$('#reader').close());
$('#reader').addEventListener('close',()=>{readerController?.abort();if(state.has('decision')){state.delete('decision');state.delete('document_page');updateUrl(true);}readerOpener?.focus();});
for(const [selector,delta] of [['#page-back',-1],['#page-forward',1]])$(selector).addEventListener('click',()=>{if(currentDecision)openReader(currentDecision.id,currentDecision.page+delta);});
window.addEventListener('popstate',()=>{state=new URLSearchParams(location.search);fillForm();runSearch();if(state.has('decision'))openReader(state.get('decision'),Number(state.get('document_page')||1),false);else $('#reader').close();});
fillForm();loadCatalog();runSearch();
if(state.has('decision'))openReader(state.get('decision'),Number(state.get('document_page')||1),false);
