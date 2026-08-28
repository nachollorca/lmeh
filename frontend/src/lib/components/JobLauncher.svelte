<script lang="ts">
	import { onMount } from 'svelte';
	import { ApiError, fetchCatalog, startEvaluate, startOptimize, startRun } from '$lib/api';
	import type {
		CatalogProject,
		CatalogResponse,
		JobManifest,
		Operation,
		OptimizeRequest,
		RunRequest
	} from '$lib/types';
	import {
		loadRecentModels,
		loadRecentProposerModels,
		rememberModel,
		rememberProposerModel
	} from '$lib/recentModels';
	import Select from '$lib/components/Select.svelte';
	import type { SelectOption } from '$lib/components/Select.svelte';

	interface Props {
		disabled?: boolean;
		onStarted: (manifest: JobManifest) => void;
		onConflict?: () => void;
	}

	let { disabled = false, onStarted, onConflict }: Props = $props();

	let catalog = $state<CatalogResponse | null>(null);
	let loadError = $state<string | null>(null);
	let submitError = $state<string | null>(null);
	let submitting = $state(false);

	let operation = $state<Operation>('run');
	let projectName = $state('');
	let program = $state('');
	let prompt = $state('');
	let examples = $state('');
	let model = $state('');
	let workers = $state(1);
	let repeats = $state(1);
	let steps = $state(1);
	let proposerModel = $state('');
	let selectedMetrics = $state<string[]>([]);

	const selectedProject = $derived(catalog?.projects.find((p) => p.name === projectName) ?? null);

	const projectOptions = $derived<SelectOption[]>(
		(catalog?.projects ?? []).map((p) => ({ value: p.name, label: p.name }))
	);
	const programOptions = $derived<SelectOption[]>(
		(selectedProject?.programs ?? []).map((name) => ({ value: name, label: name }))
	);
	const promptOptions = $derived<SelectOption[]>(
		(selectedProject?.prompts ?? []).map((name) => ({ value: name, label: name }))
	);
	const datasetOptions = $derived<SelectOption[]>(
		(selectedProject?.datasets ?? []).map((name) => ({ value: name, label: name }))
	);

	onMount(async () => {
		const recent = loadRecentModels();
		const recentProposer = loadRecentProposerModels();
		if (recent[0]) model = recent[0];
		if (recentProposer[0]) proposerModel = recentProposer[0];

		try {
			catalog = await fetchCatalog();
			if (catalog.projects.length > 0) {
				selectProject(catalog.projects[0]);
			}
		} catch (err) {
			loadError = err instanceof Error ? err.message : String(err);
		}
	});

	function selectProject(project: CatalogProject) {
		projectName = project.name;
		program = project.programs[0] ?? '';
		prompt = project.prompts[0] ?? '';
		examples = project.datasets[0] ?? '';
		selectedMetrics = project.metrics.length > 0 ? [project.metrics[0]] : [];
	}

	function onProjectChange() {
		const project = catalog?.projects.find((p) => p.name === projectName);
		if (project) selectProject(project);
	}

	function toggleMetric(metric: string) {
		if (selectedMetrics.includes(metric)) {
			selectedMetrics = selectedMetrics.filter((m) => m !== metric);
		} else {
			selectedMetrics = [...selectedMetrics, metric];
		}
	}

	function buildManifest(jobId: string): JobManifest {
		const base = {
			job_id: jobId,
			kind: operation,
			status: 'running' as const,
			started_at: new Date().toISOString(),
			project: projectName,
			program,
			prompt,
			examples,
			model,
			workers,
			repeats
		};
		if (operation === 'evaluate') {
			return { ...base, metrics: [...selectedMetrics] };
		}
		if (operation === 'optimize') {
			return {
				...base,
				metrics: [...selectedMetrics],
				steps,
				proposer_model: proposerModel
			};
		}
		return base;
	}

	async function submit() {
		submitError = null;
		submitting = true;
		try {
			rememberModel(model);
			const body: RunRequest = {
				project: projectName,
				program,
				prompt,
				model,
				examples,
				workers,
				repeats
			};

			let jobId: string;
			if (operation === 'run') {
				({ job_id: jobId } = await startRun(body));
			} else if (operation === 'evaluate') {
				if (selectedMetrics.length === 0) {
					submitError = 'Select at least one metric';
					return;
				}
				({ job_id: jobId } = await startEvaluate({ ...body, metrics: selectedMetrics }));
			} else {
				if (selectedMetrics.length === 0) {
					submitError = 'Select at least one metric';
					return;
				}
				rememberProposerModel(proposerModel);
				({ job_id: jobId } = await startOptimize({
					...body,
					metrics: selectedMetrics,
					steps,
					proposer_model: proposerModel
				} as OptimizeRequest));
			}

			onStarted(buildManifest(jobId));
		} catch (err) {
			if (err instanceof ApiError && err.status === 409) {
				submitError =
					'Another job is already running. Wait for it to finish or open the jobs list.';
				onConflict?.();
			} else {
				submitError = err instanceof Error ? err.message : String(err);
			}
		} finally {
			submitting = false;
		}
	}
