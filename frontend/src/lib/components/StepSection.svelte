<script lang="ts">
	import type { EventStoreState, StepSection as StepSectionType } from '$lib/types';
	import { THINKING_FIELDS } from '$lib/types';
	import TrialRow from './TrialRow.svelte';

	interface Props {
		step: StepSectionType;
		store: EventStoreState;
		previousScore: number | null;
		expandedTrials: Set<string>;
		onToggleTrial: (trialId: string) => void;
	}

	let { step, store, previousScore, expandedTrials, onToggleTrial }: Props = $props();

	let thinkingOpen = $state(false);

	const delta = $derived(
		step.step && previousScore !== null ? step.step.score - previousScore : null
	);

	const advice = $derived(step.proposal?.advice ?? step.step?.advice ?? null);
</script>

<section class="step-section panel">
	<header class="step-header">
		<div class="step-title">
			<span class="step-eyebrow">STEP</span>
			<h3>{step.stepIndex}</h3>
		</div>
		{#if step.step}
			<span class="score-chip">
				<span class="score-key">SCORE</span>
				<strong>{step.step.score.toFixed(3)}</strong>
			</span>
			{#if delta !== null}
				<span class="delta" class:positive={delta > 0} class:negative={delta < 0}>
					Δ {delta >= 0 ? '+' : ''}{delta.toFixed(3)}
				</span>
			{/if}
		{:else}
			<span class="step-status mono">IN PROGRESS…</span>
		{/if}
	</header>

	{#if step.proposal}
		<div class="proposal-block">
			<h4>PROPOSAL</h4>
			{#if advice}
				<aside class="advice-panel" role="note">
					<span class="advice-label">PROPOSER ADVICE</span>
					<p class="advice-text">{advice}</p>
				</aside>
			{/if}
			{#if step.proposal.thinking}
				<button
					type="button"
					class="thinking-toggle"
					onclick={() => (thinkingOpen = !thinkingOpen)}
				>
					{thinkingOpen ? '▼' : '▶'} PROPOSER THINKING
				</button>
				{#if thinkingOpen}
					<div class="thinking-sections">
						{#each THINKING_FIELDS as field (field.key)}
							<div class="thinking-item">
								<span class="thinking-label">{field.label}</span>
								<p>{step.proposal.thinking![field.key]}</p>
							</div>
						{/each}
					</div>
				{/if}
			{:else if step.stepIndex === 0}
				<p class="muted">Baseline step (no proposer thinking)</p>
			{/if}
			<p class="muted proposal-template-label">PROMPT TEMPLATE</p>
			<pre class="mono proposal-template">{step.proposal.prompt_template}</pre>
		</div>
	{/if}

	<div class="trials">
		{#each step.groupIds as groupId, i (groupId)}
			{@const replicates = (store.groups.get(groupId) ?? [])
				.map((key) => store.trialsById.get(key))
				.filter((entry) => entry !== undefined)}
			{#if replicates.length > 0}
				<TrialRow
					{replicates}
					expanded={expandedTrials.has(groupId)}
					onToggle={() => onToggleTrial(groupId)}
					index={i + 1}
					metrics={store.manifest?.metrics ?? []}
					repeats={store.manifest?.repeats ?? 1}
				/>
			{/if}
		{/each}
	</div>

	{#if step.step}
		<footer class="step-footer">
			<span class="footer-stat"
				><span class="footer-key">OVERALL MEAN</span>
				<strong>{step.step.summary.overall.mean.toFixed(3)}</strong> (n={step.step.summary.overall
					.n})</span
			>
			{#each Object.entries(step.step.summary.per_metric) as [name, stats] (name)}
				<span class="footer-stat"
					><span class="footer-key">{name}</span> {stats.mean.toFixed(3)}</span
				>
			{/each}
			<span class="footer-stat"
				><span class="footer-key">FAILURE RATE</span>
				{(step.step.summary.failure_rate * 100).toFixed(1)}%</span
			>
		</footer>
	{/if}
</section>

<style>
	.step-section {
		margin-bottom: var(--space-md);
	}

	.step-header {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		flex-wrap: wrap;
		margin-bottom: var(--space-md);
	}

	.step-title {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
	}

	.step-eyebrow {
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--accent-purple);
	}

	.step-header h3 {
		margin: 0;
		font-size: 24px;
		line-height: 32px;
	}

	.step-status {
		color: var(--muted);
		font-size: 11px;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.score-chip {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-sm);
		padding: 2px var(--space-sm);
		background: var(--surface-dim);
		border: 1px solid var(--border);
		font-family: var(--font-mono);
	}

	.score-key {
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.score-chip strong {
		font-size: 16px;
		font-weight: 600;
		color: var(--text);
	}

	.delta {
		font-family: var(--font-mono);
		font-size: 12px;
		padding: 2px var(--space-sm);
		border: 1px solid var(--border);
		background: var(--surface-dim);
		color: var(--muted);
	}

	.delta.positive {
		color: var(--success);
		background: var(--success-bg);
		border-color: var(--success);
	}

	.delta.negative {
		color: var(--danger);
		background: var(--danger-bg);
		border-color: var(--danger);
	}

	.proposal-block {
		margin-bottom: var(--space-md);
		padding-bottom: var(--space-md);
		border-bottom: 1px solid var(--border);
	}

	.proposal-block h4 {
		margin: 0 0 var(--space-sm);
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--accent-purple);
	}

	.advice-panel {
		margin-bottom: var(--space-md);
		padding: var(--space-md);
		background: var(--warning-bg);
		border: 1px solid var(--warning);
	}

	.advice-label {
		display: block;
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--warning);
		margin-bottom: var(--space-xs);
	}

	.advice-text {
		margin: 0;
		font-size: 14px;
		line-height: 20px;
		color: var(--text);
		white-space: pre-wrap;
	}

	.thinking-toggle {
		border: 1px solid var(--border);
		background: transparent;
		padding: 2px var(--space-sm);
		color: var(--accent-teal);
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		margin-bottom: var(--space-sm);
	}

	.thinking-toggle:hover {
		border-color: var(--slate-900);
	}

	.thinking-sections {
		display: grid;
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
		padding: var(--space-md);
		background: var(--surface-secondary);
		border: 1px solid var(--border);
	}

	.thinking-item {
		font-size: 14px;
		line-height: 20px;
	}

	.thinking-label {
		display: block;
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--muted);
		margin-bottom: 2px;
	}

	.thinking-item p {
		margin: 0;
	}

	.proposal-template-label {
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		margin: 0 0 var(--space-xs);
	}

	.proposal-template {
		margin: 0;
		padding: var(--space-md);
		background: var(--surface-secondary);
		border: 1px solid var(--border);
	}

	.step-footer {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-md) var(--space-lg);
		margin-top: var(--space-md);
		padding-top: var(--space-md);
		border-top: 1px solid var(--border);
		font-family: var(--font-mono);
		font-size: 12px;
		color: var(--muted);
	}

	.footer-stat {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-xs);
	}

	.footer-key {
		font-size: 11px;
		font-weight: 500;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.footer-stat strong {
		color: var(--text);
		font-weight: 600;
	}
</style>
