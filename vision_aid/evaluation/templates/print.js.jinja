/* Native printing uses embedded evidence only; review data and scores stay saved. */
(() => {
  'use strict';
  const button = document.getElementById('print-complete-report');
  const printMedia = window.matchMedia('print');
  let readingState = null;
  let pendingFocus = null;
  function restoreFocus() {
    if (!pendingFocus || printMedia.matches) return;
    const {focused, scrollX, scrollY} = pendingFocus;
    pendingFocus = null;
    if (focused?.isConnected) focused.focus({preventScroll: true});
    window.scrollTo(scrollX, scrollY);
  }
  printMedia.addEventListener('change', restoreFocus);
  function restore() {
    if (!readingState) return;
    const {hidden, disclosures, focused, scrollX, scrollY} = readingState;
    readingState = null;
    for (const [element, value] of hidden) element.hidden = value;
    for (const [element, value] of disclosures) element.open = value;
    pendingFocus = {focused, scrollX, scrollY};
    restoreFocus();
  }
  button.addEventListener('click', () => {
    if (readingState) return;
    const elements = [...document.querySelectorAll(
      '#findings > tbody > tr, [data-page-decision], [data-page-table-row]')];
    const details = [...document.querySelectorAll('details')];
    readingState = {
      hidden: elements.map(element => [element, element.hidden]),
      disclosures: details.map(element => [element, element.open]),
      focused: document.activeElement, scrollX: window.scrollX, scrollY: window.scrollY,
    };
    for (const element of elements) element.hidden = false;
    for (const element of details) element.open = true;
    try {
      window.print();
    } catch (error) {
      restore();
      throw error;
    }
  });
  // Browsers send the same notification on completion and cancellation.
  window.addEventListener('afterprint', restore);
  button.hidden = false;
})();
