<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSettings } from '../composables/useSettings.js'

const { t } = useSettings()

// -- State ----------------------------------------------------------------

const testInputParams = reactive({
	inputDataPath: 'xxx\\data_0',
})

const testMode = ref('restart')
const bitsPerSymbol = ref(8)
const hiValue = ref('')
const useBitsValue = ref('')
const verbose = ref(false)
const isRunning = ref(false)

let pollTimerId = null

const runtimeLogText = ref('')
const resultData = ref(null)
const activeResultTab = ref('summary')
const resultJson = ref('')

const progressTrackRef = ref(null)

// -- Computed --------------------------------------------------------------

const isRestart = computed(() => testMode.value === 'restart')
const isNonIID = computed(() => testMode.value === 'noniid')

const hasInputDataPath = computed(() => testInputParams.inputDataPath.trim().length > 0)
const hasRuntimeLogText = computed(() => runtimeLogText.value.trim().length > 0)
const hasTableResult = computed(() => detailTableRows.value.length > 0)

const testResult = computed(() => {
	const d = resultData.value
	if (!d) return null
	if (d.Restart_Test) return { mode: 'restart', raw: d.Restart_Test }
	if (d.IID_Test) return { mode: 'iid', raw: d.IID_Test }
	if (d.Non_IID_Test) return { mode: 'noniid', raw: d.Non_IID_Test }
	return null
})

const estimatorNames = {
	MCV: 'Most Common Value',
	Collision: 'Collision',
	Markov: 'Markov',
	Compression: 'Compression',
	't-Tuple': 't-Tuple',
	LRS: 'Longest Repeated Substring',
	MultiMCW: 'Multi Most Common in Window',
	Lag: 'Lag Prediction',
	MultiMMC: 'MultiMMC Prediction',
	LZ78Y: 'LZ78Y Prediction',
}

const detailTableRows = computed(() => {
	const tr = testResult.value
	if (!tr) return []

	if (tr.mode === 'restart') {
		return [
			{ key: 'H_I', name: 'H_I', english: 'H_min (Restart Entropy)', value: tr.raw.H_I },
			{ key: 'F', name: 'F', english: 'F (Fluctuation)', value: tr.raw.F },
			{ key: 'U', name: 'U', english: 'U (Uniformity)', value: tr.raw.U },
		]
	}

	if (tr.mode === 'iid') {
		return [
			{ key: 'IID', name: 'IID', english: 'IID Test Result', value: tr.raw.IID },
			{ key: 'min_entropy', name: 'H_min', english: 'min_entropy', value: tr.raw.min_entropy },
		]
	}

	if (tr.raw.details) {
		return Object.entries(tr.raw.details).map(([key, val]) => ({
			key,
			name: key,
			english: estimatorNames[key] || key,
			value: val,
		}))
	}

	return [{ key: 'min_entropy', name: 'H_min', english: 'min_entropy', value: tr.raw.min_entropy }]
})

const detailTableHeading = computed(() => {
	const mode = testResult.value?.mode
	if (mode === 'restart') return 'Restart 结果详情'
	if (mode === 'iid') return 'IID 结果详情'
	return 'Non-IID 估计器详情'
})

const detailTableValueHeader = computed(() => {
	const mode = testResult.value?.mode
	return mode === 'noniid' ? 'min_entropy' : '值'
})

const progressDisplay = computed(() => '0 %')
const startBtnText = computed(() => (isRunning.value ? '停止测试' : '开始测试'))

// -- Helpers ---------------------------------------------------------------

const formatNum = (val) => {
	if (val === null || val === undefined) return '-'
	const num = Number(val)
	return Number.isFinite(num) ? num.toFixed(4) : String(val)
}

const formatMode = (mode) => {
	return { restart: 'RESTART', iid: 'IID', noniid: 'NON-IID' }[mode] || '-'
}

const formatDurationMs = (elapsedMs) => {
	const ms = Math.max(0, Number(elapsedMs) || 0)
	if (ms < 1000) return `${ms.toFixed(1)} ms`
	const totalSeconds = ms / 1000
	if (totalSeconds < 60) return `${totalSeconds.toFixed(3)} s`
	const minutes = Math.floor(totalSeconds / 60)
	const seconds = totalSeconds % 60
	return `${minutes} min ${seconds.toFixed(3)} s`
}

