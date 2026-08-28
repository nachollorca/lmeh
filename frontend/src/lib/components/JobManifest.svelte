<script lang="ts">
	import { resolve } from '$app/paths';
	import type { JobManifest } from '$lib/types';

	interface Props {
		manifest: JobManifest;
	}

	let { manifest }: Props = $props();

	let copied = $state(false);

	async function copyJobId() {
		await navigator.clipboard.writeText(manifest.job_id);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

<section class="panel">
	<h2>Job</h2>
	<div class="manifest-grid">
		<div>
			<span class="label">Kind</span>
			<span>{manifest.kind}</span>
		</div>
		<div>
			<span class="label">Status</span>
			<span class="badge {manifest.status}">{manifest.status}</span>
		</div>
		<div>
			<span class="label">Project</span>
			<span>{manifest.project}</span>
		</div>
		<div>
			<span class="label">Program</span>
			<span>{manifest.program}</span>
		</div>
		<div>
			<span class="label">Prompt</span>
			<span>{manifest.prompt}</span>
		</div>
		<div>
			<span class="label">Dataset</span>
			<span>{manifest.examples}</span>
		</div>
		<div>
			<span class="label">Model</span>
			<span class="mono">{manifest.model}</span>
		</div>
		<div>
			<span class="label">Workers</span>
			<span>{manifest.workers}</span>
		</div>
		<div>
			<span class="label">Repeats</span>
			<span>{manifest.repeats ?? 1}</span>
		</div>
		{#if manifest.metrics}
			<div class="span-all">
				<span class="label">Metrics</span>
				<span>{manifest.metrics.join(', ')}</span>
			</div>
		{/if}
		{#if manifest.steps !== undefined}
			<div>
				<span class="label">Steps</span>
				<span>{manifest.steps}</span>
			</div>
		{/if}
		{#if manifest.proposer_model}
			<div>
				<span class="label">Proposer</span>
				<span class="mono">{manifest.proposer_model}</span>
			</div>
		{/if}
		<div class="span-all">
			<span class="label">Job ID</span>
			<div class="copy-row">
				<code>{manifest.job_id}</code>
				<button type="button" class="btn btn-ghost" onclick={copyJobId}>
					{copied ? 'Copied' : 'Copy'}
				</button>
				<a href={resolve('/jobs/[id]', { id: manifest.job_id })}>Replay</a>
			</div>
		</div>
		<div>
			<span class="label">Started</span>
			<span>{manifest.started_at}</span>
		</div>
		{#if manifest.finished_at}
			<div>
				<span class="label">Finished</span>
				<span>{manifest.finished_at}</span>
			</div>
		{/if}
	</div>
	{#if manifest.error}
		<div class="error-banner">{manifest.error}</div>
	{/if}
</section>

<style>
	.manifest-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: var(--space-md);
		font-size: 14px;
		line-height: 20px;
	}

	.manifest-grid > div {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.label {
		margin-bottom: 0;
	}

	.span-all {
		grid-column: 1 / -1;
	}
</style>
