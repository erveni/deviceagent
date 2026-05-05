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

    // ── navigate ──

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
                // Tap Reload button or re-navigate
                val reload = s.findNode(text = "Reload", timeoutMs = 2000)
                if (reload != null) {
                    s.clickNode(reload)
                } else {
                    s.navigateToUrl(url)
                }
                Thread.sleep(waitMs)
            } else {
                break // page loaded OK
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

        // Step C: Set clipboard & paste
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
            if (!dismissed) break
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

    fun waitForGeneration(timeoutSec: Int = 120): Boolean {
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

    // ── ranking extraction ──

    fun extractRanking(): Pair<Int?, String?> {
        s.log("── EXTRACT RANKING ──")
        val text = getResponseText()
        if (text.isBlank()) {
            s.log("No response text found")
            return Pair(null, null)
        }

        // Reverse-scan for [RANK: X/Y] pattern
        val lines = text.lines()
        val rankPattern = Regex("""\[RANK:\s*(\d+)\s*/\s*(\d+\+?)\]""", RegexOption.IGNORE_CASE)

        for (line in lines.reversed()) {
            val trimmed = line.trim()
            if (trimmed.lowercase().let { "e.g." in it || "example" in it || "where x" in it })
                continue
            val m = rankPattern.find(trimmed)
            if (m != null) {
                val position = m.groupValues[1].toIntOrNull()
                val total = m.groupValues[2]
                s.log("RANK FOUND: $position / $total from \"$trimmed\"")
                return Pair(position, total)
            }
        }

        s.log("No [RANK: X/Y] pattern found in response")
        return Pair(null, null)
    }
}