const appendRuntimeLog = (message) => {
	const line = String(message ?? '').trimEnd()
	if (!line) return
	if (runtimeLogText.value.length === 0) {
		runtimeLogText.value = line
		return
	}
	runtimeLogText.value = `${runtimeLogText.value}\n${line}`
}

const clearInputDataPath = () => { testInputParams.inputDataPath = '' }
const clearRuntimeLogText = () => { runtimeLogText.value = '' }

const stopPolling = () => {
	if (pollTimerId !== null) {
		clearInterval(pollTimerId)
		pollTimerId = null
	}
}

// -- File handling ---------------------------------------------------------

async function handlePickFile() {
	try {
		const picked = await window.pywebview.api.pick_file()
		if (picked) {
			testInputParams.inputDataPath = picked
			appendRuntimeLog(`[INFO] 已选择文件: ${picked}`)
		}
	} catch (error) {
		appendRuntimeLog(`[WARN] 选择文件取消或失败: ${error?.message ?? error}`)
	}
}

// -- Validation ------------------------------------------------------------

function validate() {
	if (!testInputParams.inputDataPath.trim()) return t('est.err.noFile')
	const ext = testInputParams.inputDataPath.trim().split('.').pop()?.toLowerCase()
	if (!['bin', 'dat', 'raw'].includes(ext)) return '不支持的文件格式，请选择 .bin / .dat / .raw 文件'
	if (!testMode.value) return t('est.err.noMode')
	if (isRestart.value) {
		const hi = parseFloat(hiValue.value)
		if (isNaN(hi) || hi < 0) return t('est.err.hiRequired')
	}
	const bps = parseInt(bitsPerSymbol.value, 10)
	if (isNaN(bps) || bps < 1 || bps > 8) return t('est.err.bpsRange')
	if (isNonIID.value && useBitsValue.value) {
		const ub = parseInt(useBitsValue.value, 10)
		if (isNaN(ub) || ub < 1) return t('est.err.ubRange')
	}
	return null
}

// -- Mode switch -----------------------------------------------------------

function onModeChange() {
	hiValue.value = ''
	useBitsValue.value = ''
	resultData.value = null
	resultJson.value = ''
}

// -- Result export ---------------------------------------------------------

async function exportResults() {
	if (!resultJson.value) return
	try {
		if (!window.pywebview?.api) {
			appendRuntimeLog('[ERROR] pywebview API 不可用')
			return
		}
		const path = await window.pywebview.api.save_file('entropy_result.json')
		if (!path) return
		await window.pywebview.api.export_results_file(resultJson.value, path)
		appendRuntimeLog('[INFO] 结果已导出: ' + path)
	} catch (err) {
		appendRuntimeLog('[ERROR] 导出失败: ' + (err?.message ?? err))
	}
}

// -- Test execution --------------------------------------------------------

async function handleStartTest() {
	if (isRunning.value) {
		stopPolling()
		isRunning.value = false
		appendRuntimeLog('[INFO] 已停止测试')
		try {
			window.pywebview?.api?.cleanup_entropy_test?.()
		} catch (_) { /* best-effort */ }
		return
	}

	const err = validate()
	if (err) {
		appendRuntimeLog(`[ERROR] ${err}`)
		return
	}

	resultData.value = null
	resultJson.value = ''

	try {
		if (!window.pywebview?.api) {
			appendRuntimeLog('[ERROR] pywebview API 不可用，请在桌面应用中运行')
			return
		}

		const payload = {
			datafile: testInputParams.inputDataPath.trim(),
			bits_per_symbol: parseInt(bitsPerSymbol.value, 10) || 8,
			mode: testMode.value,
			verbose: verbose.value,
		}
		if (isRestart.value) payload.h_i = parseFloat(hiValue.value) || null
		if (isNonIID.value) payload.use_bits = parseInt(useBitsValue.value, 10) || null

		const resp = await window.pywebview.api.start_entropy_test(payload)
		if (!resp.ok) {
			appendRuntimeLog(`[ERROR] ${resp.error}`)
			return
		}
	} catch (e) {
		appendRuntimeLog(`[ERROR] 启动测试失败: ${e?.message ?? e}`)
		return
	}

	isRunning.value = true
	const requestStartPerf = performance.now()

	appendRuntimeLog(`[INFO] 开始提交参数并执行测试... (${new Date().toLocaleString()})`)
	appendRuntimeLog(`[INFO] 模式: ${formatMode(testMode.value)}, bits_per_symbol: ${bitsPerSymbol.value}`)
	appendRuntimeLog('[INFO] 实时输出如下:')

	pollTimerId = setInterval(async () => {
		try {
			const poll = await window.pywebview.api.poll_entropy_test()

			for (const msg of poll.logs) {
				if (msg.type === 'log') {
					appendRuntimeLog(msg.line)
				} else if (msg.type === 'error') {
					appendRuntimeLog(`[ERROR] ${msg.message}`)
				} else if (msg.type === 'result') {
					resultJson.value = JSON.stringify(msg.data, null, 2)
					if (msg.data.data) resultData.value = msg.data.data
					appendRuntimeLog('[INFO] 测试完成')
				}
			}

			if (!poll.running) {
				stopPolling()
				const elapsedMs = performance.now() - requestStartPerf
				appendRuntimeLog(`[INFO] 总测试时间: ${formatDurationMs(elapsedMs)}`)
				isRunning.value = false
				// Tell backend to release all held memory (queue, result, datasets)
				window.pywebview?.api?.cleanup_entropy_test?.()
			}
		} catch (e) {
			stopPolling()
			appendRuntimeLog(`[ERROR] 轮询失败: ${e?.message ?? e}`)
			isRunning.value = false
		}
	}, 200)
}

