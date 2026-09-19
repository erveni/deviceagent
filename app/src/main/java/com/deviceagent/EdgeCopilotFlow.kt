package com.deviceagent

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Rect
import java.io.File
import java.io.FileOutputStream
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Drives Microsoft Copilot through Microsoft Edge.
 *
 * Edge's built-in Copilot is the only Copilot surface that answers logged out —
 * copilot.microsoft.com in Chrome shows a hard "Sign in to Copilot" wall with no skip,
 * so this flow never touches Chrome and none of [FlowEngine]'s Chrome helpers apply.
 *
 * Copilot is reached by a toolbar button rather than a URL, and it renders in a WebView
 * whose nodes carry no resource-ids, so everything below the toolbar is matched by class
 * and content-desc. Measured on SM-A075F / Edge 151.0.4129.101, 2026-09-02.
 */
class EdgeCopilotFlow(
    private val s: AgentAccessibilityService,
    private val flow: FlowEngine
) {
    companion object {
        const val PKG = "com.microsoft.emmx"
        private const val COPILOT_BUTTON_ID = "edge_location_bar_copilot_button"
        private const val PROMPT_BUBBLE_DESC = "Sent by you."

        /** Chrome of the Copilot surface itself — never part of an answer. */
        // Copilot's header bar plus its fade ends near 0.115 of screen height; the first
        // answer line must sit below that to be legible in the client shot.
        private const val FIRST_LINE_CLEAR_Y = 0.14f
        // Bottom edge of Copilot's header bar; rows above it stay in a client shot.
        private const val HEADER_BOTTOM_Y = 0.105f

        private val ANSWER_NOISE = listOf(
            "Message Copilot", "Show all", "Smart", "Quick response", "Think Deeper"
        )

        private const val OVERFLOW_BUTTON_ID = "overflow_button_bottom"
        private const val CLEAR_BUTTON_ID = "clear_button"
        private const val INPRIVATE_BUTTON_ID = "edge_incognito_button"
        private const val SIGN_IN_SWIPE_ATTEMPTS = 4

        /** Whatever Edge currently shows in the time-range spinner, so it can be opened. */
        private val TIME_RANGE_LABELS = listOf(
            "Last hour", "Last 15 minutes", "Last 24 hours", "Last 7 days", "Last 4 weeks", "All time"
        )

        /** Rows to tick before deleting. Passwords/autofill are left alone. */
        private val CLEAR_TARGET_LABELS = listOf(
            "Browsing history", "Cookies and site data", "Cached images and files"
        )

        private const val FRE_TIMEOUT_MS = 180_000L

        /**
         * First-run dismissals, tried in this order each round. A fresh install shows
         * default-browser -> sign-in -> privacy-confirm -> notifications permission.
         *
         * Both apostrophes for "Don't allow": the permission dialog renders the CURLY
         * U+2019, so the straight-quote form alone never matches. The resource-id is the
         * real workhorse (it exists on both Samsung and the fleet Infinix) and the text
         * forms are the fallback for OEMs that rename it.
         */
        private val FRE_BUTTONS = listOf(
            // Android's default-browser chooser appears before Edge's own FRE on
            // a phone that has never launched Edge. Cancel it; Daily explicitly
            // selects Edge and must not change the system default browser.
            "text" to "Cancel",
            "text" to "Not now",
            "id" to "fre_sign_in_later",
            "text" to "Confirm",
            "id" to "permission_deny_button",
            "text" to "Don’t allow",
            "text" to "Don't allow",
            "text" to "Skip",
            "text" to "Maybe later",
            "text" to "No thanks"
        )
    }

    // ── reset ──

    /**
     * Drop the previous job's session state and leave Edge on the Copilot surface.
     *
     * Prefers Edge's own "Delete browsing data" over a Settings storage wipe. Both end
     * up logged out and cookie-free, but the wipe also resets Edge to FIRST RUN, and the
     * FRE walk is what actually breaks under load: 23 of 80 jobs failed at 15-worker
     * concurrency (reset_edge x12, open_copilot x11) for a 45% success rate against
     * ChatGPT's 83%. Chrome's [FlowEngine.resetChrome] defaults to the same in-app
     * delete for the same reason — the full clear is fragile behind a residential proxy.
     *
     * The wipe stays as the fallback: on a phone whose Edge has never been through the
     * FRE there is no menu to drive, and only the wipe-then-walk path can get there.
     */
    fun reset(preserveCacheTrial: Boolean = false): Boolean {
        s.log("── RESET EDGE ──")
        launch()
        if (preserveCacheTrial) {
            val personalize = s.findNode(text = "Personalize your web experience", timeoutMs = 1200)
            if (personalize != null) {
                personalize.recycle()
                val deny = s.findNode(text = "Not now", timeoutMs = 1500) ?: return false
                s.clickNode(deny); deny.recycle(); Thread.sleep(1200)
                s.log("[edge] cache trial: declined personalization popup")
            }
        }
        leaveInPrivate()
        if (clearBrowsingData(preserveCacheTrial)) {
            // The clear leaves us deep in Settings; get back to the browser so the
            // Copilot button is reachable.
            launch()
            if (preserveCacheTrial) {
                for (attempt in 0 until 5) {
                    val button = copilotButton()
                    if (button != null) { button.recycle(); break }
                    s.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
                    Thread.sleep(700)
                }
            }
            if (copilotButton()?.also { it.recycle() } != null) {
                s.log("[edge] light reset done (no FRE)")
                return true
            }
            s.log("[edge] light reset left no Copilot button — falling back to full wipe")
        }
        if (preserveCacheTrial) {
            s.log("[edge] cache trial reset refused; no full-wipe fallback")
            return false
        }
        return fullWipeReset()
    }

    /**
     * Bring Edge to the foreground for non-Copilot web jobs.  Do not call
     * [reset] here: that method intentionally waits for the Copilot toolbar
     * button and can therefore block forever on ordinary ChatGPT/Gemini tabs.
     */
    fun prepareBrowser(): Boolean {
        s.log("── PREPARE EDGE BROWSER ──")
        launch()
        val deadline = System.currentTimeMillis() + 20_000L
        while (System.currentTimeMillis() < deadline) {
            val pkg = topPackage()
            if (pkg == "com.android.permissioncontroller") {
                val cancel = s.findNode(text = "Cancel", timeoutMs = 500)
                if (cancel != null) { s.clickNode(cancel); cancel.recycle(); Thread.sleep(700) }
            }
            if (topPackage() == PKG) {
                leaveInPrivate()
                s.log("[edge] browser ready")
                return true
            }
            Thread.sleep(500)
        }
        s.log("[edge] browser did not reach foreground")
        return false
    }

    /**
     * Leave InPrivate if a previous job (or an operator) left a private tab in front.
     *
     * InPrivate swaps the toolbar's Copilot button for [INPRIVATE_BUTTON_ID], so Copilot
     * is simply unreachable there — and neither the light clear nor the FRE walk exits
     * the mode on its own, so a stuck private tab burns the full 180s FRE timeout and
     * reports "reset_edge failed" with nothing actually wrong.
     */
    private fun leaveInPrivate() {
        val marker = s.findNode(resourceId = INPRIVATE_BUTTON_ID, timeoutMs = 800)
            ?: s.findNode(text = "Browse InPrivate", timeoutMs = 500)
            ?: return
        marker.recycle()
        s.log("[edge] InPrivate tab in front — leaving it")
        val exit = s.findNode(resourceId = "exit_inprivate_button", timeoutMs = 1500)
            ?: s.findNode(text = "Exit InPrivate mode", timeoutMs = 1000)
        if (exit != null) {
            clickSelfOrParent(exit); exit.recycle(); Thread.sleep(2500)
        } else {
            s.log("[edge] no exit-InPrivate button — relaunching Edge instead")
            s.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
            Thread.sleep(800)
            launch()
        }
    }

    /** Settings-storage wipe + FRE walk. Slow and load-fragile; fallback only. */
    private fun fullWipeReset(): Boolean {
        s.log("── RESET EDGE (full wipe) ──")
        val cleared = try {
            flow.clearChromeData(PKG)
        } catch (e: Exception) {
            s.log("[edge] clear ex: ${e.message}"); false
        }
        s.log("[edge] clearData -> $cleared")
        launch()
        return dismissFre()
    }

    /**
     * Browser menu -> Settings -> Privacy and security -> Clear browsing data, tick
     * history + cookies + cache over "All time", then "Delete data".
     *
     * Selectors verified on a real device (Edge on Samsung SM-A075F, 2026-09-04). Ids are
     * used where Edge provides stable ones ([OVERFLOW_BUTTON_ID], [CLEAR_BUTTON_ID]) and
     * label text elsewhere; every step returns false rather than guessing, so a layout
     * change degrades to the full wipe instead of silently skipping the clear.
     */
    private fun clearBrowsingData(preserveCacheTrial: Boolean = false): Boolean {
        s.log("── EDGE CLEAR BROWSING DATA ──")
        val menu = s.findNode(resourceId = OVERFLOW_BUTTON_ID, timeoutMs = 6000)
            ?: s.findNode(contentDesc = "Browser menu", timeoutMs = 1500)
            ?: run { s.log("[edge] browser menu not found"); return false }
        s.clickNode(menu); menu.recycle()
        Thread.sleep(1500)

        val settings = s.findNode(contentDesc = "Settings", timeoutMs = 4000)
            ?: s.findNode(text = "Settings", timeoutMs = 1500)
            ?: run { s.log("[edge] Settings entry not found"); return false }
        s.clickNode(settings); settings.recycle()
        Thread.sleep(2500)

        val privacy = s.findNode(text = "Privacy and security", timeoutMs = 5000)
            ?: s.findNode(text = "Privacy, search, and services", timeoutMs = 1500)
            ?: run { s.log("[edge] Privacy entry not found"); return false }
        clickSelfOrParent(privacy)
        Thread.sleep(2000)

        val entry = s.findNode(text = "Clear browsing data", timeoutMs = 5000)
            ?: s.findNode(text = "Delete browsing data", timeoutMs = 1500)
            ?: run { s.log("[edge] Clear browsing data entry not found"); return false }
        clickSelfOrParent(entry)
        Thread.sleep(2500)

        if (preserveCacheTrial) {
            if (!selectAllTimeRange()) return false
            val selections = mapOf("Browsing history" to true, "Cookies and site data" to true,
                "Tabs" to true, "Cached images and files" to false,
                "Saved passwords" to false, "Autofill form data" to false, "Site settings" to false)
            for ((label, checked) in selections) {
                val row = s.findNode(text = label, timeoutMs = 1500) ?: return false
                val box = checkboxFor(row) ?: run { row.recycle(); return false }
                if (box.isChecked != checked) { s.clickNode(box); Thread.sleep(500) }
                box.recycle(); row.recycle()
                val verifyRow = s.findNode(text = label, timeoutMs = 1500) ?: return false
                val verifyBox = checkboxFor(verifyRow) ?: run { verifyRow.recycle(); return false }
                val matches = verifyBox.isChecked == checked
                verifyBox.recycle(); verifyRow.recycle()
                if (!matches) return false
            }
            s.log("[edge] cache trial: all-time history/cookies/tabs selected; HTTP cache excluded")
        } else {
            selectAllTimeRange()
            tickClearTargets()
        }

        val go = s.findNode(resourceId = CLEAR_BUTTON_ID, timeoutMs = 4000)
            ?: s.findNode(text = "Delete data", timeoutMs = 1500)
            ?: s.findNode(text = "Clear data", timeoutMs = 1000)
            ?: run { s.log("[edge] Delete data button not found"); return false }
        clickSelfOrParent(go)
        Thread.sleep(3000)
        // Edge asks again when history is included on a signed-in profile.
        s.findNode(text = "Clear", timeoutMs = 1200)?.let { clickSelfOrParent(it); Thread.sleep(1500) }
        s.log("[edge] browsing data cleared")
        return true
    }

    /** Default range is "Last hour", which would leave older cookies in place. */
    private fun selectAllTimeRange(): Boolean {
        val spinner = TIME_RANGE_LABELS.firstNotNullOfOrNull { s.findNode(text = it, timeoutMs = 800) }
        if (spinner == null) { s.log("[edge] time range spinner not found — leaving default"); return false }
        clickSelfOrParent(spinner)
        Thread.sleep(1200)
        val allTime = s.findNode(text = "All time", timeoutMs = 3000)
        if (allTime == null) { s.log("[edge] 'All time' not offered"); return false }
        clickSelfOrParent(allTime)
        Thread.sleep(1000)
        val verified = s.findNode(text = "All time", timeoutMs = 1000) ?: return false
        verified.recycle()
        return true
    }

    /** Trial only: reset embedded conversation too; browser-cookie clearing alone is insufficient. */
    fun freshCachedConversation(): Boolean {
        val fresh = s.findNode(contentDesc = "New chat", timeoutMs = 2000)
            ?: return false
        s.clickNode(fresh); fresh.recycle(); Thread.sleep(2500)
        val root = s.rootInActiveWindow ?: return false
        fun stale(n: AccessibilityNodeInfo): Boolean {
            if (n.contentDescription?.toString()?.startsWith(PROMPT_BUBBLE_DESC) == true ||
                n.text?.toString()?.contains("[RANK:") == true) return true
            for (i in 0 until n.childCount) {
                val child = n.getChild(i) ?: continue
                val found = stale(child); child.recycle()
                if (found) return true
            }
            return false
        }
        val oldAnswer = stale(root); root.recycle()
        val box = composer(timeoutMs = 2000) ?: return false
        val text = box.text?.toString().orEmpty(); box.recycle()
        return !oldAnswer && (text.isBlank() || text.startsWith("Message Copilot"))
    }

    /**
     * Tick history, cookies and cache if they are not already ticked. Edge remembers the
     * previous selection, so blind tapping would UNTICK them on the second job.
     */
    private fun tickClearTargets() {
        for (label in CLEAR_TARGET_LABELS) {
            val row = s.findNode(text = label, timeoutMs = 1500) ?: continue
            val box = checkboxFor(row)
            if (box == null) { row.recycle(); s.log("[edge] no checkbox for '$label'"); continue }
            if (!box.isChecked) { s.clickNode(box); Thread.sleep(500) }
            box.recycle(); row.recycle()
        }
    }

    /** Walk up to the row container, then down to its checkbox. */
    private fun checkboxFor(row: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var container: AccessibilityNodeInfo? = row.parent
        repeat(3) {
            val c = container ?: return null
            findCheckbox(c)?.let { return it }
            container = c.parent
        }
        return null
    }

    private fun findCheckbox(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.className?.toString()?.contains("CheckBox") == true) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            findCheckbox(child)?.let { return it }
        }
        return null
    }

    private fun clickSelfOrParent(node: AccessibilityNodeInfo) {
        var n: AccessibilityNodeInfo? = node
        repeat(5) {
            val cur = n ?: return
            if (cur.isClickable) { s.clickNode(cur); return }
            n = cur.parent
        }
        s.clickNode(node)
    }

    private fun launch() {
        s.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
        Thread.sleep(500)
        val intent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
            setPackage(PKG)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        s.startActivity(intent)
        Thread.sleep(7000)
    }

    /**
     * Walk Edge's first run until the Copilot button is reachable.
     *
     * A FRESH INSTALL shows more screens than a `pm clear`ed one — measured on the fleet
     * Infinix: default-browser, sign-in, privacy-confirm, then the notifications
     * permission. Poll rather than assume an order or a count; the sign-in screen can
     * appear twice, and under a proxy the gaps between screens are long.
     *
     * Do NOT give up on a few idle rounds: a cold proxied start can sit on one screen
     * for well over half a minute, and bailing early was what made every fleet job fail
     * with "reset_edge failed" while the same code worked on the dev phone.
     */
    private fun dismissFre(): Boolean {
        s.log("── DISMISS EDGE FRE ──")
        val deadline = System.currentTimeMillis() + FRE_TIMEOUT_MS
        var idle = 0
        while (System.currentTimeMillis() < deadline) {
            copilotButton()?.let {
                it.recycle()
                s.log("[edge] FRE done — Copilot button reachable")
                return true
            }
            // A failed data-clear can leave Settings in front; the FRE is then invisible
            // and every round reads as idle. Put Edge back before looking.
            ensureEdgeForeground()
            var tapped = false
            for ((kind, value) in FRE_BUTTONS) {
                val n = if (kind == "id") s.findNode(resourceId = value, timeoutMs = 400)
                        else s.findNode(text = value, timeoutMs = 400)
                if (n != null) {
                    s.clickNode(n); n.recycle()
                    s.log("[edge] FRE: tapped $kind '$value'")
                    tapped = true
                    Thread.sleep(2000)
                    break
                }
            }
            if (tapped) {
                idle = 0
            } else {
                idle++
                // Say what is actually on screen, so an unknown screen is identifiable
                // from the job log instead of needing a phone in hand.
                if (idle % 5 == 0) {
                    s.log("[edge] FRE waiting (${idle} idle) on ${topPackage()}: " +
                          visibleAnswerLines().take(4).joinToString(" | ").take(160))
                }
                Thread.sleep(2000)
            }
        }
        s.log("[edge] FRE did not reach the Copilot button within ${FRE_TIMEOUT_MS / 1000}s " +
              "— last screen ${topPackage()}")
        return false
    }

    private fun topPackage(): String {
        val root = s.rootInActiveWindow ?: return "?"
        val pkg = root.packageName?.toString() ?: "?"
        root.recycle()
        return pkg
    }

    private fun ensureEdgeForeground() {
        if (topPackage() == PKG) return
        s.log("[edge] not in foreground (${topPackage()}) — relaunching")
        launch()
    }

    // ── copilot surface ──

    private fun copilotButton(): AccessibilityNodeInfo? =
        s.findNode(resourceId = COPILOT_BUTTON_ID, timeoutMs = 800)
            // New-tab Edge builds expose the Copilot entry as the integrated
            // "Search or ask anything" surface instead of the toolbar button.
            // It is still Copilot's entry point, not the address bar.
            ?: s.findNode(text = "Search or ask anything", timeoutMs = 800)
            ?: s.findNode(contentDesc = "Search or ask anything", timeoutMs = 500)

    /** The composer is the only EditText on the Copilot half-screen; Edge's address bar
     *  belongs to a different activity, and [AgentAccessibilityService.findInputField]
     *  ignores anything in the top band anyway. */
    private fun composer(timeoutMs: Long = 5000): AccessibilityNodeInfo? =
        s.findInputField(hintText = null, timeoutMs = timeoutMs)

    private fun composerText(): String {
        val n = composer(timeoutMs = 1200) ?: return ""
        val t = n.text?.toString() ?: ""
        n.recycle()
        return t
    }

    /** Open Copilot from the Edge toolbar and wait for its composer. */
    fun open(): Boolean {
        s.log("── OPEN COPILOT ──")
        val btn = copilotButton()
        if (btn != null) {
            s.clickNode(btn); btn.recycle()
        } else {
            // Some Edge new-tab WebViews expose neither the toolbar resource-id nor
            // the visible label to accessibility. The only Copilot entry then is the
            // large bottom "Search or ask anything" surface; the address bar is at
            // the top, so this bounded tap cannot target it.
            s.log("[edge] Copilot accessibility entry missing; tapping bottom Copilot surface")
            s.gestureTap(screenWidth() * 0.50f, screenHeight() * 0.90f)
        }
        Thread.sleep(7000)
        // Swiping the sign-in sheet away also closes the Copilot panel underneath, so
        // Copilot has to be opened a second time once the sheet is gone.
        if (dismissSignInSheet()) {
            val again = copilotButton()
            if (again == null) {
                s.log("[edge] Copilot button gone after dismissing the sign-in sheet")
                return false
            }
            s.clickNode(again); again.recycle()
            Thread.sleep(7000)
            dismissSignInSheet()
        }
        val box = if (copilotSurfaceUp()) composer(timeoutMs = 10_000) else null
        if (box != null) { box.recycle(); return true }
        // Copilot refuses some exit IPs outright ("Sorry about that / Copilot is
        // currently unavailable") and renders no composer. Measured on a Decodo session
        // that had silently widened out of the requested zip onto a datacenter-ish ASN;
        // a genuine residential exit in the target metro serves normally. Without this
        // the job reports "composer never appeared" and the proxy looks innocent — the
        // fix is to rotate the session, not to wait longer.
        if (s.findNode(text = "currently unavailable", timeoutMs = 1500) != null ||
            s.findNode(text = "Sorry about that", timeoutMs = 500) != null) {
            s.log("[edge] Copilot REFUSED this exit IP (\"currently unavailable\") — proxy problem, not a timeout")
            return false
        }
        s.log("[edge] Copilot composer never appeared")
        return false
    }

    /**
     * Copilot greets a cookie-free profile with a "Sign in for the full experience"
     * bottom sheet whose only button is "Continue with Microsoft" — no skip, and BACK
     * does not close it. It renders OVER the composer, so the job would otherwise die as
     * "composer never appeared" with Copilot itself perfectly healthy.
     *
     * The sheet is drag-dismissible: swiping it toward the bottom of the screen sends it
     * away. Measured on a real device, it takes two swipes — the first only drags the
     * card partway down — so swipe until the sheet is gone rather than a fixed count.
     */
    private fun dismissSignInSheet(): Boolean {
        var acted = false
        repeat(SIGN_IN_SWIPE_ATTEMPTS) { attempt ->
            val sheet = signInSheet() ?: return acted
            sheet.recycle()
            if (attempt == 0) s.log("[edge] Copilot sign-in sheet up — swiping it away")
            acted = true
            val h = screenHeight()
            s.gestureSwipe(0.5f * screenWidth(), 0.40f * h, 0.5f * screenWidth(), 0.99f * h, 350)
            Thread.sleep(1200)
        }
        signInSheet()?.let {
            it.recycle()
            s.log("[edge] sign-in sheet still up after $SIGN_IN_SWIPE_ATTEMPTS swipes")
        }
        return acted
    }

    private fun signInSheet(): AccessibilityNodeInfo? =
        s.findNode(text = "Sign in for the full experience", timeoutMs = 800)
            ?: s.findNode(text = "Continue with Microsoft", timeoutMs = 400)

    /**
     * True only when Copilot's own surface is in front.
     *
     * [AgentAccessibilityService.findInputField] returns the first EditText it can see,
     * and when Copilot is NOT open that is Edge's ADDRESS BAR. A job that trusted it
     * typed a client's prompt into the URL bar, reported "input" OK and then died at
     * submit looking for a Send button that was never there. Gate on Copilot's own
     * composer hint before accepting any input field.
     */
    private fun copilotSurfaceUp(): Boolean {
        val marker = s.findNode(text = "Message Copilot", timeoutMs = 4000)
            ?: s.findNode(contentDesc = "Message Copilot", timeoutMs = 1000)
        if (marker == null) {
            s.log("[edge] Copilot surface not up (would have grabbed Edge's address bar)")
            return false
        }
        marker.recycle()
        return true
    }

    private fun screenWidth(): Float = s.resources.displayMetrics.widthPixels.toFloat()
    private fun screenHeight(): Float = s.resources.displayMetrics.heightPixels.toFloat()

    // ── prompt ──

    fun inputPrompt(text: String): Boolean {
        s.log("── COPILOT INPUT: \"${text.take(50)}...\" ──")
        val box = composer() ?: run { s.log("[edge] no composer to type into"); return false }
        s.clickNode(box)
        Thread.sleep(500)
        s.setTextOnNode(box, text)
        Thread.sleep(400)
        if (composerText().contains(text.take(12))) {
            s.log("[edge] input set via ACTION_SET_TEXT")
            box.recycle()
            return true
        }
        // WebView composers routinely accept ACTION_SET_TEXT and ignore it — paste instead.
        s.setClipboard(text)
        Thread.sleep(300)
        val pasted = android.os.Build.VERSION.SDK_INT >= 29 &&
            box.performAction(AccessibilityNodeInfo.ACTION_PASTE)
        val b = Rect(); box.getBoundsInScreen(b)
        box.recycle()
        if (!pasted) {
            s.gestureTap(b.centerX().toFloat(), b.centerY().toFloat())
            Thread.sleep(300)
            s.pasteAt(b.centerX().toFloat(), b.centerY().toFloat())
        }
        Thread.sleep(700)
        val ok = composerText().contains(text.take(12))
        s.log("[edge] input via paste -> $ok")
        return ok
    }

    /**
     * Copilot swaps the composer's right-hand button by state — "Start a voice Call"
     * when empty, "Send" once it holds text — exactly like Gemini. Submitting on an
     * empty composer starts a voice call and hangs the job until its generation
     * timeout, so gate on the composer actually holding text and fail fast instead.
     */
    fun submit(): Boolean {
        s.log("── COPILOT SUBMIT ──")
        if (composerText().isBlank()) {
            s.log("[edge] composer EMPTY — not submitting (that button is the mic)")
            return false
        }
        val send = s.findNode(contentDesc = "Send", timeoutMs = 4000)
            ?: run { s.log("[edge] Send button not found"); return false }
        s.clickNode(send); send.recycle()
        Thread.sleep(1500)
        return true
    }

    // ── generation ──

    private fun isGenerating(): Boolean =
        s.findNode(contentDesc = "Loading response", timeoutMs = 400) != null ||
        s.findNode(contentDesc = "Stop", timeoutMs = 400) != null

    /**
     * Wait for the answer to finish.
     *
     * Completion is the streaming indicator clearing after it was seen — NOT the presence
     * of answer text. Copilot leaves the viewport parked at the prompt, so a finished
     * answer is routinely off-screen and unreadable until [readAnswer] scrolls to it;
     * gating on visible text here just burns the whole timeout. Poll at 1s so a fast
     * answer's streaming phase is not missed between samples.
     */
    var lastWaitFailure: String? = null
        private set

    fun waitForAnswer(timeoutSec: Int, confirmNetworkError: Boolean = false): Boolean {
        s.log("── COPILOT WAIT (${timeoutSec}s) ──")
        val deadline = System.currentTimeMillis() + timeoutSec * 1000L
        var sawStreaming = false
        var networkErrorSince = 0L
        lastWaitFailure = null
        while (System.currentTimeMillis() < deadline) {
            Thread.sleep(1000)
            val networkNode = s.findNode(text = "Network issues", timeoutMs = 300)
            val networkBounds = Rect()
            networkNode?.getBoundsInScreen(networkBounds)
            val visibleExactError = networkNode != null && networkNode.isVisibleToUser &&
                networkNode.text?.toString()?.trim()?.equals("Network issues", ignoreCase = true) == true &&
                networkBounds.width() > 0 && networkBounds.height() > 0 &&
                networkBounds.intersects(0, 0, s.screenWidth(), s.screenHeight())
            val networkError = networkNode != null && (!confirmNetworkError || visibleExactError)
            networkNode?.recycle()
            if (networkError) {
                if (!confirmNetworkError) {
                    lastWaitFailure = "copilot_network_issues"
                    s.log("[edge] Copilot reported network issues")
                    return false
                }
                if (networkErrorSince == 0L) networkErrorSince = System.currentTimeMillis()
                if (System.currentTimeMillis() - networkErrorSince >= 3000L) {
                    lastWaitFailure = "copilot_network_issues"
                    s.log("[edge] confirmed visible Network issues for >=3s")
                    return false
                }
                s.log("[edge] transient visible Network issues; confirming before abort")
                continue
            }
            networkErrorSince = 0L
            if (isGenerating()) { sawStreaming = true; continue }
            if (sawStreaming) {
                s.log("[edge] generation complete (streaming cleared)")
                return true
            }
            // Streaming can also finish inside a single poll gap. A conversation that
            // has scrollback below the fold, or visible answer text, is equally done.
            val hasScrollback = s.findNode(contentDesc = "Scroll to bottom", timeoutMs = 200) != null
            if (hasScrollback || visibleAnswerText().length > 40) {
                s.log("[edge] generation complete (answer present, streaming never sampled)")
                return true
            }
        }
        s.log("[edge] timeout waiting for answer")
        lastWaitFailure = "generation timeout"
        return false
    }

    // ── answer capture ──

    /**
     * Read the whole answer by scrolling through it.
     *
     * Unlike Chrome, Copilot's WebView virtualizes the conversation: only nodes near the
     * viewport are in the accessibility tree, so a single read returns whatever happens
     * to be on screen — usually just the prompt bubble. Collect on each screen, scroll,
     * and stop once a pass adds nothing.
     */
    fun readAnswer(maxScrolls: Int = 16): String {
        s.log("── COPILOT READ ANSWER ──")
        seekConversationTop()
        val lines = LinkedHashSet<String>()
        var barren = 0
        for (i in 0..maxScrolls) {
            val before = lines.size
            lines.addAll(visibleAnswerLines())
            // An empty pass early on means the viewport is still on blank space above
            // the answer, not that the answer has been read — only stop on empty passes
            // once something has actually been collected.
            barren = if (lines.size == before) barren + 1 else 0
            if (barren >= 3 && lines.isNotEmpty()) break
            s.gestureSwipe(s.screenWidth() / 2f, s.screenHeight() * 0.72f,
                           s.screenWidth() / 2f, s.screenHeight() * 0.32f, 600)
            Thread.sleep(1600)
        }
        val text = lines.joinToString("\n").trim()
        s.log("[edge] captured ${text.length} chars, ${lines.size} lines")
        return text
    }

    /** Scroll back to the prompt bubble so the read below starts above the answer. */
    private fun seekConversationTop() {
        for (i in 1..8) {
            if (s.findNode(contentDesc = PROMPT_BUBBLE_DESC, timeoutMs = 300) != null) return
            s.gestureSwipe(s.screenWidth() / 2f, s.screenHeight() * 0.32f,
                           s.screenWidth() / 2f, s.screenHeight() * 0.78f, 600)
            Thread.sleep(1200)
        }
    }

    private fun visibleAnswerText(): String = visibleAnswerLines().joinToString("\n")

    /**
     * Answer text currently on screen, with the prompt bubble excluded.
     *
     * The bubble is a node whose content-desc is "Sent by you." followed by the prompt,
     * and the prompt renders as a SIBLING TextView — not a child — so dropping the
     * bubble's subtree is not enough. Match each candidate line against that desc
     * instead. Reading the page whole would fold the prompt's own "[RANK: 19/19]"
     * example into the response, the same trap the Chrome rank parse already guards.
     */
    private fun visibleAnswerLines(): List<String> {
        val root = s.rootInActiveWindow ?: return emptyList()
        val sent = StringBuilder()
        val texts = mutableListOf<String>()
        collect(root, sent, texts, 0)
        root.recycle()
        val prompt = sent.toString()
        return texts.filter { line ->
            line.length > 1 &&
            !prompt.contains(line) &&
            ANSWER_NOISE.none { line.startsWith(it) }
        }
    }

    private fun collect(
        node: AccessibilityNodeInfo,
        sent: StringBuilder,
        out: MutableList<String>,
        depth: Int
    ) {
        if (depth > 25) return
        val desc = node.contentDescription?.toString()
        if (desc != null && desc.startsWith(PROMPT_BUBBLE_DESC)) {
            sent.append(desc.removePrefix(PROMPT_BUBBLE_DESC))
        } else {
            val txt = node.text?.toString()?.trim()
            if (!txt.isNullOrBlank() && node.className?.toString()?.contains("Edit") != true) {
                out.add(txt)
            }
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { collect(it, sent, out, depth + 1) }
        }
    }

    // ── backlink ──

    /**
     * Click the answer's citation for [domain] and stay on the page it opens.
     *
     * The Chrome flows find their link by targetUrl anywhere in the tree, offscreen
     * included. That does not carry over: Copilot virtualizes the conversation, so a
     * citation that has not been scrolled to simply is not in the tree. Seek downward —
     * citations sit at the end of the answer — and check each screen.
     */
    fun clickBacklink(domain: String, maxScrolls: Int = 14): Boolean {
        s.log("── COPILOT BACKLINK: \"$domain\" ──")
        val partial = domain.substringBefore(".")
        // readAnswer leaves the viewport at the end of the answer; without rewinding,
        // this scan would only ever sweep past the bottom of the conversation.
        seekConversationTop()
        for (pass in 0..maxScrolls) {
            val link = findCitation(domain, partial)
            if (link != null) {
                val label = link.text?.toString() ?: link.contentDescription?.toString() ?: "?"
                s.log("[edge] backlink candidate \"${label.take(60)}\"")
                val clicked = s.clickNode(link)
                link.recycle()
                Thread.sleep(4000)
                // A click that reported success but left the composer on screen never
                // navigated — count it as a miss rather than a backlink in the CSV.
                val stillOnCopilot = composer(timeoutMs = 1500)?.also { it.recycle() } != null
                if (!stillOnCopilot) {
                    s.log("[edge] backlink click -> $clicked, navigated away")
                    browseBacklinkPage()
                    return true
                }
                s.log("[edge] backlink click -> $clicked but still on Copilot — keep looking")
            }
            s.gestureSwipe(s.screenWidth() / 2f, s.screenHeight() * 0.72f,
                           s.screenWidth() / 2f, s.screenHeight() * 0.32f, 600)
            Thread.sleep(1400)
        }
        // Distinguish "the answer never cited this domain" from "the citation was there
        // and the matcher missed it" — the two have completely different fixes.
        s.log("[edge] backlink NOT found for $domain; answer was:\n${readAnswer()}")
        dumpLinkCandidates()
        return false
    }

    /**
     * A clickable citation for [domain].
     *
     * Copilot exposes no "AccessibilityNodeInfo.targetUrl" extra at all — the trick both
     * Chrome flows rely on — and its citation card is a clickable View with empty text
     * wrapping plain TextViews. Those hold the site NAME and page title, not always the
     * domain: "rotorooter.com" is cited as "Roto-Rooter". So compare with punctuation
     * stripped from both sides, and require a clickable ancestor — the same domain also
     * appears in the answer's prose, where clicking it does nothing.
     */
    private fun findCitation(domain: String, partial: String): AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val domainKey = squash(domain)
        val partialKey = squash(partial)
        var promptKey = ""
        var candidate: AccessibilityNodeInfo? = null
        fun walk(node: AccessibilityNodeInfo) {
            val desc = node.contentDescription?.toString()
            if (desc != null && desc.startsWith(PROMPT_BUBBLE_DESC)) {
                // The bubble echoes the business name the citation is being matched on,
                // so it out-matches the real citation. Record it and skip its subtree.
                promptKey = squash(desc)
                return
            }
            val hay = squash(
                (node.extras?.getString("AccessibilityNodeInfo.targetUrl") ?: "") + " " +
                (node.text?.toString() ?: "") + " " +
                (node.contentDescription?.toString() ?: "")
            )
            val hit = domainKey in hay || (partialKey.length > 3 && partialKey in hay)
            // The prompt also renders as a sibling TextView of the bubble. Reject it by
            // length: an echo is long and wholly inside the prompt, a citation label
            // ("Roto-Rooter", a page title) is short or carries text the prompt lacks.
            val isPromptEcho = hay.length > 25 && promptKey.isNotEmpty() && hay in promptKey
            if (hit && !isPromptEcho && hasClickableSelfOrAncestor(node)) {
                // Keep the LAST match: citations render after the prose that names the
                // same business, so the final hit on a screen is the clickable card.
                candidate?.recycle()
                candidate = AccessibilityNodeInfo.obtain(node)
            }
            for (i in 0 until node.childCount) {
                val c = node.getChild(i) ?: continue
                walk(c); c.recycle()
            }
        }
        walk(root); root.recycle()
        return candidate
    }

    private fun squash(t: String) = t.lowercase().filter { it.isLetterOrDigit() }

    private fun hasClickableSelfOrAncestor(node: AccessibilityNodeInfo): Boolean {
        if (node.isClickable) return true
        var p = node.parent
        var up = 0
        while (p != null && up < 5) {
            if (p.isClickable) { p.recycle(); return true }
            val next = p.parent
            p.recycle()
            p = next
            up++
        }
        p?.recycle()
        return false
    }

    /** Log every link-ish node so a miss can be diagnosed from one run's logcat. */
    private fun dumpLinkCandidates() {
        val root = s.rootInActiveWindow ?: return
        val sb = StringBuilder()
        fun walk(node: AccessibilityNodeInfo) {
            val target = node.extras?.getString("AccessibilityNodeInfo.targetUrl")
            val txt = node.text?.toString()
            val desc = node.contentDescription?.toString()
            if (!target.isNullOrBlank() || node.isClickable) {
                sb.appendLine("  cls=${node.className} clickable=${node.isClickable} " +
                    "target=\"${target ?: ""}\" text=\"${txt?.take(60) ?: ""}\" desc=\"${desc?.take(60) ?: ""}\"")
            }
            if (txt is android.text.Spanned) {
                for (u in txt.getSpans(0, txt.length, android.text.style.URLSpan::class.java)) {
                    sb.appendLine("  URLSpan url=\"${u.url}\"")
                }
            }
            for (i in 0 until node.childCount) {
                val c = node.getChild(i) ?: continue
                walk(c); c.recycle()
            }
        }
        walk(root); root.recycle()
        s.log("[edge] link candidates:\n$sb")
    }

    /** Dwell on the opened page so the visit registers as a real read. */
    private fun browseBacklinkPage() {
        for (i in 1..3) {
            s.gestureSwipe(s.screenWidth() / 2f, s.screenHeight() * 0.70f,
                           s.screenWidth() / 2f, s.screenHeight() * 0.35f, 700)
            Thread.sleep(2000)
        }
    }

    // ── screenshot framing ──

    /**
     * Frame the answer for the client screenshot.
     *
     * The anchor is the prompt bubble, not the rank line: it is a wall of instruction
     * text carrying the literal "[RANK: 19/19]" example and must never appear in a
     * client shot, and parking it just off the top edge puts everything worth showing —
     * the ranked names, [RANK: X/Y], the summary — at the top of the frame. Targeting
     * the rank line instead clips rank #1 whenever the list runs long.
     */
    fun frameAnswerForShot(maxSteps: Int = 14): Boolean {
        val h = s.screenHeight()
        val x = s.screenWidth() / 2f
        val headerY = h * 0.12f
        seekConversationTop()
        for (i in 1..maxSteps) {
            val b = settledPromptBubbleBounds()
            if (b == null || b.bottom <= headerY) break
            // Travel exactly the remaining distance: a fixed step overshoots on the last
            // pass and scrolls rank #1 off the top. Swipe slowly so momentum doesn't
            // add travel of its own.
            val dy = (b.bottom - headerY).coerceIn(h * 0.04f, h * 0.55f)
            s.gestureSwipe(x, h * 0.75f, x, h * 0.75f - dy, 900)
            Thread.sleep(1400)
        }
        uncoverFirstAnswerLine()
        if (rankLineBounds() != null) {
            s.log("[edge] frameAnswerForShot: prompt cleared, [RANK] in frame")
            return true
        }
        // A long answer pushes [RANK] below the fold. It matters more than a clean top
        // edge, so fall back to parking it in the lower half and accept a prompt sliver.
        return parkRankLine(maxSteps)
    }

    /**
     * The loop above measures only the bubble, and even a slow swipe releases with some
     * velocity, so it routinely lands list item 1 a few px under Copilot's header fade —
     * the one line a #1 client wants in the picture (measured on the 2026-09-05 set:
     * "1. HeavenSent Exterior Solutions" half-cut at the top of a 1/21 shot). Drag the
     * page back down until the first answer line clears the fade. The drag is short and
     * ends at rest, so it cannot fling and the correction converges.
     */
    private fun uncoverFirstAnswerLine(attempts: Int = 3) {
        val h = s.screenHeight()
        val x = s.screenWidth() / 2f
        val clearY = (h * FIRST_LINE_CLEAR_Y).toInt()
        repeat(attempts) {
            val top = firstAnswerLineTop() ?: return
            if (top >= clearY) return
            val dy = (clearY - top).toFloat().coerceAtLeast(h * 0.03f)
            s.log("[edge] frameAnswerForShot: first answer line at y=$top under header, dragging down ${dy.toInt()}px")
            s.gestureSwipe(x, h * 0.45f, x, h * 0.45f + dy, 700)
            Thread.sleep(1200)
        }
    }

    /**
     * Rows to cut out of the client shot so no prompt text survives.
     *
     * A short answer leaves the page nothing to scroll: the conversation bottoms out with
     * the bubble's last lines still under the header. Measured on the 2026-09-05 set,
     * 13 of 25 v77 Copilot shots carried "Keep the entire response under 280 words."
     * above list item 1. Scrolling cannot fix that, so the band from the header's bottom
     * edge to just above the first answer line is spliced out of the PNG instead.
     * Returns null when the bubble is already off screen or nothing is measurable.
     */
    fun promptBandForShot(): IntRange? {
        val h = s.screenHeight()
        val headerBottom = (h * HEADER_BOTTOM_Y).toInt()
        val bubble = promptBubbleBounds() ?: return null
        if (bubble.bottom <= headerBottom) return null
        val firstLine = firstAnswerLineTop() ?: return null
        val cutTo = firstLine - (h * 0.02f).toInt()
        if (cutTo - headerBottom < (h * 0.02f).toInt()) return null
        return headerBottom until cutTo
    }

    /** Splice [band] out of the PNG at [path] in place; false when nothing was written. */
    fun stripPromptBand(path: String, band: IntRange): Boolean {
        val src = BitmapFactory.decodeFile(path) ?: return false
        val cutHeight = band.last + 1 - band.first
        if (band.first <= 0 || band.last >= src.height - 1 || cutHeight <= 0) {
            src.recycle(); return false
        }
        val out = Bitmap.createBitmap(src.width, src.height - cutHeight, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        val top = Rect(0, 0, src.width, band.first)
        canvas.drawBitmap(src, top, top, null)
        val bottomSrc = Rect(0, band.last + 1, src.width, src.height)
        val bottomDst = Rect(0, band.first, src.width, out.height)
        canvas.drawBitmap(src, bottomSrc, bottomDst, null)
        src.recycle()
        val ok = try {
            FileOutputStream(File(path)).use { out.compress(Bitmap.CompressFormat.PNG, 90, it) }
        } catch (e: Exception) {
            s.log("[edge] stripPromptBand: write failed ${e.message}")
            false
        }
        out.recycle()
        if (ok) s.log("[edge] stripPromptBand: cut rows ${band.first}-${band.last} from shot")
        return ok
    }

    /** Top edge of the highest on-screen answer line; null when no answer text is visible. */
    private fun firstAnswerLineTop(): Int? {
        val root = s.rootInActiveWindow ?: return null
        val sent = StringBuilder()
        val lines = mutableListOf<Pair<String, Rect>>()
        fun walk(node: AccessibilityNodeInfo, depth: Int) {
            if (depth > 25) return
            val desc = node.contentDescription?.toString()
            if (desc != null && desc.startsWith(PROMPT_BUBBLE_DESC)) {
                sent.append(desc.removePrefix(PROMPT_BUBBLE_DESC))
            } else {
                val txt = node.text?.toString()?.trim()
                if (!txt.isNullOrBlank() && node.className?.toString()?.contains("Edit") != true) {
                    val r = Rect()
                    node.getBoundsInScreen(r)
                    if (r.height() > 0) lines.add(txt to r)
                }
            }
            for (i in 0 until node.childCount) {
                node.getChild(i)?.let { walk(it, depth + 1) }
            }
        }
        walk(root, 0)
        root.recycle()
        val prompt = sent.toString()
        return lines
            .filter { (t, _) -> t.length > 1 && !prompt.contains(t) && ANSWER_NOISE.none { t.startsWith(it) } }
            .minOfOrNull { (_, r) -> r.top }
    }

    private fun parkRankLine(maxSteps: Int): Boolean {
        val h = s.screenHeight()
        val x = s.screenWidth() / 2f
        val topBand = (h * 0.50f).toInt()
        val botBand = (h * 0.88f).toInt()
        for (i in 1..maxSteps) {
            val r = rankLineBounds()
            if (r != null) {
                if (r.centerY() in topBand..botBand) {
                    s.log("[edge] parkRankLine: [RANK] at y=${r.centerY()} (step $i)")
                    return true
                }
                if (r.centerY() < topBand) {
                    s.gestureSwipe(x, h * 0.35f, x, h * 0.62f, 600)
                    Thread.sleep(1400); continue
                }
            }
            s.gestureSwipe(x, h * 0.72f, x, h * 0.45f, 600)
            Thread.sleep(1500)
        }
        s.log("[edge] parkRankLine: [RANK] not positioned after $maxSteps steps")
        return false
    }

    /**
     * The bubble node drops out of Copilot's virtualized tree for a moment during
     * re-layout while the bubble is still on screen. Treating that first null as
     * "scrolled off" ended the parking loop with three lines of prompt text in the
     * client shot (device-103, 2026-09-05). Re-query before believing it.
     */
    private fun settledPromptBubbleBounds(): Rect? {
        repeat(3) {
            promptBubbleBounds()?.let { return it }
            Thread.sleep(500)
        }
        return null
    }

    private fun promptBubbleBounds(): Rect? {
        val n = s.findNode(contentDesc = PROMPT_BUBBLE_DESC, timeoutMs = 300) ?: return null
        val r = Rect(); n.getBoundsInScreen(r); n.recycle()
        return if (r.height() > 0) r else null
    }

    // Digits only: the prompt bubble echoes the literal "[RANK: X/Y]" instruction.
    private val rankAnswerPattern = Regex("""\[rank:\s*\d+\s*/\s*\d+""", RegexOption.IGNORE_CASE)

    private fun rankLineBounds(): Rect? {
        val root = s.rootInActiveWindow ?: return null
        var found: Rect? = null
        fun walk(node: AccessibilityNodeInfo) {
            val t = node.text?.toString() ?: ""
            if (rankAnswerPattern.containsMatchIn(t)) {
                val r = Rect(); node.getBoundsInScreen(r)
                if (r.height() > 0) found = r
            }
            for (i in 0 until node.childCount) {
                val c = node.getChild(i) ?: continue
                walk(c); c.recycle()
            }
        }
        walk(root); root.recycle()
        return found
    }
}
