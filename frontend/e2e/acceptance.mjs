/** Local browser acceptance against an already seeded, disposable TeamFlow API.
 * Required: TEAMFLOW_SEED_PATH. Optional: TEAMFLOW_FRONTEND_URL, TEAMFLOW_API_URL,
 * TEAMFLOW_CHROME_PATH, TEAMFLOW_SCREENSHOT_DIR, TEAMFLOW_EVIDENCE_PATH.
 * Never point this at a production database: tasks move and a fake guest is added.
 */
import { chromium } from 'playwright';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

const seed = JSON.parse(await readFile(process.env.TEAMFLOW_SEED_PATH, 'utf8'));
const frontend = process.env.TEAMFLOW_FRONTEND_URL || 'http://127.0.0.1:5173';
const api = process.env.TEAMFLOW_API_URL || 'http://127.0.0.1:8000/api';
const shots = process.env.TEAMFLOW_SCREENSHOT_DIR || path.resolve('../docs/screenshots');
await mkdir(shots, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.TEAMFLOW_CHROME_PATH
    ? { executablePath: process.env.TEAMFLOW_CHROME_PATH }
    : { channel: 'chrome' }),
});
const password = 'TeamFlow-Demo-42!';
const evidence = {
  runner: 'Playwright with installed Chrome, local disposable database',
  started_at: new Date().toISOString(),
  checks: [],
  page_errors: [],
};
function check(name, detail = '') {
  evidence.checks.push({ name, result: 'PASS', detail });
  console.log(`PASS ${name}`);
}
async function makePage(viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, acceptDownloads: true, locale: 'en-US' });
  const page = await context.newPage();
  page.on('pageerror', (error) => evidence.page_errors.push(error.message));
  let token;
  const receivedEvents = [];
  page.on('websocket', (socket) => {
    socket.on('framereceived', ({ payload }) => {
      try {
        const message = JSON.parse(payload.toString());
        receivedEvents.push({ type: message.type, board_id: message.board_id });
      } catch {
        // Only the application's JSON event frames are relevant here.
      }
    });
  });
  page.on('response', async (response) => {
    if (response.url().endsWith('/auth/login') && response.ok())
      token = (await response.json()).access_token;
  });
  return { context, page, token: () => token, receivedEvents };
}
async function login(page, name) {
  await page.goto(frontend);
  await page.getByLabel('Username or Email').fill(name);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Login', exact: true }).click();
  await page.getByRole('button', { name: 'Log out', exact: true }).waitFor();
}
async function openBoard(page) {
  await page.locator('#select-team').selectOption(String(seed.team_id));
  await page.locator('#select-board').selectOption(String(seed.board_id));
  await page.getByRole('heading', { name: 'Software Engineering Project', exact: true }).waitFor();
  await page.getByRole('status').filter({ hasText: 'Live' }).waitFor();
}
async function state(token) {
  const response = await fetch(`${api}/boards/${seed.board_id}/state`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(response.status, 200);
  return response.json();
}
async function resetTasks(token) {
  let snapshot = await state(token);
  const todo = snapshot.columns.find((column) => column.name === 'Todo');
  for (const id of seed.task_ids) {
    const task = snapshot.tasks.find((task) => task.id === id);
    const response = await fetch(`${api}/tasks/${id}/move`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_column_id: todo.id,
        target_index: snapshot.tasks.filter(
          (task) => task.column_id === todo.id && task.id !== id && !task.is_archived,
        ).length,
        expected_revision: snapshot.revision,
        expected_version: task.version,
      }),
    });
    assert.equal(response.status, 200);
    snapshot = await state(token);
  }
  return snapshot;
}
async function shot(page, name, options = {}) {
  await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true, ...options });
}
async function waitUntil(checkFn, timeout = 10000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await checkFn()) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('Condition timed out');
}

