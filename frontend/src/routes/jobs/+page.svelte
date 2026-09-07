<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { deleteJob, fetchJobs } from '$lib/api';
	import {
		areJobsComparable,
		canAddToComparison,
		comparableFromListItem,
		compareJobLimits,
		findCompareMismatches,
		formatCompareMismatchError
	} from '$lib/jobCompare';
	import type { JobListItem } from '$lib/types';

	let jobs = $state<JobListItem[]>([]);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let selectedIds = $state<string[]>([]);
	let deletingId = $state<string | null>(null);

	const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

	function pad2(value: number): string {
		return String(value).padStart(2, '0');
	}

	/** Render an ISO timestamp as e.g. `We, 2026-09-02 14:30` in local time. */
	function formatTimestamp(iso: string): string {
		const date = new Date(iso);
		if (Number.isNaN(date.getTime())) return iso;
		const ymd = `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
		return `${WEEKDAYS[date.getDay()]}, ${ymd} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
	}

	function sortedMetrics(job: JobListItem): string[] {
		return [...(job.metrics ?? [])].sort((a, b) => a.localeCompare(b));
	}

	const { min: minCompare, max: maxCompare } = compareJobLimits();

	const selectedJobs = $derived(jobs.filter((job) => selectedIds.includes(job.job_id)));
	const selectedComparables = $derived(selectedJobs.map(comparableFromListItem));
	const compareReady = $derived(
		selectedIds.length >= minCompare && areJobsComparable(selectedComparables)
	);

	onMount(async () => {
		try {
			const response = await fetchJobs();
			jobs = response.jobs;
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			loading = false;
		}
	});

	function isSelected(jobId: string): boolean {
		return selectedIds.includes(jobId);
	}

	function canSelect(job: JobListItem): boolean {
		if (isSelected(job.job_id)) return true;
		if (selectedIds.length >= maxCompare) return false;
		return canAddToComparison(selectedComparables, comparableFromListItem(job));
	}

	function toggleJob(job: JobListItem) {
		if (isSelected(job.job_id)) {
			selectedIds = selectedIds.filter((id) => id !== job.job_id);
			return;
		}
		if (!canSelect(job)) return;
		selectedIds = [...selectedIds, job.job_id];
	}

	function clearSelection() {
		selectedIds = [];
	}

	async function removeJob(job: JobListItem) {
		const label = job.job_id.slice(0, 8);
		if (!confirm(`Delete job ${label}…? This permanently removes its archive.`)) return;
		deletingId = job.job_id;
		error = null;
		try {
			await deleteJob(job.job_id);
			jobs = jobs.filter((entry) => entry.job_id !== job.job_id);
			selectedIds = selectedIds.filter((id) => id !== job.job_id);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			deletingId = null;
		}
	}

	const compareIds = $derived(selectedIds.join(','));

	const selectionHint = $derived.by(() => {
		if (selectedIds.length === 0) {
			return `Select ${minCompare}–${maxCompare} jobs with the same kind, project, dataset, and metrics.`;
		}
		if (selectedIds.length < minCompare) {
			return `Select at least ${minCompare - selectedIds.length} more job${minCompare - selectedIds.length === 1 ? '' : 's'}.`;
		}
		if (!areJobsComparable(selectedComparables)) {
			return formatCompareMismatchError(findCompareMismatches(selectedComparables));
		}
		return 'Comparable — program, prompt, and model may differ.';
	});
</script>

<svelte:head>
	<title>Jobs — Promptuna</title>
</svelte:head>

