/* All evidence is already in this document; no network or runtime dependencies. */
(() => {
  'use strict';
  const controls = document.getElementById('finding-controls');
  const search = document.getElementById('finding-search');
  const pageFilter = document.getElementById('finding-page');
  const outcome = document.getElementById('finding-outcome');
  const status = document.getElementById('finding-count');
  const normalize = text => text.replace(/\s+/g, ' ').trim().toLocaleLowerCase();
  const rows = [...document.querySelectorAll('#findings > tbody > tr')].map(row => {
    const locations = [...row.querySelectorAll('[data-evidence-location]')].map(element => ({
      element, text: element.textContent.replace(/\s+/g, ' ').trim(),
      label: element.dataset.evidenceLocation,
      page: element.closest('[data-page-decision]')?.dataset.page,
    }));
    const overview = [...row.children].slice(0, -1).map(cell => cell.textContent).join(' ');
    return {row, locations, decisions: [...row.querySelectorAll('[data-page-decision]')],
      selected: row.querySelector('[data-selected-page-result]'),
      overview: normalize(overview), matches: row.querySelector('[data-search-matches]')};
  });
  function matchesOutcome(data) {
    const llm = data.llm === 'Caught';
    const programmatic = data.programmatic === 'Caught';
    switch (outcome.value) {
      case 'llm-caught': return llm;
      case 'llm-missed': return data.expected === 'LLM' && !llm;
      case 'programmatic-caught': return programmatic;
      case 'programmatic-missed': return data.expected === 'Programmatic checks' && !programmatic;
      case 'overall-caught': return llm || programmatic;
      case 'overall-missed': return !llm && !programmatic;
      case 'not-testable': return data.expected === 'Not testable from the page file';
      default: return true;
    }
  }
  function update() {
    const query = normalize(search.value);
    const selectedPage = pageFilter?.value || '';
    let count = 0;
    for (const item of rows) {
      const pageDecision = selectedPage ? item.decisions.find(panel => panel.dataset.page === selectedPage) : null;
      const matches = query ? item.locations.filter(location =>
        (!selectedPage || !location.page || location.page === selectedPage) && normalize(location.text).includes(query)) : [];
      item.row.hidden = Boolean((selectedPage && !pageDecision) ||
        !matchesOutcome(pageDecision?.dataset || item.row.dataset) ||
        (query && !matches.length && !item.overview.includes(query)));
      item.selected.hidden = !selectedPage || !pageDecision;
      item.selected.textContent = pageDecision ? `Selected page: ${selectedPage}. Expected source: ${pageDecision.dataset.expected}. LLM: ${pageDecision.dataset.llm}. Programmatic checks: ${pageDecision.dataset.programmatic}. Combined results remain in the overview columns.` : '';
      for (const panel of item.decisions) panel.hidden = Boolean(selectedPage && panel.dataset.page !== selectedPage);
      for (const tr of item.row.querySelectorAll('[data-page-table-row]')) tr.hidden = Boolean(selectedPage && tr.dataset.pageTableRow !== selectedPage);
      item.matches.replaceChildren();
      if (!item.row.hidden) count++;
      if (item.row.hidden || !query) continue;
      for (const match of matches) {
        const start = Math.max(0, normalize(match.text).indexOf(query) - 35);
        const excerpt = match.text.slice(start, start + Math.max(160, query.length + 35));
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = `Show match in ${match.label}: ${start ? '…' : ''}${excerpt}`;
        button.addEventListener('click', () => {
          const panel = match.element.closest('details');
          for (let ancestor = panel; ancestor; ancestor = ancestor.parentElement.closest('details')) ancestor.open = true;
          panel.querySelector('summary').focus();
        });
        item.matches.append(button);
      }
    }
    status.textContent = `Filtered findings: ${count} of ${rows.length} original Human findings.${count ? '' : ' No matching findings.'} Complete-run detection results are unchanged.`;
  }
  search.addEventListener('input', update);
  pageFilter?.addEventListener('change', update);
  outcome.addEventListener('change', update);
  document.getElementById('clear-filters').addEventListener('click', () => {
    search.value = '';
    if (pageFilter) pageFilter.value = '';
    outcome.value = 'all';
    update();
  });
  for (const [id, open] of [['expand-visible', true], ['collapse-visible', false]]) {
    document.getElementById(id).addEventListener('click', () => {
      for (const {row} of rows) {
        if (row.hidden) continue;
        for (const panel of row.querySelectorAll('details')) {
          if (!panel.closest('[hidden]')) panel.open = open;
        }
      }
    });
  }
  update();
  controls.hidden = false;
})();
