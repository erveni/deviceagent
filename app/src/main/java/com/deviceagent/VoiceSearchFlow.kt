package com.deviceagent

import android.content.Context
import android.media.AudioManager
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Hands-free Google "voice search" via ACOUSTIC LOOPBACK.
 *
 * You cannot silently inject audio into another app's microphone on a non-rooted phone —
 * Android sandboxes mic input. So instead the phone literally SPEAKS the query out its own
 * speaker while Google's voice search listens on the mic. Proven feasible on the fleet:
 * TTS -> speaker -> mic round-trips, because Android does NOT echo-cancel the
 * VOICE_RECOGNITION input (the source Google's voice search uses) down to silence.
 *
 * Flow:
 *   open Chrome -> url  ->  dismiss FRE/cookie popups  ->  tap the "Search by voice" mic
 *   ->  (best-effort) grant the mic permission prompt
 *   ->  force media volume to max  ->  TTS the query out the speaker
 *   ->  Google transcribes the audio and runs the search.
 *
 * Reuses the AccessibilityService's existing public primitives (navigateToUrl / findNode /
 * clickNode) and FlowEngine.tryClickText for all UI interaction; only the audio is new.
 * Tune the sleeps if a step needs longer on a given device.
 */
object VoiceSearchFlow {

    private const val TAG = "VoiceSearch"

    // Google's voice-search mic exposes one of these accessibility labels in Chrome.
    private val MIC_LABELS = listOf(
        "Search by voice", "Voice Search", "Google Search by voice",
        "Search by voice button", "voice search"
    )

    // Buttons that dismiss Chrome's first-run / cookie / sign-in interstitials.
    private val POPUP_LABELS = listOf(
        "Accept all", "Accept & continue", "I agree", "No thanks", "No, thanks",
        "Got it", "Stay signed out", "Use without an account", "Not now",
        "Maybe later", "Skip", "Continue"
    )

    // Buttons that grant the Chrome microphone permission (site + OS prompts).
    private val PERMISSION_LABELS = listOf(
        "While using the app", "Allow only while using the app",
        "Allow this time", "Allow", "Allow while visiting the site"
    )

    fun run(service: AgentAccessibilityService, query: String, url: String, engine: String = "chrome"): String {
        if (query.isBlank()) return "error: empty query"
        val log = StringBuilder()
        fun step(msg: String) {
            Log.i(TAG, msg)
            AgentAccessibilityService.onLog?.invoke("[voice] $msg")
            log.append(msg).append(" | ")
        }
        return if (engine.equals("google", true)) runGoogleApp(service, query, ::step, log)
        else runChrome(service, query, url, ::step, log)
    }

    /**
     * Acoustic loopback into the NATIVE Google app voice search (Assistant/Voice).
     * Launched via the VOICE_COMMAND intent, which opens the listening UI immediately.
     * This path uses Android's recognition mic source, which (per AOSP guidance) applies
     * far less echo cancellation than Chrome's WebRTC/getUserMedia path — so the phone's
     * own speaker audio is more likely to survive into the recognizer.
     */
    private fun runGoogleApp(
        service: AgentAccessibilityService, query: String,
        step: (String) -> Unit, log: StringBuilder
    ): String {
        // SEARCH_LONG_PRESS opens the Google app's VOICE SEARCH (the search-bar mic) and
        // goes straight to "Listening…" — unlike ACTION_VOICE_COMMAND, which on newer
        // devices opens Gemini/Assistant (account-gated, never starts listening).
        step("launch Google voice search (SEARCH_LONG_PRESS)")
        try {
            val intent = android.content.Intent(android.content.Intent.ACTION_SEARCH_LONG_PRESS)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            service.startActivity(intent)
        } catch (e: Exception) {
            step("intent failed: ${e.message}")
        }
        sleep(2500)

        step("force media volume to max")
        forceVolumeMax(service)

        val listening = waitForListening(service, 6000)
        step(if (listening) "listening UI detected" else "listening UI NOT detected — speaking anyway")
        sleep(300)

        step("speak aloud: \"$query\"")
        step("tts -> " + speakBlocking(service, query))

        step("wait for recognition + results")
        sleep(4500)
        step("done")
        return log.toString().trimEnd(' ', '|')
    }

