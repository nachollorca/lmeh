import type {
	EventEnvelope,
	EventStoreState,
	JobManifest,
	JobSummary,
	LiveAggregates,
	ScoringPayload,
	StepSection,
	TrialPayload,
	TrialWithScorings
} from '$lib/types';

function emptyAggregates(): LiveAggregates {
	return {
		trialTotal: 0,
		trialSuccess: 0,
		trialFailed: 0,
		scoringTotal: 0,
		scoringSuccess: 0,
		scoringFailed: 0,
		perMetricScores: {},
		inputTokens: 0,
		outputTokens: 0,
		latency: 0
	};
}

export function createEventStoreState(manifest: JobManifest | null = null): EventStoreState {
	return {
		manifest,
		status: manifest?.status ?? 'running',
		errorMessage: manifest?.error ?? null,
		errorStacktrace: manifest?.error_stacktrace ?? null,
		trialsById: new Map(),
		groups: new Map(),
		flatGroupIds: [],
		steps: [],
		aggregates: emptyAggregates(),
		summary: null,
		lastSeq: -1,
		proposing: false
	};
}

function ensureStep(steps: StepSection[], stepIndex: number): StepSection {
	let step = steps.find((s) => s.stepIndex === stepIndex);
	if (!step) {
		step = {
			stepIndex,
			proposal: null,
			step: null,
			groupIds: [],
			complete: false
		};
		steps.push(step);
		steps.sort((a, b) => a.stepIndex - b.stepIndex);
	}
	return step;
}

/** Trials are keyed per replicate; optimize reuses ids across steps, so scope by step. */
export function trialKey(stepIndex: number, trialId: string): string {
	return `${stepIndex}:${trialId}`;
}

/**
 * Replicates of one dataset row share a group key and render as a single row.
 * Jobs written before `example_id` existed fall back to `trial_id`, i.e. one
 * group per replicate — exactly the old flat behaviour.
 */
export function groupKey(stepIndex: number, payload: TrialPayload | ScoringPayload): string {
	return `${stepIndex}:${payload.example_id ?? payload.trial_id}`;
}

/** Register a replicate under its group, appending the group on first sight. */
function addToGroup(state: EventStoreState, stepIndex: number, group: string, key: string): void {
	const members = state.groups.get(group);
	if (members) {
		if (!members.includes(key)) state.groups.set(group, [...members, key]);
		return;
	}
	state.groups.set(group, [key]);
	if (state.manifest?.kind === 'optimize') {
		ensureStep(state.steps, stepIndex).groupIds.push(group);
	} else {
		state.flatGroupIds.push(group);
	}
}

function updateTrialAggregates(aggregates: LiveAggregates, trial: TrialPayload): void {
	aggregates.trialTotal += 1;
	if (trial.status === 'success') {
		aggregates.trialSuccess += 1;
		const response = trial.telemetry?.response;
		if (response) {
			aggregates.inputTokens += response.input_tokens ?? 0;
			aggregates.outputTokens += response.output_tokens ?? 0;
			aggregates.latency += response.latency ?? 0;
		}
	} else {
		aggregates.trialFailed += 1;
	}
}

function updateScoringAggregates(aggregates: LiveAggregates, scoring: ScoringPayload): void {
	aggregates.scoringTotal += 1;
	if (scoring.status === 'success' && scoring.score) {
		aggregates.scoringSuccess += 1;
		const name = scoring.metric.name;
		if (!aggregates.perMetricScores[name]) {
			aggregates.perMetricScores[name] = [];
		}
		aggregates.perMetricScores[name].push(scoring.score.normalized);
	} else {
		aggregates.scoringFailed += 1;
	}
}

function applyTrial(state: EventStoreState, trial: TrialPayload, stepIndex: number): void {
	const key = trialKey(stepIndex, trial.trial_id);
	const existing = state.trialsById.get(key);
	if (existing) {
		// Replace the entry with a new object so consumers (e.g. TrialRow) see a
		// new trial reference and recompute derived state; mutating in place
		// would leave the prop reference unchanged and skip reactivity.
		state.trialsById.set(key, { ...existing, trial });
	} else {
		state.trialsById.set(key, { trial, scorings: [] });
		addToGroup(state, stepIndex, groupKey(stepIndex, trial), key);
	}
	updateTrialAggregates(state.aggregates, trial);
}

function applyScoring(state: EventStoreState, scoring: ScoringPayload, stepIndex: number): void {
	const key = trialKey(stepIndex, scoring.trial_id);
	const existing = state.trialsById.get(key);
	if (existing) {
		const idx = existing.scorings.findIndex(
			(s) => s.metric.name === scoring.metric.name && s.replicate === scoring.replicate
		);
		// Allocate a new scorings array so TrialRow's `scorings` prop changes
		// reference and its mean/color derived values recompute live as each
		// scoring lands (in-place push/assign would not trigger reactivity).
		const scorings =
			idx >= 0 ? existing.scorings.with(idx, scoring) : [...existing.scorings, scoring];
		state.trialsById.set(key, { ...existing, scorings });
	} else {
		state.trialsById.set(key, {
			trial: {
				status: 'failed',
				trial_id: scoring.trial_id,
				example_id: scoring.example_id,
				example: { inputs: {}, reference: null },
				replicate: scoring.replicate,
				error: { type: 'MissingTrial', message: 'Scoring arrived before trial' }
			},
			scorings: [scoring]
		});
		addToGroup(state, stepIndex, groupKey(stepIndex, scoring), key);
	}
	updateScoringAggregates(state.aggregates, scoring);
}

