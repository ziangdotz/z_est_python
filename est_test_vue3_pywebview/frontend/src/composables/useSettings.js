import { ref } from 'vue'

const theme = ref('dark')

const hasApi = () => {
	return !!(window.pywebview && window.pywebview.api)
}

function applyTheme() {
	const t = theme.value === 'system'
		? (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light')
		: theme.value
	document.documentElement.setAttribute('data-theme', t)
}

/* Apply default theme immediately so CSS matches on first paint */
applyTheme()

async function loadAllSettings() {
	if (!hasApi()) return
	try {
		const settings = await window.pywebview.api.get_settings()
		if (settings && settings.theme) {
			theme.value = settings.theme
			applyTheme()
		}
	} catch (e) {
		console.warn('Failed to load settings:', e)
	}
}

const translations = {
	zh: {
		'app.title': 'NIST SP800-90B 熵评估工具',
		'nav.est': '熵评估',
		'nav.about': '关于',
		'est.mode': '测试模式',
		'est.restart': 'Restart',
		'est.iid': 'IID',
		'est.noniid': 'Non-IID',
		'est.file': '选择文件',
		'est.start': '开始测试',
		'est.stop': '停止测试',
		'est.running': '正在执行熵评估...',
		'est.apiAddr': '测试地址',
		'est.updateAddr': '更新地址',
		'est.params': '参数配置',
		'est.bps': 'bits_per_symbol（符号位宽）',
		'est.bps.desc': '每个采样值使用的比特数，范围 1~8，默认 8',
		'est.hi': 'H_I（初始熵估值）',
		'est.hi.desc': 'Restart 测试需要验证的目标初始最小熵估计值',
		'est.hi.placeholder': '例如 7.99',
		'est.ub': 'use_bits（位级分析）',
		'est.ub.desc': '仅使用每个采样的最低 N 位进行测试',
		'est.ub.placeholder': '例如 1',
		'est.verbose': 'verbose（详细输出）',
		'est.verbose.desc': '启用后将在结果中输出更详细的测试过程信息',
		'est.result': '熵评估结果',
		'est.summary': '汇总',
		'est.json': 'JSON',
		'est.tab.mode': '测试模式',
		'est.tab.status': '测试状态',
		'est.tab.hmin': 'H_min（最小熵）',
		'est.tab.detail': '详情 / 参数',
		'est.tab.note': '备注',
		'est.noniid.detail': 'Non-IID 各估计器明细',
		'est.pass': '通过',
		'est.fail': '失败',
		'est.complete': '熵评估完成。',
		'est.aborted': '测试已由用户中止。',
		'est.err.noFile': '每次必须且只能选择 1 个文件。',
		'est.err.noMode': '请选择一项测试模式（Restart / IID / Non-IID）。',
		'est.err.hiRequired': 'Restart 测试需要填写有效的初始熵估值 H_I（≥ 0）。',
		'est.err.bpsRange': '符号位宽 bits_per_symbol 必须在 1~8 之间。',
		'est.err.ubRange': 'use_bits 必须为 ≥ 1 的整数。',
		'est.err.fetchFailed': '请求失败，请确认后端已启动并可访问',
		'est.err.serverEmpty': '服务端返回空响应，请检查后端日志。',
		'est.err.serverNonJson': '服务端返回了非 JSON 内容，请确认测试地址。',
		'est.err.serverHttp': '请求失败。',
		'about.title': '关于',
		'about.appName': 'NIST SP800-90B 熵评估工具',
		'about.version': '版本',
		'about.desc': '支持 Restart、IID、Non-IID 三种熵评估模式，基于 NIST SP800-90B 标准',
		'about.tech': '技术栈：Vue 3 + pywebview + Python + FastAPI',
		'about.standard': 'NIST SP800-90B（January 2018）',
	}
}

function t(key) {
	return translations.zh[key] || key
}

export function useSettings() {
	return { t }
}

/* Called from Python backend via evaluate_js when user toggles theme in system tray */
window.setThemeFromTray = (newTheme) => {
	theme.value = newTheme
	applyTheme()
}

export { theme, applyTheme, loadAllSettings }