<section class="panel">
	<div class="jobs-header">
		<h2>Past jobs</h2>
		{#if selectedIds.length > 0}
			<div class="selection-actions">
				<button type="button" class="btn btn-ghost" onclick={clearSelection}>Clear</button>
				{#if compareReady}
					<a class="btn btn-primary" href={resolve('/jobs/compare/[ids]', { ids: compareIds })}>
						Compare ({selectedIds.length})
					</a>
				{:else}
					<span class="btn btn-primary disabled" aria-disabled="true">
						Compare ({selectedIds.length})
					</span>
				{/if}
			</div>
		{/if}
	</div>

	{#if loading}
		<p class="muted">Loading…</p>
	{:else if error}
		<div class="error-banner">{error}</div>
	{:else if jobs.length === 0}
		<div class="empty-state dot-grid-surface">
			<span class="micro-label">NO JOBS YET</span>
			<p>Launch a run, evaluate, or optimize job to populate the archive.</p>
		</div>
	{:else}
		<p
			class="selection-hint"
			class:incompatible={selectedIds.length >= minCompare && !compareReady}
		>
			{selectionHint}
		</p>
		<table class="job-table">
			<thead>
				<tr>
					<th class="compare-col" aria-label="Compare"></th>
					<th>Job ID</th>
					<th>Kind</th>
					<th>Status</th>
					<th>Project</th>
					<th>Dataset</th>
					<th>Metrics</th>
					<th>Started</th>
					<th class="actions-col" aria-label="Actions"></th>
				</tr>
			</thead>
			<tbody>
				{#each jobs as job (job.job_id)}
					{@const selectable = canSelect(job)}
					<tr
						class:selected={isSelected(job.job_id)}
						class:dimmed={!selectable && !isSelected(job.job_id)}
					>
						<td class="compare-col">
							<input
								type="checkbox"
								checked={isSelected(job.job_id)}
								disabled={!selectable}
								onchange={() => toggleJob(job)}
								aria-label="Select job {job.job_id.slice(0, 8)} for comparison"
							/>
						</td>
						<td
							><a class="mono" href={resolve('/jobs/[id]', { id: job.job_id })}
								>{job.job_id.slice(0, 8)}…</a
							></td
						>
						<td>{job.kind}</td>
						<td><span class="badge {job.status}">{job.status}</span></td>
						<td>{job.project}</td>
						<td>{job.examples}</td>
						<td>
							{#if sortedMetrics(job).length > 0}
								{sortedMetrics(job).join(', ')}
							{:else}
								<span class="muted">—</span>
							{/if}
						</td>
						<td class="mono">{formatTimestamp(job.started_at)}</td>
						<td class="actions-col">
							<button
								type="button"
								class="btn btn-ghost btn-danger"
								disabled={deletingId === job.job_id}
								onclick={() => removeJob(job)}
							>
								{deletingId === job.job_id ? 'Deleting…' : 'Delete'}
							</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>

<style>
	.jobs-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-md);
		margin-bottom: var(--space-md);
	}

	.jobs-header h2 {
		margin: 0;
	}

	.selection-actions {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.selection-hint {
		margin: 0 0 var(--space-md);
		font-size: 13px;
		color: var(--muted);
		white-space: pre-wrap;
	}

	.selection-hint.incompatible {
		color: var(--danger);
	}

	.compare-col {
		width: 40px;
	}

	.actions-col {
		width: 1%;
		white-space: nowrap;
		text-align: right;
	}

	.btn-danger {
		color: var(--danger);
	}

	.btn-danger:hover:not(:disabled) {
		border-color: var(--danger);
	}

	.btn-danger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.compare-col input[type='checkbox'] {
		appearance: none;
		-webkit-appearance: none;
		width: 16px;
		height: 16px;
		border: 1px solid var(--slate-300);
		background: var(--surface);
		display: inline-grid;
		place-content: center;
		cursor: pointer;
		accent-color: var(--primary);
	}

	.compare-col input[type='checkbox']:hover:not(:disabled) {
		border-color: var(--slate-900);
	}

	.compare-col input[type='checkbox']:checked {
		background: var(--slate-900);
		border-color: var(--slate-900);
	}

	.compare-col input[type='checkbox']:checked::after {
		content: '';
		width: 8px;
		height: 8px;
		background: var(--on-primary);
		clip-path: polygon(14% 44%, 0 60%, 50% 100%, 100% 20%, 86% 6%, 42% 62%);
	}

	.compare-col input[type='checkbox']:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	tr.selected td {
		background: var(--accent-teal-bg) !important;
	}

	tr.dimmed td {
		opacity: 0.5;
	}

	.btn-primary.disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding: var(--space-xl);
		border: 1px solid var(--border);
	}

	.empty-state p {
		margin: 0;
		color: var(--muted);
		font-size: 14px;
	}
</style>
