<script setup lang="ts">
import { reactive } from 'vue'

import AppHeroBanner from './components/AppHeroBanner.vue'
import AppTopTabs from './components/AppTopTabs.vue'
import AssetsView from './components/AssetsView.vue'
import ImageDetectView from './components/ImageDetectView.vue'
import MonitorView from './components/MonitorView.vue'
import Mot17View from './components/Mot17View.vue'
import VideoDetectView from './components/VideoDetectView.vue'
import { useDashboard } from './composables/useDashboard'

const dashboard = reactive(useDashboard())
</script>

<template>
  <div class="app-shell">
    <AppTopTabs
      :tabs="dashboard.viewTabs"
      :active-view="dashboard.activeView"
      :runtime-label="dashboard.runtimeLabel"
      @change="dashboard.activeView = $event"
    />

    <AppHeroBanner
      :current-tab="dashboard.currentTab"
      :runtime-state="dashboard.runtimeState"
      :runtime-label="dashboard.runtimeLabel"
      :backend-hint="dashboard.backendHint"
      :monitor-highlights="dashboard.monitorHighlights"
    />

    <MonitorView
      v-if="dashboard.activeView === 'monitor'"
      :source-options="dashboard.sourceOptions"
      :tracker-options="dashboard.trackerOptions"
      :scenario-presets="dashboard.scenarioPresets"
      :monitor-highlights="dashboard.monitorHighlights"
      :event-log="dashboard.eventLog"
      :current-preset-title="dashboard.currentPreset.title"
      :current-preset-summary="dashboard.currentPreset.summary"
      :command-display="dashboard.commandDisplay"
      :runtime-label="dashboard.runtimeLabel"
      :runtime-state="dashboard.runtimeState"
      :source-label="dashboard.sourceLabel"
      :tracker-label="dashboard.trackerLabel"
      :api-error="dashboard.apiError"
      :status-detail="dashboard.statusDetail"
      :is-requesting="dashboard.isRequesting"
      :people-count="dashboard.peopleCount"
      :fps="dashboard.fps"
      :latency="dashboard.latency"
      :track-stability="dashboard.trackStability"
      :coverage="dashboard.coverage"
      :active-preset-id="dashboard.activePresetId"
      v-model:source="dashboard.source"
      v-model:tracker="dashboard.tracker"
      v-model:confidence="dashboard.confidence"
      v-model:image-size="dashboard.imageSize"
      v-model:save-video="dashboard.saveVideo"
      v-model:show-window="dashboard.showWindow"
      v-model:sample-path="dashboard.samplePath"
      v-model:rtsp-url="dashboard.rtspUrl"
      @update:active-preset-id="dashboard.applyPresetById"
      @start="dashboard.startRuntime"
      @stop="dashboard.stopRuntime"
    />

    <Mot17View
      v-else-if="dashboard.activeView === 'mot17'"
      :mot17-sequences="dashboard.mot17Sequences"
      :mot17-running="dashboard.mot17Running"
      :mot17-error="dashboard.mot17Error"
      :mot17-result="dashboard.mot17Result"
      :mot17-summary="dashboard.mot17Summary"
      :tracker-options="dashboard.trackerOptions"
      v-model:mot17-sequence-path="dashboard.mot17SequencePath"
      v-model:mot17-tracker="dashboard.mot17Tracker"
      v-model:mot17-confidence="dashboard.mot17Confidence"
      v-model:mot17-image-size="dashboard.mot17ImageSize"
      @run="dashboard.runMot17Test"
    />

    <ImageDetectView
      v-else-if="dashboard.activeView === 'image'"
      :image-file-name="dashboard.imageFileName"
      :image-local-preview="dashboard.imageLocalPreview"
      :image-running="dashboard.imageRunning"
      :image-error="dashboard.imageError"
      :image-result="dashboard.imageResult"
      :image-summary="dashboard.imageSummary"
      :has-image-file="Boolean(dashboard.imageFile)"
      v-model:confidence="dashboard.confidence"
      v-model:image-size="dashboard.imageSize"
      @file-change="dashboard.onImageFileChange"
      @run="dashboard.runImageDetect"
    />

    <VideoDetectView
      v-else-if="dashboard.activeView === 'video'"
      :video-file-name="dashboard.videoFileName"
      :video-running="dashboard.videoRunning"
      :video-error="dashboard.videoError"
      :video-result="dashboard.videoResult"
      :video-status="dashboard.videoStatus"
      :video-summary="dashboard.videoSummary"
      :tracker-options="dashboard.trackerOptions"
      :has-video-file="Boolean(dashboard.videoFile)"
      v-model:video-tracker="dashboard.videoTracker"
      v-model:video-confidence="dashboard.videoConfidence"
      v-model:video-image-size="dashboard.videoImageSize"
      @file-change="dashboard.onVideoFileChange"
      @run="dashboard.runVideoDetect"
    />

    <AssetsView
      v-else
      :asset-cards="dashboard.assetCards"
      :flow-steps="dashboard.flowSteps"
      :current-preset="dashboard.currentPreset"
    />
  </div>
</template>
