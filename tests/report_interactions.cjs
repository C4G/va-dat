/* Browser checks observe CLI-generated documents, never a template/helper API. */
const assert = require('node:assert/strict');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const {chromium} = require(path.join(process.env.REPORT_BROWSER_MODULES, 'playwright'));
const [behavior, fullFile, pageFile] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.REPORT_BROWSER_EXECUTABLE});
  try {
    for (const filename of [fullFile, pageFile]) {
      const context = await browser.newContext({offline: true});
      const page = await context.newPage();
      page.setDefaultTimeout(3000);
      const requests = [];
      page.on('request', request => {if (!request.url().startsWith('file:')) requests.push(request.url());});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(pathToFileURL(filename).href);
      const rows = page.locator('#findings > tbody > tr');
      assert.equal(await page.locator('#finding-controls').isVisible(), true);
      assert.equal(await page.locator('input[type=search], #finding-search, [data-search-matches]').count(), 0);
      assert.equal(await page.locator('#finding-controls legend').textContent(), 'Filter findings');
      const cost = page.locator('#performance .run-cost');
      assert.equal(await cost.isVisible(), true);
      assert.match(await cost.textContent(), /Estimated run cost:\$0\.\d{6} USD/);
      assert.equal(await page.locator('#provenance, a[href="#provenance"]').count(), 0);
      assert.ok((await cost.boundingBox()).y < (await page.locator('.detection-chart').first().boundingBox()).y);
      await page.setViewportSize({width: 320, height: 800});
      const costBox = await cost.boundingBox();
      assert.ok(costBox.x >= 0 && costBox.x + costBox.width <= 320);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 320));
      const findingsRegion = page.locator('.findings-panel > .table-scroll');
      assert.ok(await findingsRegion.evaluate(e => e.scrollWidth > e.clientWidth));
      const firstSummary = rows.first().locator('summary').first();
      assert.ok((await firstSummary.boundingBox()).width >= 200);
      await findingsRegion.focus();
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction(() => document.querySelector('.findings-panel > .table-scroll').scrollLeft > 0);
      await findingsRegion.evaluate(e => {e.scrollLeft = 0;});
      await page.setViewportSize({width: 1280, height: 900});
      const visibleTitles = () => page.locator('#findings > tbody > tr:visible > th').allTextContents();
      if (behavior === 'filters') {
        const performance = await page.locator('#performance').textContent();
        const outcome = page.getByLabel('Detection outcome', {exact: true});
        const count = page.getByRole('status');
        await outcome.selectOption({label: 'LLM missed (LLM eligible)'});
        assert.deepEqual(await visibleTitles(), filename === fullFile ? ['Contact local', 'Partial across pages'] : ['Shared defect', 'Partial across pages']);
        await outcome.focus();
        await page.keyboard.press('Home');
        await page.keyboard.press('End');
        assert.equal(await outcome.evaluate(e => document.activeElement === e), true);
        // Explicit catches include cross-catches irrespective of expected source.
        await outcome.selectOption({label: 'LLM caught (any eligibility)'});
        assert.deepEqual(await visibleTitles(), filename === fullFile ? ['First local', 'Second local', 'Shared defect'] : ['First local', 'Second local']);
        assert.match(await count.textContent(), /Filtered findings: (2|3) of (7|8)/);
        assert.equal(await count.getAttribute('aria-live'), 'polite');
        if (filename === fullFile) {
          const pageFilter = page.getByLabel('Page', {exact: true});
          await pageFilter.selectOption({label: 'https://example.test/'});
          await outcome.selectOption({label: 'LLM missed (LLM eligible)'});
          assert.deepEqual(await visibleTitles(), ['Shared defect', 'Partial across pages']);
          const shared = rows.filter({has: page.getByRole('rowheader', {name: 'Shared defect', exact: true})});
          const selected = shared.getByText(/Selected page:/);
          assert.match(await selected.textContent(), /https:\/\/example.test\/.*LLM: Not caught.*Programmatic checks: Caught/);
          assert.match(await shared.locator(':scope > td').nth(3).textContent(), /Caught/);
          await pageFilter.selectOption({label: 'https://example.test/contact/'});
          assert.deepEqual(await visibleTitles(), ['Contact local', 'Partial across pages']);
          await outcome.selectOption({label: 'Programmatic missed (Programmatic eligible)'});
          assert.deepEqual(await visibleTitles(), ['Eligible uncaught']);
          await pageFilter.selectOption({label: 'https://example.test/'});
          assert.deepEqual(await visibleTitles(), ['Second local', 'Joint catch']);
          await outcome.selectOption({label: 'Not testable from the page file'});
          assert.deepEqual(await visibleTitles(), ['Shared second defect', 'Eligible uncaught']);
        }
        assert.equal(await page.locator('#performance').textContent(), performance);
        await page.getByRole('button', {name: 'Clear filters', exact: true}).click();
        assert.equal(await rows.filter({visible: true}).count(), filename === fullFile ? 8 : 7);
        assert.equal(await page.getByRole('button', {name: 'Clear filters', exact: true}).evaluate(e => document.activeElement === e), true);
      }
      if (behavior === 'disclosures') {
        for (const row of await rows.all()) {
          const title = await row.locator(':scope > th').textContent();
          const summary = row.locator('summary').first();
          assert.equal(await summary.textContent(), 'View details');
          assert.equal(await summary.getAttribute('aria-label'), `View details: ${title}`);
          await summary.click();
          const decisionSummaries = row.locator('[data-page-decision] > summary');
          for (const decisionSummary of await decisionSummaries.all()) {
            const visibleName = await decisionSummary.textContent();
            assert.equal(await decisionSummary.getAttribute('aria-label'), `${visibleName} for ${title}`);
          }
          await summary.click();
        }
        await page.getByLabel('Detection outcome', {exact: true}).selectOption({label: 'Programmatic caught (any eligibility)'});
        if (filename === fullFile) await page.getByLabel('Page', {exact: true}).selectOption({label: 'https://example.test/'});
        const expand = page.getByRole('button', {name: 'Expand all dropdowns', exact: true});
        await expand.focus();
        await page.keyboard.press('Enter');
        assert.equal(await expand.evaluate(e => document.activeElement === e), true);
        assert.equal(await rows.locator('details[open]').count(), 2);
        // Clearing expands neither the formerly hidden rows nor other page panels.
        await page.getByRole('button', {name: 'Clear filters', exact: true}).click();
        assert.equal(await rows.locator('details[open]').count(), 2);
        await page.getByRole('button', {name: 'Collapse all dropdowns', exact: true}).click();
        assert.equal(await rows.locator('details[open]').count(), 0);
        const local = rows.filter({has: page.getByRole('rowheader', {name: 'First local', exact: true})});
        await local.locator('summary').first().click();
        assert.equal(await local.locator('.matched').first().isVisible(), false);
        const localPageSummary = local.locator('details details > summary');
        assert.equal(await localPageSummary.count(), 1);
        await localPageSummary.focus();
        await page.keyboard.press('Enter');
        assert.equal(await local.locator('.matched').first().isVisible(), true);
        await expand.click();
        assert.equal(await rows.locator('details:not([open])').count(), 0);
        await page.setViewportSize({width: 320, height: 800});
        const evidenceBox = await local.locator('.evidence').boundingBox();
        assert.ok(evidenceBox.width >= 200 && evidenceBox.width <= 294);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 320));
        await page.setViewportSize({width: 1280, height: 900});
        if (filename === fullFile) {
          const global = rows.filter({has: page.getByRole('rowheader', {name: 'Shared defect', exact: true})});
          const summaries = global.locator('details details > summary');
          await summaries.nth(0).click();
          assert.equal(await global.locator('details details[open]').count(), 2);
          await summaries.nth(0).click();
          assert.equal(await global.locator('details details[open]').count(), 3);
        }
      }
      if (behavior === 'print') {
        const print = page.getByRole('button', {name: 'Print report', exact: true});
        assert.equal(await print.count(), 1);
        // Preserve an uneven mixture of independently opened nested disclosures.
        await rows.nth(0).locator('summary').first().click();
        if (filename === fullFile) {
          const shared = rows.filter({has: page.getByRole('rowheader', {name: 'Shared defect', exact: true})});
          await shared.locator('summary').first().click();
          await shared.locator('details details > summary').nth(0).click();
          await shared.locator('details details > summary').nth(2).click();
          await page.getByLabel('Page', {exact: true}).selectOption({label: 'https://example.test/'});
        }
        await page.getByLabel('Detection outcome', {exact: true}).selectOption({label: 'LLM missed (LLM eligible)'});
        // Browser printing and the button share the summary-only layout.
        await page.emulateMedia({media: 'print'});
        assert.equal(await page.locator('#performance').isVisible(), true);
        assert.equal(await page.locator('#human-findings').isVisible(), false);
        assert.equal(await page.locator('#method').isVisible(), false);
        await page.emulateMedia({media: 'screen'});
        const originalEvidence = await page.locator('main').textContent();
        const savedState = () => page.evaluate(() => ({
          hidden: [...document.querySelectorAll('#findings tr, [data-page-decision]')].map(e => e.hidden),
          open: [...document.querySelectorAll('details')].map(e => e.open),
          values: [...document.querySelectorAll('input, select')].map(e => e.value),
          status: document.getElementById('finding-count').textContent,
          focused: document.activeElement.id,
        }));
        // Headless Chromium cannot operate native preview or distinguish its
        // completion/cancellation. Simulate those browser lifecycle notifications
        // and separately inspect a real Chromium PDF before restoring the state.
        await page.evaluate(() => {window.print = () => window.dispatchEvent(new Event('beforeprint'));});
        for (const result of ['completed', 'cancelled']) {
          await print.focus();
          const before = await savedState();
          await page.keyboard.press('Enter');
          assert.deepEqual(await savedState(), before, 'Print action preserves reading state');
          await page.emulateMedia({media: 'print'});
          assert.equal(await print.isVisible(), false);
          assert.equal(await page.locator('#performance').isVisible(), true);
          assert.equal(await page.locator('#human-findings').isVisible(), false);
          assert.equal(await page.locator('#method').isVisible(), false);
          assert.equal(await page.locator('#combined-method:visible').count(), 0);
          if (result === 'completed') {
            const pdf = path.join(path.dirname(filename), `${path.basename(filename)}.pdf`);
            await page.pdf({path: pdf, format: 'A4', printBackground: true});
            const text = execFileSync('pdftotext', ['-layout', pdf, '-'], {encoding: 'utf8'}).replace(/\s+/g, ' ');
            for (const expected of ['Detection overview', 'Review decisions by: Combined reviewer',
              'Estimated run cost:', await cost.locator('.cost-value').textContent()]) {
              assert.ok(text.includes(expected), `PDF includes ${expected}`);
            }
            if (filename === fullFile) assert.ok(text.includes('LLM detection by page'));
            const compactText = text.replace(/\s+/g, '');
            for (const value of await page.locator('.chart-value').allTextContents()) {
              assert.ok(compactText.includes(value.replace(/\s+/g, '')), `PDF includes chart value ${value}`);
            }
            for (const omitted of ['Tool Findings and Human Finding Matches', 'Original Human finding',
              'Matching rationale', 'Long evidence begins.', 'Long evidence ends.', 'Page decisions',
              'How to read this report', 'Full evaluation scoring']) {
              assert.ok(!text.includes(omitted), `PDF omits ${omitted}`);
            }
          }
          await page.emulateMedia({media: 'screen'});
          await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
          assert.deepEqual(await savedState(), before, `${result} restores reading state`);
          assert.equal(await page.locator('main').textContent(), originalEvidence);
        }
      }
      assert.deepEqual(requests, []);
      assert.deepEqual(errors, []);
      await context.close();
      if (behavior === 'disclosures' || behavior === 'print') {
        const nojs = await browser.newContext({offline: true, javaScriptEnabled: false});
        const plain = await nojs.newPage();
        await plain.goto(pathToFileURL(filename).href);
        assert.equal(await plain.locator('#finding-controls').isVisible(), false);
        assert.equal(await plain.getByRole('button', {name: 'Print report', exact: true}).isVisible(), false);
        assert.equal(await plain.locator('#findings > tbody > tr:visible').count(), filename === fullFile ? 8 : 7);
        const global = plain.locator('#findings > tbody > tr').filter({has: plain.getByRole('rowheader', {name: 'Shared defect', exact: true})});
        await global.locator('summary').first().focus();
        await plain.keyboard.press('Enter');
        assert.equal(await global.locator('details[open]').count(), 1);
        for (const n of filename === fullFile ? [0, 1] : [0]) {
          await global.locator('details details > summary').nth(n).focus();
          await plain.keyboard.press('Enter');
        }
        assert.equal(await global.locator('details[open]').count(), filename === fullFile ? 3 : 2);
        if (behavior === 'print') {
          const pdf = path.join(path.dirname(filename), `${path.basename(filename)}-nojs.pdf`);
          await plain.pdf({path: pdf, format: 'A4'});
          const text = execFileSync('pdftotext', ['-layout', pdf, '-'], {encoding: 'utf8'}).replace(/\s+/g, ' ');
          for (const expected of ['Detection overview', 'Estimated run cost:']) {
            assert.ok(text.includes(expected), `Basic no-JavaScript PDF includes ${expected}`);
          }
          for (const omitted of ['Shared defect', 'Eligibility classification', 'Complete Global on home', 'How to read this report']) {
            assert.ok(!text.includes(omitted), `Basic no-JavaScript PDF omits ${omitted}`);
          }
        }
        await nojs.close();
      }
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
