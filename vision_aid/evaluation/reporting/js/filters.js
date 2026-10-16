/* All evidence is already in this document; no network or runtime dependencies. */
(() => {
  'use strict';
  const controls = document.getElementById('finding-controls');
  const pageFilter = document.getElementById('finding-page');
  const outcome = document.getElementById('finding-outcome');
  const status = document.getElementById('finding-count');
  const rows = [...document.querySelectorAll('#findings > tbody > tr')].map(row => {
    return {row, decisions: [...row.querySelectorAll('[data-page-decision]')],
      selected: row.querySelector('[data-selected-page-result]')};
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
    const selectedPage = pageFilter?.value || '';
    let count = 0;
    for (const item of rows) {
      const pageDecision = selectedPage ? item.decisions.find(panel => panel.dataset.page === selectedPage) : null;
      item.row.hidden = Boolean((selectedPage && !pageDecision) ||
        !matchesOutcome(pageDecision?.dataset || item.row.dataset));
      item.selected.hidden = !selectedPage || !pageDecision;
      item.selected.textContent = pageDecision ? `Selected page: ${selectedPage}. Expected source: ${pageDecision.dataset.expected}. LLM: ${pageDecision.dataset.llm}. Programmatic checks: ${pageDecision.dataset.programmatic}. Combined results remain in the overview columns.` : '';
      for (const panel of item.decisions) panel.hidden = Boolean(selectedPage && panel.dataset.page !== selectedPage);
      for (const tr of item.row.querySelectorAll('[data-page-table-row]')) tr.hidden = Boolean(selectedPage && tr.dataset.pageTableRow !== selectedPage);
      if (!item.row.hidden) count++;
    }
    status.textContent = `Filtered findings: ${count} of ${rows.length} original Human findings.${count ? '' : ' No matching findings.'}`;
  }
  pageFilter?.addEventListener('change', update);
  outcome.addEventListener('change', update);
  document.getElementById('clear-filters').addEventListener('click', () => {
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
