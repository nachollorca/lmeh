import { PUBLIC_API_URL } from '$env/static/public';
import type {
	CatalogResponse,
	EvaluateRequest,
	JobDetailResponse,
	JobListItem,
	OptimizeRequest,
	RunRequest
} from '$lib/types';

const baseUrl = PUBLIC_API_URL.replace(/\/$/, '');
const API_PREFIX = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(`${baseUrl}${API_PREFIX}${path}`, init);
	if (!response.ok) {
		let detail = response.statusText;
		try {
			const body = await response.json();
			if (typeof body.detail === 'string') {
				detail = body.detail;
			}
		} catch {
			// ignore parse errors
		}
		throw new ApiError(response.status, detail);
	}
	if (response.status === 204) {
		return undefined as T;
	}
	return response.json() as Promise<T>;
}

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		message: string
	) {
		super(message);
		this.name = 'ApiError';
	}
}

export function apiBaseUrl(): string {
	return baseUrl;
}

export function fetchHealth(): Promise<{ status: string }> {
	return request('/health');
}

export function fetchCatalog(): Promise<CatalogResponse> {
	return request('/catalog');
}

export function fetchJobs(): Promise<{ jobs: JobListItem[] }> {
	return request('/jobs');
}

export function fetchJob(jobId: string): Promise<JobDetailResponse> {
	return request(`/jobs/${jobId}`);
}

export function deleteJob(jobId: string): Promise<void> {
	return request(`/jobs/${jobId}`, { method: 'DELETE' });
}

export function startRun(body: RunRequest): Promise<{ job_id: string }> {
	return request('/run', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
}

export function startEvaluate(body: EvaluateRequest): Promise<{ job_id: string }> {
	return request('/evaluate', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
}

export function startOptimize(body: OptimizeRequest): Promise<{ job_id: string }> {
	return request('/optimize', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
}
