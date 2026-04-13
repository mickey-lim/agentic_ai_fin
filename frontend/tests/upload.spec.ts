import { test, expect } from '@playwright/test';
import * as path from 'path';
import * as os from 'os';
import * as fs from 'fs';

test.describe('Multi-file Upload Smoke Test', () => {
  let file1Path: string;
  let file2Path: string;
  let file3Path: string;

  test.beforeAll(() => {
    // Create temporary dummy files
    const tmpDir = os.tmpdir();
    file1Path = path.join(tmpDir, 'dummy1.csv');
    file2Path = path.join(tmpDir, 'dummy2.pdf');
    file3Path = path.join(tmpDir, 'dummy3.xlsx');
    
    fs.writeFileSync(file1Path, 'dummy data 1');
    fs.writeFileSync(file2Path, 'dummy data 2');
    fs.writeFileSync(file3Path, 'dummy data 3');
  });

  test.afterAll(() => {
    // Cleanup
    try {
      if (fs.existsSync(file1Path)) fs.unlinkSync(file1Path);
      if (fs.existsSync(file2Path)) fs.unlinkSync(file2Path);
      if (fs.existsSync(file3Path)) fs.unlinkSync(file3Path);
    } catch { }
  });

  test('should allow selecting multiple files, clearing, and uploading', async ({ page }) => {
    // Go to the board page
    await page.goto('http://localhost:3001/board');

    // Wait for the login screen to appear and click bypass
    await expect(page.getByRole('heading', { name: 'Agentic 시스템 인증' })).toBeVisible();
    await page.getByRole('button', { name: '검토자(Reviewer)로 계속하기' }).click();

    // Verify main console load
    await expect(page.getByText('Agentic 통합 관제 콘솔')).toBeVisible();

    // Wait for file input to exist
    const fileInput = page.locator('input[type="file"]');
    
    // Attach multiple files (simulating multiple selection or drag and drop array mapping)
    await fileInput.setInputFiles([file1Path, file2Path, file3Path]);

    // Check if files are rendered
    await expect(page.getByText('첨부된 증빙자료 (3건)')).toBeVisible();
    await expect(page.getByText('dummy1.csv')).toBeVisible();
    await expect(page.getByText('dummy2.pdf')).toBeVisible();
    await expect(page.getByText('dummy3.xlsx')).toBeVisible();

    // Remove one file
    const removeButtons = page.locator('button[title="첨부 취소"]');
    await expect(removeButtons).toHaveCount(3);
    await removeButtons.nth(1).click(); // Remove dummy2.pdf
    
    await expect(page.getByText('첨부된 증빙자료 (2건)')).toBeVisible();
    await expect(page.getByText('dummy1.csv')).toBeVisible();
    await expect(page.getByText('dummy2.pdf')).toBeHidden();
    await expect(page.getByText('dummy3.xlsx')).toBeVisible();

    // Clear all files
    await page.getByRole('button', { name: '모두 지우기' }).click();
    await expect(page.getByText('첨부된 증빙자료')).toBeHidden();
    
    // Attach 2 files again to test submit 
    // We won't actually submit to avoid real backend mocking dependency, 
    // but we will verify the button is accessible.
    await fileInput.setInputFiles([file1Path, file3Path]);
    await expect(page.getByText('첨부된 증빙자료 (2건)')).toBeVisible();
    
    // Enter prompt
    await page.getByPlaceholder('예: 이번 달 급여대장 엑셀 파일 검증해줘').fill('Playwright Test Smoke Prompt');
    
    // The play button
    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeEnabled();
  });
});
