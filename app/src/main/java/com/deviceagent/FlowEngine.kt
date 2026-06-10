package com.deviceagent

class FlowEngine(private val s: AgentAccessibilityService) {

    // ── chrome reset ──

    fun resetChrome(): Boolean {
        s.log("── RESET CHROME ──")

        // Pre-cleanup
        s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        Thread.sleep(300)
        s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        Thread.sleep(300)
        s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME)
        Thread.sleep(500)

        // Open Chrome
        s.navigateToUrl("https://www.google.com")
        Thread.sleep(5000)
        dismissFreInline()
        Thread.sleep(500)

        // Find 3-dot menu (English Chrome — works on all brands when locale is EN)
        val menuBtn = s.findNode(contentDesc = "Customise and control Google Chrome", timeoutMs = 8000)
            ?: s.findNode(contentDesc = "Customize and control Google Chrome", timeoutMs = 3000)
        if (menuBtn == null) {
            s.log("Chrome menu not found — continuing without data clear")
            return true
        }
        s.clickNode(menuBtn)
        Thread.sleep(1500)

        // "Delete browsing data"
        val deleteBrowsing = s.findNode(text = "Delete browsing data", timeoutMs = 2000)
        if (deleteBrowsing == null) {
            s.log("Delete browsing data not found — skipping clear")
            s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
            Thread.sleep(500)
            return true
        }
        s.clickNode(deleteBrowsing)
        Thread.sleep(2000)

        // Change time range to "All time"
        val timeRange = s.findNode(text = "Last 15 minutes", timeoutMs = 1500)
            ?: s.findNode(text = "Last hour", timeoutMs = 1000)
            ?: s.findNode(text = "Last 24 hours", timeoutMs = 1000)
            ?: s.findNode(text = "Last 7 days", timeoutMs = 1000)
            ?: s.findNode(text = "Last 4 weeks", timeoutMs = 1000)
        if (timeRange != null) {
            s.clickNode(timeRange)
            Thread.sleep(800)
            s.findNode(text = "All time", timeoutMs = 2000)?.let {
                s.clickNode(it); Thread.sleep(800)
            }
        }

