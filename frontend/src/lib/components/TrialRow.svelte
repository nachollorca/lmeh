<script lang="ts">
	import type { TrialWithScorings } from '$lib/types';
	import { trialRowColor, scoreGradient, meanNormalizedScore } from '$lib/eventStore';
	import CollapsibleSection from './CollapsibleSection.svelte';
	import JsonView from './JsonView.svelte';

	interface Props {
		/** Every replicate of one dataset row; length 1 for a single-repeat job. */
		replicates: TrialWithScorings[];
		expanded: boolean;
		onToggle: () => void;
		index: number;
		/** Metrics the job scores; a row pulses until all of them have reported. */
		metrics?: string[];
		/** Replicates the job was launched with; a row pulses until they all land. */
		repeats?: number;
	}

	let { replicates, expanded, onToggle, index, metrics = [], repeats }: Props = $props();

	// The dataset row is identical across replicates; the first one represents it.
	const trial = $derived(replicates[0].trial);
	// Pooling every replicate's scorings mirrors the backend's (example, metric)
	// cell: one mean over both the program and the judge replicate axes.
	const scorings = $derived(replicates.flatMap((r) => r.scorings));
	const colorMode = $derived(trialRowColor(replicates, metrics, repeats ?? replicates.length));
	// Withhold the mean until scoring is complete, else a partially-scored row
	// shows a chip (and colour) computed from the metrics that happened to finish first.
	const meanScore = $derived(colorMode === 'running' ? null : meanNormalizedScore(scorings));

	// Dataset-provided id wins; fall back to the 1-based row index.
	const displayId = $derived.by(() => {
		const inputs = trial.example.inputs as Record<string, unknown>;
		const id = inputs?.id ?? inputs?.ID ?? inputs?._id;
		return id !== undefined && id !== null ? String(id) : `#${index}`;
	});

	const borderStyle = $derived.by(() => {
		if (colorMode === 'grey') return 'border-color: var(--border); background: var(--surface-dim)';
		if (colorMode === 'running') return '';
		if (meanScore !== null) {
			return `border-color: ${scoreGradient(meanScore).replace('88%', '55%')}; background: ${scoreGradient(meanScore).replace('88%', '92%')}`;
		}
		return '';
	});

	function scoreTier(normalized: number): 'green' | 'amber' | 'red' {
		if (normalized >= 0.66) return 'green';
		if (normalized >= 0.33) return 'amber';
		return 'red';
	}

	// Per-metric mean normalized score (averaged across replicates), 2 decimals.
	const perMetric = $derived.by(() => {
		const groups: Record<string, number[]> = {};
		for (const s of scorings) {
			if (s.status === 'success' && s.score) {
				(groups[s.metric.name] ??= []).push(s.score.normalized);
			}
		}
		return Object.entries(groups).map(([name, vals]) => ({
			name,
			value: vals.reduce((a, b) => a + b, 0) / vals.length
		}));
	});

	// Render a value as a JsonView when it's a container, else as plain text in a pre.
	function isJson(v: unknown): boolean {
		return typeof v === 'object' && v !== null;
	}

	function hintFor(v: unknown): string | undefined {
		if (Array.isArray(v)) return `Array(${v.length})`;
		if (v && typeof v === 'object') return `{${Object.keys(v).length}}`;
		return undefined;
	}
</script>

<article
	class="trial-row"
	class:expanded
	class:running={colorMode === 'running'}
	style={borderStyle}
