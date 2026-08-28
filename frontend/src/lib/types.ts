export type JobKind = 'run' | 'evaluate' | 'optimize';
export type JobStatus = 'running' | 'done' | 'error';
export type EventType = 'trial' | 'scoring' | 'step' | 'proposal' | 'error';
export type TrialStatus = 'success' | 'failed';

export interface Thinking {
	reinstate_goal: string;
	trajectory_summary: string;
	failure_analysis: string;
	what_works: string;
	what_hurts: string;
	improvement_hypothesis: string;
	edit_plan: string;
}

export interface TrialPayload {
	status: TrialStatus;
	trial_id: string;
	/** Shared by every replicate of the same dataset row (absent on pre-1.36 jobs). */
	example_id?: string;
	example: { inputs: Record<string, unknown>; reference: unknown };
	replicate: number;
	output?: unknown;
	telemetry?: {
		rendered_prompt?: string;
		request?: Record<string, unknown>;
		response?: {
			content?: unknown;
			input_tokens?: number;
			output_tokens?: number;
			latency?: number;
		};
	};
	error?: { type: string; message: string };
}

export interface ScoringPayload {
	trial_id: string;
	example_id?: string;
	metric: { name: string; description: string; kind: 'programmatic' | 'llm_judge' };
	replicate: number;
	status: TrialStatus;
	score?: { raw: unknown; normalized: number; reason: string };
	error?: { type: string; message: string };
}

export interface ProposalPayload {
	prompt_template: string;
	thinking: Thinking | null;
	advice?: string | null;
}

export interface StepPayload {
	score: number;
	prompt_template: string;
	thinking: Thinking | null;
	advice?: string | null;
	summary: {
		overall: { mean: number; sd: number; n: number };
		per_metric: Record<string, { mean: number; sd: number; n: number }>;
		failure_rate: number;
		scoring_failure_rate: number;
	};
}

export interface ErrorPayload {
	message: string;
}

export interface EventEnvelope {
	seq: number;
	job_id: string;
	step_index: number;
	type: EventType;
	payload: TrialPayload | ScoringPayload | ProposalPayload | StepPayload | ErrorPayload;
}

export interface CatalogProject {
	name: string;
	programs: string[];
	metrics: string[];
	prompts: string[];
	datasets: string[];
}

export interface CatalogResponse {
	projects_root: string;
	projects: CatalogProject[];
}

export interface RunRequest {
	project: string;
	program: string;
	prompt: string;
	model: string;
	examples: string;
	workers: number;
	repeats: number;
}

export interface EvaluateRequest extends RunRequest {
	metrics: string[];
}

export interface OptimizeRequest extends EvaluateRequest {
	steps: number;
	proposer_model: string;
}

export interface JobManifest {
	job_id: string;
	kind: JobKind;
	status: JobStatus;
	started_at: string;
	finished_at?: string | null;
	project: string;
	program: string;
	prompt: string;
	examples: string;
	model: string;
	workers: number;
	repeats?: number;
	metrics?: string[];
	steps?: number;
	proposer_model?: string;
	dataset_sha256?: string;
	error?: string | null;
}

export interface JobListItem {
	job_id: string;
	kind: JobKind;
	status: JobStatus;
	started_at: string;
	finished_at: string | null;
	project: string;
	program: string;
	prompt: string;
	examples: string;
	model: string;
	workers: number;
	repeats: number;
	metrics: string[] | null;
	steps: number | null;
	proposer_model: string | null;
	error: string | null;
}

export interface AggregateStats {
	mean: number;
	sd: number;
	n: number;
}

export interface JobDetailResponse {
	manifest: Record<string, unknown>;
	events: EventEnvelope[];
	summary: JobSummary | null;
}

export interface JobSummary {
	job_id: string;
	kind: JobKind;
	trial_count: number;
	scoring_count: number;
	failure_rate: number;
	scoring_failure_rate: number;
	overall: AggregateStats | null;
	per_metric: Record<string, AggregateStats>;
	replicate_noise?: Record<string, AggregateStats>;
	telemetry: {
		input_tokens: number;
		output_tokens: number;
		latency: number;
		replicate_divergence?: AggregateStats | null;
	};
	steps?: Array<{
		step_index: number;
		score: number;
		prompt_template: string;
		summary: StepPayload['summary'];
	}>;
	best_step?: {
		step_index: number;
		score: number;
		prompt_template: string;
		summary: StepPayload['summary'];
	};
}

export interface TrialWithScorings {
	trial: TrialPayload;
	scorings: ScoringPayload[];
}

export interface StepSection {
	stepIndex: number;
	proposal: ProposalPayload | null;
	step: StepPayload | null;
	/** Group keys (`${stepIndex}:${example_id}`) in arrival order. */
	groupIds: string[];
	complete: boolean;
}

export interface LiveAggregates {
	trialTotal: number;
	trialSuccess: number;
	trialFailed: number;
	scoringTotal: number;
	scoringSuccess: number;
	scoringFailed: number;
	perMetricScores: Record<string, number[]>;
	inputTokens: number;
	outputTokens: number;
	latency: number;
}

export interface EventStoreState {
	manifest: JobManifest | null;
	status: JobStatus;
	errorMessage: string | null;
	trialsById: Map<string, TrialWithScorings>;
	/** Group key -> its replicate keys into `trialsById`, in arrival order. */
	groups: Map<string, string[]>;
	flatGroupIds: string[];
	steps: StepSection[];
	aggregates: LiveAggregates;
	summary: JobSummary | null;
	lastSeq: number;
	proposing: boolean;
}

export type Operation = JobKind;

export const THINKING_FIELDS: Array<{ key: keyof Thinking; label: string }> = [
	{ key: 'reinstate_goal', label: 'Reinstate goal' },
	{ key: 'trajectory_summary', label: 'Trajectory summary' },
	{ key: 'failure_analysis', label: 'Failure analysis' },
	{ key: 'what_works', label: 'What works' },
	{ key: 'what_hurts', label: 'What hurts' },
	{ key: 'improvement_hypothesis', label: 'Improvement hypothesis' },
	{ key: 'edit_plan', label: 'Edit plan' }
];
