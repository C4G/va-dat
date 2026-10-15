/* Browser checks observe CLI-generated documents, never a template/helper API. */
const assert = require('node:assert/strict');
const path = require('node:path');
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
      const visibleTitles = () => page.locator('#findings > tbody > tr:visible > th').allTextContents();
      if (behavior === 'search') {
        assert.equal(await rows.locator('details[open]').count(), 0);
        const search = page.getByLabel('Search findings and evidence');
        await search.fill('Complete Global on home');
        assert.deepEqual(await visibleTitles(), ['Shared defect']);
        assert.equal(await search.evaluate(e => document.activeElement === e), true);
        const match = page.getByRole('button', {name: /Show match in.*Complete Global on home/});
        assert.equal(await match.count(), 1);
        assert.match(await match.textContent(), /https:\/\/example.test\//);
        await match.click();
        const global = rows.filter({has: page.getByRole('rowheader', {name: 'Shared defect', exact: true})});
        assert.equal(await global.locator('details[open]').count(), filename === fullFile ? 2 : 1);
        if (filename === fullFile) {
          await search.fill('Complete Global on another page');
          const pageMatches = page.getByRole('button', {name: /Show match in.*Complete Global on another page/});
          assert.equal(await pageMatches.count(), 2);
          await pageMatches.nth(0).click();
          await pageMatches.nth(1).click();
          assert.equal(await global.locator('details details[open]').count(), 3);
        }
        await search.fill('Synthetic failure');
        assert.deepEqual(await visibleTitles(), filename === fullFile ? ['First local', 'Second local', 'Shared defect'] : ['First local', 'Second local']);
        assert.ok(await page.getByRole('button', {name: /Show match in.*Synthetic failure/}).count());
        await search.fill('Original evidence');
        assert.equal(await rows.filter({visible: true}).count(), filename === fullFile ? 5 : 4);
        assert.ok(await page.getByRole('button', {name: /Show match in Original Human finding/}).count());
        await search.fill('does-not-appear-in-any-evidence');
        assert.equal(await rows.filter({visible: true}).count(), 0);
        assert.match(await page.getByRole('status').textContent(), /No matching findings/);
        await page.getByRole('button', {name: 'Clear filters', exact: true}).click();
        assert.equal(await rows.filter({visible: true}).count(), filename === fullFile ? 8 : 7);
      }
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
          await page.getByLabel('Search findings and evidence').fill('Complete Global on another page');
          assert.deepEqual(await visibleTitles(), []);
          await page.getByLabel('Search findings and evidence').fill('Complete Global on home');
          assert.deepEqual(await visibleTitles(), ['Shared defect']);
          await page.getByLabel('Search findings and evidence').fill('');
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
        const search = page.getByLabel('Search findings and evidence');
        await search.fill('Shared defect');
        if (filename === fullFile) await page.getByLabel('Page', {exact: true}).selectOption({label: 'https://example.test/'});
        const expand = page.getByRole('button', {name: 'Expand all visible evidence', exact: true});
        await expand.focus();
        await page.keyboard.press('Enter');
        assert.equal(await expand.evaluate(e => document.activeElement === e), true);
        assert.equal(await rows.locator('details[open]').count(), filename === fullFile ? 2 : 1);
        // Clearing expands neither the formerly hidden rows nor other page panels.
        await page.getByRole('button', {name: 'Clear filters', exact: true}).click();
        assert.equal(await rows.locator('details[open]').count(), filename === fullFile ? 2 : 1);
        await page.getByRole('button', {name: 'Collapse all visible evidence', exact: true}).click();
        assert.equal(await rows.locator('details[open]').count(), 0);
        await expand.click();
        assert.equal(await rows.locator('details:not([open])').count(), 0);
        if (filename === fullFile) {
          const global = rows.filter({has: page.getByRole('rowheader', {name: 'Shared defect', exact: true})});
          const summaries = global.locator('details details > summary');
          await summaries.nth(0).click();
          assert.equal(await global.locator('details details[open]').count(), 2);
          await summaries.nth(0).click();
          assert.equal(await global.locator('details details[open]').count(), 3);
        }
      }
      assert.deepEqual(requests, []);
      assert.deepEqual(errors, []);
      await context.close();
      if (behavior === 'disclosures') {
        const nojs = await browser.newContext({offline: true, javaScriptEnabled: false});
        const plain = await nojs.newPage();
        await plain.goto(pathToFileURL(filename).href);
        assert.equal(await plain.getByLabel('Search findings and evidence').isVisible(), false);
        assert.equal(await plain.locator('#findings > tbody > tr:visible').count(), filename === fullFile ? 8 : 7);
        const global = plain.locator('#findings > tbody > tr').filter({has: plain.getByRole('rowheader', {name: 'Shared defect', exact: true})});
        await global.locator('summary').first().focus();
        await plain.keyboard.press('Enter');
        assert.equal(await global.locator('details[open]').count(), 1);
        if (filename === fullFile) {
          for (const n of [0, 1]) {
            await global.locator('details details > summary').nth(n).focus();
            await plain.keyboard.press('Enter');
          }
          assert.equal(await global.locator('details[open]').count(), 3);
        }
        await nojs.close();
      }
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