>
	<button type="button" class="trial-header" onclick={onToggle} aria-expanded={expanded}>
		<span class="chevron">{expanded ? '▼' : '▶'}</span>
		<span class="trial-id">{displayId}</span>
		{#if replicates.length > 1}
			<span class="replicate-badge" title="Program replicates pooled in this row"
				>×{replicates.length}</span
			>
		{/if}
		{#if meanScore !== null}
			<span class="chip {scoreTier(meanScore)}" title="Mean of metric normalized scores">
				<span class="chip-metric">MEAN</span>
				<span class="chip-value">{meanScore.toFixed(2)}</span>
			</span>
			{#each perMetric as m (m.name)}
				<span class="chip {scoreTier(m.value)}" title={`${m.name} normalized score`}>
					<span class="chip-metric">{m.name}</span>
					<span class="chip-value">{m.value.toFixed(2)}</span>
				</span>
			{/each}
		{:else if colorMode !== 'running' && scorings.length > 0}
			<span class="chip failed" title="All scorings failed for this row">
				<span class="chip-metric">SCORE</span>
				<span class="chip-value">FAILED</span>
			</span>
		{/if}
	</button>

	{#if expanded}
		<div class="trial-detail">
			<CollapsibleSection label="Inputs" hint={hintFor(trial.example.inputs)}>
				{#if isJson(trial.example.inputs)}
					<div class="json-box"><JsonView value={trial.example.inputs} /></div>
				{:else}
					<pre class="mono">{trial.example.inputs ?? '—'}</pre>
				{/if}
			</CollapsibleSection>

			<CollapsibleSection label="Reference" hint={hintFor(trial.example.reference)}>
				{#if isJson(trial.example.reference)}
					<div class="json-box"><JsonView value={trial.example.reference} /></div>
				{:else}
					<pre class="mono">{trial.example.reference ?? '—'}</pre>
				{/if}
			</CollapsibleSection>

			{#each replicates as { trial: rep, scorings: repScorings } (rep.trial_id)}
				{#if replicates.length > 1}
					<h3 class="replicate-heading">Replicate {rep.replicate}</h3>
				{/if}
				{#if rep.status === 'success'}
					<CollapsibleSection label="Output" hint={hintFor(rep.output)}>
						{#if isJson(rep.output)}
							<div class="json-box"><JsonView value={rep.output} /></div>
						{:else}
							<pre class="mono">{rep.output ?? '—'}</pre>
						{/if}
					</CollapsibleSection>

					{#if rep.telemetry}
						<section class="telemetry-section">
							<h4>Telemetry</h4>
							{#if rep.telemetry.rendered_prompt}
								<CollapsibleSection
									label="Rendered prompt"
									hint={`${rep.telemetry.rendered_prompt.length} chars`}
								>
									<pre class="mono">{rep.telemetry.rendered_prompt}</pre>
								</CollapsibleSection>
							{/if}
							{#if rep.telemetry.response}
								<ul class="telemetry-stats">
									<li>Tokens in: {rep.telemetry.response.input_tokens ?? '—'}</li>
									<li>Tokens out: {rep.telemetry.response.output_tokens ?? '—'}</li>
									<li>Latency: {rep.telemetry.response.latency?.toFixed(3) ?? '—'}s</li>
								</ul>
							{/if}
						</section>
					{/if}
				{:else if rep.error}
					<section>
						<h4>Error</h4>
						<p class="error-text">{rep.error.type}: {rep.error.message}</p>
					</section>
				{/if}
				{#each repScorings as scoring (scoring.metric.name + scoring.replicate)}
					<section class="scoring-section">
						<h4>Scoring — {scoring.metric.name}</h4>
						{#if scoring.status === 'success' && scoring.score}
							<p class="scoring-stat">
								<span class="scoring-key">NORMALIZED</span>
								<strong>{scoring.score.normalized.toFixed(3)}</strong>
							</p>
							<CollapsibleSection label="Reason">
								<pre class="mono">{scoring.score.reason}</pre>
							</CollapsibleSection>
						{:else if scoring.error}
							<p class="error-text">{scoring.error.type}: {scoring.error.message}</p>
						{/if}
					</section>
				{/each}
			{/each}
		</div>
	{/if}
</article>

<style>
	.trial-row {
		border: 1px solid var(--border);
		margin-bottom: var(--space-sm);
		overflow: hidden;
		transition: border-width 0.05s ease;
	}

	.trial-row.expanded {
		border-width: 2px;
	}

	.trial-header {
		width: 100%;
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		border: none;
		background: transparent;
		text-align: left;
	}

	.trial-header:hover {
		background: rgba(15, 23, 42, 0.03);
	}

	.chevron {
		color: var(--muted);
		font-family: var(--font-mono);
		font-size: 10px;
		flex-shrink: 0;
	}

	.trial-id {
		flex: 1;
		min-width: 0;
		font-family: var(--font-mono);
		font-size: 13px;
		font-weight: 500;
		color: var(--text);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Running state: neutral grey with a subtle border pulse to signal work in progress.
	   Animations override the inline style, so the keyframes win over the base border. */
	@keyframes trial-running-pulse {
		0%,
		100% {
			border-color: var(--border);
			background: var(--surface-dim);
		}
		50% {
			border-color: var(--slate-300);
			background: var(--slate-200);
		}
	}

	.trial-row.running {
		background: var(--surface-dim);
		animation: trial-running-pulse 1.8s ease-in-out infinite;
	}

	@media (prefers-reduced-motion: reduce) {
		.trial-row.running {
			animation: none;
		}
	}

	.chip {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-xs);
		padding: 1px var(--space-sm);
		border: 1px solid transparent;
		font-family: var(--font-mono);
		font-size: 11px;
		line-height: 16px;
		letter-spacing: 0.03em;
	}

	.replicate-badge {
		flex-shrink: 0;
		padding: 1px var(--space-sm);
		border: 1px solid var(--border);
		background: var(--surface-dim);
		color: var(--muted);
		font-family: var(--font-mono);
		font-size: 11px;
		line-height: 16px;
	}

	/* Replicate bands own the boundary between replicates: they must read as a
	   level above the Telemetry/Scoring headings nested under them. */
	.replicate-heading {
		margin: var(--space-md) calc(-1 * var(--space-md)) var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		border-top: 2px solid var(--slate-900);
		background: var(--surface-dim);
		font-family: var(--font-mono);
		font-size: 13px;
		line-height: 20px;
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--accent-purple);
	}

	.chip-metric {
		font-weight: 500;
		text-transform: uppercase;
		opacity: 0.7;
	}

	.chip-value {
		font-weight: 600;
	}

	/* Functional scoring colors: 10% bg + full-color text + border */
	.chip.green {
		background: var(--success-bg);
		border-color: var(--success);
		color: var(--success);
	}

	.chip.amber {
		background: var(--warning-bg);
		border-color: var(--warning);
		color: var(--warning);
	}

	.chip.red,
	.chip.failed {
		background: var(--danger-bg);
		border-color: var(--danger);
		color: var(--danger);
	}

	.trial-detail {
		padding: 0 var(--space-md) var(--space-md);
		border-top: 1px solid var(--border);
	}

	/* Section headers use a consistent small uppercase mono label so children
	   (e.g. "Rendered prompt") never read larger than their parent. */
	.trial-detail :global(h4) {
		margin: var(--space-md) 0 var(--space-sm);
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text);
	}

	.trial-detail :global(.telemetry-section),
	.trial-detail :global(.scoring-section) {
		margin-top: var(--space-md);
	}

	.json-box {
		padding: var(--space-sm) var(--space-md);
		background: var(--surface-secondary);
		border: 1px solid var(--border);
		font-family: var(--font-mono);
		font-size: 12px;
		line-height: 18px;
		overflow-x: auto;
	}

	.trial-detail :global(pre.mono) {
		margin: 0;
		padding: var(--space-md);
		background: var(--surface-secondary);
		border: 1px solid var(--border);
		font-size: 12px;
		line-height: 18px;
		white-space: pre-wrap;
		overflow-x: auto;
	}

	.telemetry-stats {
		margin: var(--space-sm) 0 0;
		padding: var(--space-sm) var(--space-sm) var(--space-sm) var(--space-lg);
		font-family: var(--font-mono);
		font-size: 12px;
		line-height: 20px;
		border: 1px solid var(--border);
		background: var(--surface-secondary);
		list-style: square;
	}

	.error-text {
		color: var(--danger);
		margin: 0;
		font-family: var(--font-mono);
		font-size: 13px;
	}

	.scoring-stat {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
		margin: 0 0 var(--space-xs);
	}

	.scoring-key {
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.scoring-stat strong {
		font-family: var(--font-mono);
		font-size: 13px;
		font-weight: 600;
		color: var(--text);
	}
</style>
