<script lang="ts">
	import JsonView from './JsonView.svelte';

	interface Props {
		value: unknown;
		/** When false this node is rendered as a key: value pair row. */
		root?: boolean;
		key?: string;
	}

	let { value, root = true, key }: Props = $props();

	const isContainer = $derived(typeof value === 'object' && value !== null);
	const isArr = $derived(Array.isArray(value));

	// ponytail: containers with ≤2 entries stay open by default; larger collapse.
	// `value` is fixed per node instance, so a one-shot computation is fine.
	const initialOpen =
		typeof value !== 'object' || value === null
			? true
			: (Array.isArray(value) ? value.length : Object.keys(value).length) <= 2;
	let open = $state(initialOpen);

	function entries(v: unknown): [string, unknown][] {
		if (Array.isArray(v)) return (v as unknown[]).map((item, i) => [String(i), item]);
		if (v && typeof v === 'object') return Object.entries(v as Record<string, unknown>);
		return [];
	}

	function count(v: unknown): number {
		return Array.isArray(v) ? v.length : v && typeof v === 'object' ? Object.keys(v).length : 0;
	}

	function summary(v: unknown): string {
		return Array.isArray(v) ? `Array(${count(v)})` : `{${count(v)}}`;
	}

	function scalar(v: unknown): string {
		if (typeof v === 'string') return JSON.stringify(v);
		if (v === null) return 'null';
		return String(v);
	}

	function scalarClass(v: unknown): string {
		if (typeof v === 'string') return 's-str';
		if (typeof v === 'number') return 's-num';
		if (typeof v === 'boolean') return 's-bool';
		if (v === null) return 's-null';
		return '';
	}
</script>

{#if !isContainer}
	{#if root}
		<span class="scalar {scalarClass(value)}">{scalar(value)}</span>
	{:else}
		<div class="row">
			<span class="key">{JSON.stringify(key)}</span>
			<span class="colon">:</span>
			<span class="scalar {scalarClass(value)}">{scalar(value)}</span>
		</div>
	{/if}
{:else if root}
	<div class="node">
		<button type="button" class="toggle" onclick={() => (open = !open)} aria-expanded={open}>
			<span class="chev">{open ? '▾' : '▸'}</span>
			<span class="bracket">{isArr ? '[' : '{'}</span>
			{#if !open}<span class="summary">{summary(value)}</span>{/if}
		</button>
		{#if open}
			<div class="children">
				{#each entries(value) as [k, v] (k)}
					<JsonView value={v} root={false} key={k} />
				{/each}
			</div>
			<div class="bracket close">{isArr ? ']' : '}'}</div>
		{/if}
	</div>
{:else}
	<div class="node">
		<div class="row">
			<button
				type="button"
				class="toggle inline"
				onclick={() => (open = !open)}
				aria-expanded={open}
			>
				<span class="chev">{open ? '▾' : '▸'}</span>
				<span class="key">{isArr ? key : JSON.stringify(key)}</span>
				<span class="colon">:</span>
				<span class="bracket">{isArr ? '[' : '{'}</span>
				{#if !open}<span class="summary">{summary(value)}</span>{/if}
			</button>
		</div>
		{#if open}
			<div class="children">
				{#each entries(value) as [k, v] (k)}
					<JsonView value={v} root={false} key={k} />
				{/each}
			</div>
			<div class="bracket close">{isArr ? ']' : '}'}</div>
		{/if}
	</div>
{/if}

<style>
	.node {
		display: block;
	}

	.toggle {
		display: inline-flex;
		align-items: baseline;
		gap: 2px;
		border: none;
		background: transparent;
		padding: 0;
		font-family: var(--font-mono);
		font-size: 12px;
		line-height: 18px;
		color: var(--text);
		cursor: pointer;
		text-align: left;
	}

	.toggle:hover .bracket,
	.toggle:hover .key {
		color: var(--accent-purple);
	}

	.chev {
		color: var(--muted);
		font-size: 9px;
	}

	.bracket {
		color: var(--muted);
	}

	.close {
		margin-left: 0;
	}

	.summary {
		color: var(--muted);
		opacity: 0.7;
		margin: 0 2px;
	}

	.children {
		padding-left: var(--space-md);
		border-left: 1px dotted var(--border);
		margin: 1px 0 1px 4px;
	}

	.row {
		display: block;
		line-height: 18px;
	}

	.key {
		color: var(--slate-700);
	}

	.colon {
		color: var(--muted);
		margin: 0 4px 0 2px;
	}

	.scalar {
		color: var(--text);
	}

	.s-str {
		color: var(--success);
	}

	.s-num {
		color: var(--accent-teal);
	}

	.s-bool {
		color: var(--accent-purple);
	}

	.s-null {
		color: var(--muted);
		opacity: 0.7;
	}
</style>
