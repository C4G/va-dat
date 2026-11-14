/* Print styling limits output to the report header, cost and detection charts. */
(() => {
  'use strict';
  const button = document.getElementById('print-report');
  const printMedia = window.matchMedia('print');
  let readingState = null;
  function restoreFocus() {
    if (!readingState || printMedia.matches) return;
    const {focused, scrollX, scrollY} = readingState;
    readingState = null;
    if (focused?.isConnected) focused.focus({preventScroll: true});
    window.scrollTo(scrollX, scrollY);
  }
  printMedia.addEventListener('change', restoreFocus);
  window.addEventListener('afterprint', restoreFocus);
  button.addEventListener('click', () => {
    if (readingState) return;
    readingState = {
      focused: document.activeElement, scrollX: window.scrollX, scrollY: window.scrollY,
    };
    try {
      window.print();
    } catch (error) {
      restoreFocus();
      throw error;
    }
  });
  button.hidden = false;
})();