try {
  const owner = await makePage();
  const member = await makePage();
  const outsider = await makePage();
  await login(owner.page, seed.usernames?.owner || 'owner');
  await openBoard(owner.page);
  await waitUntil(() => !!owner.token());
  const previous = await state(owner.token());
  const priorTask = previous.tasks.find((task) => task.id === seed.task_ids[0]);
  for (const [resource, items] of [
    [
      'comments',
      priorTask.comments.filter((item) => item.content.startsWith('Browser acceptance:')),
    ],
    [
      'checklist',
      priorTask.checklist.filter((item) => item.content.startsWith('Browser acceptance checklist')),
    ],
    ['labels', priorTask.labels.filter((item) => item.name === 'browser-verified')],
  ]) {
    for (const item of items) {
      const response = await fetch(`${api}/tasks/${priorTask.id}/${resource}/${item.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${owner.token()}` },
      });
      assert.ok(response.ok);
    }
  }
  await resetTasks(owner.token());
  await login(member.page, seed.usernames?.member || 'member');
  await openBoard(member.page);
  await login(outsider.page, seed.usernames?.outsider || 'outsider');
  check('Three distinct browser contexts authenticate independently');
  const snapshot = await state(owner.token());
  const progress = snapshot.columns.find((column) => column.name === 'In Progress');
  const todo = snapshot.columns.find((column) => column.name === 'Todo');
  const first = snapshot.tasks.find((task) => task.id === seed.task_ids[0]);
  const second = snapshot.tasks.find((task) => task.id === seed.task_ids[1]);
  const third = snapshot.tasks.find((task) => task.id === seed.task_ids[2]);
  const firstMove = owner.page.waitForResponse((response) =>
    response.url().endsWith(`/tasks/${first.id}/move`),
  );
  const handle = owner.page.getByLabel(`Drag ${first.title}`, { exact: true });
  const handleBox = await handle.boundingBox();
  const destinationBox = await owner.page
    .getByRole('region', { name: 'In Progress column' })
    .locator('.column-content')
    .boundingBox();
  assert.ok(handleBox && destinationBox);
  await owner.page.mouse.move(
    handleBox.x + handleBox.width / 2,
    handleBox.y + handleBox.height / 2,
  );
  await owner.page.mouse.down();
  await owner.page.mouse.move(
    handleBox.x + handleBox.width / 2 + 12,
    handleBox.y + handleBox.height / 2,
  );
  await owner.page.mouse.move(destinationBox.x + destinationBox.width / 2, destinationBox.y + 45, {
    steps: 20,
  });
  await owner.page.mouse.up();
  assert.equal((await firstMove).status(), 200);
  await member.page
    .getByRole('region', { name: 'In Progress column' })
    .getByRole('button', { name: first.title, exact: true })
    .waitFor();
  await waitUntil(() =>
    member.receivedEvents.some(
      (event) => event.type === 'task.moved' && event.board_id === seed.board_id,
    ),
  );
  check(
    'Owner drags a task; member receives task.moved and sees the committed move without reload',
  );
  const secondMove = owner.page.waitForResponse((response) =>
    response.url().endsWith(`/tasks/${second.id}/move`),
  );
  const keyboardHandle = owner.page.getByLabel(`Drag ${second.title}`, { exact: true });
  await keyboardHandle.focus();
  await keyboardHandle.press('Space');
  await keyboardHandle.press('ArrowRight');
  await keyboardHandle.press('Space');
  assert.equal((await secondMove).status(), 200);
  check('Keyboard Space/ArrowRight/Space moves a task through the drag-and-drop library');
  await owner.page
    .getByRole('region', { name: 'In Progress column' })
    .getByText('WIP limit reached', { exact: true })
    .waitFor();
  const rejectedMove = owner.page.waitForResponse((response) =>
    response.url().endsWith(`/tasks/${third.id}/move`),
  );
  await owner.page.getByLabel(`Move ${third.title} to column`).selectOption(String(progress.id));
  assert.equal((await rejectedMove).status(), 409);
  const rollbackNotice = owner.page.getByText(/WIP limit reached\. .*Your move was rolled back\./);
  await rollbackNotice.waitFor();
  await owner.page
    .getByRole('region', { name: 'Todo column' })
    .getByRole('button', { name: third.title, exact: true })
    .waitFor();
  const afterWip = await state(owner.token());
  assert.equal(
    afterWip.tasks.filter((task) => task.column_id === progress.id && !task.is_archived).length,
    2,
  );
  check('Third incoming move is rejected with HTTP 409; UI rolls back and WIP remains exactly two');
  await waitUntil(async () => {
    const box = await rollbackNotice.boundingBox();
    return box && box.y >= 0 && box.y + box.height < owner.page.viewportSize().height;
  });
  await shot(owner.page, 'wip-conflict');
  await owner.page
    .getByText(/WIP limit reached\. .*Your move was rolled back\./)
    .waitFor({ state: 'hidden' });
  await shot(owner.page, 'board');
  await owner.page.getByRole('button', { name: first.title, exact: true }).click();
  await owner.page.getByRole('dialog').waitFor();
  assert.equal(await owner.page.getByLabel('Assignee').inputValue(), String(seed.users.member));
  assert.ok(
    await owner.page
      .getByRole('dialog')
      .getByText(first.comments[0].content, { exact: true })
      .count(),
  );
  const fileButton = owner.page.getByRole('button', {
    name: first.attachments[0].filename,
    exact: true,
  });
  const download = owner.page.waitForEvent('download');
  await fileButton.click();
  const downloaded = await download;
  assert.equal(downloaded.suggestedFilename(), first.attachments[0].filename);
  assert.equal(await readFile(await downloaded.path(), 'utf8'), 'TeamFlow demo requirements\n');
  check(
    'Existing assignment, checklist, label, comments and authenticated private download render correctly',
  );
  await owner.page
    .getByLabel('Add comment', { exact: true })
    .fill('Browser acceptance: confirmed with a second session.');
  await owner.page.getByRole('button', { name: 'Post comment', exact: true }).click();
  await owner.page
    .getByText('Browser acceptance: confirmed with a second session.', { exact: true })
    .waitFor();
  await owner.page.getByLabel('New checklist item').fill('Browser acceptance checklist');
  await owner.page.getByRole('button', { name: 'Add item', exact: true }).click();
  await owner.page.getByLabel('Browser acceptance checklist', { exact: true }).waitFor();
  await owner.page.getByLabel('Browser acceptance checklist', { exact: true }).click();
  await waitUntil(() =>
    owner.page.getByLabel('Browser acceptance checklist', { exact: true }).isChecked(),
  );
  await owner.page.getByLabel('New label').fill('browser-verified');
  await owner.page.getByRole('button', { name: 'Add label', exact: true }).click();
  await owner.page
    .getByRole('dialog')
    .getByRole('button', { name: 'Remove label browser-verified', exact: true })
    .waitFor();
  await owner.page.getByRole('dialog').evaluate((dialog) => {
    dialog.scrollTop = 0;
  });
  await shot(owner.page, 'task-details');
  await owner.page.getByRole('button', { name: 'Close dialog' }).click();
  check('Comment, checklist addition/toggle and label mutations persist through the actual UI/API');
  await owner.page.getByRole('button', { name: 'Activity', exact: true }).click();
  await owner.page.getByRole('dialog').getByText('task moved', { exact: false }).first().waitFor();
  await shot(owner.page, 'activity');
  await owner.page.getByRole('button', { name: 'Close dialog' }).click();
  check('Activity timeline shows real committed move/comment/checklist/label records');
  await outsider.page.getByRole('button', { name: 'Open shared board', exact: true }).click();
  await outsider.page.getByLabel('Board ID').fill(String(seed.board_id));
  await outsider.page.getByRole('button', { name: 'Open board', exact: true }).click();
  await outsider.page.getByRole('alert').filter({ hasText: 'Board permission required' }).waitFor();
  assert.equal(
    await outsider.page.getByRole('button', { name: first.title, exact: true }).count(),
    0,
  );
  const denied = await outsider.page.request.get(
    `${api}/attachments/${seed.attachment_id}/download`,
    { headers: { Authorization: `Bearer ${outsider.token()}` } },
  );
  assert.equal(denied.status(), 403);
  check('Outsider cannot open the private board or download a guessed attachment ID');
  const guestName = `guest${Date.now().toString().slice(-8)}`;
  const guestEmail = `${guestName}@example.test`;
  const guest = await makePage();
  await guest.page.goto(frontend);
  await guest.page.getByRole('button', { name: 'Register', exact: true }).click();
  await guest.page.getByLabel('Email', { exact: true }).fill(guestEmail);
  await guest.page.getByLabel('Username', { exact: true }).fill(guestName);
  await guest.page.getByLabel('Full Name (Optional)', { exact: true }).fill('Invited Teammate');
  await guest.page.getByLabel('Password', { exact: true }).fill(password);
  await guest.page.getByLabel('Confirm Password', { exact: true }).fill(password);
  await guest.page.getByRole('button', { name: 'Register', exact: true }).click();
  await guest.page.getByRole('button', { name: 'Log out', exact: true }).waitFor();
  await owner.page.getByRole('button', { name: 'Members & settings', exact: true }).click();
  await owner.page.getByLabel('Email', { exact: true }).fill(guestEmail);
  await owner.page.getByRole('button', { name: 'Create invitation', exact: true }).click();
  const link = await owner.page.getByLabel('Invitation link').inputValue();
  const invitationToken = new URL(link).searchParams.get('invite');
  assert.ok(invitationToken);
  await shot(owner.page, 'team-members-invitations', {
    mask: [owner.page.locator('#invite-link')],
    maskColor: '#e2e8f0',
  });
  await owner.page.getByRole('button', { name: 'Close dialog' }).click();
  await guest.page.getByRole('button', { name: 'Accept invitation', exact: true }).click();
  await guest.page.getByLabel('Invitation token').fill(invitationToken);
  await guest.page
    .getByRole('dialog')
    .getByRole('button', { name: 'Accept invitation', exact: true })
    .click();
  await guest.page
    .getByRole('heading', { name: 'Software Engineering Project', exact: true })
    .waitFor();
  check('Owner creates a real single-use invitation; matching registered guest accepts via UI');
  await owner.page.setViewportSize({ width: 768, height: 1024 });
  await shot(owner.page, 'tablet');
  await owner.page.setViewportSize({ width: 390, height: 844 });
  await shot(owner.page, 'mobile');
  assert.equal(
    await owner.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
  );
  await owner.page.getByRole('button', { name: first.title, exact: true }).click();
  await owner.page.getByRole('dialog').waitFor();
  assert.equal(
    await owner.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
  );
  await shot(owner.page, 'mobile-task-details');
  await owner.page.getByRole('button', { name: 'Close dialog' }).click();
  check(
    'Desktop, tablet and mobile board/dialog layouts stay usable with intentional board scrolling',
  );
  await member.page.getByRole('button', { name: 'Log out', exact: true }).click();
  await member.page
    .getByRole('heading', { name: 'Sign in to your account', exact: true })
    .waitFor();
  assert.equal(await member.page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.equal(
    await member.page.getByRole('button', { name: first.title, exact: true }).count(),
    0,
  );
  check('Logout clears the workspace and leaves no access token in browser storage');
  assert.equal(evidence.page_errors.length, 0);
  check('No uncaught browser JavaScript errors');
  evidence.completed_at = new Date().toISOString();
  evidence.result = 'PASS';
} catch (error) {
  evidence.result = 'FAIL';
  evidence.failure = error.message;
  throw error;
} finally {
  if (process.env.TEAMFLOW_EVIDENCE_PATH)
    await writeFile(process.env.TEAMFLOW_EVIDENCE_PATH, JSON.stringify(evidence, null, 2));
  await browser.close();
}
