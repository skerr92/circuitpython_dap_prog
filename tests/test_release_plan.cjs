const {test} = require('node:test');
const assert = require('node:assert/strict');
const {taggedPlan, snapshotPlan, run} = require('../.github/scripts/release-plan.cjs');
const sha = '1234567890abcdef1234567890abcdef12345678';

test('stable tags resolve to the exact version and commit', () => {
  const result = taggedPlan('v1.2.3', sha, false);
  assert.equal(result.version, '1.2.3');
  assert.equal(result.ref, sha);
  assert.equal(result.prerelease, false);
});

test('release candidates remain prereleases', () => {
  assert.equal(taggedPlan('v1.2.3-rc.1', sha, false).prerelease, true);
});

test('unchanged commits do not create weekly releases', () => {
  assert.deepEqual(snapshotPlan(sha, sha, new Date('2026-10-24T15:00:00Z')), {release: false});
});

test('a changed commit produces a unique dated prerelease', () => {
  const result = snapshotPlan(sha, 'different', new Date('2026-10-24T15:00:00Z'));
  assert.equal(result.tag, 'dev-20261024-12345678');
  assert.equal(result.version, '0.0.0.dev20261024+g12345678');
  assert.equal(result.prerelease, true);
});

test('manual rebuild can reuse an unchanged snapshot', () => {
  assert.equal(snapshotPlan(sha, sha, new Date('2026-10-24T15:00:00Z'), true).release, true);
});

test('invalid tags and development tags pointing at another commit fail', () => {
  assert.throws(() => taggedPlan('latest', sha));
  assert.throws(() => taggedPlan('dev-20261024-aaaaaaaa', sha));
});

test('scheduled workflow skips the commit from the last published release', async () => {
  const outputs = {};
  const github = {
    paginate: async () => [{tag_name: 'v1.2.3', published_at: '2026-10-20T00:00:00Z', draft: false}],
    rest: {repos: {listReleases: () => {}, getCommit: async () => ({data: {sha}})}}
  };
  await run({github, context: {repo: {owner: 'owner', repo: 'library'},
    eventName: 'schedule', ref: 'refs/heads/main', sha, payload: {}},
    core: {setOutput: (key, value) => outputs[key] = value, info: () => {}}});
  assert.deepEqual(outputs, {release: 'false'});
});

test('published releases build the tagged commit instead of the default branch', async () => {
  const outputs = {};
  const github = {rest: {repos: {getCommit: async ({ref}) => {
    assert.equal(ref, 'v2.0.0');
    return {data: {sha}};
  }}}};
  await run({github, context: {repo: {owner: 'owner', repo: 'library'},
    eventName: 'release', ref: 'refs/tags/v2.0.0', sha: 'default-branch-commit',
    payload: {release: {tag_name: 'v2.0.0', prerelease: false}}},
    core: {setOutput: (key, value) => outputs[key] = value}});
  assert.equal(outputs.ref, sha);
  assert.equal(outputs.version, '2.0.0');
});
