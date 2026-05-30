import { expect, test } from '@playwright/test';

const viewports = [
  { name: 'mobile', width: 375, height: 812 },
  { name: 'tablet', width: 768, height: 900 },
  { name: 'desktop', width: 1280, height: 900 },
] as const;

for (const viewport of viewports) {
  test(`auth page renders cleanly at ${viewport.name}`, async ({ page }) => {
    const consoleIssues: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error' || message.type() === 'warning') {
        consoleIssues.push(message.text());
      }
    });

    await page.setViewportSize(viewport);
    await page.goto('/');
    await expect(page.getByText('把混乱目标安静整理成学习地图。')).toBeVisible();
    await expect(page.getByRole('button', { name: '进入系统' })).toBeVisible();
    await page.screenshot({ path: `test-results/auth-${viewport.name}.png`, fullPage: true });
    expect(consoleIssues).toEqual([]);
  });
}

test('mock oauth flow shows authorization panel then success', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /学习通登录/ }).click();
  await expect(page.getByRole('dialog', { name: '模拟授权' })).toBeVisible();
  await expect(page.getByText('思绪已对齐')).toBeVisible();
});

test('reduced motion disables active animations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const animationCount = await page.locator('.agent-hero').evaluate((element) => {
    return element.getAnimations({ subtree: true }).length;
  });

  expect(animationCount).toBe(0);
});

test('dark mode uses dark material tokens', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  const glassToken = await page.evaluate(() => {
    return getComputedStyle(document.documentElement).getPropertyValue('--glass-bg').trim();
  });

  expect(glassToken).toContain('21%');
  await expect(page.getByText('欢迎回来')).toBeVisible();
});