export function reduceEvent(state: EventStoreState, envelope: EventEnvelope): EventStoreState {
	if (envelope.seq <= state.lastSeq) {
		return state;
	}

	const next: EventStoreState = {
		...state,
		trialsById: new Map(state.trialsById),
		groups: new Map(state.groups),
		flatGroupIds: [...state.flatGroupIds],
		steps: state.steps.map((s) => ({
			...s,
			groupIds: [...s.groupIds]
		})),
		aggregates: { ...state.aggregates, perMetricScores: { ...state.aggregates.perMetricScores } },
		lastSeq: envelope.seq
	};

	switch (envelope.type) {
		case 'trial':
			applyTrial(next, envelope.payload as TrialPayload, envelope.step_index);
			break;
		case 'scoring':
			applyScoring(next, envelope.payload as ScoringPayload, envelope.step_index);
			break;
		case 'proposal': {
			const step = ensureStep(next.steps, envelope.step_index);
			step.proposal = envelope.payload as StepSection['proposal'];
			next.proposing = false;
			break;
		}
		case 'step': {
			const step = ensureStep(next.steps, envelope.step_index);
			step.step = envelope.payload as StepSection['step'];
			step.complete = true;
			next.proposing = next.manifest?.kind === 'optimize' && next.status === 'running';
			break;
		}
		case 'error': {
			const payload = envelope.payload as { message: string; stacktrace?: string };
			next.status = 'error';
			next.errorMessage = payload.message;
			next.errorStacktrace = payload.stacktrace ?? null;
			next.proposing = false;
			break;
		}
	}

	return next;
}

export function reduceEvents(
	state: EventStoreState,
	events: EventEnvelope[],
	manifest?: JobManifest | null,
	summary?: JobSummary | null
): EventStoreState {
	let next = manifest ? { ...createEventStoreState(manifest), manifest } : { ...state };
	for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
		next = reduceEvent(next, event);
	}
	if (summary) {
		next = { ...next, summary, status: manifest?.status ?? next.status };
	} else if (manifest?.status === 'done' || manifest?.status === 'error') {
		next = {
			...next,
			status: manifest.status,
			errorMessage: manifest.error ?? next.errorMessage,
			errorStacktrace: manifest.error_stacktrace ?? next.errorStacktrace
		};
	}
	next.proposing =
		next.manifest?.kind === 'optimize' &&
		next.status === 'running' &&
		next.steps.some((s) => s.complete) &&
		!next.steps.some((s) => !s.complete && s.proposal);
	return next;
}

export function manifestFromRecord(record: Record<string, unknown>): JobManifest {
	return record as unknown as JobManifest;
}

export function computeOverallMean(aggregates: LiveAggregates): number | null {
	const metrics = Object.values(aggregates.perMetricScores);
	if (metrics.length === 0) return null;
	const means = metrics.map((scores) => scores.reduce((a, b) => a + b, 0) / scores.length);
	return means.reduce((a, b) => a + b, 0) / means.length;
}

export function perMetricMeans(
	aggregates: LiveAggregates
): Record<string, { mean: number; n: number }> {
	const result: Record<string, { mean: number; n: number }> = {};
	for (const [name, scores] of Object.entries(aggregates.perMetricScores)) {
		if (scores.length === 0) continue;
		result[name] = {
			mean: scores.reduce((a, b) => a + b, 0) / scores.length,
			n: scores.length
		};
	}
	return result;
}

export function meanNormalizedScore(scorings: ScoringPayload[]): number | null {
	const normalized = scorings
		.filter((s) => s.status === 'success' && s.score)
		.map((s) => s.score!.normalized);
	if (normalized.length === 0) return null;
	return normalized.reduce((a, b) => a + b, 0) / normalized.length;
}

/**
 * A row only leaves the pulsing state once every replicate has arrived and every
 * expected metric has reported; colouring on the first arriving scoring paints a
 * misleading (often red) mean while the other metrics are still running.
 */
export function trialRowColor(
	replicates: TrialWithScorings[],
	metrics: string[] = [],
	expectedReplicates = replicates.length
): 'grey' | 'running' | 'score' {
	if (replicates.every(({ trial }) => trial.status === 'failed')) return 'grey';
	if (replicates.length < expectedReplicates) return 'running';
	const pending = replicates.some(
		({ trial, scorings }) =>
			trial.status === 'success' &&
			new Set(scorings.map((s) => s.metric.name)).size < metrics.length // empty for `run`
	);
	if (pending) return 'running';
	return meanNormalizedScore(replicates.flatMap((r) => r.scorings)) === null ? 'grey' : 'score';
}

export function scoreGradient(normalized: number): string {
	const clamped = Math.max(0, Math.min(1, normalized));
	const hue = clamped * 120;
	return `hsl(${hue} 55% 88%)`;
}

export function formatValue(value: unknown): string {
	if (value === null || value === undefined) return '—';
	if (typeof value === 'string') return value;
	try {
		return JSON.stringify(value, null, 2);
	} catch {
		return String(value);
	}
}

export function snippet(text: unknown, max = 80): string {
	const s = typeof text === 'string' ? text : formatValue(text);
	const oneLine = s.replace(/\s+/g, ' ').trim();
	return oneLine.length > max ? `${oneLine.slice(0, max)}…` : oneLine;
}