</script>

<section class="panel">
	<h2>Launch job</h2>

	{#if loadError}
		<div class="error-banner">Failed to load catalog: {loadError}</div>
	{:else if !catalog}
		<p class="muted">Loading catalog…</p>
	{:else}
		<div class="operation-toggle">
			{#each ['run', 'evaluate', 'optimize'] as op (op)}
				<button
					type="button"
					class="op-btn"
					class:active={operation === op}
					onclick={() => (operation = op as Operation)}
				>
					{op}
				</button>
			{/each}
		</div>

		<form
			class="form-grid"
			onsubmit={(e) => {
				e.preventDefault();
				void submit();
			}}
		>
			<div class="field">
				<label for="project">Project</label>
				<Select
					id="project"
					options={projectOptions}
					bind:value={projectName}
					onchange={onProjectChange}
				/>
			</div>
			<div class="field">
				<label for="program">Program</label>
				<Select id="program" options={programOptions} bind:value={program} />
			</div>
			<div class="field">
				<label for="prompt">Prompt</label>
				<Select id="prompt" options={promptOptions} bind:value={prompt} />
			</div>
			<div class="field">
				<label for="examples">Dataset</label>
				<Select id="examples" options={datasetOptions} bind:value={examples} />
			</div>
			<div class="field">
				<label for="model">Model</label>
				<input
					id="model"
					class="mono"
					type="text"
					bind:value={model}
					placeholder="provider:model-id"
					required
				/>
			</div>
			<div class="field">
				<label for="workers">Workers</label>
				<input id="workers" type="number" min="1" bind:value={workers} required />
			</div>
			<div class="field">
				<label for="repeats">Repeats</label>
				<input id="repeats" type="number" min="1" bind:value={repeats} required />
			</div>

			{#if operation === 'optimize'}
				<div class="field">
					<label for="steps">Steps</label>
					<input id="steps" type="number" min="0" bind:value={steps} required />
				</div>
				<div class="field">
					<label for="proposer">Proposer model</label>
					<input
						id="proposer"
						class="mono"
						type="text"
						bind:value={proposerModel}
						placeholder="provider:model-id"
						required
					/>
				</div>
			{/if}

			{#if operation !== 'run' && selectedProject}
				<div class="field metrics-field">
					<span class="field-label">Metrics</span>
					<div class="metrics-list">
						{#each selectedProject.metrics as metric (metric)}
							<label>
								<input
									type="checkbox"
									checked={selectedMetrics.includes(metric)}
									onchange={() => toggleMetric(metric)}
								/>
								{metric}
							</label>
						{/each}
					</div>
				</div>
			{/if}

			<div class="submit-row">
				<button type="submit" class="btn btn-primary" disabled={disabled || submitting}>
					{submitting ? 'Starting…' : `Start ${operation}`}
				</button>
			</div>
		</form>

		{#if submitError}
			<div class="error-banner">{submitError}</div>
		{/if}

		<p class="muted catalog-path">Projects root: {catalog.projects_root}</p>
	{/if}
</section>

<style>
	.operation-toggle {
		display: flex;
		gap: 0;
		margin-bottom: var(--space-md);
		border: 1px solid var(--border);
		width: fit-content;
	}

	.op-btn {
		padding: var(--space-sm) var(--space-md);
		border: none;
		border-right: 1px solid var(--border);
		background: var(--surface);
		color: var(--muted);
		font-family: var(--font-mono);
		font-size: 12px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.op-btn:last-child {
		border-right: none;
	}

	.op-btn:hover {
		background: var(--surface-dim);
		color: var(--text);
	}

	.op-btn.active {
		background: var(--primary);
		color: var(--on-primary);
	}

	.submit-row {
		grid-column: 1 / -1;
		display: flex;
		justify-content: flex-end;
	}

	.catalog-path {
		margin: var(--space-md) 0 0;
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.03em;
		word-break: break-all;
	}
</style>
