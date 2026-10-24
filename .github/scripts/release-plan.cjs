// Decide what to release without creating or moving any tags.
function taggedPlan(tag, sha, prerelease) {
  const semver = /^v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/;
  const development = /^dev-(\d{8})-([0-9a-f]{8})$/;
  let version;
  if (semver.test(tag)) {
    version = tag.match(semver)[1];
    prerelease = Boolean(prerelease || version.includes('-'));
  } else if (development.test(tag)) {
    const [, date, shortSha] = tag.match(development);
    if (!sha.startsWith(shortSha)) throw new Error('Development tag does not match its commit');
    version = `0.0.0.dev${date}+g${shortSha}`;
    prerelease = true;
  } else {
    throw new Error('Release tags must use vMAJOR.MINOR.PATCH (optionally -rc.N)');
  }
  return {release: true, tag, ref: sha, version, prerelease,
    title: prerelease ? `Development ${tag}` : tag};
}

function snapshotPlan(sha, previousSha, date, force = false) {
  if (!force && sha === previousSha) return {release: false};
  const day = date.toISOString().slice(0, 10).replaceAll('-', '');
  const tag = `dev-${day}-${sha.slice(0, 8)}`;
  return taggedPlan(tag, sha, true);
}

async function run({github, context, core}) {
  const repo = {...context.repo};
  let result;
  if (context.eventName === 'release' || context.ref.startsWith('refs/tags/')) {
    const tag = context.payload.release?.tag_name || context.ref.slice('refs/tags/'.length);
    const {data: commit} = await github.rest.repos.getCommit({...repo, ref: tag});
    result = taggedPlan(tag, commit.sha, context.payload.release?.prerelease);
  } else {
    const releases = await github.paginate(github.rest.repos.listReleases, {...repo, per_page: 100});
    const latest = releases.filter(item => !item.draft && item.published_at)
      .sort((a, b) => b.published_at.localeCompare(a.published_at))[0];
    let previousSha;
    if (latest) {
      try {
        const {data: commit} = await github.rest.repos.getCommit({...repo, ref: latest.tag_name});
        previousSha = commit.sha;
      } catch (error) {
        if (error.status !== 404) throw error;
        core.warning('Previous release tag is missing; building a new snapshot');
      }
    }
    const force = context.payload.inputs?.force === 'true' || context.payload.inputs?.force === true;
    result = snapshotPlan(context.sha, previousSha, new Date(), force);
  }
  core.setOutput('release', String(result.release));
  if (result.release) {
    for (const key of ['tag', 'ref', 'version', 'prerelease', 'title']) {
      core.setOutput(key, String(result[key]));
    }
  } else {
    core.info('No commits since the last release; skipping snapshot');
  }
}

module.exports = {taggedPlan, snapshotPlan, run};