        // Tap "Delete data"
        (s.findNode(text = "Delete data", timeoutMs = 3000)
            ?: s.findNode(text = "Clear data", timeoutMs = 2000))?.let {
            s.clickNode(it)
            Thread.sleep(2000)
        }
        s.log("Chrome reset done")
        return true
    }

    // ── FRE dismissal ──

    fun dismissChromeFre(): Boolean {
        s.log("── DISMISS CHROME FRE ──")
        s.navigateToUrl("https://www.google.com")
        Thread.sleep(2000)

        val freButtons = listOf(
            "Accept & continue", "Use without an account", "Stay signed out",
            "Got it", "No thanks", "Never allow", "Skip", "Not now", "Maybe later",
            "Next", "Continue", "OK"
        )

        for (attempt in 1..12) {
            var dismissed = false
            for (btnText in freButtons) {
                val node = s.findNode(text = btnText, timeoutMs = 500)
                if (node != null) {
                    s.log("FRE: clicking \"$btnText\"")
                    s.clickNode(node)
                    dismissed = true
                    Thread.sleep(800)
                    break
                }
            }
            if (!dismissed) {
                s.log("FRE: no known buttons found (attempt $attempt)")
                break
            }
        }
        return true
    }

    // ── preflight ──

    /**
     * Verify the proxy can reach the kind of sites we actually audit.
     * Loads google.com (same parent as Gemini, same TLS/Cloudflare profile
     * as ChatGPT/Perplexity) and looks for the search input. This is a
     * far better signal than ifconfig.me, which uses a different route
     * and frequently works even when the platforms fail.
     *
     * Returns "google_ok" on success, null on failure. The IP can no longer
     * be captured this way (no plain-IP endpoint), but the platform
     * reachability signal is far more valuable.
     */
    fun preflightConnectivity(): String? {
        s.log("── PREFLIGHT: checking proxy via google.com ──")
        s.navigateToUrl("https://www.google.com")
        Thread.sleep(3000)
        // Look for the Google search box. It's an EditText below the URL bar.
        // findInputField filters out the URL bar (top > 200) so any returned
        // node is real page content.
        if (s.findInputField(timeoutMs = 6000) != null) {
            s.log("PREFLIGHT OK — google.com loaded with search box visible")
            return "google_ok"
        }
        // Try a reload once — slow proxies sometimes need it
        s.log("PREFLIGHT: no search box on first try — reloading")
        s.navigateToUrl("https://www.google.com")
        Thread.sleep(4000)
        if (s.findInputField(timeoutMs = 8000) != null) {
            s.log("PREFLIGHT OK — google.com loaded after reload")
            return "google_ok"
        }
        // Failed. Dump deeper tree + screenshot so logs show truth.
        val tree = s.dumpTree(20)
        s.log("PREFLIGHT FAILED — google.com unreachable through this proxy")
        s.log("PREFLIGHT tree-depth20 (first 1000 chars): ${tree.take(1000)}")
        try {
            val shot = s.saveScreenshot("preflight_fail_${System.currentTimeMillis()}")
            if (shot != null) s.log("PREFLIGHT screenshot: $shot")
        } catch (e: Exception) {
            // screenshot is best-effort
        }
        return null
    }

    private fun isPrivateOrLoopback(ip: String): Boolean {
        val parts = ip.split(".").mapNotNull { it.toIntOrNull() }
        if (parts.size != 4) return true
        val (a, b) = parts[0] to parts[1]
        return a == 10 ||
            a == 127 ||
            (a == 172 && b in 16..31) ||
            (a == 192 && b == 168) ||
            (a == 169 && b == 254) ||
            a == 0
    }

    // ── navigate ──

    /**
     * Open the platform's URL in Chrome and wait until the page is interactive
     * — defined as "an EditText (the prompt input) is present below the URL bar".
     *
     * This is a stronger signal than text-matching "site can't be reached":
     * Chrome's WebView error page is not always exposed via accessibility,
     * and a blank/half-loaded page also lacks the input field. Either case
     * means we can't run a session — fail fast and let the dispatcher rotate
     * the Decodo session.
     */
    fun navigateTo(platform: String): Boolean {
        s.log("── NAVIGATE TO $platform ──")
        val url = when (platform.lowercase()) {
            "gemini" -> "https://gemini.google.com"
            "chatgpt" -> "https://chatgpt.com"
            "perplexity" -> "https://www.perplexity.ai"
            else -> return false
        }
        s.navigateToUrl(url)
        // Wait for page to load — ChatGPT is slower than Gemini
        val waitMs = if (platform.lowercase() == "chatgpt") 6000L else 3000L
        Thread.sleep(waitMs)
        // Check for "site cannot be reached" and auto-reload up to 2 times
        for (retry in 1..2) {
            val tree = s.dumpTree(8).lowercase()
            if ("site can" in tree || "err_" in tree || "net::err" in tree) {
                s.log("Page load error detected — reloading (retry $retry/2)...")
                val reload = s.findNode(text = "Reload", timeoutMs = 2000)
                if (reload != null) {
                    s.clickNode(reload)
                } else {
                    s.navigateToUrl(url)
                }
                Thread.sleep(waitMs)
            } else {
                break
            }
        }
        return true
    }

    // ── google maps map-pack (CitedLogic) ──

    /** Navigate straight to a Google Maps search URL for the query and wait for the
     *  local results pack to render. When lat/lng are given, they are embedded in
     *  the URL (`/@lat,lng,13z`) so the map CENTERS on the target metro — Maps reads
     *  the viewport center, not the device GPS, which the mock doesn't reliably
     *  override for Chrome's geolocation. Dismisses Google's consent interstitials. */
    fun navigateGoogleMapsSearch(query: String, lat: Double, lng: Double): Boolean {
        // "near me" forces Maps to resolve to the DEVICE location (overriding the
        // @viewport), so strip it when we have coords — the map center IS the metro.
        val hasCoords = lat.isFinite() && lng.isFinite() && (lat != 0.0 || lng != 0.0)
        val q = if (hasCoords)
            query.replace(Regex("(?i)\\s*\\bnear\\s*(by|me)\\b"), "").trim()
        else query
        s.log("── GOOGLE MAPS SEARCH: \"${q.take(50)}\" @ $lat,$lng ──")
        var url = "https://www.google.com/maps/search/" +
            java.net.URLEncoder.encode(q, "UTF-8")
        if (hasCoords) {
            url += "/@$lat,$lng,13z"
        }
        s.navigateToUrl(url)
        Thread.sleep(9000)  // Maps is heavy — give the map + results time to load
        for (retry in 1..2) {
            val tree = s.dumpTree(8).lowercase()
            if ("site can" in tree || "net::err" in tree || "err_" in tree) {
                s.log("Maps load error — reloading (retry $retry/2)")
                s.navigateToUrl(url)
                Thread.sleep(8000)
            } else break
        }
        dismissGoogleConsent()
        Thread.sleep(3500)  // let the results list settle after consent
        return true
    }

    private fun dismissGoogleConsent() {
        val labels = listOf(
            "Accept all", "Reject all", "I agree", "Accept", "Got it",
            "No thanks", "Dismiss", "Stay on web", "Continue"
        )
        for (round in 1..2) {
            var hit = false
            for (label in labels) {
                val node = s.findNode(text = label, timeoutMs = 800)
                    ?: s.findNode(contentDesc = label, timeoutMs = 500)
                if (node != null) {
                    s.clickNode(node)
                    s.log("Maps consent dismissed: $label")
                    hit = true
                    Thread.sleep(900)
                }
            }
            if (!hit) break
        }
    }

    // ── google SERP in Chrome (CitedLogic `google-maps` engine) ──
    // Ported from the proven v0.8.0 SEO flow: launch Chrome → google.com home →
    // human-typed search → ?q= fallback. The "google-maps" engine captures the
    // SERP map pack from a PLAIN Google search, not maps.google.com.

    /** Buttons that dismiss Chrome interstitials / cookie consent blocking google.com. */
    private val googleDialogButtons = listOf(
        "No thanks", "No, thanks", "Got it", "Accept all", "Reject all",
        "I agree", "I Agree", "Continue", "Close", "Use without an account"
    )

    /** Open google.com home, dismiss any interstitial, and wait for the search box to be ready. */
    fun navigateToGoogleHome(): Boolean {
        s.log("── NAVIGATE google.com ──")
        s.navigateToUrl("https://www.google.com")
        for (attempt in 1..12) {
            Thread.sleep(800)
            for (label in googleDialogButtons) {
                val b = s.findNode(text = label, timeoutMs = 250)
                if (b != null) {
                    s.clickNode(b); b.recycle()
                    s.log("dismissed dialog: $label")
                    Thread.sleep(600)
                }
            }
            val n = s.findInputField(hintText = null, timeoutMs = 1200)
            if (n != null) { n.recycle(); s.log("Google search box ready (attempt $attempt)"); return true }
        }
        s.log("Google search box not found")
        return false
    }

    /**
     * Submit the human-typed search. After typing, Google opens an autocomplete dropdown and
     * moves the box up (to y≈179) — so the on-page submit button vanishes and findInputField's
     * top>200 guard skips the box. Order that actually works (verified on-device):
     *   1) tap the exact-match autocomplete suggestion row (human; preserves the exact query)
     *   2) IME "search" action on the box found by its query text (any y, not the omnibox)
     *   3) on-page "Google Search" button (only present when the box is empty/unfocused)
     *   4) keyboard enter tap
     */
    fun submitSearch(keyword: String): Boolean {
        s.log("── SUBMIT SEARCH ──")
        ensureChromeForeground()
        Thread.sleep(400)

        val sugg = findSearchSuggestion(keyword)
        if (sugg != null) {
            val ok = s.clickNode(sugg); sugg.recycle()
            if (ok) { s.log("Tapped exact suggestion row"); Thread.sleep(1500); return true }
        }

        val box = findEditTextContaining(keyword)
        if (box != null && android.os.Build.VERSION.SDK_INT >= 30) {
            val ok = try {
                box.performAction(
                    android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id
                )
            } catch (e: Exception) { s.log("IME_ENTER threw: ${e.message}"); false }
            box.recycle()
            if (ok) { s.log("IME_ENTER on query box ok"); Thread.sleep(1500); return true }
        } else box?.recycle()

        for (cd in listOf("Google Search", "Search")) {
            val b = s.findNode(contentDesc = cd, timeoutMs = 800)
            if (b != null) {
                val ok = s.clickNode(b); b.recycle()
                if (ok) { s.log("Clicked '$cd' submit"); Thread.sleep(1500); return true }
            }
        }

        s.gestureTap(s.screenWidth() - 40f, s.screenHeight() - 45f)
        s.log("Fallback keyboard-enter tap")
        Thread.sleep(1500)
        return true
    }

    /** Find a clickable autocomplete row whose text exactly matches the typed query. */
    private fun findSearchSuggestion(keyword: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val match = findSuggestionRec(root, keyword.trim().lowercase())
        root.recycle()
        return match
    }

    private fun findSuggestionRec(
        node: android.view.accessibility.AccessibilityNodeInfo,
        kw: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val cls = node.className?.toString() ?: ""
        val txt = node.text?.toString()?.trim()?.lowercase()
        if (txt == kw && node.isClickable && !cls.contains("EditText")) return node
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                findSuggestionRec(child, kw)?.let { return it }
            }
        }
        return null
    }

    /** Find the search-box EditText by its query text (excludes the Chrome omnibox). */
    private fun findEditTextContaining(keyword: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val kw = keyword.trim().lowercase().take(12)
        val match = findEditContainingRec(root, kw)
        root.recycle()
        return match
    }

    private fun findEditContainingRec(
        node: android.view.accessibility.AccessibilityNodeInfo,
        kw: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val cls = node.className?.toString() ?: ""
        val txt = node.text?.toString()?.trim()?.lowercase() ?: ""
        if (cls.contains("EditText") && txt.contains(kw) &&
            !txt.startsWith("google.com") && !txt.startsWith("http")) {
            return node
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                findEditContainingRec(child, kw)?.let { return it }
            }
        }
        return null
    }

    private val imagePuzzlePhrases = listOf(
        "select all", "select each image", "verify you are human by completing",
        "traffic lights", "crosswalk", "bicycles", "fire hydrant", "press & hold",
        "try again later", "click verify once there are none"
    )

    /**
     * Attempt to clear a Google "unusual traffic" reCAPTCHA by ticking the "I'm not a robot"
     * checkbox. For a low-risk (soft) challenge this passes outright and Google redirects to the
     * results — returns true once a SERP appears. If reCAPTCHA escalates to an image puzzle
     * (or "try again later"), it can't be auto-solved here and returns false.
     */
    fun solveChallenge(timeoutSec: Int = 22): Boolean {
        s.log("── SOLVE CHALLENGE (tick 'I'm not a robot') ──")
        ensureChromeForeground()
        val box = s.findNode(text = "I'm not a robot", timeoutMs = 2500)
            ?: s.findNode(className = "CheckBox", timeoutMs = 1500)
        if (box == null) { s.log("'I'm not a robot' checkbox not found"); return false }
        val r = android.graphics.Rect(); box.getBoundsInScreen(r)
        val clicked = s.clickNode(box)
        box.recycle()
        if (!clicked) {
            // The checkbox often lives in an iframe — fall back to a direct tap on its bounds.
            s.gestureTap(r.centerX().toFloat(), r.centerY().toFloat())
        }
        s.log("ticked checkbox (clickNode=$clicked) at ${r.centerX()},${r.centerY()}")

        val deadline = System.currentTimeMillis() + timeoutSec * 1000L
        while (System.currentTimeMillis() < deadline) {
            Thread.sleep(1200)
            val nodes = flattenTree()
            val blob = nodes.joinToString(" ") { it.text + " " + it.cd }.lowercase()
            if (imagePuzzlePhrases.any { it in blob }) {
                s.log("reCAPTCHA escalated to an image/advanced puzzle — cannot auto-solve")
                return false
            }
            val ready = nodes.any { it.text == "Search Results" || it.text == "Web results" } ||
                nodes.any { httpRe.containsMatchIn(it.text) && !it.text.contains("google.com") }
            if (ready) { s.log("✓ challenge passed — SERP loaded"); return true }
        }
        s.log("challenge not cleared in ${timeoutSec}s")
        return false
    }

    /** Guaranteed SERP fallback: load google.com/search?q=<keyword> directly. */
    fun navigateToSerp(keyword: String): Boolean {
        val q = java.net.URLEncoder.encode(keyword, "UTF-8")
        s.log("── NAVIGATE SERP DIRECT: ?q=$q ──")
        s.navigateToUrl("https://www.google.com/search?q=$q")
        return true
    }

    /**
     * Load a Google SERP localized to [location] via the `uule` URL parameter.
     * [location] is a canonical "City,State,United States" string; Google renders
     * results as if the searcher is physically there — no proxy/GPS needed, and
     * (on a clean home IP) no reCAPTCHA. Falls back to a plain ?q= search when
     * [location] is blank.
     */
    fun navigateToSerpLocalized(keyword: String, location: String): Boolean {
        if (location.isBlank()) return navigateToSerp(keyword)
        val q = java.net.URLEncoder.encode(keyword, "UTF-8")
        val uule = buildUule(location)
        s.log("── NAVIGATE SERP uule: ?q=$q loc=\"$location\" ──")
        s.navigateToUrl("https://www.google.com/search?q=$q&uule=$uule&gl=us&hl=en")
        return true
    }

    /**
     * Build Google's `uule` location parameter (the SerpApi/rank-tracker standard).
     * Protobuf-style header [8,2,16,32,34,len] + the canonical-name bytes, base64'd
     * (URL-safe: +→-, /→_, no padding), prefixed "w+". Mirrors ogun/uule_grabber.
     */
    private fun buildUule(location: String): String {
        val nameBytes = location.toByteArray(Charsets.UTF_8)
        val header = byteArrayOf(8, 2, 16, 32, 34, nameBytes.size.toByte())
        val b64 = android.util.Base64.encodeToString(
            header + nameBytes,
            android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING
        ).replace('+', '-').replace('/', '_')
        return "w+$b64"
    }

    /** Set by waitForSerp when a Cloudflare / Google bot challenge interstitial was seen. */
    var lastChallengeSeen: Boolean = false
        private set

    private val challengePhrases = listOf(
        "verifying you are human", "checking your browser", "just a moment",
        "needs to review the security", "unusual traffic", "i'm not a robot",
        "detected unusual traffic", "verify you are a human", "cloudflare"
    )

    private val connErrPhrases = listOf(
        "site can't be reached", "site can’t be reached", "err_connection",
        "err_timed_out", "err_name_not_resolved", "err_proxy", "err_tunnel",
        "err_empty_response", "err_address_unreachable", "webpage is not available"
    )

    /** Poll until the SERP looks loaded (results header or a non-google result URL present). */
    fun waitForSerp(timeoutSec: Int = 15): Boolean {
        lastChallengeSeen = false
        val deadline = System.currentTimeMillis() + timeoutSec * 1000L
        while (System.currentTimeMillis() < deadline) {
            val nodes = flattenTree()
            val blob = nodes.joinToString(" ") { it.text + " " + it.cd }.lowercase()
            if (challengePhrases.any { it in blob }) {
                lastChallengeSeen = true
                s.log("⚠ bot/cloudflare challenge interstitial — waiting it out")
                Thread.sleep(1500)
                continue
            }
            if (connErrPhrases.any { it in blob }) {
                s.log("⚠ connection-error page — tapping Reload")
                val reload = s.findNode(text = "Reload", timeoutMs = 800)
                    ?: s.findNode(contentDesc = "Refresh", timeoutMs = 500)
                if (reload != null) { s.clickNode(reload); reload.recycle() }
                Thread.sleep(2800)
                continue
            }
            val ready = nodes.any { it.text == "Search Results" || it.text == "Web results" } ||
                nodes.any { httpRe.containsMatchIn(it.text) && !it.text.contains("google.com") }
            if (ready) { s.log("SERP ready"); return true }
            Thread.sleep(800)
        }
        s.log("SERP wait timed out (challenge=$lastChallengeSeen)")
        return false
    }

    /** Dismiss "See results closer to you?" and similar overlays sitting on the SERP. */
    fun dismissSerpDialogs(): Boolean {
        val dismissButtons = listOf(
            "Not now", "No thanks", "No, thanks", "Dismiss", "Got it",
            "Maybe later", "Skip", "Close", "Reject all"
        )
        var any = false
        for (attempt in 1..3) {
            var hit = false
            for (btn in dismissButtons) {
                val node = s.findNode(text = btn, timeoutMs = 400)
                if (node != null) {
                    s.log("SERP dialog: clicking \"$btn\"")
                    s.clickNode(node); node.recycle()
                    hit = true; any = true
                    Thread.sleep(700)
                    break
                }
            }
            if (!hit) break
        }
        return any
    }

    private data class FlatNode(val cls: String, val text: String, val cd: String, val targetUrl: String?)

    private fun flattenTree(): List<FlatNode> {
        val out = ArrayList<FlatNode>()
        val root = s.rootInActiveWindow ?: return out
        flattenInto(root, out, 0)
        root.recycle()
        return out
    }

    private fun flattenInto(
        node: android.view.accessibility.AccessibilityNodeInfo,
        out: ArrayList<FlatNode>,
        depth: Int
    ) {
        if (depth > 40) return
        val cls = node.className?.toString()?.substringAfterLast('.') ?: ""
        val text = node.text?.toString()?.trim() ?: ""
        val cd = node.contentDescription?.toString()?.trim() ?: ""
        var url: String? = null
        try {
            node.extras?.getCharSequence("AccessibilityNodeInfo.targetUrl")?.toString()?.let {
                if (it.isNotBlank()) url = it
            }
        } catch (_: Exception) {}
        if (text.isNotEmpty() || cd.isNotEmpty() || url != null) {
            out.add(FlatNode(cls, text, cd, url))
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { flattenInto(it, out, depth + 1) }
        }
    }

    private val httpRe = Regex("^https?://")

    // ── content-aware capture stop ──

    /** Per-platform markers that only appear at the END of the answer/results.
     *  For google-maps the deliverable is the SERP map pack (the "Businesses"
     *  block) — "More businesses" is its bottom edge, so the capture stops there
     *  instead of scrolling the rest of the SERP. */
    private val answerEndMarkers = mapOf(
        "chatgpt" to listOf("Read aloud", "Good response", "Bad response"),
        "gemini" to listOf("Good response", "Bad response", "Show drafts"),
        "perplexity" to listOf("Related", "Ask a follow-up", "Ask follow-up"),
        "google-maps" to listOf("More businesses", "Related searches", "More results", "People also search for")
    )

    /**
     * True when the captured text is ChatGPT's "Log in or sign up" auth wall
     * instead of an answer. ChatGPT hard-gates logged-out sessions on some proxy
     * IPs — this is the full auth page (not a dismissable modal), so the only
     * recovery is a fresh exit IP. A real med-spa answer never contains two+
     * "Continue with <provider>" buttons, so this won't false-positive.
     */
    fun isLoginWall(responseText: String): Boolean {
        val providers = listOf(
            "Continue with Google", "Continue with Apple", "Continue with Microsoft",
            "Continue with phone"
        )
        val hits = providers.count { responseText.contains(it, ignoreCase = true) }
        return hits >= 2 ||
            (responseText.contains("Log in or sign up", ignoreCase = true) && hits >= 1) ||
            (responseText.contains("Welcome back", ignoreCase = true) && hits >= 1)
    }

    /** Popups that appear ASYNCHRONOUSLY over the page mid-capture (e.g. Google's
     *  "See results closer to you?" — observed popping up AFTER dismiss_serp_dialogs
     *  already ran, covering the map pack in every frame). Cheap enough to call
     *  before every frame. */
    fun dismissMidCapturePopup(): Boolean {
        for (label in listOf("Not now", "No thanks")) {
            val node = s.findNode(text = label, timeoutMs = 250)
            if (node != null) {
                s.clickNode(node); node.recycle()
                s.log("mid-capture popup dismissed: $label")
                Thread.sleep(600)
                return true
            }
        }
        return false
    }

    /**
     * True when an end-of-answer marker is actually VISIBLE on screen (not just present
     * in the tree below the fold) — the capture loop stops scrolling once the frame
     * containing the answer's end has been grabbed, instead of swiping to the very
     * bottom of the page.
     */
    fun isAnswerEndVisible(platform: String): Boolean {
        val markers = answerEndMarkers[platform.lowercase()] ?: return false
        val h = s.screenHeight()
        for (m in markers) {
            val node = s.findNode(text = m, timeoutMs = 300)
                ?: s.findNode(contentDesc = m, timeoutMs = 200)
            if (node != null) {
                val r = android.graphics.Rect()
                node.getBoundsInScreen(r)
                val visible = node.isVisibleToUser && r.top in 1 until h
                node.recycle()
                if (visible) { s.log("answer end marker visible: \"$m\" (top=${r.top})"); return true }
            }
        }
        return false
    }

    // ── input text ──

    fun inputText(text: String): Boolean {
        s.log("── INPUT TEXT: \"${text.take(50)}...\" ──")
        ensureChromeForeground()
        Thread.sleep(1000)

        var inputNode: android.view.accessibility.AccessibilityNodeInfo? = null
        var inputBounds: android.graphics.Rect? = null

        // Step A: Find the input field (fast)
        inputNode = s.findInputField(hintText = null, timeoutMs = 5000)
        if (inputNode == null) {
            for (attempt in 1..4) {
                Thread.sleep(1500)
                inputNode = s.findInputField(hintText = null, timeoutMs = 2000)
                if (inputNode != null) break
            }
        }
        if (inputNode == null) {
            inputNode = findPerplexityInput()
        }
        if (inputNode != null) {
            val b = android.graphics.Rect()
            inputNode.getBoundsInScreen(b)
            inputBounds = android.graphics.Rect(b)
            s.log("[A] Input at $inputBounds")
        } else {
            s.log("[A] Input NOT FOUND!")
        }

        // Step B: Try ACTION_SET_TEXT (Chrome lies — returns true but doesn't set)
        if (inputNode != null) {
            s.clickNode(inputNode)
            Thread.sleep(300)
            s.setTextOnNode(inputNode, text) // ignore return — Chrome lies
            // Quick verify
            Thread.sleep(150)
            val v = s.findInputField(hintText = null, timeoutMs = 800)
            val actual = v?.text?.toString() ?: ""
            v?.recycle()
            if (actual.contains(text.take(10))) {
                s.log("[B] Text set OK")
                inputNode.recycle()
                return true
            }
            s.log("[B] Text NOT set, going to paste...")
        }

        // Step C: Set clipboard & paste.
        // Clear the field first: Step B's ACTION_SET_TEXT may have actually landed even
        // though the verify missed it (Chrome lies about timing) — pasting on top then
        // produces doubled text ("querytquery"). Emptying the field makes paste idempotent.
        if (inputNode != null) {
            try { s.setTextOnNode(inputNode, "") } catch (_: Exception) {}
            Thread.sleep(120)
        }
        s.setClipboard(text)
        Thread.sleep(150)

        if (inputNode != null && tryPasteOnNode(inputNode)) {
            s.log("[C] ACTION_PASTE OK")
            inputNode.recycle()
            return true
        }

        // Step D: Long-press paste at exact input position
        val pasteX = if (inputBounds != null) inputBounds.centerX().toFloat() else s.screenWidth() / 2f
        val pasteY = if (inputBounds != null) inputBounds.centerY().toFloat() else s.screenHeight() * 0.85f
        s.gestureTap(pasteX, pasteY)
        Thread.sleep(200)
        if (s.pasteAt(pasteX, pasteY)) {
            s.log("[D] Paste menu OK")
            inputNode?.recycle()
            return true
        }

        // Step E: Last resort
        s.gestureTap(pasteX, pasteY)
        Thread.sleep(500)
        val focused = s.findNode(className = "EditText", timeoutMs = 1500)
        if (focused != null && tryPasteOnNode(focused)) {
            s.log("[E] ACTION_PASTE OK")
            focused.recycle()
            inputNode?.recycle()
            return true
        }
        focused?.recycle()
        inputNode?.recycle()
        s.log("── ALL INPUT STRATEGIES FAILED ──")
        return false
    }

    /** Try ACTION_PASTE (API 29+) on a node. Sets clipboard first. */
    private fun tryPasteOnNode(node: android.view.accessibility.AccessibilityNodeInfo): Boolean {
        if (android.os.Build.VERSION.SDK_INT < 29) return false
        try {
            val ok = node.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_PASTE)
            if (ok) {
                s.log("ACTION_PASTE succeeded")
                return true
            }
        } catch (e: Exception) {
            s.log("ACTION_PASTE error: ${e.message}")
        }
        return false
    }

    /** Find Perplexity's contenteditable input by every possible match */
    private fun findPerplexityInput(): android.view.accessibility.AccessibilityNodeInfo? {
        return s.findNode(resourceId = "ask-input", timeoutMs = 1500)
            ?: s.findNode(contentDesc = "Ask anything", timeoutMs = 1000)
            ?: s.findNode(text = "Ask anything", timeoutMs = 1000)
            ?: s.findNode(resourceId = "ask", timeoutMs = 500)
            ?: s.findNode(text = "Type @", timeoutMs = 500)
            ?: s.findNode(text = "Type /", timeoutMs = 500)
    }

    private fun ensureChromeForeground() {
        val root = s.rootInActiveWindow
        if (root == null) return  // can't determine, assume Chrome is ok
        val pkg = root.packageName?.toString()
        root.recycle()
        if (pkg != "com.android.chrome") {
            s.log("Switching to Chrome...")
            val intent = android.content.Intent(android.content.Intent.ACTION_MAIN).apply {
                addCategory(android.content.Intent.CATEGORY_LAUNCHER)
                setPackage("com.android.chrome")
                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            s.startActivity(intent)
            Thread.sleep(1000)
            s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
            Thread.sleep(500)
        }
    }

    // ── submit ──

    fun submit(expectedText: String? = null): Boolean {
        s.log("── SUBMIT ──")
        ensureChromeForeground()
        val submitSelectors = listOf(
            "Submit" to "cd",
            "Send message" to "cd",
            "Send prompt" to "cd",
            "Send" to "text",
            "Go" to "cd"
        )
        // Two passes: prefer clickable, then any match
        var clickedAny = false
        outer@ for (pass in 1..2) {
            for ((label, type) in submitSelectors) {
                val node = if (type == "cd") {
                    s.findNode(contentDesc = label, timeoutMs = 2000)
                } else {
                    s.findNode(text = label, timeoutMs = 2000)
                }
                if (node != null) {
                    val clicked = s.clickNode(node)
                    if (clicked) {
                        s.log("Clicked submit: $label (pass $pass)")
                        Thread.sleep(1000)
                        clickedAny = true
                        break@outer
                    }
                    s.log("Found '$label' but click failed, trying next...")
                }
            }
            Thread.sleep(500)
        }
        if (!clickedAny) {
            // Fallback: tap bottom-right corner (Perplexity submit button area)
            s.gestureTap(s.screenWidth() - 60f, s.screenHeight() * 0.82f)
            s.log("Fallback tap for submit (bottom-right)")
        }
        if (expectedText == null) return true
        return verifySubmitted(expectedText, submitSelectors)
    }

    /**
     * ACTION_CLICK on a web "send" button can silently do nothing when the page's JS
     * never registered the ACTION_SET_TEXT input (Gemini's logged-out composer keeps
     * the send button functionally disabled — seen 2026-06-10: prompt typed, submit
     * "OK", page still on the landing screen 70s later). Verify the composer actually
     * EMPTIED; if not, escalate: real gesture tap on the button → clear + focus +
     * clipboard-paste re-input (paste fires real input events) → gesture tap again.
     */
    private fun verifySubmitted(expectedText: String, submitSelectors: List<Pair<String, String>>): Boolean {
        // The reliable "it actually sent" signal: the prompt is echoed back as a
        // message bubble — a NON-edit text node with the prompt's text. Checking
        // composer emptiness false-positives when the IME window owns the a11y
        // tree at poll time (seen on Gemini 2026-06-10).
        val kw = expectedText.trim().lowercase()
        // The echo bubble must sit ABOVE the composer: web composers render an inner
        // TextView with the same text at the same bounds as the EditText, which a
        // text-only check mistakes for the echo (seen on Gemini 2026-06-10).
        fun promptEchoVisible(): Boolean {
            val root = s.rootInActiveWindow ?: return false
            var composerTop = Int.MAX_VALUE
            var echoBottom = -1
            fun walk(node: android.view.accessibility.AccessibilityNodeInfo, depth: Int) {
                if (depth > 40) return
                val txt = node.text?.toString()?.trim()?.lowercase() ?: ""
                val matches = txt == kw || (kw.length >= 12 && txt.startsWith(kw))
                if (matches) {
                    val r = android.graphics.Rect()
                    node.getBoundsInScreen(r)
                    if (node.className?.toString()?.contains("EditText") == true) {
                        if (r.top < composerTop) composerTop = r.top
                    } else if (r.bottom > echoBottom) {
                        echoBottom = r.bottom
                    }
                }
                for (i in 0 until node.childCount) {
                    node.getChild(i)?.let { walk(it, depth + 1) }
                }
            }
            walk(root, 0)
            root.recycle()
            if (echoBottom < 0) return false
            // No EditText with the text left (composer cleared) — the matching text
            // node IS the echo... unless it's the composer's inner TextView, which
            // always sits in the bottom fifth of the screen. Require it higher up.
            if (composerTop == Int.MAX_VALUE) return echoBottom < (s.screenHeight() * 4) / 5
            return echoBottom < composerTop - 10
        }
        fun pollEcho(seconds: Int): Boolean {
            for (i in 1..seconds) {
                Thread.sleep(1000)
                if (promptEchoVisible()) return true
            }
            return false
        }
        fun gestureTapSend(): Boolean {
            for ((label, type) in submitSelectors) {
                val node = if (type == "cd") s.findNode(contentDesc = label, timeoutMs = 600)
                           else s.findNode(text = label, timeoutMs = 600)
                if (node != null) {
                    val r = android.graphics.Rect()
                    node.getBoundsInScreen(r)
                    node.recycle()
                    s.gestureTap(r.exactCenterX(), r.exactCenterY())
                    s.log("gesture-tapped send '$label' at ${r.centerX()},${r.centerY()}")
                    return true
                }
            }
            return false
        }

        // Sent = echo bubble visible above the composer, OR generation already
        // started (Stop button), OR the prompt text is GONE from the Chrome window
        // entirely (after a send the echo either shows above or has scrolled off as
        // the answer streams — it is never still sitting in the composer; seen on
        // the proxied Gemini run 2026-06-10 where the echo scrolled away and the
        // echo-only check aborted a job whose answer was already rendering).
        fun chromeWindowStillHasPrompt(): Boolean {
            val root = try {
                s.windows.firstOrNull {
                    it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION &&
                        it.root?.packageName == "com.android.chrome"
                }?.root
            } catch (_: Exception) { null } ?: s.rootInActiveWindow ?: return true
            var found = false
            fun walk(node: android.view.accessibility.AccessibilityNodeInfo, depth: Int) {
                if (found || depth > 40) return
                val txt = node.text?.toString()?.trim()?.lowercase() ?: ""
                if (txt == kw || (kw.length >= 12 && txt.startsWith(kw))) {
                    // Only the composer (bottom fifth) counts as "still unsent" —
                    // a match higher up is the echo bubble.
                    val r = android.graphics.Rect()
                    node.getBoundsInScreen(r)
                    if (r.top >= (s.screenHeight() * 4) / 5) found = true
                }
                for (i in 0 until node.childCount) {
                    node.getChild(i)?.let { walk(it, depth + 1) }
                }
            }
            walk(root, 0)
            return found
        }
        fun generationStarted(): Boolean =
            s.findNode(contentDesc = "Stop streaming", timeoutMs = 300) != null ||
            s.findNode(contentDesc = "Stop generating", timeoutMs = 300) != null ||
            s.findNode(contentDesc = "Stop response", timeoutMs = 300) != null
        fun sentSignal(): Boolean =
            promptEchoVisible() || generationStarted() || !chromeWindowStillHasPrompt()
        fun pollSent(seconds: Int): Boolean {
            for (i in 1..seconds) {
                Thread.sleep(1000)
                if (sentSignal()) return true
            }
            return false
        }

        if (pollSent(5)) { s.log("submit verified"); return true }

        s.log("no sent signal — escalating: gesture tap on send")
        gestureTapSend()
        if (pollSent(5)) { s.log("submit verified after gesture tap"); return true }

        s.log("still unsent — re-input via clipboard paste (fires real input events)")
        val box = findEditTextContaining(expectedText)
        if (box != null) {
            try { s.setTextOnNode(box, "") } catch (_: Exception) {}
            Thread.sleep(200)
            s.clickNode(box)            // focus the composer
            Thread.sleep(300)
            s.setClipboard(expectedText)
            Thread.sleep(200)
            tryPasteOnNode(box)
            box.recycle()
            Thread.sleep(600)
        }
        gestureTapSend()
        val sent = pollSent(8)
        s.log(if (sent) "submit verified after paste re-input" else "submit STILL unverified — prompt still in composer")
        return sent
    }

    // ── scroll ──

    fun scrollResponse(count: Int = 12): Boolean {
        s.log("── SCROLL ($count swipes) ──")
        ensureChromeForeground()
        val x = s.screenWidth() - 3f
        val startY = s.screenHeight() * 0.7f
        val endY = startY - 400f
        for (i in 1..count) {
            s.gestureSwipe(x, startY, x, endY, 700)
            Thread.sleep(2200)
            s.log("Scroll $i/$count")
        }
        return true
    }

    // ── full flow ──

    /** Full daily session: reset → FRE → navigate → input → submit → wait → scroll → follow-up → backlink */
    fun fullDailySession(
        platform: String,
        prompt: String,
        followUp: String?,
        backlinkDomain: String?,
        onStatus: (String) -> Unit
    ) {
        Thread {
            try {
                onStatus("Resetting Chrome...")
                resetChrome()
                Thread.sleep(500)

                onStatus("Navigating to $platform...")
                navigateTo(platform)
                Thread.sleep(3000)
                dismissPlatformPopups(platform)

                onStatus("Inputting prompt...")
                inputText(prompt)
                Thread.sleep(500)

                onStatus("Submitting...")
                submit()

                onStatus("Waiting for response...")
                waitForGeneration()

                onStatus("Scrolling to sources...")
                scrollResponse(5)

                // ── FOLLOW-UP ──
                if (!followUp.isNullOrBlank()) {
                    onStatus("Sending follow-up...")
                    sendFollowUp(followUp)
                }

                // ── BACKLINK CLICK ──
                if (!backlinkDomain.isNullOrBlank()) {
                    onStatus("Searching for backlink: $backlinkDomain")
                    clickBacklink(backlinkDomain, platform)
                }

                onStatus("DONE - Daily session completed")
            } catch (e: Exception) {
                onStatus("ERROR: ${e.message}")
                s.log("Flow error: ${e.stackTraceToString()}")
            }
        }.start()
    }

    /** Full flow for single platform without follow-up/backlink */
    fun fullGeminiFlow(prompt: String, onStatus: (String) -> Unit) {
        fullDailySession("gemini", prompt, null, null, onStatus)
    }

    // ── follow-up ──

    fun sendFollowUp(text: String): Boolean {
        s.log("── FOLLOW-UP ──")
        ensureChromeForeground()
        Thread.sleep(500)

        // Re-find input, type, submit
        if (!inputText(text)) {
            s.log("ERROR: Follow-up input failed")
            return false
        }
        Thread.sleep(500)

        if (!submit()) {
            s.log("ERROR: Follow-up submit failed")
            return false
        }

        s.log("Waiting for follow-up response...")
        if (!waitForGeneration(timeoutSec = 90)) {
            s.log("Follow-up generation timed out - continuing")
        } else {
            s.log("Scrolling follow-up response...")
            scrollResponse(4)
        }

        s.log("Follow-up complete")
        return true
    }

    // ── backlink click (accessibility-based, no CDP) ──

    fun clickBacklink(domain: String, platform: String = "gemini"): Boolean {
        s.log("── BACKLINK [$platform]: search for \"$domain\" ──")
        ensureChromeForeground()
        Thread.sleep(1000)

        // ── ChatGPT: links are embedded as clickable elements in the response text ──
        if (platform.lowercase() == "chatgpt") {
            return clickBacklinkChatGPT(domain)
        }

        // Step 1: Open the sources/links panel
        var isCarousel = false
        val linksTab = s.findNode(text = "Links", timeoutMs = 2000)
        if (linksTab != null && linksTab.isClickable) {
            s.log("Tapping Links tab (Perplexity)...")
            s.clickNode(linksTab)
            Thread.sleep(2000)
        } else {
            // Gemini: click "Sources" button
            for (attempt in 1..10) {
                val btn = s.findNode(text = "Sources", timeoutMs = 2000)
                    ?: s.findNode(contentDesc = "Sources", timeoutMs = 1500)
                if (btn != null) {
                    s.log("Clicked Sources button...")
                    s.clickNode(btn)
                    Thread.sleep(2500)
                    isCarousel = true  // Gemini uses carousel
                    break
                }
                Thread.sleep(2000)
            }
        }

        // Step 2: Search for domain, cycling carousel slides if needed
        val partial = domain.substringBefore(".")
        for (slide in 1..10) {
            s.log("Searching slide $slide for \"$domain\" / \"$partial\"...")
            var node = deepSearchForDomain(domain, partial)
            if (node == null) {
                // Not found on this slide
                if (isCarousel) {
                    val nextBtn = s.findNode(contentDesc = "Next slide", timeoutMs = 1500)
                        ?: s.findNode(text = "Next", timeoutMs = 1000)
                    if (nextBtn != null) {
                        s.log("Clicking 'Next slide'...")
                        s.clickNode(nextBtn)
                        Thread.sleep(1500)
                        continue
                    }
                }
                Thread.sleep(2000)
                continue
            }

            // Found the source card — click it to open/expand
            s.log("FOUND on slide $slide: ${(node.contentDescription ?: node.text).toString().take(60)}")
            s.clickNode(node)
            node.recycle()
            Thread.sleep(2500)

            // Gemini expanded panel: search for any clickable containing the domain
            // The expanded panel has: description text, maybe a "Visit site" link
            var actualLink: android.view.accessibility.AccessibilityNodeInfo? = null
            for (retry in 1..3) {
                actualLink = s.findNode(text = domain, timeoutMs = 2000)
                    ?: s.findNode(contentDesc = domain, timeoutMs = 1500)
                    ?: deepSearchForDomain(domain, partial)
                if (actualLink != null) break
                s.log("Link not found in panel, retry $retry...")
                Thread.sleep(1000)
            }
            if (actualLink != null) {
                s.log("Tapping actual link via gesture...")
                val b = android.graphics.Rect()
                actualLink.getBoundsInScreen(b)
                actualLink.recycle()
                s.gestureTap(b.centerX().toFloat(), b.centerY().toFloat())
                Thread.sleep(4000)
                // Gemini opens keyboard + URL bar after source navigation — dismiss both
                s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK) // close keyboard
                Thread.sleep(400)
                s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK) // dismiss URL bar
                Thread.sleep(400)
                browseBacklinkPage()
                // goBack() — stay on page for verification
                s.log("Backlink done")
                return true
            } else {
                s.log("Link NOT found in expanded panel — clicking source card again")
                val card = deepSearchForDomain(domain, partial)
                if (card != null) {
                    s.clickNode(card)
                    card.recycle()
                    Thread.sleep(1000)
                    s.log("Source card re-clicked — STOPPED for investigation")
                    return true
                }
            }

            // goBack() — stay on page for verification
            return true
        }

        s.log("Backlink not found for: $domain")
        return false
    }

    /**
     * ChatGPT-specific backlink: links are embedded as clickable [C] nodes within
     * the response text. They show the page TITLE as text (not the URL), so we need
     * a broader search: find ALL clickable nodes in the response area, dump them,
     * then try to match by domain in either text or contentDescription.
     */
    private fun clickBacklinkChatGPT(domain: String): Boolean {
        val partial = domain.substringBefore(".")
        // Also extract business name keywords from domain for fuzzy matching
        // e.g., "maeschildcare.com" → "maes", "childcare"
        val nameHints = partial.split(Regex("[^a-zA-Z]"))
            .filter { it.length > 3 }
            .map { it.lowercase() }
        s.log("ChatGPT backlink: domain=$domain partial=$partial nameHints=$nameHints")

        // Search response for link with matching targetUrl.
        // Try direct click first (link may still be in view). Retry a few times
        // since ChatGPT may still be rendering.
        for (attempt in 1..5) {
            val link = findNodeByTargetUrl(domain)
            if (link != null) {
                val label = (link.text?.toString() ?: link.contentDescription?.toString() ?: "?")
                val url = link.extras?.getString("AccessibilityNodeInfo.targetUrl") ?: ""
                val b = android.graphics.Rect(); link.getBoundsInScreen(b)
                s.log("ChatGPT link FOUND: \"$label\" -> $url bounds=$b")
                val clicked = link.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)
                s.log("ACTION_CLICK result: $clicked")
                link.recycle()
                Thread.sleep(4000)
                browseBacklinkPage()
                s.log("ChatGPT backlink done — STAYING on page")
                return true
            }
            s.log("ChatGPT link not found, retry $attempt...")
            Thread.sleep(1500)
        }

        // Debug: dump the response area to see what links exist
        s.log("ChatGPT: dumping FULL tree (depth=20)...")
        s.log("FULL TREE (depth=20):\n" + s.dumpTree(20))
        s.log("ChatGPT: dumping ALL nodes in response area (y > 150)...")
        dumpResponseArea()
        s.log("ChatGPT: searching for URL spans...")
        dumpUrlSpans()
        s.log("ChatGPT backlink NOT found for: $domain")
        return false
    }

    /** Find a clickable node whose contentDescription contains a URL with the domain */
    private fun findClickableWithUrl(domain: String, partial: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val result = findClickableWithUrlRecursive(root, domain.lowercase(), partial.lowercase())
        root.recycle()
        return result
    }

    private fun findClickableWithUrlRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        domain: String,
        partial: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        if (node.isClickable) {
            val cd = node.contentDescription?.toString()?.lowercase() ?: ""
            val txt = node.text?.toString()?.lowercase() ?: ""
            // Also check extras for targetUrl (Chrome exposes href here)
            val targetUrl = node.extras?.getString("AccessibilityNodeInfo.targetUrl")?.lowercase() ?: ""
            // Match: domain in text, cd, OR targetUrl from extras
            if (domain in cd || domain in txt || partial in cd || partial in txt ||
                domain in targetUrl || partial in targetUrl ||
                (cd.contains("http") && (domain in cd || partial in cd))) {
                // Skip UI chrome (URL bar, buttons at top)
                val rect = android.graphics.Rect()
                node.getBoundsInScreen(rect)
                if (rect.top > 200) {
                    return android.view.accessibility.AccessibilityNodeInfo.obtain(node)
                }
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findClickableWithUrlRecursive(child, domain, partial)
            if (result != null) {
                child.recycle()
                return result
            }
            child.recycle()
        }
        return null
    }

    /** Search ALL nodes (not just clickable) for domain in text or contentDescription */
    private fun findAnyNodeWithDomain(domain: String, partial: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val result = findAnyNodeRecursive(root, domain.lowercase(), partial.lowercase())
        root.recycle()
        return result
    }

    private fun findAnyNodeRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        domain: String,
        partial: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val cd = node.contentDescription?.toString()?.lowercase() ?: ""
        val txt = node.text?.toString()?.lowercase() ?: ""
        val targetUrl = node.extras?.getString("AccessibilityNodeInfo.targetUrl")?.lowercase() ?: ""
        if (domain in cd || domain in txt || partial in cd || partial in txt ||
            domain in targetUrl || partial in targetUrl) {
            val rect = android.graphics.Rect()
            node.getBoundsInScreen(rect)
            // Skip Chrome URL bar area
            if (rect.top > 200) {
                return android.view.accessibility.AccessibilityNodeInfo.obtain(node)
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findAnyNodeRecursive(child, domain, partial)
            if (result != null) {
                child.recycle()
                return result
            }
            child.recycle()
        }
        return null
    }

    /** Find a node whose extras contain targetUrl matching the domain */
    private fun findNodeByTargetUrl(domain: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val result = findNodeByTargetUrlRecursive(root, domain.lowercase())
        root.recycle()
        return result
    }

    private fun findNodeByTargetUrlRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        domain: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val targetUrl = node.extras?.getString("AccessibilityNodeInfo.targetUrl")?.lowercase() ?: ""
        if (domain in targetUrl && node.isClickable) {
            // No y-filter — targetUrl is a perfect match, the node may be offscreen
            return android.view.accessibility.AccessibilityNodeInfo.obtain(node)
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findNodeByTargetUrlRecursive(child, domain)
            if (result != null) { child.recycle(); return result }
            child.recycle()
        }
        return null
    }

    /** Fuzzy search: find a clickable node whose text or cd CONTAINS a keyword hint */
    private fun findClickableByTextHint(hint: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val result = findClickableByTextHintRecursive(root, hint.lowercase())
        root.recycle()
        return result
    }

    private fun findClickableByTextHintRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        hint: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        if (node.isClickable) {
            val txt = node.text?.toString()?.lowercase() ?: ""
            val cd = node.contentDescription?.toString()?.lowercase() ?: ""
            if (hint in txt || hint in cd) {
                val rect = android.graphics.Rect()
                node.getBoundsInScreen(rect)
                if (rect.top > 200) {
                    return android.view.accessibility.AccessibilityNodeInfo.obtain(node)
                }
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findClickableByTextHintRecursive(child, hint)
            if (result != null) { child.recycle(); return result }
            child.recycle()
        }
        return null
    }

    /** Dump all clickable nodes in the current window for diagnostics */
    private fun dumpClickableNodes() {
        val root = s.rootInActiveWindow ?: run {
            s.log("dumpClickable: no root")
            return
        }
        val sb = StringBuilder()
        dumpClickableRecursive(root, 0, sb)
        root.recycle()
        s.log("Clickable nodes dump:\n$sb")
    }

    private fun dumpClickableRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        depth: Int,
        sb: StringBuilder
    ) {
        if (depth > 12) return
        if (node.isClickable) {
            val txt = node.text?.toString()?.take(80) ?: ""
            val cd = node.contentDescription?.toString()?.take(80) ?: ""
            val cls = node.className?.toString()?.split(".")?.lastOrNull() ?: ""
            val rect = android.graphics.Rect()
            node.getBoundsInScreen(rect)
            sb.appendLine("  ".repeat(depth) + "[C] $cls text=\"$txt\" cd=\"$cd\" y=${rect.top}")
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { dumpClickableRecursive(it, depth + 1, sb) }
        }
    }

    /** Dump ALL nodes in the response area (y > 200) with full details */
    private fun dumpResponseArea() {
        val root = s.rootInActiveWindow ?: run {
            s.log("dumpResponseArea: no root")
            return
        }
        val sb = StringBuilder()
        var count = 0
        dumpResponseAreaRecursive(root, 0, sb, count)
        root.recycle()
        s.log("Response area nodes:\n$sb")
    }

    private fun dumpResponseAreaRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        depth: Int,
        sb: StringBuilder,
        count: Int
    ): Int {
        if (depth > 25) return count
        var c = count
        val rect = android.graphics.Rect()
        node.getBoundsInScreen(rect)
        // Only dump nodes in the page content area (below Chrome toolbar)
        if (rect.top > 150) {
            val cls = node.className?.toString()?.split(".")?.lastOrNull() ?: ""
            val txt = node.text?.toString()?.take(120) ?: ""
            val cd = node.contentDescription?.toString()?.take(120) ?: ""
            val flags = buildString {
                if (node.isClickable) append("C")
                if (node.isFocusable) append("F")
                if (node.isEditable) append("E")
                if (node.isScrollable) append("S")
            }
            if (txt.isNotBlank() || cd.isNotBlank() || node.isClickable || node.childCount == 0) {
                val indent = "  ".repeat(depth.coerceAtMost(20))
                // Dump extras for clickable nodes (may contain URL)
                val extrasStr = if (node.isClickable) dumpExtras(node) else ""
                sb.appendLine("$indent$cls[$flags] text=\"$txt\" cd=\"$cd\" y=${rect.top}$extrasStr")
                c++
                if (c > 200) return c // limit output
            }
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                c = dumpResponseAreaRecursive(child, depth + 1, sb, c)
                if (c > 200) return c
            }
        }
        return c
    }

    /** Extract URL from AccessibilityNodeInfo extras (Chrome-specific) */
    private fun dumpExtras(node: android.view.accessibility.AccessibilityNodeInfo): String {
        val extras = node.extras ?: return ""
        val sb = StringBuilder()
        for (key in extras.keySet()) {
            val value = extras[key]
            val valStr = value?.toString()?.take(120) ?: "null"
            sb.append(" $key=\"$valStr\"")
        }
        return sb.toString()
    }

    /** Dump all URL spans found in text nodes */
    private fun dumpUrlSpans() {
        val root = s.rootInActiveWindow ?: run {
            s.log("dumpUrlSpans: no root")
            return
        }
        val sb = StringBuilder()
        dumpUrlSpansRecursive(root, sb)
        root.recycle()
        if (sb.isEmpty()) sb.append("(none found)")
        s.log("URL spans:\n$sb")
    }

    private fun dumpUrlSpansRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        sb: StringBuilder
    ) {
        val text = node.text
        if (text is android.text.Spanned) {
            val urls = text.getSpans(0, text.length, android.text.style.URLSpan::class.java)
            for (url in urls) {
                val urlStr = url.url
                val spanStart = text.getSpanStart(url)
                val spanEnd = text.getSpanEnd(url)
                val spanText = text.substring(spanStart, spanEnd.coerceAtMost(text.length))
                val rect = android.graphics.Rect()
                node.getBoundsInScreen(rect)
                sb.appendLine("  URLSpan: text=\"$spanText\" url=\"$urlStr\" y=${rect.top} clickable=${node.isClickable}")
            }
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { dumpUrlSpansRecursive(it, sb) }
        }
    }

    /** Walk the entire accessibility tree looking for a clickable node whose cd or text contains domain */
    private fun deepSearchForDomain(domain: String, partial: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val result = deepSearchRecursive(root, domain.lowercase(), partial.lowercase())
        root.recycle()
        return result
    }

    private fun deepSearchRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        domain: String,
        partial: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        if (node.isClickable) {
            val cd = node.contentDescription?.toString()?.lowercase() ?: ""
            val txt = node.text?.toString()?.lowercase() ?: ""
            val targetUrl = node.extras?.getString("AccessibilityNodeInfo.targetUrl")?.lowercase() ?: ""
            if (domain in cd || domain in txt || partial in cd || partial in txt ||
                domain in targetUrl || partial in targetUrl) {
                return android.view.accessibility.AccessibilityNodeInfo.obtain(node)
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = deepSearchRecursive(child, domain, partial)
            if (result != null) {
                child.recycle()
                return result
            }
            child.recycle()
        }
        return null
    }

    private fun browseBacklinkPage() {
        s.log("Browsing backlink page...")
        Thread.sleep(4000)
        // Same scroll approach as main scroll — far right edge to avoid buttons
        val x = s.screenWidth() - 3f
        val startY = s.screenHeight() * 0.7f
        val endY = startY - 400f
        for (i in 1..2) {
            s.gestureSwipe(x, startY, x, endY, 500)
            Thread.sleep(1500)
            s.log("Browse scroll $i/2")
        }
        Thread.sleep(2000)
    }

    fun goBack(): Boolean {
        s.log("Going back...")
        s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        Thread.sleep(1500)
        return true
    }

    // ── platform popup dismissal ──

    fun dismissPlatformPopups(platform: String) {
        s.log("── DISMISS ${platform.uppercase()} POPUPS ──")

        // Perplexity shows its first interstitial ad/modal 1–4s after navigate
        // returns. Wait for it to render so the first dismiss round actually
        // finds the close button instead of bailing on an empty screen.
        if (platform.lowercase() == "perplexity") Thread.sleep(2500)

        val popups = when (platform.lowercase()) {
            "gemini" -> listOf("No thanks", "Try it", "Close banner")
            "chatgpt" -> listOf(
                "Reject non-essential", "Reject all", "Close", "Stay logged out",
                "Not now", "Maybe later", "Skip", "Stay signed out",
                // "Share your precise location" card that pops post-generation
                "No thanks", "No, thanks", "Dismiss"
            )
            "perplexity" -> listOf(
                // ONLY dismiss/close actions — NEVER tap "Install", "Download", "Open", etc.
                "Close", "No thanks", "Not now", "Maybe later", "Skip",
                "Got it", "Dismiss", "Decline", "Accept all cookies", "Opt out"
            )
            else -> emptyList()
        }
        // Perplexity: more rounds for layered modals (Download app → Comet → Cookie)
        val rounds = if (platform.lowercase() == "perplexity") 6 else 1
        for (round in 1..rounds) {
            var dismissed = false
            for (label in popups) {
                val node = s.findNode(text = label, timeoutMs = 800)
                    ?: s.findNode(contentDesc = label, timeoutMs = 600)
                if (node != null) {
                    s.clickNode(node)
                    s.log("Dismissed popup: $label")
                    dismissed = true
                    Thread.sleep(600)
                }
            }
            // For perplexity keep polling all rounds — an ad/modal can appear
            // between rounds. For other platforms break early to save time.
            if (!dismissed && platform.lowercase() != "perplexity") break
            Thread.sleep(400)
        }
    }

    // ── helpers ──

    private fun dismissFreInline() {
        val buttons = listOf(
            "Stay signed out", "No thanks", "No, thanks", "Got it",
            "Skip", "Not now", "Accept & continue", "Next", "Maybe later"
        )
        for (attempt in 1..5) {
            var found = false
            for (btn in buttons) {
                val node = s.findNode(text = btn, timeoutMs = 300)
                if (node != null) {
                    s.clickNode(node)
                    s.log("FRE dismissed: $btn")
                    found = true
                    Thread.sleep(500)
                    break
                }
            }
            if (!found) break
        }
    }

    fun waitForGeneration(timeoutSec: Int = 180): Boolean {
        s.log("── WAIT FOR GENERATION ──")
        val start = System.currentTimeMillis()
        val timeout = timeoutSec * 1000L
        while (System.currentTimeMillis() - start < timeout) {
            Thread.sleep(3000)
            val stopBtn = s.findNode(contentDesc = "Stop streaming", timeoutMs = 500)
                ?: s.findNode(contentDesc = "Stop generating", timeoutMs = 500)
                ?: s.findNode(contentDesc = "Stop response", timeoutMs = 500)
            if (stopBtn != null) {
                s.log("Still generating...")
                continue
            }
            val hasContent = s.findNode(contentDesc = "Copy", timeoutMs = 500) != null
                || s.findNode(contentDesc = "Share", timeoutMs = 500) != null
                || s.findNode(contentDesc = "Read aloud", timeoutMs = 500) != null
                || s.findNode(contentDesc = "Good response", timeoutMs = 500) != null
                || s.findNode(contentDesc = "Bad response", timeoutMs = 500) != null
            if (hasContent) {
                s.log("Generation complete")
                return true
            }
        }
        s.log("Timeout waiting for generation")
        return false
    }

    // ── response text capture ──

    fun getResponseText(): String {
        s.log("── GET RESPONSE TEXT ──")
        val root = s.rootInActiveWindow ?: return ""
        val sb = StringBuilder()
        collectTextNodes(root, sb, 0)
        root.recycle()
        val text = sb.toString().trim()
        s.log("Captured ${text.length} chars, ${text.lines().size} lines")
        return text
    }

    private fun collectTextNodes(
        node: android.view.accessibility.AccessibilityNodeInfo,
        sb: StringBuilder,
        depth: Int
    ) {
        if (depth > 20) return
        val rect = android.graphics.Rect()
        node.getBoundsInScreen(rect)
        if (rect.top > 150) {
            val txt = node.text?.toString()
            if (!txt.isNullOrBlank() && node.className?.toString()?.contains("Edit") != true) {
                if (sb.isNotEmpty()) sb.append("\n")
                sb.append(txt.trim())
            }
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { collectTextNodes(it, sb, depth + 1) }
        }
    }

    // ── screenshot passthrough ──

    fun saveScreenshot(name: String): String? = s.saveScreenshot(name)

    // ── helpers for per-platform audit checks ──

    /** Return true if any of these texts is currently visible (via accessibility tree). */
    fun findAnyText(texts: List<String>): Boolean {
        for (t in texts) {
            val n = s.findNode(text = t, timeoutMs = 400)
            if (n != null) { n.recycle(); return true }
        }
        return false
    }

    /** Try to click a node by visible text. Returns true if clicked. */
    fun tryClickText(text: String): Boolean {
        val n = s.findNode(text = text, timeoutMs = 400) ?: return false
        val ok = s.clickNode(n)
        n.recycle()
        return ok
    }

    /** Return true if a node with this resource-id is present. */
    fun hasNodeByResourceId(resourceId: String): Boolean {
        val n = s.findNode(resourceId = resourceId, timeoutMs = 400) ?: return false
        n.recycle()
        return true
    }

    // ── ranking extraction ──

    fun extractRanking(): Pair<Int?, String?> = extractRankingFromText(getResponseText())

    fun extractRankingFromText(text: String): Pair<Int?, String?> {
        s.log("── EXTRACT RANKING ──")
        if (text.isBlank()) {
            s.log("No response text found")
            return Pair(null, null)
        }

        // Whole-text scan: accessibility tree often concatenates markdown without
        // proper newlines, so a per-line regex would miss [RANK: X/Y] embedded in
        // a long blob. Take the LAST non-instruction match (model output > prompt echo).
        val rankPattern = Regex("""\[RANK:\s*(\d+)\s*/\s*(\d+\+?)\]""", RegexOption.IGNORE_CASE)
        val matches = rankPattern.findAll(text).toList()
        val chosen = matches.lastOrNull { m ->
            val start = maxOf(0, m.range.first - 60)
            val end = minOf(text.length, m.range.last + 60)
            val ctx = text.substring(start, end).lowercase()
            !("e.g." in ctx || "where x" in ctx || "for example" in ctx)
        } ?: matches.lastOrNull()

        if (chosen != null) {
            val position = chosen.groupValues[1].toIntOrNull()
            val total = chosen.groupValues[2]
            s.log("RANK FOUND: $position / $total from \"${chosen.value}\"")
            return Pair(position, total)
        }

        s.log("No [RANK: X/Y] pattern found in response")
        return Pair(null, null)
    }
}
