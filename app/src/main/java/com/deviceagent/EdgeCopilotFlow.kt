package com.deviceagent

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.graphics.Rect
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
        private val ANSWER_NOISE = listOf(
            "Message Copilot", "Show all", "Smart", "Quick response", "Think Deeper"
        )
    }

    // ── reset ──

    /**
     * Wipe Edge to first-run, relaunch it and walk the FRE until Copilot is reachable.
     * The wipe is what keeps every job logged out and cookie-free, the same reason the
     * Chrome flows use a full clear rather than "Delete browsing data".
     */
    fun reset(): Boolean {
        s.log("── RESET EDGE ──")
        val cleared = try {
            flow.clearChromeData(PKG)
        } catch (e: Exception) {
            s.log("[edge] clear ex: ${e.message}"); false
        }
        s.log("[edge] clearData -> $cleared")
        launch()
        return dismissFre()
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
     * Edge's first run is a fixed sequence of screens — sign-in, a data-collection
     * confirm, then a notifications permission — each identified by one node. Poll
     * rather than assume an order: under a proxy the screens arrive slowly and the
     * sign-in one appears twice. Done as soon as the Copilot button is reachable.
     */
    private fun dismissFre(): Boolean {
        s.log("── DISMISS EDGE FRE ──")
        val buttons = listOf(
            "text" to "Not now",
            "id" to "fre_sign_in_later",
            "text" to "Confirm",
            "id" to "permission_deny_button",
            "text" to "Don't allow",
            "text" to "Skip"
        )
        val deadline = System.currentTimeMillis() + 90_000
        var idle = 0
        while (System.currentTimeMillis() < deadline) {
            copilotButton()?.let {
                it.recycle()
                s.log("[edge] FRE done — Copilot button reachable")
                return true
            }
            var tapped = false
            for ((kind, value) in buttons) {
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
            if (!tapped) { idle++; if (idle >= 8) break; Thread.sleep(2000) } else idle = 0
        }
        s.log("[edge] FRE did not reach the Copilot button")
        return false
    }

    // ── copilot surface ──

    private fun copilotButton(): AccessibilityNodeInfo? =
        s.findNode(resourceId = COPILOT_BUTTON_ID, timeoutMs = 800)

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
        val btn = copilotButton() ?: run { s.log("[edge] Copilot button not found"); return false }
        s.clickNode(btn); btn.recycle()
        Thread.sleep(7000)
        val box = composer(timeoutMs = 10_000)
        if (box == null) { s.log("[edge] Copilot composer never appeared"); return false }
        box.recycle()
        return true
    }

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
    fun waitForAnswer(timeoutSec: Int): Boolean {
        s.log("── COPILOT WAIT (${timeoutSec}s) ──")
        val deadline = System.currentTimeMillis() + timeoutSec * 1000L
        var sawStreaming = false
        while (System.currentTimeMillis() < deadline) {
            Thread.sleep(1000)
            if (s.findNode(text = "Network issues", timeoutMs = 300) != null) {
                s.log("[edge] Copilot reported network issues")
                return false
            }
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
            val b = promptBubbleBounds()
            if (b == null || b.bottom <= headerY) break
            // Travel exactly the remaining distance: a fixed step overshoots on the last
            // pass and scrolls rank #1 off the top. Swipe slowly so momentum doesn't
            // add travel of its own.
            val dy = (b.bottom - headerY).coerceIn(h * 0.04f, h * 0.55f)
            s.gestureSwipe(x, h * 0.75f, x, h * 0.75f - dy, 900)
            Thread.sleep(1400)
        }
        if (rankLineBounds() != null) {
            s.log("[edge] frameAnswerForShot: prompt cleared, [RANK] in frame")
            return true
        }
        // A long answer pushes [RANK] below the fold. It matters more than a clean top
        // edge, so fall back to parking it in the lower half and accept a prompt sliver.
        return parkRankLine(maxSteps)
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
