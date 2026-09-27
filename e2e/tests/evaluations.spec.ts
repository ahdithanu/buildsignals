import { test, expect, type Page } from '@playwright/test';
import { registerAndLogin, uniqueEmail } from './helpers';

async function expectNoHorizontalOverflow(page: Page) {
  // Check the scrolling app container too: the document alone can hide overflow.
  await expect.poll(() => page.evaluate(() => {
    const main = document.querySelector('main');
    return document.documentElement.scrollWidth <= window.innerWidth
      && !!main && main.scrollWidth <= main.clientWidth;
  })).toBe(true);
}

test('admin seeds examples, inspects replay evidence, and compares persisted runs on desktop and mobile', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 1000 });

  await test.step('register an isolated organization and use desktop admin navigation', async () => {
    await registerAndLogin(page, uniqueEmail());
    await page.getByRole('button', { name: 'Admin', exact: true }).click();
    await page.getByRole('menuitem', { name: 'AI Evaluations', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/evals$/);
    await expect(page.getByRole('heading', { name: 'Evaluations', exact: true })).toBeVisible();
    await expect(page.getByText('No evaluation datasets yet', { exact: true })).toBeVisible();
    await expect(page.getByText(/Replay evaluates supplied outputs; it does not invoke an LLM/)).toBeVisible();
  });

  await test.step('seed real synthetic datasets without duplicating them', async () => {
    const seed = page.getByRole('button', { name: 'Seed four synthetic examples' });
    const datasets = page.getByLabel('Dataset', { exact: true });
    await seed.click();
    await expect(datasets.locator('option')).toHaveCount(4);
    await expect(page.getByText('No runs yet', { exact: true })).toBeVisible();
    await seed.click();
    await expect(seed).toBeEnabled();
    await page.reload();
    await expect(datasets.locator('option')).toHaveCount(4);
    await datasets.selectOption({ label: 'Example: copilot_answer (Copilot answer)' });
    await expect(page.getByRole('heading', { name: 'Example: copilot_answer', exact: true })).toBeVisible();
  });

  const inspect = page.getByLabel('Inspect run', { exact: true });
  const replay = page.getByRole('button', { name: 'Run example replay', exact: true });
  let baselineId: string;
  let candidateId: string;

  await test.step('run a real replay and inspect evidence and unknown telemetry', async () => {
    await replay.click();
    await expect(page.getByText('Gate: passed', { exact: true })).toBeVisible();
    await expect(inspect.locator('option')).toHaveCount(1);
    await expect(inspect.locator('option:checked')).toHaveText(/fixture \/ example-v1 \| replay \| completed \|/);
    baselineId = await inspect.inputValue();
    expect(baselineId).not.toBe('');

    const result = page.getByRole('article').filter({
      has: page.getByRole('heading', { name: 'Evidence-grounded response', exact: true }),
    });
    await expect(result).toHaveCount(1);
    for (const label of ['Expected output / rubric', 'Actual output', 'Retrieved context', 'Citations']) {
      await expect(result.getByRole('heading', { name: label, exact: true })).toBeVisible();
    }
    const actualOutput = result.getByRole('heading', { name: 'Actual output', exact: true })
      .locator('..').locator('pre');
    await expect(actualOutput).toContainText('Verify the construction schedule');
    await expect(actualOutput).toContainText('fixture:cedar');
    await expect(page.getByText(/Confidence metrics are heuristic, not calibrated probabilities/)).toBeVisible();
    for (const label of ['Input tokens', 'Output tokens', 'Cost (USD)', 'Latency (ms)']) {
      const metric = result.locator('dl > div').filter({ has: page.locator('dt', { hasText: label }) });
      await expect(metric.locator('dd')).toHaveText('Unknown');
    }
    await expect(page.getByText(/Null usage is unknown, never zero/)).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  await test.step('persist a second replay and compare it with the baseline', async () => {
    await replay.click();
    await expect(inspect.locator('option')).toHaveCount(2);
    await expect(inspect).not.toHaveValue(baselineId);
    candidateId = await inspect.inputValue();
    expect(candidateId).not.toBe('');

    await page.reload();
    await page.getByLabel('Dataset', { exact: true }).selectOption({ label: 'Example: copilot_answer (Copilot answer)' });
    await expect(inspect.locator('option')).toHaveCount(2);
    await inspect.selectOption(baselineId);
    await expect(page.getByText('Gate: passed', { exact: true })).toBeVisible();
    await page.getByLabel('Baseline run', { exact: true }).selectOption(baselineId);
    await page.getByLabel('Candidate run', { exact: true }).selectOption(candidateId);
    await page.getByRole('button', { name: 'Compare runs', exact: true }).click();
    await expect(page.getByText('Comparable runs', { exact: true })).toBeVisible();
    await expect(page.getByText('Candidate gate: passed', { exact: true })).toBeVisible();
    await expect(page.getByText('No pass-to-fail gate regression.', { exact: true })).toBeVisible();
    await expect(page.getByText('Regressed cases: None', { exact: true })).toBeVisible();
    const comparison = page.locator('[aria-live="polite"]').filter({ hasText: 'Comparable runs' });
    const deltas = comparison.locator('dd');
    expect(await deltas.count()).toBeGreaterThan(0);
    await expect(deltas).toHaveText(Array(await deltas.count()).fill('0.000'));
    await expectNoHorizontalOverflow(page);
    await page.getByRole('heading', { name: 'Evaluations', exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('evaluations-desktop.png'), fullPage: true });
  });

  await test.step('navigate through the mobile account menu and compare without overflow', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.getByRole('button', { name: 'Account menu', exact: true }).click();
    await page.getByRole('menuitem', { name: 'AI Evaluations', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/evals$/);
    await expect(page.getByRole('heading', { name: 'Evaluations', exact: true })).toBeVisible();
    await page.getByLabel('Dataset', { exact: true }).selectOption({ label: 'Example: copilot_answer (Copilot answer)' });
    await expect(inspect.locator('option')).toHaveCount(2);
    await expect(page.getByText('Gate: passed', { exact: true })).toBeVisible();
    await page.getByLabel('Baseline run', { exact: true }).selectOption(baselineId);
    await page.getByLabel('Candidate run', { exact: true }).selectOption(baselineId);
    await expect(page.getByText('Choose two different runs.', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Compare runs', exact: true })).toBeDisabled();
    await page.getByLabel('Candidate run', { exact: true }).selectOption(candidateId);
    await page.getByRole('button', { name: 'Compare runs', exact: true }).click();
    await expect(page.getByText('Comparable runs', { exact: true })).toBeVisible();
    await expect(page.getByText('Regressed cases: None', { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.getByRole('article').getByRole('heading', { name: 'Actual output', exact: true })
      .locator('..').screenshot({ path: testInfo.outputPath('evaluations-mobile-evidence.png') });
    await page.getByRole('article').locator('dl').last()
      .screenshot({ path: testInfo.outputPath('evaluations-mobile-telemetry.png') });
    await page.locator('[aria-live="polite"]').filter({ hasText: 'Comparable runs' })
      .screenshot({ path: testInfo.outputPath('evaluations-mobile-comparison.png') });
    await page.getByRole('heading', { name: 'Evaluations', exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('evaluations-mobile-overview.png') });
    await page.screenshot({ path: testInfo.outputPath('evaluations-mobile.png'), fullPage: true });
  });
});
