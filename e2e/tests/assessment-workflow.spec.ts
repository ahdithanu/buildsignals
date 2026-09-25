import { execFile } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { test, expect } from '@playwright/test';

const run = promisify(execFile);

test('multi-entity assessment lifecycle and history on mobile, tablet and desktop', async ({}, testInfo) => {
  test.setTimeout(240_000);
  const artifactDir = testInfo.outputPath('assessment-workflow');
  const { stdout } = await run(process.execPath, [fileURLToPath(new URL('../../scripts/verify_assessment_workflow.cjs', import.meta.url))], {
    env: {
      ...process.env,
      ASSESSMENT_TEST_API: 'http://localhost:8000/v1',
      ASSESSMENT_TEST_WEB: 'http://localhost:8080',
      ASSESSMENT_ARTIFACT_DIR: artifactDir,
    },
    timeout: 230_000,
  });
  for (const width of [390, 768, 1440]) {
    expect(stdout).toContain(`PASS ${width}px`);
    for (const name of ['composer', 'published', 'history', 'settings']) {
      await testInfo.attach(`${name}-${width}`, { path: path.join(artifactDir, `${name}-${width}.png`), contentType: 'image/png' });
    }
  }
});
