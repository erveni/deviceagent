package com.deviceagent

class FlowEngine(private val s: AgentAccessibilityService) {

    // ── chrome reset ──

    /**
     * Full Chrome app-data wipe via the system "App info → Storage → Clear storage" flow,
     * driven by accessibility (no device-owner / root needed). This is equivalent to
     * `pm clear com.android.chrome` and is STRONGER than the in-app "Delete browsing data":
     * a full wipe yields a genuine first-run Chrome, and logged-out Gemini then PERSISTS
     * the conversation (~17s+) instead of insta-deleting it (~7s) — long enough to click
     * the daily backlink. Returns true if the Clear/OK buttons were tapped.
     */
    fun clearChromeData(pkg: String = "com.android.chrome"): Boolean {
        s.log("── CLEAR CHROME DATA (pm-clear via Settings) ──")
        s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME)
        Thread.sleep(400)
        s.openAppDetails(pkg)
        Thread.sleep(2500)
        // 1) Tap the "Storage & Cache" / "Storage" entry. Label CASE + wording vary by
        // OEM ("Storage & cache" on Tecno, "Storage & Cache" on Transsion W-series, etc.)
        // so match case-insensitively by substring rather than exact text.
        var storage: android.view.accessibility.AccessibilityNodeInfo? = null
        for (attempt in 1..4) {
            storage = findNodeContaining("storage")
            if (storage != null) break
            Thread.sleep(1000)
        }
        if (storage == null) { s.log("[clear] Storage entry not found"); return false }
        clickSelfOrParent(storage); storage.recycle()
        Thread.sleep(1800)
        // 2) Tap "Clear storage" / "Clear data" (case-insensitive substring).
        var clearBtn: android.view.accessibility.AccessibilityNodeInfo? = null
        for (attempt in 1..4) {
            clearBtn = findNodeContaining("clear storage") ?: findNodeContaining("clear data")
            if (clearBtn != null) break
            Thread.sleep(800)
        }
        if (clearBtn == null) { s.log("[clear] Clear button not found"); return false }
        clickSelfOrParent(clearBtn); clearBtn.recycle()
        Thread.sleep(1200)
        // 3) Confirm the dialog ("OK" / "Delete" / "Clear").
        val ok = s.findNode(text = "OK", timeoutMs = 3000)
            ?: s.findNode(text = "Ok", timeoutMs = 800)
            ?: s.findNode(text = "Delete", timeoutMs = 800)
            ?: findNodeContaining("ok")
            ?: findNodeContaining("delete")
        if (ok != null) { clickSelfOrParent(ok); ok.recycle(); s.log("[clear] confirmed") }
        else s.log("[clear] no confirm dialog (some OEMs clear immediately)")
        Thread.sleep(1500)
        s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        Thread.sleep(400)
        return true
    }

    /**
     * Close EVERY open Chrome tab via Chrome's own tab switcher, selected by stable
     * Chrome resource-ids (`tab_switcher_button` / `menu_button`) so it behaves
     * identically on every OEM — unlike the Settings "Clear storage" path, which the
     * W-series phones fail. This is what makes the per-job clear real on all phones
     * with NO adb: even when the Settings wipe falls back to the light in-app delete
     * (which never closed tabs), tabs no longer pile up job-after-job.
     */
    fun closeAllChromeTabs(): Boolean {
        s.log("── CLOSE ALL CHROME TABS ──")
        // Bring Chrome forward with a real page so the toolbar (and tab-switcher button) is present.
        s.navigateToUrl("https://www.google.com")
        Thread.sleep(2500)
        dismissFreInline()
        Thread.sleep(400)
        val switcher = s.findNode(resourceId = "tab_switcher_button", timeoutMs = 4000)
            ?: s.findNode(contentDesc = "Switch or close tabs", timeoutMs = 1500)
            ?: findNodeContaining("switch or close tabs")
        if (switcher == null) { s.log("[tabs] tab-switcher button not found — skipping"); return false }
        clickSelfOrParent(switcher); switcher.recycle()
        // A tab grid holding hundreds/thousands of accumulated tabs renders slowly, so
        // wait generously before the menu lookups — short timeouts here were why the
        // 318- and 1987-tab phones silently fell through with 'item not found'.
        Thread.sleep(3500)
        // Overflow menu inside the tab switcher (resource-id "menu_button", desc "Manage open tabs").
        val menu = s.findNode(resourceId = "menu_button", timeoutMs = 6000)
            ?: s.findNode(contentDesc = "Manage open tabs", timeoutMs = 2000)
            ?: s.findNode(contentDesc = "More options", timeoutMs = 1500)
            ?: s.findNode(contentDesc = "Customise and control Google Chrome", timeoutMs = 1000)
            ?: s.findNode(contentDesc = "Customize and control Google Chrome", timeoutMs = 1000)
        if (menu == null) { s.log("[tabs] tab-switcher overflow not found — skipping"); return false }
        clickSelfOrParent(menu); menu.recycle()
        Thread.sleep(1500)
        val closeAll = s.findNode(text = "Close all tabs", timeoutMs = 7000)
            ?: findNodeContaining("close all tabs")
        if (closeAll == null) { s.log("[tabs] 'Close all tabs' item not found — skipping"); return false }
        clickSelfOrParent(closeAll); closeAll.recycle()
        Thread.sleep(1200)
        // Confirm dialog: the button reads "Close all tabs and groups" (not just "Close"),
        // so match the "close all" substring, not an exact label.
        (findNodeContaining("close all tabs and groups")
            ?: findNodeContaining("close all")
            ?: s.findNode(text = "Close", timeoutMs = 800))?.let { clickSelfOrParent(it); it.recycle() }
        Thread.sleep(1200)
        s.log("[tabs] closed all tabs")
        return true
    }

    /** Find the first node whose text OR contentDescription contains [needle] (case-insensitive). */
    private fun findNodeContaining(needle: String): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        val n = needle.lowercase()
        val hit = findContainingRecursive(root, n)
        root.recycle()
        return hit
    }

    private fun findContainingRecursive(
        node: android.view.accessibility.AccessibilityNodeInfo,
        needle: String
    ): android.view.accessibility.AccessibilityNodeInfo? {
        val t = node.text?.toString()?.lowercase() ?: ""
        val cd = node.contentDescription?.toString()?.lowercase() ?: ""
        if (t.contains(needle) || cd.contains(needle)) {
            return android.view.accessibility.AccessibilityNodeInfo.obtain(node)
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val r = findContainingRecursive(child, needle)
            if (r != null) { child.recycle(); return r }
            child.recycle()
        }
        return null
    }

    /** Click a node, or its nearest clickable ancestor if the node itself isn't clickable. */
    private fun clickSelfOrParent(node: android.view.accessibility.AccessibilityNodeInfo) {
        var n: android.view.accessibility.AccessibilityNodeInfo? = node
        var depth = 0
        while (n != null && depth < 6) {
            if (n.isClickable) { s.clickNode(n); return }
            n = n.parent; depth++
        }
        s.clickNode(node) // fall back to ACTION_CLICK on the original
    }

    /**
     * @param fullClear when true, do a FULL Chrome app-data wipe (pm-clear equivalent) so
     *   logged-out Gemini PERSISTS the conversation — required for the DAILY backlink click.
     *   When false (default), use the lighter in-app "Delete browsing data" — enough for
     *   RANKING (screenshot-first captures the answer inside the pre-wipe window) and far
     *   more robust under the residential proxy (the full clear triggers Chrome's first-run
     *   experience + cold page loads, which are fragile behind a proxy).
     */
    fun resetChrome(fullClear: Boolean = false): Boolean {
        s.log("── RESET CHROME (fullClear=$fullClear) ──")

        // Always close every open tab first, via Chrome's own UI (no adb). The Settings
        // "Clear storage" wipe below is the truest reset but fails on several W-series
        // phones and silently degrades to the light in-app delete, which never closed
        // tabs — so tabs accumulated job-after-job. Closing them here makes the clear
        // real on EVERY phone for BOTH daily and ranking. (per directive 2026-06-22)
        closeAllChromeTabs()

        if (fullClear) {
            val cleared = try { clearChromeData() } catch (e: Exception) { s.log("[clear] ex: ${e.message}"); false }
            s.log("clearChromeData -> $cleared")
            if (cleared) {
                // Chrome is now at first-run — dismiss the FRE robustly (it appears slowly
                // under a proxy) before returning.
                dismissChromeFreRobust()
                s.log("Chrome reset done (full clear)")
                return true
            }
            s.log("[clear] full clear failed — falling back to in-app delete")
        }

        // ── Light reset: legacy in-app "Delete browsing data" (v29 behaviour). ──
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

    /**
     * Robustly dismiss the first-run experience that appears after a FULL Chrome clear:
     * "Make Chrome your own" (Stay signed out) → notifications ("No thanks") → privacy
     * dialogs. Under a residential proxy these appear slowly, so poll for ~40s and keep
     * tapping any known FRE button (case-insensitive) until an input field is reachable.
     */
    private fun dismissChromeFreRobust() {
        s.log("── DISMISS CHROME FRE (robust) ──")
        s.navigateToUrl("https://www.google.com")
        val buttons = listOf(
            "stay signed out", "use without an account", "no thanks", "not now",
            "maybe later", "got it", "accept & continue", "skip", "no, thanks",
            "continue", "next", "ok", "i agree", "accept all", "reject all"
        )
        val deadline = System.currentTimeMillis() + 40_000
        var idle = 0
        while (System.currentTimeMillis() < deadline) {
            // Done as soon as a real input/search field is present.
            val input = s.findInputField(hintText = null, timeoutMs = 800)
            if (input != null) { input.recycle(); s.log("FRE done — input field reachable"); return }
            var tapped = false
            for (label in buttons) {
                val n = findNodeContaining(label) ?: continue
                val r = android.graphics.Rect(); n.getBoundsInScreen(r)
                // FRE buttons live in the lower 60% of the screen; ignore page text matches.
                if (r.centerY() > s.screenHeight() * 0.4) {
                    clickSelfOrParent(n); n.recycle()
                    s.log("FRE: tapped '$label'")
                    tapped = true
                    Thread.sleep(1200)
                    break
                }
                n.recycle()
            }
            if (!tapped) { idle++; if (idle >= 6) break; Thread.sleep(1500) } else idle = 0
        }
        s.log("FRE robust dismissal finished")
    }

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

    // ── input text ──

    /**
     * Type [text] through the Agent IME's real [android.view.inputmethod.InputConnection]
     * (commitText) — the genuine keyboard path. EXPERIMENT: tests whether logged-out
     * Gemini stops deleting the conversation when input looks like real typing.
     * Requires the Agent IME to be selected (adb shell ime set com.deviceagent/.AgentImeService).
     */
    fun inputTextViaIme(text: String): Boolean {
        s.log("── INPUT TEXT (IME): \"${text.take(40)}...\" ──")
        ensureChromeForeground()
        Thread.sleep(800)
        var inputNode = s.findInputField(hintText = null, timeoutMs = 5000)
        if (inputNode == null) {
            for (attempt in 1..4) {
                Thread.sleep(1500)
                inputNode = s.findInputField(hintText = null, timeoutMs = 2000)
                if (inputNode != null) break
            }
        }
        if (inputNode == null) inputNode = findPerplexityInput()
        if (inputNode == null) { s.log("[IME] input field NOT FOUND"); return false }
        val b = android.graphics.Rect(); inputNode.getBoundsInScreen(b); inputNode.recycle()
        // Tap to focus → binds the (invisible) Agent IME's InputConnection to the field.
        s.gestureTap(b.centerX().toFloat(), b.centerY().toFloat())
        Thread.sleep(700)
        if (!ImeBridge.awaitConnection(4000)) {
            s.log("[IME] no InputConnection — Agent IME not selected? (adb ime set)")
            return false
        }
        var ok = true
        for (ch in text) {
            if (!ImeBridge.commitText(ch.toString())) { ok = false; break }
            Thread.sleep(25)   // mimic human typing cadence
        }
        s.log("[IME] committed ${text.length} chars ok=$ok")
        return ok
    }

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

        // Step C: Set clipboard & paste. Clear the field first so a partial Step-B
        // set-text doesn't get a paste appended on top of it (double-prompt bug).
        if (inputNode != null) s.setTextOnNode(inputNode, "")
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

    private fun isGenerating(): Boolean =
        s.findNode(contentDesc = "Stop streaming", timeoutMs = 400) != null ||
        s.findNode(contentDesc = "Stop generating", timeoutMs = 400) != null ||
        s.findNode(contentDesc = "Stop response", timeoutMs = 400) != null

    private val sendSelectors = listOf("Send message", "Submit", "Send prompt", "Send", "Go")

    /** Find the current send button node (by contentDesc then text), or null if gone. */
    private fun findSendNode(): android.view.accessibility.AccessibilityNodeInfo? {
        for (label in sendSelectors) {
            val n = s.findNode(contentDesc = label, timeoutMs = 300)
                ?: s.findNode(text = label, timeoutMs = 200)
            if (n != null) return n
        }
        return null
    }

    /** True once the prompt has been sent: the send button is gone OR generation started. */
    private fun didSend(): Boolean {
        if (isGenerating()) return true
        val n = findSendNode()
        if (n == null) return true
        n.recycle()
        return false
    }

    fun submit(platform: String = ""): Boolean {
        s.log("── SUBMIT (${platform.ifBlank { "?" }}) ──")
        ensureChromeForeground()
        if (isGenerating()) { s.log("Already generating — not submitting"); return true }

        // ── GEMINI: ACTION_CLICK reports success but does NOT actually send on the new
        // logged-out web UI, so tap the send button's real on-screen center. ──
        if (platform.lowercase() == "gemini") {
            val node = findSendNode()
            if (node == null) {
                s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
                Thread.sleep(600)
                if (!isGenerating()) { s.gestureTap(s.screenWidth() * 0.864f, s.screenHeight() * 0.925f); Thread.sleep(1200) }
                return true
            }
            val r = android.graphics.Rect(); node.getBoundsInScreen(r)
            s.clickNode(node); node.recycle()
            Thread.sleep(1200)
            if (didSend()) { s.log("Submit[gemini]: sent via ACTION_CLICK"); return true }
            if (r.width() > 0 && r.height() > 0 &&
                r.centerX() in 0..s.screenWidth() && r.centerY() in 0..s.screenHeight()) {
                s.gestureTap(r.centerX().toFloat(), r.centerY().toFloat())
                s.log("Submit[gemini]: gesture-tapped bounds center (${r.centerX()},${r.centerY()})")
                Thread.sleep(1200)
                if (didSend()) return true
            }
            s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
            Thread.sleep(600)
            if (!didSend()) { s.gestureTap(s.screenWidth() * 0.864f, s.screenHeight() * 0.925f); Thread.sleep(1200) }
            return true
        }

        // ── ChatGPT: the new logged-out chatgpt.com UI ignores ACTION_CLICK on the
        // send button — the prompt clears and it resets to the empty home screen,
        // never sending (same class of bug Gemini hit). Tap the real on-screen
        // send-button center instead; verify via didSend(). ACTION_CLICK only as a
        // last resort. ──
        if (platform.lowercase() == "chatgpt") {
            // The real send button sits at the BOTTOM, next to the input. Only tap
            // a send node found in the bottom half — findSendNode() can resolve to a
            // top-right element (Chrome's ⋮ overflow), and tapping that opened the
            // Chrome menu instead of sending (confirmed on-screen). Reject top nodes.
            val node = findSendNode()
            if (node != null) {
                val r = android.graphics.Rect(); node.getBoundsInScreen(r); node.recycle()
                // Reject ONLY the top toolbar zone: Chrome's ⋮ overflow is at the
                // very top (~8% of height). The real send arrow sits mid-screen
                // (~40%) when the keyboard is up, so a bottom-half (>50%) guard
                // wrongly rejected it. Anything below the toolbar (~15%) is fair.
                val notToolbar = r.centerY() > s.screenHeight() * 0.15
                if (r.width() > 0 && r.height() > 0 && notToolbar &&
                    r.centerX() in 0..s.screenWidth() && r.centerY() in 0..s.screenHeight()) {
                    s.gestureTap(r.centerX().toFloat(), r.centerY().toFloat())
                    s.log("Submit[chatgpt]: gesture-tapped send center (${r.centerX()},${r.centerY()})")
                    Thread.sleep(1500)
                    if (didSend()) return true
                } else {
                    s.log("Submit[chatgpt]: ignoring send node at (${r.centerX()},${r.centerY()}) — top toolbar (Chrome ⋮)")
                }
            }
            // Fallback: the send arrow is at the right end of the input row. Tap
            // there relative to the input field's Y (never the top toolbar).
            val inp = s.findInputField(hintText = null, timeoutMs = 2000)
            if (inp != null) {
                val ib = android.graphics.Rect(); inp.getBoundsInScreen(ib); inp.recycle()
                // Send arrow is at the right end of the input row, near the box's
                // bottom edge — tap there regardless of where the keyboard pushed it.
                val ty = (ib.bottom - 8).coerceIn(0, s.screenHeight()).toFloat()
                s.gestureTap(s.screenWidth() - 60f, ty)
                s.log("Submit[chatgpt]: input-relative send tap (${s.screenWidth() - 60},${ty.toInt()})")
                Thread.sleep(1500)
                if (didSend()) return true
            }
            s.log("Submit[chatgpt]: send not confirmed")
            return true
        }

        // ── Perplexity (PROVEN original path): semantic ACTION_CLICK on the
        // labelled send button. Works regardless of the node's (often degenerate) web
        // bounds — Perplexity's send button reports zero-height bounds, so any coordinate
        // tap misses; ACTION_CLICK does not. Two passes, return on first successful click. ──
        val selectors = listOf(
            "Submit" to "cd", "Send message" to "cd", "Send prompt" to "cd",
            "Send" to "text", "Go" to "cd"
        )
        for (pass in 1..2) {
            for ((label, type) in selectors) {
                val node = if (type == "cd") s.findNode(contentDesc = label, timeoutMs = 2000)
                           else s.findNode(text = label, timeoutMs = 2000)
                if (node != null) {
                    val clicked = s.clickNode(node); node.recycle()
                    if (clicked) { s.log("Submit: ACTION_CLICK '$label' (pass $pass)"); Thread.sleep(1000); return true }
                    s.log("Submit: found '$label' but click failed, next…")
                }
            }
            Thread.sleep(500)
        }
        // Fallback: bottom-right corner (Perplexity submit button area).
        s.gestureTap(s.screenWidth() - 60f, s.screenHeight() * 0.82f)
        s.log("Submit: bottom-right fallback tap")
        return true
    }

    // ── scroll ──

    /** Zoom OUT a few times so a long top-3 answer (list + [RANK: X/Y] line) fits
     *  in one screenshot — the client needs to SEE ranks 1-3 together with the
     *  rank line, which over-scrolling to the rank line alone pushes #1 off-top. */
    fun zoomOutResponse(times: Int = 2): Boolean {
        ensureChromeForeground()
        val cx = s.screenWidth() / 2f
        val cy = s.screenHeight() / 2f
        for (i in 1..times) {
            s.gesturePinchZoomOut(cx, cy)
            Thread.sleep(800)
            s.log("zoomOut $i/$times")
        }
        return true
    }

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

    // The ANSWER's rank line carries real numbers ("[RANK: 8/25]"); the prompt
    // bubble echoes the literal "[RANK: X/Y]" instruction, so match digits only.
    private val rankAnswerPattern =
        Regex("""\[rank:\s*\d+\s*/\s*\d+""", RegexOption.IGNORE_CASE)

    /** The LAST on-tree node whose text is the numeric [RANK] answer (not the
     *  prompt bubble's placeholder). Caller must recycle the returned node. */
    private fun findRankAnswerNode(): android.view.accessibility.AccessibilityNodeInfo? {
        val root = s.rootInActiveWindow ?: return null
        var last: android.view.accessibility.AccessibilityNodeInfo? = null
        fun walk(node: android.view.accessibility.AccessibilityNodeInfo) {
            val t = node.text?.toString() ?: ""
            if (rankAnswerPattern.containsMatchIn(t)) {
                last?.recycle()
                last = android.view.accessibility.AccessibilityNodeInfo.obtain(node)
            }
            for (i in 0 until node.childCount) {
                val c = node.getChild(i) ?: continue
                walk(c); c.recycle()
            }
        }
        walk(root); root.recycle()
        return last
    }

    /**
     * Scroll so the answer's [RANK: X/Y] line is on-screen for the screenshot,
     * instead of over-scrolling onto the trailing Google Maps embed ChatGPT adds
     * for local-business queries. Scrolls down in modest steps and stops the
     * moment the rank line enters the visible band; nudges back up if overshot.
     * Falls back (returns false) if the line is never positioned.
     */
    fun scrollToRankLine(maxSteps: Int = 14): Boolean {
        ensureChromeForeground()
        val x = s.screenWidth() - 3f
        val h = s.screenHeight()
        // Park [RANK] as LOW as it will go so the ranks 1-3 ABOVE it get the most
        // room — that's what keeps rank #1 from clipping off the top. [RANK] now
        // sits right after the top-3 (prompt outputs it before the summary), so a
        // low [RANK] means #1, #2, #3 fill the screen above it (the summary + the
        // trailing map scroll below the fold). We can't zoom-out to fit a tall list
        // (chatgpt.com sets user-scalable=no), and scrolling UP toward the answer
        // top snaps logged-out ChatGPT back to its zero-state — so the only safe
        // lever is parking [RANK] low and relying on the short-description prompt.
        val topBand = (h * 0.70f).toInt()
        val botBand = (h * 0.92f).toInt()
        for (i in 1..maxSteps) {
            val node = findRankAnswerNode()
            if (node != null) {
                val r = android.graphics.Rect(); node.getBoundsInScreen(r); node.recycle()
                if (r.height() > 0 && r.centerY() in topBand..botBand) {
                    s.log("scrollToRankLine: [RANK] on-screen y=${r.centerY()} (step $i)")
                    return true
                }
                if (r.height() > 0 && r.centerY() < topBand) {
                    // overshot past it onto the map — nudge back up (swipe down)
                    s.gestureSwipe(x, h * 0.35f, x, h * 0.65f, 600)
                    Thread.sleep(1400); continue
                }
            }
            // not found yet, or below the band — scroll down a modest amount
            s.gestureSwipe(x, h * 0.70f, x, h * 0.45f, 600)
            Thread.sleep(1600)
        }
        s.log("scrollToRankLine: [RANK] not positioned after $maxSteps steps")
        return false
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

        // ── ChatGPT: links are embedded as clickable elements in the response text ──
        if (platform.lowercase() == "chatgpt") {
            Thread.sleep(1000)
            return clickBacklinkChatGPT(domain)
        }

        // ── Gemini (logged out): the answer embeds inline "Visit <business>" website
        // links, NOT a Sources carousel. Click the embedded link directly —
        // findNodeByTargetUrl works on offscreen nodes (no scroll needed) and is fast
        // enough to beat the ~3s logged-out wipe. The Sources-panel path below stays as
        // a fallback for signed-in Gemini (which does render a Sources carousel).
        if (platform.lowercase() == "gemini") {
            val ghint = domain.substringBefore(".")
            for (attempt in 1..3) {
                val link = findNodeByTargetUrl(domain) ?: findClickableWithUrl(domain, ghint)
                if (link != null) {
                    val url = link.extras?.getString("AccessibilityNodeInfo.targetUrl") ?: ""
                    s.log("Gemini embedded backlink FOUND -> $url")
                    val clicked = link.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)
                    link.recycle()
                    s.log("Gemini embedded backlink ACTION_CLICK -> $clicked")
                    Thread.sleep(3000)
                    browseBacklinkPage()
                    return true
                }
                Thread.sleep(400)
            }
            // Logged-out Gemini has no Sources carousel and the chat is wiped within
            // ~3s, so the slow Sources fallback below can't help — give up fast instead
            // of burning ~20s per job on a screen that's already gone.
            s.log("Gemini embedded link not found — skipping (logged-out, no Sources panel)")
            return false
        }

        Thread.sleep(1000)
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
            val url = node.extras?.getString("AccessibilityNodeInfo.targetUrl")?.take(80) ?: ""
            val rect = android.graphics.Rect()
            node.getBoundsInScreen(rect)
            sb.appendLine("  ".repeat(depth) + "[C] $cls text=\"$txt\" cd=\"$cd\" url=\"$url\" y=${rect.top}")
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

    fun waitForGeneration(timeoutSec: Int = 240): Boolean {
        s.log("── WAIT FOR GENERATION ──")
        val start = System.currentTimeMillis()
        val timeout = timeoutSec * 1000L
        // New logged-out Gemini (3.5) produces an answer then RESETS to the welcome
        // screen, stripping the Copy/Share action buttons — so "buttons appeared" is no
        // longer a reliable completion signal. Track whether we ever saw streaming; once
        // the Stop button clears after a streaming phase, the answer was produced.
        // Poll at a forgiving cadence: on slow proxied pages, too-short a11y finds MISS the
        // completion buttons and cause false generation_timeouts. 500ms finds (the proven
        // June-14 value) reliably detect them. sawStreaming still handles logged-out Gemini.
        var sawStreaming = false
        while (System.currentTimeMillis() - start < timeout) {
            Thread.sleep(2000)
            val stopBtn = s.findNode(contentDesc = "Stop streaming", timeoutMs = 500)
                ?: s.findNode(contentDesc = "Stop generating", timeoutMs = 500)
                ?: s.findNode(contentDesc = "Stop response", timeoutMs = 500)
            if (stopBtn != null) {
                sawStreaming = true
                s.log("Still generating...")
                continue
            }
            val hasContent = s.findNode(contentDesc = "Copy", timeoutMs = 500) != null
                || s.findNode(contentDesc = "Share", timeoutMs = 500) != null
                || s.findNode(contentDesc = "Read aloud", timeoutMs = 500) != null
            if (hasContent) {
                s.log("Generation complete (action buttons)")
                return true
            }
            // New logged-out Gemini: it streamed, the Stop button is now gone, but the
            // action buttons were wiped by the reset — still count it as complete.
            if (sawStreaming) {
                s.log("Generation complete (stop cleared, buttons wiped by reset)")
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
