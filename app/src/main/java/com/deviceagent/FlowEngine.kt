package com.deviceagent

// ── SEO / Google SERP data model (SerpApi-like) ──
data class SerpResult(
    val position: Int,
    val title: String,
    val domain: String,
    val url: String,
    val site: String?,
    val snippet: String? = null,
    val displayedLink: String? = null
)

data class LocalResult(
    val position: Int,
    val name: String,
    val rating: String?,
    val sponsored: Boolean,
    val reviews: Int? = null,
    val reviewsOriginal: String? = null,
    val price: String? = null,
    val type: String? = null,
    val address: String? = null,
    val description: String? = null
)

data class SerpTarget(
    val domain: String,
    val organicRank: Int?,
    val localRank: Int?
)

data class SerpData(
    val organic: List<SerpResult>,
    val local: List<LocalResult>,
    val adsExcluded: Int,
    val localAdsExcluded: Int,
    val location: String?,
    val target: SerpTarget?
)

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

    /** Dismiss on-SERP overlays (esp. Google's "See results closer to you?" precise-location
     *  prompt) that sit on top of the results and break parsing. Does NOT navigate (unlike
     *  dismissChromeFre) — it only taps a dismiss button if one is present, so it's safe to
     *  call after the SERP has loaded. Returns true if something was dismissed. */
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

    fun submit(): Boolean {
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
        for (pass in 1..2) {
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
                        return true
                    }
                    s.log("Found '$label' but click failed, trying next...")
                }
            }
            Thread.sleep(500)
        }
        // Fallback: tap bottom-right corner (Perplexity submit button area)
        s.gestureTap(s.screenWidth() - 60f, s.screenHeight() * 0.82f)
        s.log("Fallback tap for submit (bottom-right)")
        return true
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
                "Not now", "Maybe later", "Skip", "Stay signed out"
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

    // ── SEO / Google SERP ────────────────────────────────────────────────
    // Grounded against a live mobile SERP dump — see
    // seo-voice-rank/docs/SERP-PARSE-REFERENCE.md for the discriminators.

    /** One flattened a11y node: class tail, text, content-desc, Chrome targetUrl extra. */
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

    private val localLabelStop = setOf(
        "Website", "Directions", "Reviews", "Terms", "Open", "Closed", "Share", "Map",
        "Sponsored", "More businesses", "Businesses", "Call", "·"
    )
    private val numericOnly = Regex("^[0-9.,KMmi+()\\s]+$")

    /** A plausible local-pack business name (not a button label, status text, or review count). */
    private fun isLocalName(t: String): Boolean {
        if (t.length < 4 || t.none { it.isLetter() }) return false
        if (t.startsWith("Call") || t.startsWith("+") || t.startsWith("http")) return false
        // Open-status / hours text ("Open 24 hours", "Open ⋅ Closes 5 PM", "Closed").
        if (t.startsWith("Open") || t.startsWith("Closed") || t.startsWith("Closes") || t.startsWith("Opens")) return false
        if (t.contains(" hours", true) || t.contains("years in business", true)) return false
        if (t in localLabelStop) return false
        if (t.contains("review", true)) return false
        // " · " is Google's metadata separator (e.g. a "More places" list blob), never a name.
        if (t.contains(" · ")) return false
        if (numericOnly.matches(t)) return false
        return true
    }

    /** Dedupe key for a local-pack name — drops trailing taglines after " - " and lowercases. */
    private fun localKey(name: String): String =
        name.lowercase().substringBefore(" - ").trim()

    /** Reduce a visible URL line (incl. ad breadcrumb "https://x.com › a › b") to a bare host. */
    private fun hostOf(raw: String): String {
        var u = raw.trim().substringBefore(' ').substringBefore('›').trim() // › = ›
        u = u.removePrefix("https://").removePrefix("http://")
        u = u.substringBefore('/').substringBefore('?')
        return u.removePrefix("www.").trim().lowercase()
    }

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
            // Clear any Chrome notification / consent dialog sitting over the page.
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
     * Submit a Google search the human way: fire the IME "search" editor action on the
     * search box (API 30+), then fall back to the Search button / on-screen Enter.
     */
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

        // 1) exact-match autocomplete suggestion row
        val sugg = findSearchSuggestion(keyword)
        if (sugg != null) {
            val ok = s.clickNode(sugg); sugg.recycle()
            if (ok) { s.log("Tapped exact suggestion row"); Thread.sleep(1500); return true }
        }

        // 2) IME enter on the query box (found by text so the y<200 guard doesn't skip it)
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

        // 3) on-page Google Search button (empty-box state)
        for (cd in listOf("Google Search", "Search")) {
            val b = s.findNode(contentDesc = cd, timeoutMs = 800)
            if (b != null) {
                val ok = s.clickNode(b); b.recycle()
                if (ok) { s.log("Clicked '$cd' submit"); Thread.sleep(1500); return true }
            }
        }

        // 4) keyboard enter tap
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

    /**
     * Guaranteed SERP fallback: load google.com/search?q=<keyword> directly. Used when the
     * human-typed submit doesn't navigate — mirrors the proven voice-search simplification
     * ("don't rely on auto-submit; load the search URL directly"). Same organic SERP.
     */
    fun navigateToSerp(keyword: String): Boolean {
        val q = java.net.URLEncoder.encode(keyword, "UTF-8")
        s.log("── NAVIGATE SERP DIRECT: ?q=$q ──")
        s.navigateToUrl("https://www.google.com/search?q=$q&hl=en&gl=us")
        return true
    }

    /**
     * Load a Google SERP localized to [location] via the `uule` URL parameter +
     * pinned `gl=us&hl=en`. [location] is a canonical "City,State,United States"
     * string; Google renders results as if the searcher is physically there. This
     * is the SEO PRIMARY path — direct `?q=` nav skips the flaky human-typed input
     * (DEFECT #2) and pins locale deterministically. Blank [location] → no uule.
     */
    fun navigateToSerpLocalized(keyword: String, location: String): Boolean {
        val q = java.net.URLEncoder.encode(keyword, "UTF-8")
        if (location.isBlank()) {
            s.log("── NAVIGATE SERP (gl=us, no uule): ?q=$q ──")
            s.navigateToUrl("https://www.google.com/search?q=$q&hl=en&gl=us")
            return true
        }
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

    /**
     * Poll until the SERP looks loaded (results header or a non-google result URL present).
     * If a Cloudflare / Google bot-challenge interstitial appears, keep waiting (these usually
     * auto-resolve) and record it in [lastChallengeSeen] so the caller can report it distinctly
     * instead of as a generic timeout.
     */
    private val connErrPhrases = listOf(
        "site can't be reached", "site can’t be reached", "err_connection",
        "err_timed_out", "err_name_not_resolved", "err_proxy", "err_tunnel",
        "err_empty_response", "err_address_unreachable", "webpage is not available"
    )

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
            // Connection-aborted page (flaky cellular proxy) — tap Reload; transient aborts recover.
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

    /**
     * Scroll the SERP so a header (e.g. "Businesses", the local pack) sits near the top of the
     * screen, so the proof screenshot starts there instead of on the top sponsored ads.
     *
     * Calibrated on-device: swipes MUST run on the far-right edge — a centre swipe lands on the
     * local pack's embedded map and pans it instead of scrolling the page. An off-screen node
     * reports a clamped top ≈ screenHeight-90 ("still below the fold"); only once it enters the
     * viewport does it report real coordinates. We reveal until it's on-screen, then nudge it
     * into the [180, 440] top band and stop.
     */
    fun scrollToTextTop(texts: List<String>, targetTop: Int = 300, maxSwipes: Int = 9): Boolean =
        scrollNodeToTop("text:$texts", targetTop, maxSwipes) { findExactTextNode(texts) }

    /**
     * Generic: swipe the SERP until the node returned by [finder] sits in the [180,440] top
     * band, so a proof screenshot frames that EXACT element regardless of its header label.
     * Far-right-edge swipes only (a centre swipe pans the local-pack map). An off-screen node
     * reports a clamped top ≈ screenH-140; reveal until on-screen, then nudge into the band.
     */
    private fun scrollNodeToTop(
        label: String, targetTop: Int = 300, maxSwipes: Int = 9,
        finder: () -> android.view.accessibility.AccessibilityNodeInfo?
    ): Boolean {
        s.log("── SCROLL TO $label (top) ──")
        ensureChromeForeground()
        val x = s.screenWidth() - 3f
        val h = s.screenHeight()
        val offscreenClamp = h - 140  // ~1460 on a 1600px screen → treat as "below the fold"
        for (i in 1..maxSwipes) {
            val node = finder()
            val top = node?.let {
                val r = android.graphics.Rect(); it.getBoundsInScreen(r); it.recycle(); r.top
            }
            when {
                top == null || top >= offscreenClamp -> {
                    s.gestureSwipe(x, h * 0.70f, x, h * 0.70f - 480f, 450)
                    s.log("reveal swipe (top=${top ?: "NF"})")
                }
                top in 180..440 -> { s.log("aligned $label at top=$top (swipe $i)"); return true }
                top > 440 -> {
                    val dy = (top - targetTop).coerceIn(150, 520).toFloat()
                    s.gestureSwipe(x, h * 0.70f, x, h * 0.70f - dy, 450)
                }
                else -> { // top < 180 → scrolled a touch too far, ease back down
                    val dy = (targetTop - top).coerceIn(120, 360).toFloat()
                    s.gestureSwipe(x, h * 0.35f, x, h * 0.35f + dy, 450)
                }
            }
            Thread.sleep(1300)
        }
        s.log("$label not aligned to top after $maxSwipes swipes")
        return false
    }

    /** Align the first local-pack business card (a "Rated X out of 5" node) to the top — robust
     *  to the pack's header varying ("Places" / "Businesses" / "With outdoor seating" / …). */
    fun scrollToLocalPackTop(): Boolean = scrollNodeToTop("local-pack") { findFirstRatedNode() }

    private val ratedCd = Regex("Rated\\s+[\\d.]+\\s+out of 5")
    private fun findFirstRatedNode(): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val found = findFirstRec(root) { n ->
            ratedCd.containsMatchIn(n.contentDescription?.toString() ?: "") ||
            (n.text?.toString()?.contains("out of 5") == true)
        }
        root.recycle(); return found
    }
    private fun findFirstRec(
        node: android.view.accessibility.AccessibilityNodeInfo,
        pred: (android.view.accessibility.AccessibilityNodeInfo) -> Boolean
    ): android.view.accessibility.AccessibilityNodeInfo? {
        if (pred(node)) return node
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child -> findFirstRec(child, pred)?.let { return it } }
        }
        return null
    }

    /**
     * Scroll so the ORGANIC results block sits near the top, for the organic proof shot.
     * Organic follows the local pack: prefer the "Web results" header, else the local-pack
     * footer ("More places"/"More businesses") — organic renders just below it.
     */
    fun scrollToOrganicTop(): Boolean {
        if (scrollToTextTop(listOf("Web results"))) return true
        return scrollToTextTop(listOf("More places", "More businesses"))
    }

    /** First node (DOM order) whose text EXACTLY equals one of the candidates. */
    private fun findExactTextNode(texts: List<String>): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val found = findExactRec(root, texts)
        root.recycle()
        return found
    }

    private fun findExactRec(
        node: android.view.accessibility.AccessibilityNodeInfo,
        texts: List<String>
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val t = node.text?.toString()?.trim()
        if (t != null && texts.any { it.equals(t, ignoreCase = true) }) return node
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                findExactRec(child, texts)?.let { return it }
            }
        }
        return null
    }

    /** Known mobile-SERP filter chips whose active form is "Remove <name>". */
    private val knownFilters = listOf(
        "Top rated", "Open now", "Cheap", "Upscale", "Online appointments",
        "Open 24 hours", "Highly rated", "Dine-in", "Takeout", "Delivery", "Deals"
    )

    /**
     * Clear any active search-result filter chip (e.g. "Top rated") so the ranking reflects the
     * default, unfiltered SERP — essential for honest SEO rank. An active chip exposes a clickable
     * "Remove <filter>" node in the top filter strip; clicking it toggles the filter off.
     * Returns how many were cleared.
     */
    fun clearSearchFilters(): Int {
        s.log("── CLEAR SEARCH FILTERS ──")
        var cleared = 0
        for (pass in 1..5) {
            val chip = findActiveFilterChip() ?: break
            val r = android.graphics.Rect(); chip.getBoundsInScreen(r)
            val cd = chip.contentDescription?.toString() ?: ""
            val ok = s.clickNode(chip); chip.recycle()
            if (!ok) s.gestureTap(r.centerX().toFloat(), r.centerY().toFloat())
            s.log("cleared filter: \"$cd\"")
            cleared++
            Thread.sleep(1800) // let the SERP re-render unfiltered
        }
        if (cleared == 0) s.log("no active filters")
        return cleared
    }

    private fun findActiveFilterChip(): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val found = findActiveFilterRec(root)
        root.recycle()
        return found
    }

    private fun findActiveFilterRec(
        node: android.view.accessibility.AccessibilityNodeInfo
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val cd = node.contentDescription?.toString()?.trim() ?: ""
        if (node.isClickable && cd.startsWith("Remove ")) {
            val name = cd.removePrefix("Remove ").trim()
            // Only known filter chips, and only in the top filter strip (avoids unrelated "Remove …").
            if (knownFilters.any { it.equals(name, ignoreCase = true) }) {
                val r = android.graphics.Rect(); node.getBoundsInScreen(r)
                if (r.top < s.screenHeight() * 0.5f) return node
            }
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                findActiveFilterRec(child)?.let { return it }
            }
        }
        return null
    }

    /**
     * Parse the currently-rendered mobile Google SERP into SerpApi-like structured data:
     * ordered organic results (ads excluded), the local/Maps pack, and an ad count.
     * Off-screen SERP nodes only materialise after layout, so callers should scroll the
     * full page before parsing (see executeGoogleSerpStatic).
     */
    fun parseSerp(targetDomain: String?): SerpData {
        s.log("── PARSE SERP ──")
        val nodes = flattenTree()
        if (nodes.isEmpty()) {
            s.log("SERP parse: empty tree")
            return SerpData(emptyList(), emptyList(), 0, 0, null, null)
        }

        val ratedRe = Regex("Rated\\s+([\\d.]+)\\s+out of 5")

        // Mark the sponsored region (between "Sponsored results" and "Hide sponsored results").
        val sponsoredAt = BooleanArray(nodes.size)
        var inSponsored = false
        for (i in nodes.indices) {
            when (nodes[i].text) {
                "Sponsored results" -> inSponsored = true
                "Hide sponsored results" -> inSponsored = false
            }
            sponsoredAt[i] = inSponsored
        }

        val location = nodes.firstOrNull { it.text.matches(Regex(".+,\\s+[A-Z]{2},\\s+USA")) }?.text

        // WEB results: anchor on each visible https:// URL text line.
        val organicRaw = ArrayList<SerpResult>()
        var adCount = 0
        val adDomains = HashSet<String>()
        for (i in nodes.indices) {
            val urlText = nodes[i].text
            if (urlText.isBlank() || !httpRe.containsMatchIn(urlText)) continue
            val domain = hostOf(urlText)
            if (domain.isBlank() || domain.contains("google.com")) continue

            var site: String? = null
            for (j in i - 1 downTo maxOf(0, i - 4)) {
                val tj = nodes[j].text
                if (tj.isNotBlank() && !httpRe.containsMatchIn(tj)) { site = tj; break }
            }
            var title: String? = null
            var titleIdx = -1
            for (j in i + 1..minOf(nodes.size - 1, i + 5)) {
                val tj = nodes[j].text
                if (tj.length > 3 && !httpRe.containsMatchIn(tj) && tj != "About this result") { title = tj; titleIdx = j; break }
            }
            // Snippet: the first sentence-like line after the title (before the next result URL).
            var snippet: String? = null
            if (titleIdx >= 0) {
                for (j in titleIdx + 1..minOf(nodes.size - 1, titleIdx + 6)) {
                    val tj = nodes[j].text
                    if (tj.isNotBlank() && httpRe.containsMatchIn(tj)) break
                    if (tj.length > 40 && tj.contains(' ') && tj != "About this result") { snippet = tj; break }
                }
            }
            // Classify: first marker button scanning forward is THIS result's marker.
            var isAd = sponsoredAt[i]
            for (j in i + 1..minOf(nodes.size - 1, i + 8)) {
                val c = nodes[j].cd
                if (c == "Why this ad?") { isAd = true; break }
                if (c == "About this result") { isAd = sponsoredAt[i]; break }
                if (nodes[j].text.isNotBlank() && httpRe.containsMatchIn(nodes[j].text)) break // next result
            }
            if (isAd) {
                if (adDomains.add(domain)) adCount++
            } else {
                organicRaw.add(SerpResult(0, title ?: site ?: domain, domain, urlText.substringBefore(' '), site, snippet, urlText.substringBefore(' ')))
            }
        }
        // Dedupe organic by domain (sitelinks repeat), assign 1-based positions.
        val seen = HashSet<String>()
        val organic = ArrayList<SerpResult>()
        for (r in organicRaw) {
            if (!seen.add(r.domain)) continue
            organic.add(r.copy(position = organic.size + 1))
        }

        // LOCAL pack: anchor on "Rated X out of 5". The business name is either packed in
        // the card container's content-desc ("<name> Rated …") or a name-like TextView just
        // above the star image — never a button label (Call / Website / Directions / …).
        // Scope the local pack to the actual Places/Businesses cluster so organic rich-result
        // ratings (e.g. a Yelp listicle showing stars) aren't mistaken for local businesses.
        var lpStart = nodes.indexOfFirst { it.text == "Places" || it.text == "Businesses" }
        if (lpStart < 0) {
            // Themed local pack (e.g. "With outdoor seating") has no Places/Businesses header.
            // Anchor on the rated-card cluster sitting just above the "More places/businesses" footer.
            val moreIdx = nodes.indexOfFirst { it.text == "More places" || it.text == "More businesses" }
            if (moreIdx > 0) {
                lpStart = ((0 until moreIdx).firstOrNull { ratedRe.containsMatchIn(nodes[it].cd) } ?: 0) - 1
            }
        }
        val lpEnd = if (lpStart < 0) 0 else {
            val endMarkers = setOf(
                "More places", "More businesses", "People also ask", "Web results",
                "Discussions and forums", "Related searches", "People also search for"
            )
            (lpStart + 1 until nodes.size).firstOrNull { nodes[it].text in endMarkers } ?: nodes.size
        }
        val seenL = HashSet<String>()
        val local = ArrayList<LocalResult>()
        var localAdsExcluded = 0
        for (i in (if (lpStart < 0) IntRange.EMPTY else (lpStart + 1) until lpEnd)) {
            val m = ratedRe.find(nodes[i].cd) ?: continue
            // 1) container prefix before "Rated"
            var name: String? = nodes[i].cd.substring(0, m.range.first).trim().ifBlank { null }
                ?.takeIf { isLocalName(it) }
            // 2) else nearest name-like TextView above (skip UI/button labels)
            if (name == null) {
                for (j in i - 1 downTo maxOf(0, i - 6)) {
                    val nj = nodes[j]
                    if (nj.cls == "TextView" && isLocalName(nj.text)) { name = nj.text; break }
                }
            }
            if (name.isNullOrBlank()) continue
            val sponsored = (maxOf(0, i - 8) until i).any { nodes[it].text == "Sponsored" || nodes[it].cd == "Why this ad?" }
            // Drop sponsored local ads entirely (parity with organic ad exclusion); count them.
            // Check sponsored BEFORE dedup so a sponsored card doesn't shadow the same
            // business's real organic entry that follows it.
            if (sponsored) { localAdsExcluded++; continue }
            if (!seenL.add(localKey(name))) continue
            // Extra fields: Google packs the whole card into the container's content-desc, e.g.
            //   "Little Foot Preschool  Rated 5.0 out of 5,  (12)  ·  Bilingual preschools 20+ years
            //    in business Open now · Serves San Francisco"
            //   "Via Nova Children's School Rated 4.6 out of 5 16 reviews · Bilingual preschools …
            //    1319 20th Ave …"
            // Parse it with substring regexes (strip Unicode bidi isolates U+2066/U+2069 first).
            val cd = nodes[i].cd.replace('⁦', ' ').replace('⁩', ' ')
                .replace(Regex("\\s+"), " ").trim()
            val revStr = Regex("\\((\\d[\\d.,]*[KkMm]?)\\)").find(cd)?.groupValues?.get(1)
                ?: Regex("([\\d.,]+[KkMm]?)\\s+reviews?").find(cd)?.groupValues?.get(1)
            val reviews = revStr?.let { parseReviewCount(it) }
            val reviewsOrig = revStr?.let { if (cd.contains("($it)")) "($it)" else "$it reviews" }
            val price = Regex("\\$\\d[\\d–\\-]*").find(cd)?.value
            val type = Regex("·\\s*([A-Za-z][A-Za-z'&/ -]{2,30}?)(?=\\s+\\d|\\s+Open|\\s+Closed|\\s+Serves|·|$)")
                .find(cd)?.groupValues?.get(1)?.trim()
            val addr = Regex(
                "\\d{1,5}\\s+[A-Za-z0-9.\\- ]+?\\s+(Ave|Avenue|St|Street|Rd|Road|Dr|Drive|Blvd|Ln|Lane|Way|Ct|Court|Pl|Place|Hwy|Sq|Ste|Suite)\\b\\.?",
                RegexOption.IGNORE_CASE
            ).find(cd)?.value?.trim()
            val desc = Regex("(\\d+\\+?\\s+years in business)").find(cd)?.value?.trim()
            local.add(LocalResult(local.size + 1, name, m.groupValues[1], false, reviews, reviewsOrig, price, type, addr, desc))
        }

        // Target match.
        var target: SerpTarget? = null
        if (!targetDomain.isNullOrBlank()) {
            val td = hostOf(targetDomain)
            val orank = organic.firstOrNull { it.domain.contains(td) || td.contains(it.domain) }?.position
            // Local cards show the business NAME, not a domain — match the domain's brand token
            // (e.g. "epoch.coffee" → "epoch" → "Epoch Coffee"; "ramosjames.com" → "ramosjames"
            // → "Ramos James Law"). Compare against the space-stripped name.
            val brand = td.substringBefore('.')
            val lrank = local.firstOrNull {
                val collapsed = it.name.replace(" ", "").lowercase()
                it.name.contains(td, true) || (brand.length >= 4 && collapsed.contains(brand))
            }?.position
            target = SerpTarget(td, orank, lrank)
        }

        s.log("SERP parsed: ${organic.size} organic, ${local.size} local, $adCount ads excluded, $localAdsExcluded local-ads excluded")
        return SerpData(organic, local, adCount, localAdsExcluded, location, target)
    }

    /** "(1.2K)" -> 1200, "(353)" -> 353, "(1,400)" -> 1400. Null if unparseable. */
    private fun parseReviewCount(s: String): Int? {
        val t = s.trim().removePrefix("(").removeSuffix(")").replace(",", "").trim()
        val mult = when {
            t.endsWith("K", true) -> 1000.0
            t.endsWith("M", true) -> 1_000_000.0
            else -> 1.0
        }
        val num = t.trimEnd('K', 'k', 'M', 'm').toDoubleOrNull() ?: return null
        return (num * mult).toInt()
    }
}
