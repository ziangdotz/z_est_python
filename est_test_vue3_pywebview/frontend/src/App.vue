
<script setup>
import { ref, onMounted } from 'vue'
import EstMain from './components/EstMain.vue'
import About from './components/About.vue'
import { loadAllSettings } from './composables/useSettings.js'

// ── State ────────────────────────────────────────────────────────

const isAboutPanelOpen = ref(false)

// ── Callbacks ────────────────────────────────────────────────────

/* Called from Python backend via evaluate_js when user clicks "About" in system tray */
window.showAboutPanel = () => {
	isAboutPanelOpen.value = true
}

function closeAboutPanel() {
	isAboutPanelOpen.value = false
}

// ── Lifecycle ────────────────────────────────────────────────────

onMounted(() => { loadAllSettings() })
</script>

<template>
	<div class="app"
		tabindex="0">
		<main class="app_viewer">
			<EstMain />
		</main>

		<Transition name="about_panel_slide">
			<About v-if="isAboutPanelOpen" @close="closeAboutPanel" />
		</Transition>
	</div>
</template>

<style scoped>
* {
	-ms-user-select: none;
	-moz-user-select: none;
	-webkit-user-select: none;
	user-select: none;
}

/* ---- App Shell ---- */

.app {
	position: relative;
	width: 100%;
	height: 100%;
	padding: 0;
	box-sizing: border-box;
	display: flex;
	flex-direction: column;
	overflow: hidden;
	background-color: var(--window-bg);
}

.app_viewer {
	width: 100%;
	flex: 1;
	display: flex;
	align-items: stretch;
	min-height: 0;
	overflow: hidden;
	overscroll-behavior: none;
	background-color: transparent;
}

/* ---- About Panel Slide ---- */

.about_panel_slide-enter-active {
	will-change: opacity, transform;
	transition:
		opacity 180ms cubic-bezier(0.22, 1, 0.36, 1),
		transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
	transform-origin: top right;
}

.about_panel_slide-leave-active {
	will-change: opacity, transform;
	transition:
		opacity 180ms cubic-bezier(0.32, 0, 0.67, 0),
		transform 200ms cubic-bezier(0.32, 0, 0.67, 0);
	transform-origin: top right;
}

.about_panel_slide-enter-from {
	opacity: 0;
	transform: translate3d(16px, 0, 0) scale(0.992);
}

.about_panel_slide-enter-to,
.about_panel_slide-leave-from {
	opacity: 1;
	transform: translate3d(0, 0, 0) scale(1);
}

.about_panel_slide-leave-to {
	opacity: 0;
	transform: translate3d(10px, 0, 0) scale(0.996);
}

@media (prefers-reduced-motion: reduce) {
	.about_panel_slide-enter-active,
	.about_panel_slide-leave-active {
		transition: opacity 120ms linear;
	}

	.about_panel_slide-enter-from,
	.about_panel_slide-enter-to,
	.about_panel_slide-leave-from,
	.about_panel_slide-leave-to {
		transform: none;
	}
}
</style>