    private fun runChrome(
        service: AgentAccessibilityService, query: String, url: String,
        step: (String) -> Unit, log: StringBuilder
    ): String {
        val fe = FlowEngine(service)
        step("open $url")
        service.navigateToUrl(url)
        sleep(3800)

        step("dismiss popups")
        for (label in POPUP_LABELS) fe.tryClickText(label)
        sleep(800)

        // Tap Google's voice-search mic. ACTION_CLICK on the node reliably opens the
        // "Listening…" overlay (verified); gesture-tap is the fallback.
        val micRect = tapMic(service) { step(it) }
        sleep(1800)

        // First run, Chrome asks for the mic permission. Granting it does NOT start
        // listening, so after granting we re-tap the mic to actually open the voice UI.
        var granted = false
        for (label in PERMISSION_LABELS) {
            if (fe.tryClickText(label)) { granted = true; step("granted via \"$label\""); break }
        }
        if (granted && micRect != null) {
            sleep(1000)
            service.gestureTap(micRect.centerX().toFloat(), micRect.centerY().toFloat())
            step("re-tapped mic after grant")
        }

        step("force media volume to max")
        forceVolumeMax(service)

        // Wait for Google's "Speak now" listening overlay before speaking, so the audio
        // isn't lost into a not-yet-listening UI.
        val listening = waitForListening(service, 6000)
        step(if (listening) "listening UI detected" else "listening UI NOT detected — speaking anyway")
        sleep(400)

        step("speak aloud: \"$query\"")
        val spoken = speakBlocking(service, query)
        step("tts -> $spoken")

        step("wait for Google to transcribe + load results")
        sleep(4500)

        step("done")
        return log.toString().trimEnd(' ', '|')
    }

    /**
     * Find and click the voice-search mic. Prefers the lower/centered mic (the homepage
     * search box one, which opens the "Listening…" overlay) over the top omnibox icon.
     * Returns its bounds so the caller can re-tap after a permission prompt.
     */
    private fun tapMic(service: AgentAccessibilityService, step: (String) -> Unit): android.graphics.Rect? {
        var best: AccessibilityNodeInfoHolder? = null
        for (label in MIC_LABELS) {
            val node = service.findNode(contentDesc = label, timeoutMs = 1500)
                ?: service.findNode(text = label, timeoutMs = 400)
            if (node != null) {
                val r = android.graphics.Rect()
                node.getBoundsInScreen(r)
                if (r.width() > 0 && r.height() > 0) {
                    // Prefer the lowest match on screen (the in-page mic, not the toolbar).
                    if (best == null || r.centerY() > best!!.rect.centerY()) {
                        best?.node?.recycle()
                        best = AccessibilityNodeInfoHolder(node, android.graphics.Rect(r), label)
                        continue
                    }
                }
                node.recycle()
            }
        }
        val chosen = best ?: run { step("mic NOT found (labels: $MIC_LABELS)"); return null }
        val clicked = service.clickNode(chosen.node)
        if (!clicked) service.gestureTap(chosen.rect.centerX().toFloat(), chosen.rect.centerY().toFloat())
        chosen.node.recycle()
        step("mic tapped via \"${chosen.label}\" @${chosen.rect.centerX()},${chosen.rect.centerY()} (click=$clicked)")
        return chosen.rect
    }

    private class AccessibilityNodeInfoHolder(
        val node: android.view.accessibility.AccessibilityNodeInfo,
        val rect: android.graphics.Rect,
        val label: String
    )

    /**
     * Poll for Google's listening overlay. The web voice UI shows "Listening..." as page
     * text (no exact accessible label), so scan the tree for the substring rather than
     * exact-matching a node.
     */
    private fun waitForListening(service: AgentAccessibilityService, timeoutMs: Long): Boolean {
        val needles = listOf("listening", "speak now", "go ahead", "i'm listening")
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val tree = service.dumpTree(18).lowercase()
            if (needles.any { it in tree }) return true
            sleep(300)
        }
        return false
    }

    private fun forceVolumeMax(service: AgentAccessibilityService) {
        try {
            val am = service.getSystemService(Context.AUDIO_SERVICE) as AudioManager
            am.setStreamVolume(
                AudioManager.STREAM_MUSIC,
                am.getStreamMaxVolume(AudioManager.STREAM_MUSIC),
                0
            )
        } catch (e: Exception) {
            Log.w(TAG, "volume set failed: ${e.message}")
        }
    }

    /** Synthesize [text] out the speaker and block until playback completes. */
    private fun speakBlocking(service: AgentAccessibilityService, text: String): String {
        val initLatch = CountDownLatch(1)
        var okInit = false
        val tts = TextToSpeech(service) { status ->
            okInit = status == TextToSpeech.SUCCESS
            initLatch.countDown()
        }
        if (!initLatch.await(8, TimeUnit.SECONDS) || !okInit) {
            tts.shutdown(); return "tts-init-failed"
        }
        tts.language = Locale.US
        val doneLatch = CountDownLatch(1)
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onDone(id: String?) { doneLatch.countDown() }
            @Deprecated("required override")
            override fun onError(id: String?) { doneLatch.countDown() }
            override fun onError(id: String?, code: Int) { doneLatch.countDown() }
        })
        val params = Bundle().apply {
            putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC)
            putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
        }
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, "vs-utt")
        val finished = doneLatch.await(15, TimeUnit.SECONDS)
        sleep(400) // let the last word finish before teardown
        tts.shutdown()
        return if (finished) "spoke-ok" else "tts-timeout"
    }

    private fun sleep(ms: Long) { try { Thread.sleep(ms) } catch (_: InterruptedException) {} }
}