// -- Lifecycle -------------------------------------------------------------

onMounted(async () => {
	try {
		const settings = await window.pywebview?.api?.get_settings?.() || {}
		if (settings.mode) testMode.value = settings.mode
		if (settings.bits_per_symbol) bitsPerSymbol.value = settings.bits_per_symbol
	} catch (e) {
		console.warn('Failed to initialize settings:', e)
	}
})

onBeforeUnmount(() => {
	stopPolling()
})
</script>

<template>
	<section class="est-main">
		<!-- Left: 结果汇总 -->
		<div class="summary_panel">
			<header class="summary_title">
				<span class="summary_dot" />
				<h2>结果汇总:</h2>
				<div v-if="hasTableResult" class="summary_actions">
					<button class="summary_action_btn" type="button"
						@click="activeResultTab = activeResultTab === 'json' ? 'summary' : 'json'">
						{{ activeResultTab === 'json' ? '收起 JSON' : '展开 JSON' }}
					</button>
					<button class="summary_action_btn primary" type="button" @click="exportResults">结果导出</button>
				</div>
			</header>

			<div v-if="testResult && detailTableRows.length > 0" class="detail_section">
				<div class="detail_table_wrap">
					<table class="detail_table">
						<thead>
							<tr>
								<th>估计器</th>
								<th>英文名</th>
								<th>{{ detailTableValueHeader }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in detailTableRows" :key="row.key"
								:class="{ 'row-min': row.value === Math.min(...detailTableRows.map(r => Number(r.value))) }">
								<td>{{ row.name }}</td>
								<td>{{ row.english }}</td>
								<td>{{ typeof row.value === 'boolean' ? (row.value ? '通过' : '未通过') :
									formatNum(row.value) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>

			<div v-if="resultJson" class="json_output_row">
				<div v-show="activeResultTab === 'json'" class="json_output_wrap">
					<pre>{{ resultJson }}</pre>
				</div>
			</div>
		</div>

		<!-- Right: 控制面板 -->
		<div class="control_panel">
			<!-- Mode selector + verbose -->
			<div class="selectors_row">
				<div class="field_pair selector_pair">
					<label>测试模式</label>
					<select v-model="testMode" @change="onModeChange">
						<option value="restart">Restart</option>
						<option value="iid">IID</option>
						<option value="noniid">Non-IID</option>
					</select>
				</div>
				<label class="verbose_toggle" :title="t('est.verbose.desc') || '启用详细输出，显示每个估计器的计算过程'">
					<input v-model="verbose" type="checkbox" />
					<span class="verbose_toggle_track">
						<span class="verbose_toggle_thumb" />
					</span>
					<span class="verbose_toggle_label">verbose</span>
				</label>
			</div>

			<!-- Parameters: bps / h_i / use_bits -->
			<div class="threshold_row">
				<div class="field_pair">
					<label>
						bps
						<span class="param_tooltip">{{ t('est.bps.desc') }}</span>
					</label>
					<input v-model.number="bitsPerSymbol" type="number" :min="1" :max="8" step="1" />
				</div>
				<div class="field_pair" :class="{ disabled: !isRestart }">
					<label>
						h_i
						<span class="param_tooltip">{{ t('est.hi.desc') }} Restart 模式下必填。</span>
					</label>
					<input v-model="hiValue" type="number" min="0" step="0.01" :disabled="!isRestart" />
				</div>
				<div class="field_pair" :class="{ disabled: !isNonIID }">
					<label>
						use_bits
						<span class="param_tooltip">{{ t('est.ub.desc') }} Non-IID 模式下可选。</span>
					</label>
					<input v-model="useBitsValue" type="number" min="1" step="1" :disabled="!isNonIID" />
				</div>
			</div>

			<!-- File selection -->
			<div class="path_row">
				<button class="pick_btn" type="button" @click="handlePickFile">选择文件</button>
				<div class="selected_path_input_wrap">
					<input v-model="testInputParams.inputDataPath" type="text" />
					<span v-if="hasInputDataPath" class="clear_hint" @click="clearInputDataPath">清除</span>
				</div>
			</div>

			<!-- Progress + Start button -->
			<div class="action_progress_row">
				<div ref="progressTrackRef" class="progress_track">
					<div class="progress_fill" />
					<span>{{ progressDisplay }}</span>
				</div>
				<button class="start_btn" :class="{ 'is-running': isRunning }" type="button" @click="handleStartTest">
					{{ startBtnText }}
				</button>
			</div>

			<!-- Terminal output -->
			<div class="terminal_output_row">
				<div class="terminal_output_wrap">
					<textarea class="terminal_output_box" :value="runtimeLogText" wrap="off" readonly
						spellcheck="false" />
					<span v-if="hasRuntimeLogText" class="clear_output_hint" @click="clearRuntimeLogText">清除</span>
				</div>
			</div>
		</div>
	</section>
</template>

<style scoped>
/* -- Page root ---------------------------------------------------------- */

.est-main {
	--wails-draggable: no-drag;
	display: grid;
	grid-template-columns: minmax(0, 4fr) minmax(0, 6fr);
	gap: clamp(8px, 1vw, 14px);
	width: 100%;
	height: 100%;
	min-width: 0;
	padding: clamp(8px, 1vw, 14px);
	box-sizing: border-box;
	overflow: hidden;
	overscroll-behavior: contain;
	background: var(--rt-main-bg-solid);
	color: var(--rt-main-text);
	font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei", sans-serif;
}

/* -- Shared panel ------------------------------------------------------- */

.summary_panel,
.control_panel {
	min-width: 0;
	min-height: 0;
	padding: clamp(10px, 1vw, 14px);
	box-sizing: border-box;
	border: 1px solid var(--panel-border);
	border-radius: 14px;
	background: var(--rt-panel-bg-solid);
	box-shadow: none;
}

/* -- Left summary panel ------------------------------------------------- */

.summary_panel {
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.summary_title {
	--wails-draggable: no-drag;
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 8px;
	overflow: hidden;
	overscroll-behavior: none;
	touch-action: none;
}

.summary_dot {
	width: 10px;
	height: 10px;
	border-radius: 3px;
	background: linear-gradient(135deg, var(--rt-title-dot-start), var(--rt-title-dot-end));
	box-shadow: 0 0 8px var(--rt-title-dot-shadow);
}

.summary_title h2 {
	margin: 0;
	color: var(--rt-title-text);
	font-size: clamp(18px, 1.5vw, 26px);
	font-weight: 700;
	line-height: 1;
	letter-spacing: 0.2px;
}

.summary_actions {
	margin-left: auto;
	display: flex;
	align-items: center;
	gap: 6px;
	flex-shrink: 0;
}

.summary_action_btn {
	height: 28px;
	padding: 0 10px;
	border: 1px solid var(--field-border);
	border-radius: 8px;
	background: var(--field-bg);
	color: var(--rt-open-file-hint-text);
	font-size: clamp(11px, 0.8vw, 13px);
	font-weight: 600;
	cursor: pointer;
	white-space: nowrap;
	transition: opacity 0.16s ease, filter 0.16s ease;
}

.summary_action_btn:hover {
	filter: brightness(1.12);
}

.summary_action_btn.primary {
	border-color: var(--rt-start-btn-border);
	background: linear-gradient(180deg, var(--rt-start-btn-bg-start), var(--rt-start-btn-bg-end));
	color: var(--rt-start-btn-text);
}

.summary_action_btn.primary:hover {
	filter: brightness(1.06) saturate(1.04);
}

/* -- Detail table ------------------------------------------------------- */

.detail_section {
	flex: 1 1 0;
	min-height: 0;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.detail_section h3 {
	margin: 0 0 6px;
	font-size: clamp(12px, 0.85vw, 14px);
	font-weight: 700;
	color: var(--rt-title-dot-start);
	flex-shrink: 0;
}

.detail_table_wrap {
	overflow: auto;
	border: 1px solid var(--rt-table-wrap-border);
	background: var(--rt-table-wrap-bg);
	scrollbar-width: thin;
	scrollbar-color: var(--rt-table-scroll-thumb) var(--rt-table-scroll-track);
	flex: 1 1 0;
	min-height: 0;
}

.detail_table {
	width: 100%;
	min-width: 360px;
	border-collapse: collapse;
	font-size: clamp(10px, 0.72vw, 12px);
}

.detail_table th,
.detail_table td {
	height: clamp(22px, 1.9vh, 26px);
	padding: 0 6px;
	border: 1px solid var(--rt-table-cell-border);
	background: var(--rt-table-cell-bg);
	text-align: center;
	vertical-align: middle;
	white-space: nowrap;
}

.detail_table th {
	position: sticky;
	top: 0;
	z-index: 4;
	background: var(--rt-table-head-bg);
	color: var(--rt-table-head-text);
	font-weight: 700;
}

.detail_table .row-min {
	background: var(--rt-table-head-bg);
	font-weight: 700;
}

/* -- Right control panel ------------------------------------------------ */

.control_panel {
	--action-btn-width: 110px;
	--pair-label-width: 12.5ch;
	--pair-value-width: 12.5ch;
	--row-block-gap: 8px;
	--row-inline-gap: clamp(8px, 0.85vw, 12px);
	display: flex;
	flex-direction: column;
	gap: clamp(12px, 1.45vh, 20px);
	width: auto;
	height: 100%;
	overflow: hidden;
	scrollbar-width: thin;
	scrollbar-color: var(--rt-scroll-thumb) var(--rt-scroll-track);
}

.control_panel::-webkit-scrollbar {
	width: 8px;
	height: 8px;
}

.control_panel::-webkit-scrollbar-track {
	border-radius: 6px;
	background: var(--rt-scroll-track);
}

.control_panel::-webkit-scrollbar-thumb {
	border-radius: 6px;
	background: var(--rt-scroll-thumb);
}

.control_panel::-webkit-scrollbar-thumb:hover {
	background: var(--rt-scroll-thumb-hover);
}

/* -- Shared form primitives --------------------------------------------- */

.threshold_row,
.selectors_row,
.path_row,
.terminal_output_row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: var(--row-inline-gap);
	row-gap: var(--row-block-gap);
}

/* -- Threshold row (bps / h_i / use_bits) ------------------------------ */

.threshold_row {
	justify-content: flex-start;
	flex-wrap: nowrap;
	column-gap: clamp(8px, 0.85vw, 14px);
}

.threshold_row .field_pair {
	flex: 1 1 0;
	min-width: 0;
}

.threshold_row .field_pair input {
	width: 100%;
	min-width: 0;
}

.threshold_row .field_pair.disabled {
	opacity: 0.4;
	pointer-events: none;
}

.field_pair {
	display: flex;
	flex: 0 0 auto;
	align-items: center;
	gap: var(--row-inline-gap);
}

.field_pair input {
	width: var(--pair-value-width);
}

.field_pair label {
	display: flex;
	flex: 0 0 auto;
	align-items: center;
	justify-content: center;
	position: relative;
	width: var(--pair-label-width);
	height: 30px;
	min-width: 0;
	padding: 0 10px;
	box-sizing: border-box;
	border: 1px solid var(--label-border);
	border-radius: 9px;
	background: var(--label-bg);
	color: var(--label-text);
	font-size: clamp(12px, 0.9vw, 14px);
	font-weight: 600;
	text-align: center;
}

/* -- Floating tooltip --------------------------------------------------- */

.field_pair label .param_tooltip {
	display: none;
	position: absolute;
	top: calc(100% + 6px);
	left: 0;
	z-index: 20;
	width: max-content;
	max-width: 260px;
	padding: 8px 10px;
	border: 1px solid var(--panel-border);
	border-radius: 8px;
	background: var(--rt-panel-bg-solid);
	box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
	color: var(--rt-meta-text);
	font-size: 12px;
	font-weight: 400;
	line-height: 1.5;
	text-align: left;
	white-space: normal;
	pointer-events: none;
}

.field_pair label:hover .param_tooltip {
	display: block;
}

/* -- Input & select primitives ------------------------------------------ */

.control_panel input,
.control_panel select {
	height: 30px;
	padding: 0 10px;
	box-sizing: border-box;
	border: 1px solid var(--field-border);
	border-radius: 10px;
	background: var(--field-bg);
	color: var(--field-text);
	font-size: clamp(12px, 0.9vw, 14px);
	outline: none;
	transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.control_panel input::placeholder {
	color: var(--field-placeholder);
}

.control_panel input[type="number"]::-webkit-inner-spin-button,
.control_panel input[type="number"]::-webkit-outer-spin-button {
	-webkit-appearance: none;
	margin: 0;
}

.control_panel input[type="number"] {
	-moz-appearance: textfield;
	appearance: textfield;
}

.control_panel input:focus,
.control_panel select:focus {
	border-color: var(--focus-border);
	box-shadow: 0 0 0 2px var(--focus-ring);
}

/* -- Verbose toggle switch ---------------------------------------------- */

.verbose_toggle {
	display: inline-flex;
	align-items: center;
	gap: 8px;
	flex: 1 1 0;
	min-width: 0;
	padding: 0 10px;
	height: 30px;
	border: 1px solid var(--label-border);
	border-radius: 9px;
	background: var(--label-bg);
	cursor: pointer;
	user-select: none;
	box-sizing: border-box;
	transition: border-color 0.16s ease, background 0.16s ease;
}

.verbose_toggle:hover {
	border-color: var(--focus-border);
	background: rgba(79, 142, 247, 0.06);
}

.verbose_toggle input[type="checkbox"] {
	position: absolute;
	width: 0;
	height: 0;
	opacity: 0;
	pointer-events: none;
}

.verbose_toggle_track {
	position: relative;
	flex: 0 0 auto;
	width: 32px;
	height: 18px;
	border-radius: 9px;
	background: #c4c9d4;
	transition: background 0.2s ease;
}

.verbose_toggle input[type="checkbox"]:checked+.verbose_toggle_track {
	background: var(--focus-border);
}

.verbose_toggle_thumb {
	position: absolute;
	top: 2px;
	left: 2px;
	width: 14px;
	height: 14px;
	border-radius: 50%;
	background: #ffffff;
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
	transition: transform 0.2s ease;
}

.verbose_toggle input[type="checkbox"]:checked+.verbose_toggle_track .verbose_toggle_thumb {
	transform: translateX(14px);
}

.verbose_toggle_label {
	flex: 0 0 auto;
	color: var(--label-text);
	font-size: clamp(12px, 0.9vw, 14px);
	font-weight: 600;
	line-height: 1;
}

/* -- Selectors row (mode + verbose) ------------------------------------- */

.selectors_row {
	justify-content: flex-start;
	flex-wrap: nowrap;
	column-gap: clamp(8px, 0.85vw, 14px);
	width: 100%;
}

.selector_pair {
	flex: 1 1 0;
	min-width: 0;
}

.selector_pair select {
	width: 100%;
	min-width: 0;
	height: 30px;
	padding-right: 24px;
	font-size: clamp(12px, 0.9vw, 14px);
	background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%23DAE6FB' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
	background-repeat: no-repeat;
	background-position: right 8px center;
	background-size: 12px 8px;
	appearance: none;
	-webkit-appearance: none;
	-moz-appearance: none;
}

.control_panel select::-ms-expand {
	display: none;
}

select option {
	background-color: var(--select-option-bg);
	color: var(--select-option-text);
}

select option:checked {
	background-color: var(--select-option-bg);
	color: var(--select-option-text);
}

select option:hover {
	background-color: var(--select-option-selected-bg);
	color: var(--select-option-selected-text);
}

/* -- Path row ----------------------------------------------------------- */

.path_row {
	justify-content: flex-start;
}

.path_row input {
	flex: 1;
	min-width: 0;
}

.selected_path_input_wrap {
	position: relative;
	flex: 1;
	min-width: 0;
}

.selected_path_input_wrap input {
	width: 100%;
	padding-right: 58px;
}

.clear_hint {
	position: absolute;
	top: 50%;
	right: 12px;
	transform: translateY(-50%);
	opacity: 0;
	pointer-events: auto;
	color: var(--rt-open-file-hint-text);
	font-size: clamp(11px, 0.8vw, 13px);
	font-weight: 600;
	white-space: nowrap;
	cursor: pointer;
	transition: opacity 0.16s ease;
}

.selected_path_input_wrap:hover .clear_hint,
.selected_path_input_wrap:focus-within .clear_hint {
	opacity: 0.82;
}

/* -- Action progress row ----------------------------------------------- */

.action_progress_row {
	display: flex;
	align-items: center;
	gap: var(--row-inline-gap);
}

.action_progress_row .start_btn {
	flex: 0 0 auto;
}

.action_progress_row .progress_track {
	flex: 1;
	min-width: 0;
}

/* -- Buttons ----------------------------------------------------------- */

.pick_btn,
.start_btn {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	width: var(--action-btn-width);
	min-width: var(--action-btn-width);
	height: 32px;
	padding: 0 16px;
	border: 1px solid var(--btn-border);
	border-radius: 10px;
	background: linear-gradient(180deg, var(--btn-bg-start), var(--btn-bg-end));
	box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2);
	color: var(--btn-text);
	font-size: clamp(12px, 0.95vw, 15px);
	font-weight: 600;
	line-height: 1;
	white-space: nowrap;
	cursor: pointer;
	transition: all 0.16s ease;
}

.pick_btn:hover,
.start_btn:hover {
	filter: brightness(1.12);
}

.start_btn {
	height: 34px;
	border-color: var(--rt-start-btn-border);
	background: linear-gradient(180deg, var(--rt-start-btn-bg-start), var(--rt-start-btn-bg-end));
	box-shadow:
		inset 0 1px 0 rgba(255, 255, 255, 0.36),
		0 0 0 1px rgba(255, 255, 255, 0.08),
		0 6px 14px var(--rt-start-btn-shadow);
	color: var(--rt-start-btn-text);
	text-shadow: none;
}

.start_btn:hover {
	filter: brightness(1.06) saturate(1.04);
	box-shadow:
		inset 0 1px 0 rgba(255, 255, 255, 0.42),
		0 0 0 1px rgba(255, 255, 255, 0.08),
		0 8px 18px var(--rt-start-btn-shadow);
}

.start_btn.is-running {
	border-color: var(--rt-stop-btn-border);
	background: linear-gradient(180deg, var(--rt-stop-btn-bg-start), var(--rt-stop-btn-bg-end));
	box-shadow:
		inset 0 1px 0 rgba(255, 255, 255, 0.3),
		0 0 0 1px rgba(255, 255, 255, 0.08),
		0 6px 14px var(--rt-stop-btn-shadow);
	color: var(--rt-stop-btn-text);
}

.start_btn.is-running:hover {
	filter: brightness(1.05) saturate(1.03);
	box-shadow:
		inset 0 1px 0 rgba(255, 255, 255, 0.36),
		0 0 0 1px rgba(255, 255, 255, 0.08),
		0 8px 18px var(--rt-stop-btn-shadow);
}

/* -- Progress track ---------------------------------------------------- */

.progress_track {
	position: relative;
	display: flex;
	align-items: center;
	height: 30px;
	overflow: hidden;
	border: 1px solid var(--rt-progress-track-border);
	border-radius: 10px;
	background: var(--rt-progress-track-bg);
}

.progress_fill {
	position: relative;
	width: var(--rt-progress-width, 0%);
	height: 100%;
	overflow: hidden;
	background: linear-gradient(90deg, var(--rt-progress-fill-start), var(--rt-progress-fill-end));
	background-size: 220% 100%;
	animation: progressGradientShift 1.5s linear infinite;
	transition: width 0.2s ease;
}

.progress_fill::after {
	position: absolute;
	inset: 0;
	content: '';
	transform: translateX(-100%);
	background: linear-gradient(100deg, rgba(255, 255, 255, 0) 15%, rgba(255, 255, 255, 0.28) 50%, rgba(255, 255, 255, 0) 85%);
	animation: progressGlowSweep 1.8s ease-in-out infinite;
}

.progress_track span {
	position: absolute;
	left: 50%;
	transform: translateX(-50%);
	color: var(--rt-progress-text);
	font-size: clamp(12px, 0.95vw, 14px);
	font-weight: 700;
	text-shadow: var(--rt-progress-text-shadow);
}

/* -- Terminal output row ----------------------------------------------- */

.terminal_output_row {
	display: block;
	flex: 1 1 auto;
	align-items: stretch;
	min-height: 120px;
}

.terminal_output_wrap {
	position: relative;
	width: 100%;
	height: 100%;
	min-height: 120px;
}

.terminal_output_box {
	width: 100%;
	height: 100%;
	min-height: 120px;
	margin: 0;
	padding: 8px 10px;
	box-sizing: border-box;
	overflow-x: auto;
	overflow-y: auto;
	resize: none;
	border: 1px solid var(--rt-output-border);
	border-radius: 10px;
	background: var(--rt-output-bg);
	color: var(--rt-output-text);
	font-family: Consolas, "Courier New", monospace;
	font-size: 12px;
	line-height: 1.45;
	text-align: left;
	white-space: pre;
	overflow-wrap: normal;
	word-break: normal;
	cursor: text;
	user-select: text;
	scrollbar-width: thin;
	scrollbar-color: var(--rt-scroll-thumb) var(--rt-scroll-track-transparent);
}

.terminal_output_box::-webkit-scrollbar {
	width: 8px;
	height: 8px;
}

.terminal_output_box::-webkit-scrollbar-track {
	border-radius: 10px;
	background: var(--rt-scroll-track-transparent);
}

.terminal_output_box::-webkit-scrollbar-thumb {
	border: 1px solid transparent;
	border-radius: 10px;
	background: var(--rt-scroll-thumb);
	background-clip: padding-box;
}

.clear_output_hint {
	position: absolute;
	top: 10px;
	right: 12px;
	opacity: 0;
	pointer-events: auto;
	color: var(--rt-open-file-hint-text);
	font-size: clamp(11px, 0.8vw, 13px);
	font-weight: 600;
	white-space: nowrap;
	cursor: pointer;
	user-select: none;
	transition: opacity 0.16s ease;
}

.terminal_output_wrap:hover .clear_output_hint,
.terminal_output_wrap:focus-within .clear_output_hint {
	opacity: 0.82;
}

/* -- JSON output ------------------------------------------------------- */

.json_output_row {
	flex-shrink: 0;
	max-height: 200px;
}

.json_output_wrap {
	height: 100%;
	overflow: auto;
	padding: 10px;
	border: 1px solid var(--rt-output-border);
	border-radius: 10px;
	background: var(--rt-output-bg);
	scrollbar-width: thin;
	scrollbar-color: var(--rt-scroll-thumb) var(--rt-scroll-track-transparent);
	box-sizing: border-box;
}

.json_output_wrap pre {
	margin: 0;
	font-family: Consolas, "Courier New", monospace;
	font-size: 11px;
	line-height: 1.45;
	color: var(--rt-output-text);
	white-space: pre-wrap;
	word-break: break-all;
}

/* -- Animations -------------------------------------------------------- */

@keyframes progressGradientShift {
	0% {
		background-position: 0% 50%;
	}

	100% {
		background-position: 100% 50%;
	}
}

@keyframes progressGlowSweep {
	0% {
		transform: translateX(-100%);
	}

	100% {
		transform: translateX(130%);
	}
}

/* -- Responsive -------------------------------------------------------- */

@media (max-width: 820px) {
	.est-main {
		grid-template-columns: minmax(0, 4fr) minmax(0, 6fr);
		min-width: 0;
		padding: 8px;
	}

	.path_row input {
		min-width: 130px;
	}

	.start_btn,
	.pick_btn {
		height: 32px;
		padding: 0 12px;
	}

	.terminal_output_row,
	.terminal_output_box {
		min-height: 96px;
	}
}
</style>
