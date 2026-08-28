<script lang="ts">
	import type { EventStoreState, JobSummary } from '$lib/types';
	import { computeOverallMean, perMetricMeans } from '$lib/eventStore';

	interface Props {
		summary: JobSummary | null;
		store: EventStoreState;
		complete: boolean;
	}

	let { summary, store, complete }: Props = $props();

	const liveMetrics = $derived(perMetricMeans(store.aggregates));
	const liveOverall = $derived(computeOverallMean(store.aggregates));
	const agg = $derived(store.aggregates);
</script>

{#if summary || agg.trialTotal > 0}
	<section class="panel">
		<h2>Summary</h2>
		{#if summary}
			<div class="summary-grid">
				<div>
					<span class="label">Trials</span>
					<strong>{summary.trial_count}</strong>
					<span class="muted"> · failure rate {(summary.failure_rate * 100).toFixed(1)}%</span>
				</div>
				{#if summary.scoring_count > 0}
					<div>
						<span class="label">Scorings</span>
						<strong>{summary.scoring_count}</strong>
						<span class="muted">
							· scoring failure {(summary.scoring_failure_rate * 100).toFixed(1)}%
						</span>
					</div>
				{/if}
				{#if summary.overall}
					<div>
						<span class="label">Overall mean</span>
						<strong>{summary.overall.mean.toFixed(3)}</strong>
						<span class="muted"> (n={summary.overall.n})</span>
					</div>
				{/if}
				{#each Object.entries(summary.per_metric) as [name, stats] (name)}
					<div>
						<span class="label">{name}</span>
						<strong>{stats.mean.toFixed(3)}</strong>
						<span class="muted"> (n={stats.n})</span>
						{#if summary.replicate_noise?.[name]}
							<span class="muted">
								· noise floor {summary.replicate_noise[name].mean.toFixed(3)}
							</span>
						{/if}
					</div>
				{/each}
				{#if summary.telemetry.replicate_divergence}
					<div>
						<span class="label" title="Mean pairwise text dissimilarity between replicates">
							Replicate divergence
						</span>
						<strong>{summary.telemetry.replicate_divergence.mean.toFixed(3)}</strong>
						<span class="muted">
							± {summary.telemetry.replicate_divergence.sd.toFixed(3)} (n={summary.telemetry
								.replicate_divergence.n})
						</span>
					</div>
				{/if}
				<div>
					<span class="label">Tokens</span>
					<strong>{summary.telemetry.input_tokens}</strong> in /
					<strong>{summary.telemetry.output_tokens}</strong> out
				</div>
				<div>
					<span class="label">Latency</span>
					<strong>{summary.telemetry.latency.toFixed(2)}</strong>s total
				</div>
			</div>
			{#if summary.best_step}
				<div class="best-step">
					<strong>Best step:</strong>
					{summary.best_step.step_index} — score
					{summary.best_step.score.toFixed(3)}
				</div>
			{/if}
		{:else}
			<div class="summary-grid">
				<div>
					<span class="label">Trials</span>
					<strong>{agg.trialSuccess}/{agg.trialTotal}</strong> success
					{#if !complete}<span class="partial">(partial)</span>{/if}
				</div>
				{#if agg.scoringTotal > 0}
					<div>
						<span class="label">Scorings</span>
						<strong>{agg.scoringSuccess}/{agg.scoringTotal}</strong>
						{#if !complete}<span class="partial">(partial)</span>{/if}
					</div>
				{/if}
				{#if liveOverall !== null}
					<div>
						<span class="label">Overall mean</span>
						<strong>{liveOverall.toFixed(3)}</strong>
						{#if !complete}<span class="partial">(partial)</span>{/if}
					</div>
				{/if}
				{#each Object.entries(liveMetrics) as [name, stats] (name)}
					<div>
						<span class="label">{name}</span>
						<strong>{stats.mean.toFixed(3)}</strong>
						<span class="muted"> (n={stats.n})</span>
						{#if !complete}<span class="partial">(partial)</span>{/if}
					</div>
				{/each}
				<div>
					<span class="label">Tokens</span>
					<strong>{agg.inputTokens}</strong> in / <strong>{agg.outputTokens}</strong> out
				</div>
				<div>
					<span class="label">Latency</span>
					<strong>{agg.latency.toFixed(2)}</strong>s
				</div>
			</div>
		{/if}
	</section>
{/if}

<style>
	.summary-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: var(--space-md);
		font-size: 14px;
		line-height: 20px;
	}

	.summary-grid > div {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.summary-grid strong {
		font-family: var(--font-mono);
		font-size: 20px;
		font-weight: 600;
		color: var(--text);
	}

	.label {
		margin-bottom: 0;
	}

	.partial {
		color: var(--muted);
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		margin-left: var(--space-xs);
	}

	.best-step {
		margin-top: var(--space-md);
		padding: var(--space-sm) var(--space-md);
		background: var(--success-bg);
		border: 1px solid var(--success);
		color: var(--success);
		font-family: var(--font-mono);
		font-size: 13px;
	}

	.best-step strong {
		font-weight: 600;
	}
</style>
