package com.deviceagent

import android.content.ComponentName
import android.content.Intent
import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.io.OutputStream
import java.io.OutputStreamWriter
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicReference

class AgentHttpServer(private val flowEngine: FlowEngine) {

    companion object {
        const val PORT = 8765
        // Kept in sync with app/build.gradle.kts. Reported by /health so the
        // Mac-side dispatcher can detect a fleet running mixed APK versions.
        const val APP_VERSION_NAME = "0.9.9-seo"
        const val APP_VERSION_CODE = 20
        val lastResult = AtomicReference<SessionResult?>(null)
        // Approximation of app startup time — initialized when the class is first
        // referenced (which happens at HTTP server start, very early in the
        // process lifecycle). Used for /health uptime reporting.
        val PROCESS_START_MS = System.currentTimeMillis()

        private const val AUDIT_PROMPT_TEMPLATE = (
            "Top 3 businesses for {keyword} in {city}, {state}. " +
            "Format: numbered list, each entry: name, 2-3 sentence description of why they stand out, " +
            "and whether they appear on Google Maps (yes/no). " +
            "Do not include any maps, images, or embedded content — text only. " +
            "After the list, rank {biz_name} ({biz_url}) among all businesses in this space. " +
            "You MUST include this exact line on its own: [RANK: X/Y] " +
            "where X is the position and Y is total businesses (e.g., [RANK: 7/25]). " +
            "Then one sentence explaining why. " +
            "Keep entire response under 200 words."
        )

        fun buildAuditPrompt(bizName: String, bizUrl: String, city: String, state: String, keyword: String): String {
            return AUDIT_PROMPT_TEMPLATE
                .replace("{keyword}", keyword)
                .replace("{city}", city)
                .replace("{state}", state)
                .replace("{biz_name}", bizName)
                .replace("{biz_url}", bizUrl)
        }

        /** Execute a session from anywhere (HTTP or MQTT). Updates result in-place. */
        fun executeSessionStatic(
            result: SessionResult,
            flowEngine: FlowEngine,
            platform: String,
            prompt: String,
            followUp: String?,
            backlinkDomain: String?
        ) {
            fun step(name: String, block: () -> Boolean): Boolean {
                result.steps.add("$name...")
                val ok = try { block() } catch (e: Exception) {
                    result.steps.add("$name: ERROR - ${e.message}")
                    false
                }
                result.steps.add("$name: ${if (ok) "OK" else "FAILED"}")
                return ok
            }
            try {
                if (!step("reset_chrome") { flowEngine.resetChrome() }) {
                    result.status = "error"; result.error = "reset_chrome failed"; return
                }
                Thread.sleep(500)
                if (!step("navigate") { flowEngine.navigateTo(platform) }) {
                    result.status = "error"; result.error = "navigate failed"; return
                }
                Thread.sleep(if (platform == "chatgpt") 6000L else 3000L)
                step("dismiss_popups") { flowEngine.dismissPlatformPopups(platform); true }
                Thread.sleep(500)
                if (!step("input") { flowEngine.inputText(prompt) }) {
                    result.status = "error"; result.error = "input failed"; return
                }
                Thread.sleep(300)
                step("submit") { flowEngine.submit() }
                Thread.sleep(2000)
                if (!step("wait_generation") { flowEngine.waitForGeneration(timeoutSec = 120) }) {
                    result.status = "error"; result.error = "generation timeout"; return
                }
                // ChatGPT: click backlink BEFORE scroll (links at top of response).
                // Wait a moment for response to fully render before searching.
                if (!backlinkDomain.isNullOrBlank() && platform.lowercase() == "chatgpt") {
                    Thread.sleep(3000)
                    val clicked = step("backlink") { flowEngine.clickBacklink(backlinkDomain, platform) }
                    result.backlinkClicked = clicked
                }
                step("scroll") { flowEngine.scrollResponse(12) }
                if (!followUp.isNullOrBlank()) {
                    step("follow_up") { flowEngine.sendFollowUp(followUp) }
                }
                // Other platforms: click backlink AFTER scroll
                if (!backlinkDomain.isNullOrBlank() && platform.lowercase() != "chatgpt") {
                    val clicked = step("backlink") { flowEngine.clickBacklink(backlinkDomain, platform) }
                    result.backlinkClicked = clicked
                }
                result.status = "completed"
            } catch (e: Exception) {
                result.status = "error"
                result.error = e.message
                Log.e("DeviceAgent", "Session error: ${e.stackTraceToString()}")
            }
        }

        /** Execute an audit session — runs specified platforms. If platforms is empty, runs all 3. */
        fun executeAuditSessionStatic(
            result: SessionResult,
            flowEngine: FlowEngine,
            bizName: String,
            bizUrl: String,
            city: String,
            state: String,
            keyword: String,
            platformsFilter: String? = null
        ) {
            val prompt = buildAuditPrompt(bizName, bizUrl, city, state, keyword)
            result.prompt = prompt
            result.type = "audit"

            val platformsOrder = if (platformsFilter.isNullOrBlank()) {
                listOf("gemini", "chatgpt", "perplexity")
            } else {
                listOf(platformsFilter.lowercase())
            }

            // No preflight. Audit must mirror daily exactly — daily has near-100%
            // success without any preflight call. Adding a navigateToUrl before
            // resetChrome caused subsequent jobs on the same phone to fail
            // (Chrome state mismatch after the extra nav). The audit flow body
            // below is now structurally identical to executeSessionStatic
            // (the daily flow), one platform at a time.

            for (platform in platformsOrder) {
                val pr = PlatformResult(status = "running")
                result.platforms[platform] = pr

                val stepBase = System.currentTimeMillis()
                fun step(name: String, block: () -> Boolean): Boolean {
                    val t0 = System.currentTimeMillis()
                    val ok = try { block() } catch (e: Exception) {
                        result.steps.add("[$platform] $name FAILED ${(System.currentTimeMillis()-t0)/1000}s - ${e.message}")
                        false
                    }
                    val dt = (System.currentTimeMillis() - t0) / 1000
                    val total = (System.currentTimeMillis() - stepBase) / 1000
                    result.steps.add("[$platform] $name ${if (ok) "OK" else "FAILED"} ${dt}s (total ${total}s)")
                    return ok
                }

                try {
                    // Audit flow MATCHES daily exactly. Steps below are identical to
                    // executeSessionStatic — no audit-only guards, no platform-specific
                    // branches. If daily reliability holds, audit reliability holds.
                    if (!step("reset_chrome") { flowEngine.resetChrome() }) {
                        pr.status = "error"; pr.error = "reset_chrome failed"; continue
                    }
                    Thread.sleep(500)
                    if (!step("navigate") { flowEngine.navigateTo(platform) }) {
                        pr.status = "error"; pr.error = "navigate failed"; continue
                    }
                    Thread.sleep(if (platform == "chatgpt") 6000L else 3000L)
                    step("dismiss_popups") { flowEngine.dismissPlatformPopups(platform); true }
                    Thread.sleep(500)
                    if (!step("input") { flowEngine.inputText(prompt) }) {
                        pr.status = "error"; pr.error = "input failed"; continue
                    }
                    Thread.sleep(300)
                    step("submit") { flowEngine.submit() }
                    Thread.sleep(2000)
                    if (!step("wait_generation") { flowEngine.waitForGeneration(timeoutSec = 120) }) {
                        pr.status = "error"; pr.error = "generation timeout"; continue
                    }
                    // 200-word capped response — 6 scrolls covers the full response
                    // and lands on the [RANK: X/Y] line near the end. Saves ~17s vs 12.
                    step("scroll") { flowEngine.scrollResponse(6) }
                    Thread.sleep(1000)
                    // Capture full LLM response text once; reuse for rank scan + audit log.
                    val responseText = flowEngine.getResponseText()
                    val (pos, total) = flowEngine.extractRankingFromText(responseText)
                    pr.rankingPosition = pos
                    pr.rankingTotal = total
                    pr.responseText = responseText

                    // Capture screenshot — saved to phone-side scoped dir and
                    // ALSO base64-encoded inline so the Mac dispatcher can write
                    // the file locally without an `adb pull` round-trip. Falls
                    // back to the path-only behaviour when the file can't be
                    // read back (caller will adb-pull as before).
                    val ssName = "audit_${platform}_${System.currentTimeMillis()}"
                    val ssPath = try { flowEngine.saveScreenshot(ssName) } catch (e: Exception) { null }
                    pr.screenshotPath = ssPath
                    if (!ssPath.isNullOrBlank()) {
                        pr.screenshotB64 = try {
                            val bytes = File(ssPath).readBytes()
                            android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
                        } catch (e: Exception) {
                            Log.w("DeviceAgent", "screenshot b64 encode failed for $ssPath: ${e.message}")
                            null
                        }
                    }

                    pr.status = "completed"
                    result.steps.add("[$platform] ranking: $pos / $total  ss=$ssPath")
                } catch (e: Exception) {
                    pr.status = "error"
                    pr.error = e.message
                    Log.e("DeviceAgent", "Audit $platform error: ${e.stackTraceToString()}")
                }
            }

            // Set overall ranking from first platform that has one
            for (platform in platformsOrder) {
                val pr = result.platforms[platform] ?: continue
                if (pr.rankingPosition != null) {
                    result.rankingPosition = pr.rankingPosition
                    result.rankingTotal = pr.rankingTotal
                    break
                }
            }

            val hasError = result.platforms.values.any { it.status == "error" }
            result.status = if (hasError && result.platforms.values.all { it.status == "error" }) "error" else "completed"
        }

        /**
         * Execute a Google SEO session: real Chrome → human-typed search → parse the SERP
         * into SerpApi-like organic + local-pack rankings (ads excluded) + a proof screenshot.
         * Structurally mirrors the daily/audit flow (reset → navigate → input → submit).
         */
        fun executeGoogleSerpStatic(
            result: SessionResult,
            flowEngine: FlowEngine,
            keyword: String,
            targetDomain: String?,
            location: String = ""
        ) {
            result.type = "seo"
            result.prompt = keyword
            val stepBase = System.currentTimeMillis()
            fun step(name: String, block: () -> Boolean): Boolean {
                val t0 = System.currentTimeMillis()
                val ok = try { block() } catch (e: Exception) {
                    result.steps.add("[seo] $name FAILED ${(System.currentTimeMillis()-t0)/1000}s - ${e.message}")
                    false
                }
                val dt = (System.currentTimeMillis() - t0) / 1000
                val total = (System.currentTimeMillis() - stepBase) / 1000
                result.steps.add("[seo] $name ${if (ok) "OK" else "FAILED"} ${dt}s (total ${total}s)")
                return ok
            }

            try {
                if (!step("reset_chrome") { flowEngine.resetChrome() }) {
                    result.status = "error"; result.error = "reset_chrome failed"; return
                }
                Thread.sleep(500)
                // PRIMARY path: load the SERP URL directly (?q= + uule + gl=us&hl=en).
                // Skips the through-proxy-flaky human-typed input ladder (DEFECT #2) and
                // pins locale deterministically. `location` (canonical "City,State,United
                // States") localizes via uule; blank → gl=us only. Matches the precision
                // posture (no human-typing theater).
                if (!step("navigate_serp") { flowEngine.navigateToSerpLocalized(keyword, location) }) {
                    result.status = "error"; result.error = "serp navigate failed"; return
                }
                Thread.sleep(2500)

                // Reach a real SERP, self-checking for a Google/Cloudflare bot challenge and
                // auto-recovering (wait + reload) so no manual intervention is needed. A soft
                // "unusual traffic" interstitial often clears with a short cool-down + reload;
                // a hard reCAPTCHA does not (that needs a fresh proxy IP — reported as blocked).
                var onSerp = flowEngine.waitForSerp(12)
                if (onSerp) {
                    result.steps.add("[seo] wait_serp OK (human submit)")
                } else {
                    var attempt = 0
                    while (!onSerp && attempt < 3) {
                        attempt++
                        if (flowEngine.lastChallengeSeen) {
                            // Try to clear the reCAPTCHA by ticking "I'm not a robot".
                            onSerp = step("solve_challenge_$attempt") { flowEngine.solveChallenge(22) }
                            if (onSerp) break
                            // Couldn't tick/pass — cool down and reload for a fresh challenge.
                            onSerp = step("challenge_reload_$attempt") {
                                Thread.sleep(6000)
                                flowEngine.navigateToSerpLocalized(keyword, location)
                                flowEngine.waitForSerp(18)
                            }
                        } else {
                            onSerp = step("serp_fallback_$attempt") {
                                flowEngine.navigateToSerpLocalized(keyword, location)
                                flowEngine.waitForSerp(20)
                            }
                        }
                    }
                    if (!onSerp) {
                        result.challenge = flowEngine.lastChallengeSeen
                        result.status = "blocked"
                        result.error = if (flowEngine.lastChallengeSeen)
                            "bot/recaptcha challenge — needs fresh proxy IP" else "serp load timeout"
                        // Capture the blocking page itself as evidence.
                        val blkName = "seo_blocked_${System.currentTimeMillis()}"
                        val blkPath = try { flowEngine.saveScreenshot(blkName) } catch (e: Exception) { null }
                        result.screenshotPath = blkPath
                        if (!blkPath.isNullOrBlank()) {
                            result.screenshotB64 = try {
                                android.util.Base64.encodeToString(File(blkPath).readBytes(), android.util.Base64.NO_WRAP)
                            } catch (e: Exception) { null }
                        }
                        result.steps.add("[seo] BLOCKED: ${result.error}")
                        return
                    }
                }

                // Dismiss Google's "See results closer to you?" precise-location prompt (and
                // similar overlays) that otherwise sit on top of the results and break parsing.
                step("dismiss_serp_dialogs") { flowEngine.dismissSerpDialogs(); true }

                // Clear any active result filter (e.g. "Top rated") so the ranking is the default,
                // unfiltered SERP — a selected filter would skew the SEO rank.
                step("clear_filters") { flowEngine.clearSearchFilters() >= 0 }

                // Capture TWO proof screenshots: one framed on the LOCAL/Maps pack, one on the
                // ORGANIC results — a rank audit needs both. Each scroll falls back gracefully
                // if its section is absent; we still shoot whatever is on screen.
                fun shootB64(tag: String): Pair<String?, String?> {
                    Thread.sleep(800)
                    val name = "seo_${tag}_${System.currentTimeMillis()}"
                    val path = try { flowEngine.saveScreenshot(name) } catch (e: Exception) { null }
                    val b64 = if (!path.isNullOrBlank()) try {
                        android.util.Base64.encodeToString(File(path).readBytes(), android.util.Base64.NO_WRAP)
                    } catch (e: Exception) { Log.w("DeviceAgent", "seo $tag ss b64 failed: ${e.message}"); null } else null
                    return path to b64
                }
                // 1) local/Maps pack — anchor on the first star-rating card (header label varies)
                step("scroll_to_local") {
                    flowEngine.scrollToLocalPackTop() || flowEngine.scrollToTextTop(listOf("Places", "Businesses")); true
                }
                shootB64("local").let { (p, b) -> result.screenshotLocalPath = p; result.screenshotLocalB64 = b }
                // 2) organic results — anchor on the organic block top (proven reliable; a
                //    target-row anchor over-scrolled off the SERP when the row wasn't yet rendered).
                step("scroll_to_organic") { flowEngine.scrollToOrganicTop(); true }
                shootB64("organic").let { (p, b) -> result.screenshotOrganicPath = p; result.screenshotOrganicB64 = b }
                // legacy single-screenshot fields → local shot, for back-compat
                result.screenshotPath = result.screenshotLocalPath
                result.screenshotB64 = result.screenshotLocalB64

                // Scroll the rest of the SERP so off-screen results materialise in the a11y tree, then parse.
                step("scroll") { flowEngine.scrollResponse(8) }
                Thread.sleep(800)
                val serp = flowEngine.parseSerp(targetDomain)
                result.serp = serp
                result.rankingPosition = serp.target?.organicRank
                result.steps.add(
                    "[seo] parsed: ${serp.organic.size} organic, ${serp.local.size} local, " +
                    "${serp.adsExcluded} ads + ${serp.localAdsExcluded} local-ads excluded, " +
                    "target_organic=${serp.target?.organicRank} target_local=${serp.target?.localRank}"
                )
                result.status = "completed"
            } catch (e: Exception) {
                result.status = "error"; result.error = e.message
                Log.e("DeviceAgent", "SEO error: ${e.stackTraceToString()}")
            }
        }
    }

    private var serverThread: Thread? = null
    private var serverSocket: java.net.ServerSocket? = null
    private var running = false

    data class PlatformResult(
        var status: String = "idle",
        var rankingPosition: Int? = null,
        var rankingTotal: String? = null,
        var screenshotPath: String? = null,
        // Base64-encoded PNG bytes. Inlined in the audit response so the Mac
        // dispatcher can write the file locally without `adb pull` — works
        // during active VPN since the response travels over the existing
        // adb-forward HTTP tunnel.
        var screenshotB64: String? = null,
        var responseText: String? = null,
        var error: String? = null
    )

    data class SessionResult(
        val platform: String = "",
        var status: String = "idle",       // idle | running | completed | error
        val steps: MutableList<String> = mutableListOf(),
        var backlinkClicked: Boolean = false,
        var backlinkDomain: String? = null,
        var error: String? = null,
        var prompt: String = "",
        var type: String = "daily",
        var rankingPosition: Int? = null,
        var rankingTotal: String? = null,
        var proxyIp: String? = null,
        // SEO (Google SERP) results — populated for type=="seo".
        var serp: SerpData? = null,
        var challenge: Boolean = false,
        var screenshotPath: String? = null,
        var screenshotB64: String? = null,
        var screenshotLocalB64: String? = null,
        var screenshotOrganicB64: String? = null,
        var screenshotLocalPath: String? = null,
        var screenshotOrganicPath: String? = null,
        val platforms: MutableMap<String, PlatformResult> = mutableMapOf()
    )

    fun start() {
        running = true
        serverThread = Thread {
            try {
                val server = ServerSocket().apply {
                    reuseAddress = true
                    bind(java.net.InetSocketAddress(PORT))
                }
                serverSocket = server
                Log.d("DeviceAgent", "HTTP API listening on port $PORT")
                while (running) {
                    try {
                        val client = server.accept()
                        Thread { handleClient(client) }.start()
                    } catch (e: Exception) {
                        if (running) Log.e("DeviceAgent", "Accept error: ${e.message}")
                    }
                }
                server.close()
            } catch (e: Exception) {
                Log.e("DeviceAgent", "Server error: ${e.message}")
            }
        }.apply {
            name = "agent-http"
            isDaemon = true
            start()
        }
    }

    fun stop() {
        running = false
        try { serverSocket?.close() } catch (_: Exception) {}
        serverSocket = null
        serverThread?.interrupt()
    }

    private fun handleClient(socket: Socket) {
        try {
            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
            val writer = OutputStreamWriter(socket.outputStream)

            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return
            val method = parts[0]
            val path = parts[1]

            var contentLength = 0
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isBlank()) break
                if (line.startsWith("Content-Length:", ignoreCase = true)) {
                    contentLength = line.substringAfter(":").trim().toIntOrNull() ?: 0
                }
            }

            val body = if (contentLength > 0) {
                val buf = CharArray(contentLength)
                reader.read(buf, 0, contentLength)
                String(buf)
            } else ""

            Log.d("DeviceAgent", "HTTP $method $path")

            when {
                path == "/ping" || path == "/ping/" -> {
                    respond(writer, 200, """{"pong":true}""")
                }
                path == "/status" || path == "/status/" -> {
                    handleStatus(writer)
                }
                path == "/health" || path == "/health/" -> {
                    handleHealth(writer)
                }
                path.startsWith("/screenshot") -> {
                    handleScreenshot(socket.outputStream, writer, path)
                }
                path.startsWith("/voice_search") -> {
                    handleVoiceSearch(writer, path)
                }
                path == "/session" || path == "/session/" -> {
                    if (method == "POST") {
                        handleSession(writer, body)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                path == "/mqtt/config" || path == "/mqtt/config/" -> {
                    if (method == "POST") {
                        handleMqttConfig(writer, body)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                path == "/proxy/start" || path == "/proxy/start/" -> {
                    if (method == "POST") {
                        handleProxyStart(writer, body)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                path == "/proxy/stop" || path == "/proxy/stop/" -> {
                    if (method == "POST") {
                        handleProxyStop(writer)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                path == "/agent/start" || path == "/agent/start/" -> {
                    if (method == "POST") {
                        handleAgentStart(writer, body)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                path == "/agent/stop" || path == "/agent/stop/" -> {
                    if (method == "POST") {
                        handleAgentStop(writer)
                    } else {
                        respond(writer, 405, """{"error":"use POST"}""")
                    }
                }
                else -> {
                    respond(writer, 404, """{"error":"not found"}""")
                }
            }

            writer.flush()
        } catch (e: Exception) {
            Log.e("DeviceAgent", "Client error: ${e.message}")
        } finally {
            try { socket.close() } catch (_: Exception) {}
        }
    }

    private fun handleSession(writer: OutputStreamWriter, body: String) {
        try {
            val json = JSONObject(body)
            val sessionType = json.optString("type", "daily")

            when (sessionType) {
                "audit" -> handleAuditSession(writer, json)
                "seo" -> handleSeoSession(writer, json)
                "noop" -> handleNoopSession(writer, json)
                else -> handleDailySession(writer, json)
            }
        } catch (e: Exception) {
            Log.e("DeviceAgent", "Session error: ${e.message}")
            respond(writer, 400, """{"error":"${e.message?.replace("\"", "'")}"}""")
        }
    }

    /**
     * Dry-run handler for the HTTP control model (CONTROL_MODE=http). Parses a
     * FULL job-shaped body — including the new self-managed proxy + GPS envelope —
     * and echoes back exactly what it received, the current device state, and the
     * actions it WOULD take. Runs NO LLM flow, starts NO proxy, sets NO GPS.
     * Lets the Mac prove the stateless per-request control path on one phone
     * before the real self-management code lands. type:"noop".
     */
    private fun handleNoopSession(writer: OutputStreamWriter, json: JSONObject) {
        val platform = json.optString("platform", "")
        val keyword = json.optString("keyword", "").let { if (it == "null") "" else it }
        val prompt = json.optString("prompt", "").let { if (it == "null") "" else it }

        // New control-model envelope (forward-compat with the self-managed path).
        val proxyIn = json.optJSONObject("proxy")
        val gpsIn = json.optJSONObject("gps")
        // Accept a nested gps{} object OR flat lat/lng (latitude/longitude) fields.
        val lat = gpsIn?.opt("lat") ?: gpsIn?.opt("latitude")
            ?: json.opt("lat") ?: json.opt("latitude")
        val lng = gpsIn?.opt("lng") ?: gpsIn?.opt("longitude")
            ?: json.opt("lng") ?: json.opt("longitude")

        Log.d(
            "DeviceAgent",
            "NOOP dry-run: platform=$platform kw=${keyword.take(40)} " +
                "proxy=${proxyIn?.optString("host")}:${proxyIn?.optInt("port")} gps=$lat,$lng"
        )

        val wouldStartProxy = proxyIn?.let {
            JSONObject().apply {
                put("host", it.optString("host", ""))
                put("port", it.optInt("port", 0))
                put("mode", it.optString("mode", "gost"))
                put("zip", it.optString("zip", ""))
                put("username", it.optString("username", ""))
            }
        }
        val wouldSetGps = if (lat != null && lng != null) {
            JSONObject().apply { put("lat", lat); put("lng", lng) }
        } else null

        val tun = readTunInterface()
        val response = JSONObject().apply {
            put("status", "ok")
            put("type", "noop")
            put("dry_run", true)
            put("ts", System.currentTimeMillis())
            put("device", JSONObject().apply {
                put("version", APP_VERSION_NAME)
                put("versionCode", APP_VERSION_CODE)
                put("wifiIp", currentWifiIp() ?: "")
                put("accessibility", AgentAccessibilityService.instance != null)
                put("tun0_up", tun.first)
                put("tun0_addr", tun.second ?: "")
            })
            put("received", JSONObject().apply {
                put("platform", platform)
                put("keyword", keyword)
                put("prompt", prompt)
                put("proxy", proxyIn ?: JSONObject.NULL)
                put("gps", gpsIn ?: JSONObject.NULL)
                put("raw_keys", org.json.JSONArray(json.keys().asSequence().toList()))
            })
            put("would_do", JSONObject().apply {
                put("start_proxy", wouldStartProxy ?: JSONObject.NULL)
                put("set_gps", wouldSetGps ?: JSONObject.NULL)
                put("verify_egress", proxyIn != null)
                put("run_platform", platform)
                put("run_keyword", keyword)
            })
        }
        respond(writer, 200, response.toString())
    }

    private fun handleDailySession(writer: OutputStreamWriter, json: JSONObject) {
        val platform = json.optString("platform", "gemini")
        val prompt = json.optString("prompt", "").let { if (it == "null") "" else it }
        val followUp = json.optString("followUp", "").let { if (it.isBlank() || it == "null") null else it }
        val backlinkDomain = json.optString("backlinkDomain", "").let { if (it.isBlank()) null else it }

        if (prompt.isBlank()) {
            respond(writer, 400, """{"error":"prompt is required"}""")
            return
        }

        Log.d("DeviceAgent", "Daily: $platform prompt=${prompt.take(50)}... backlink=$backlinkDomain")

        val result = SessionResult(
            platform = platform,
            status = "running",
            prompt = prompt,
            backlinkDomain = backlinkDomain,
            type = "daily"
        )
        lastResult.set(result)

        executeSession(result, platform, prompt, followUp, backlinkDomain)

        val response = JSONObject().apply {
            put("status", result.status)
            put("type", "daily")
            put("platform", result.platform)
            put("backlink_clicked", result.backlinkClicked)
            put("backlink_domain", result.backlinkDomain ?: "")
            put("error", result.error ?: "")
            put("steps", result.steps.size)
            put("step_log", org.json.JSONArray(result.steps))
        }
        // Always 200 — caller inspects per-platform status in the JSON body.
        // Returning 500 made urllib.urlopen raise and discard the body.
        respond(writer, 200, response.toString())
    }

    private fun handleAuditSession(writer: OutputStreamWriter, json: JSONObject) {
        val bizName = json.optString("bizName", "")
        val bizUrl = json.optString("bizUrl", "")
        val city = json.optString("city", "")
        val state = json.optString("state", "")
        val keyword = json.optString("keyword", "")

        if (bizName.isBlank() || bizUrl.isBlank() || city.isBlank() || state.isBlank() || keyword.isBlank()) {
            respond(writer, 400, """{"error":"bizName, bizUrl, city, state, keyword are required for audit"}""")
            return
        }

        Log.d("DeviceAgent", "Audit: $bizName ($bizUrl) | $keyword in $city, $state")

        val result = SessionResult(
            platform = "all",
            status = "running",
            type = "audit"
        )
        lastResult.set(result)

        val platformFilter = json.optString("platform", "").let { if (it.isBlank()) null else it }
        executeAuditSession(result, bizName, bizUrl, city, state, keyword, platformFilter)

        val response = JSONObject().apply {
            put("status", result.status)
            put("type", "audit")
            put("prompt", result.prompt)
            put("ranking_position", result.rankingPosition ?: 0)
            put("ranking_total", result.rankingTotal ?: "")
            put("error", result.error ?: "")
            put("proxy_ip", result.proxyIp ?: "")
            put("steps", result.steps.size)
            put("step_log", org.json.JSONArray(result.steps))
            val platformsJson = JSONObject()
            for ((name, pr) in result.platforms) {
                val pj = JSONObject().apply {
                    put("status", pr.status)
                    put("ranking_position", pr.rankingPosition ?: 0)
                    put("ranking_total", pr.rankingTotal ?: "")
                    put("screenshot_path", pr.screenshotPath ?: "")
                    // Base64 PNG bytes — Mac decodes + writes locally; saves an adb pull.
                    put("screenshot_b64", pr.screenshotB64 ?: "")
                    put("response_text", pr.responseText ?: "")
                    put("error", pr.error ?: "")
                }
                platformsJson.put(name, pj)
            }
            put("platforms", platformsJson)
        }
        // Always 200 — caller inspects per-platform status in the JSON body.
        // Returning 500 made urllib.urlopen raise and discard the body.
        respond(writer, 200, response.toString())
    }

    /** Normalize a location string to uule's canonical "City,State,United States".
     *  "San Francisco, California" → "San Francisco,California,United States".
     *  Already-canonical or empty strings pass through. */
    private fun canonicalizeLocation(raw: String): String {
        val s = raw.trim()
        if (s.isBlank()) return ""
        if (s.contains("United States", ignoreCase = true)) {
            return s.split(",").joinToString(",") { it.trim() }
        }
        val parts = s.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        if (parts.isEmpty()) return ""
        return (parts + "United States").joinToString(",")
    }

    private fun handleSeoSession(writer: OutputStreamWriter, json: JSONObject) {
        val keyword = json.optString("keyword", "").let { if (it == "null") "" else it }
        val targetDomain = json.optString("targetDomain", "")
            .ifBlank { json.optString("bizUrl", "") }
            .let { if (it.isBlank() || it == "null") null else it }
        // Optional location → uule. Accept "City, State" or a full canonical
        // "City,State,United States"; normalize to the canonical form.
        val location = canonicalizeLocation(
            json.optString("location", "").let { if (it == "null") "" else it }
        )

        if (keyword.isBlank()) {
            respond(writer, 400, """{"error":"keyword is required for seo"}""")
            return
        }

        Log.d("DeviceAgent", "SEO: \"$keyword\" target=$targetDomain loc=\"$location\"")

        val result = SessionResult(platform = "google", status = "running", type = "seo")
        lastResult.set(result)

        executeGoogleSerpStatic(result, flowEngine, keyword, targetDomain, location)

        val serp = result.serp
        val response = JSONObject().apply {
            put("status", result.status)
            put("type", "seo")
            put("keyword", keyword)
            put("challenge", result.challenge)
            put("error", result.error ?: "")
            put("steps", result.steps.size)
            put("step_log", org.json.JSONArray(result.steps))
            put("screenshot_path", result.screenshotPath ?: "")
            put("screenshot_b64", result.screenshotB64 ?: "")
            put("screenshot_local_b64", result.screenshotLocalB64 ?: "")
            put("screenshot_organic_b64", result.screenshotOrganicB64 ?: "")
            put("screenshot_local_path", result.screenshotLocalPath ?: "")
            put("screenshot_organic_path", result.screenshotOrganicPath ?: "")
            put("serp", serpToJson(serp))
        }
        respond(writer, 200, response.toString())
    }

    private fun serpToJson(serp: SerpData?): JSONObject {
        val obj = JSONObject()
        if (serp == null) {
            obj.put("organic", org.json.JSONArray())
            obj.put("local_pack", org.json.JSONArray())
            obj.put("ads_excluded", 0)
            return obj
        }
        val organic = org.json.JSONArray()
        for (r in serp.organic) {
            organic.put(JSONObject().apply {
                put("position", r.position)
                put("title", r.title)
                put("domain", r.domain)
                put("url", r.url)
                put("source", r.site ?: "")
                put("snippet", r.snippet ?: "")
                put("displayed_link", r.displayedLink ?: "")
            })
        }
        val local = org.json.JSONArray()
        for (r in serp.local) {
            local.put(JSONObject().apply {
                put("position", r.position)
                put("name", r.name)
                put("rating", r.rating ?: "")
                put("sponsored", r.sponsored)
                put("reviews", r.reviews ?: JSONObject.NULL)
                put("reviews_original", r.reviewsOriginal ?: "")
                put("price", r.price ?: "")
                put("type", r.type ?: "")
                put("address", r.address ?: "")
                put("description", r.description ?: "")
            })
        }
        obj.put("organic", organic)
        obj.put("local_pack", local)
        obj.put("ads_excluded", serp.adsExcluded)
        obj.put("local_ads_excluded", serp.localAdsExcluded)
        obj.put("location", serp.location ?: "")
        serp.target?.let { t ->
            obj.put("target", JSONObject().apply {
                put("domain", t.domain)
                put("organic_rank", t.organicRank ?: 0)
                put("local_rank", t.localRank ?: 0)
            })
        }
        return obj
    }

    fun executeGoogleSerp(result: SessionResult, keyword: String, targetDomain: String?) {
        executeGoogleSerpStatic(result, flowEngine, keyword, targetDomain)
    }

    fun executeSession(
        result: SessionResult,
        platform: String,
        prompt: String,
        followUp: String?,
        backlinkDomain: String?
    ) {
        executeSessionStatic(result, flowEngine, platform, prompt, followUp, backlinkDomain)
    }

    fun executeAuditSession(
        result: SessionResult,
        bizName: String,
        bizUrl: String,
        city: String,
        state: String,
        keyword: String,
        platformFilter: String? = null
    ) {
        executeAuditSessionStatic(result, flowEngine, bizName, bizUrl, city, state, keyword, platformFilter)
    }

    private fun handleMqttConfig(writer: OutputStreamWriter, body: String) {
        try {
            val json = JSONObject(body)
            val brokerUrl = json.optString("broker_url", "")
            val username = json.optString("username", "")
            val password = json.optString("password", "")
            val heartbeatTopic = json.optString("heartbeat_topic", "device/heartbeat")
            val commandTopic = json.optString("command_topic", "device/command")

            if (brokerUrl.isBlank()) {
                respond(writer, 400, """{"error":"broker_url is required"}""")
                return
            }

            // Save to SharedPreferences via the accessibility service
            val svc = AgentAccessibilityService.instance
            if (svc != null) {
                val prefs = svc.getSharedPreferences("mqtt", android.content.Context.MODE_PRIVATE)
                prefs.edit()
                    .putString("broker_url", brokerUrl)
                    .putString("username", username)
                    .putString("password", password)
                    .putString("heartbeat_topic", heartbeatTopic)
                    .putString("command_topic", commandTopic)
                    .apply()

                // Restart MQTT
                AgentAccessibilityService.mqttManager?.stop()
                svc.startMqttIfConfiguredPublic()

                respond(writer, 200, """{"status":"ok","message":"MQTT configured and connecting"}""")
            } else {
                respond(writer, 503, """{"error":"accessibility service not running"}""")
            }
        } catch (e: Exception) {
            respond(writer, 400, """{"error":"${e.message?.replace("\"", "'")}"}""")
        }
    }

    private fun handleStatus(writer: OutputStreamWriter) {
        val result = lastResult.get()
        if (result == null) {
            respond(writer, 200, """{"status":"idle"}""")
            return
        }
        val json = JSONObject().apply {
            put("status", result.status)
            put("type", result.type)
            put("platform", result.platform)
            put("backlink_clicked", result.backlinkClicked)
            put("backlink_domain", result.backlinkDomain ?: "")
            put("error", result.error ?: "")
            put("steps", result.steps.joinToString(" | "))
            if (result.type == "audit") {
                put("ranking_position", result.rankingPosition ?: 0)
                put("ranking_total", result.rankingTotal ?: "")
                val platformsJson = JSONObject()
                for ((name, pr) in result.platforms) {
                    val pj = JSONObject().apply {
                        put("status", pr.status)
                        put("ranking_position", pr.rankingPosition ?: 0)
                        put("ranking_total", pr.rankingTotal ?: "")
                        put("error", pr.error ?: "")
                    }
                    platformsJson.put(name, pj)
                }
                put("platforms", platformsJson)
            }
        }
        respond(writer, 200, json.toString())
    }

    private fun handleHealth(writer: OutputStreamWriter) {
        // Phase 1 endpoint: report enough state for the Mac to decide whether to
        // dispatch to this phone without falling back to `adb devices` / `adb shell`.
        val wifiIp = currentWifiIp() ?: ""
        val tun = readTunInterface()
        val accessibilityActive = AgentAccessibilityService.instance != null
        val lastStatus = lastResult.get()?.status ?: "idle"

        val json = JSONObject().apply {
            put("ok", true)
            put("version", APP_VERSION_NAME)
            put("versionCode", APP_VERSION_CODE)
            put("wifiIp", wifiIp)
            put("accessibility", accessibilityActive)
            put("lastJobStatus", lastStatus)
            put("uptimeMs", System.currentTimeMillis() - PROCESS_START_MS)
            put("tun0", JSONObject().apply {
                put("up", tun.first)
                put("addr", tun.second ?: "")
            })
        }
        respond(writer, 200, json.toString())
    }

    private fun handleScreenshot(rawOut: OutputStream, writer: OutputStreamWriter, fullPath: String) {
        // GET /screenshot?path=<URL-encoded absolute path on phone>
        // Replaces `adb pull` for the Mac-side consumer when running in direct-WiFi mode.
        val qIdx = fullPath.indexOf('?')
        if (qIdx < 0) { respond(writer, 400, """{"error":"path query param required"}"""); return }
        val query = fullPath.substring(qIdx + 1)
        val pathParam = query.split("&")
            .map { it.split("=", limit = 2) }
            .firstOrNull { it.size == 2 && it[0] == "path" }
            ?.let { java.net.URLDecoder.decode(it[1], "UTF-8") }

        if (pathParam.isNullOrBlank()) {
            respond(writer, 400, """{"error":"path query param required"}""")
            return
        }
        // Path-traversal + allow-list guard. Screenshots live under /sdcard, /storage, or /data/local/tmp.
        if (pathParam.contains("..") ||
            !(pathParam.startsWith("/sdcard/") ||
              pathParam.startsWith("/storage/") ||
              pathParam.startsWith("/data/local/tmp/"))) {
            respond(writer, 403, """{"error":"path not allowed"}""")
            return
        }
        val file = File(pathParam)
        if (!file.exists() || !file.isFile) {
            respond(writer, 404, """{"error":"file not found"}""")
            return
        }
        try {
            val bytes = file.readBytes()
            val header = buildString {
                append("HTTP/1.1 200 OK\r\n")
                append("Content-Type: image/png\r\n")
                append("Content-Length: ${bytes.size}\r\n")
                append("Connection: close\r\n")
                append("\r\n")
            }
            rawOut.write(header.toByteArray(Charsets.UTF_8))
            rawOut.write(bytes)
            rawOut.flush()
        } catch (e: Exception) {
            respond(writer, 500, """{"error":"read failed: ${e.message?.replace("\"", "'")}"}""")
        }
    }

    // Hands-free voice search via acoustic loopback. GET /voice_search?query=<text>[&url=<url>]
    // Speaks the query out the speaker so Google's voice search (Chrome) hears + runs it.
    private fun handleVoiceSearch(writer: OutputStreamWriter, fullPath: String) {
        val svc = AgentAccessibilityService.instance
        if (svc == null) {
            respond(writer, 503, """{"error":"accessibility service not running"}""")
            return
        }
        val query = queryParam(fullPath, "query") ?: queryParam(fullPath, "q") ?: ""
        val url = queryParam(fullPath, "url") ?: "https://www.google.com"
        val engine = queryParam(fullPath, "engine") ?: "chrome"
        if (query.isBlank()) {
            respond(writer, 400, """{"error":"query param required"}""")
            return
        }
        Log.d("DeviceAgent", "VoiceSearch[$engine]: \"$query\"")
        val result = try {
            VoiceSearchFlow.run(svc, query, url, engine)
        } catch (e: Exception) {
            respond(writer, 500, """{"error":"${e.message?.replace("\"", "'")}"}""")
            return
        }
        val json = JSONObject().apply {
            put("status", "ok")
            put("query", query)
            put("result", result)
        }
        respond(writer, 200, json.toString())
    }

    /** Pull a single decoded query-string param from a raw request path. */
    private fun queryParam(fullPath: String, key: String): String? {
        val qIdx = fullPath.indexOf('?')
        if (qIdx < 0) return null
        return fullPath.substring(qIdx + 1).split("&")
            .map { it.split("=", limit = 2) }
            .firstOrNull { it.size == 2 && it[0] == key }
            ?.let { java.net.URLDecoder.decode(it[1], "UTF-8") }
    }

    // ---- HTTP control model: app self-manages the SocksDroid proxy (CONTROL_MODE=http) ----
    // Replaces the Mac's per-job `adb shell am start ... ACTION_START_VPN`. One-time
    // provisioning (VPN consent + `appops set net.typeblog.socks ACTIVATE_VPN allow`)
    // still happens once per phone over ADB — not per run.

    /** Fire SocksDroid's ACTION_START_VPN from inside the app (no per-run ADB). */
    private fun startSocksDroid(
        host: String, port: Int, dns: String, route: String, uname: String, passwd: String
    ): Boolean {
        val ctx = AgentAccessibilityService.instance ?: return false
        return try {
            val intent = Intent("net.typeblog.socks.ACTION_START_VPN").apply {
                component = ComponentName("net.typeblog.socks", "net.typeblog.socks.AdbStartActivity")
                putExtra("SOCKSSERV", host)
                putExtra("SOCKSPORT", port)
                putExtra("SOCKSUNAME", uname)
                putExtra("SOCKSPASSWD", passwd)
                putExtra("SOCKSDNS", dns)
                putExtra("SOCKSROUTE", route)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            ctx.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.e("DeviceAgent", "startSocksDroid failed: ${e.message}")
            false
        }
    }

    /** Fetch the phone's public egress IP THROUGH the tunnel — proves the full chain
     *  (socksdroid -> gost -> Decodo) carries traffic, and returns the residential IP. */
    private fun fetchEgressIp(): String? {
        // ip-api first: most reliable over the Decodo SOCKS chain in testing
        // (returns the bare IP via fields=query). ipify/ifconfig.me as fallbacks.
        for (u in listOf("http://ip-api.com/line/?fields=query", "https://api.ipify.org", "http://ifconfig.me/ip")) {
            try {
                val conn = (java.net.URL(u).openConnection() as java.net.HttpURLConnection).apply {
                    connectTimeout = 6000
                    readTimeout = 6000
                    requestMethod = "GET"
                    setRequestProperty("User-Agent", "curl/8.0")
                }
                val ip = conn.inputStream.bufferedReader().use { it.readText().trim() }
                conn.disconnect()
                if (ip.isNotBlank() && ip.length <= 45 && !ip.contains("<")) return ip
            } catch (_: Exception) { /* try next */ }
        }
        return null
    }

    /** Set the device's mock GPS to lat/lng using LocationManager test providers.
     *  Requires one-time provisioning: `appops set com.deviceagent android:mock_location allow`
     *  + ACCESS_FINE_LOCATION granted. Replaces the old per-job fakegps ADB intent. */
    private fun setMockLocation(lat: Double, lng: Double): Boolean {
        val ctx = AgentAccessibilityService.instance ?: return false
        return try {
            val lm = ctx.getSystemService(android.content.Context.LOCATION_SERVICE)
                as android.location.LocationManager
            var any = false
            for (provider in listOf(
                android.location.LocationManager.GPS_PROVIDER,
                android.location.LocationManager.NETWORK_PROVIDER
            )) {
                try {
                    lm.addTestProvider(
                        provider, false, false, false, false, true, true, true,
                        android.location.Criteria.POWER_LOW, android.location.Criteria.ACCURACY_FINE
                    )
                } catch (_: Exception) { /* may already exist */ }
                try { lm.setTestProviderEnabled(provider, true) } catch (_: Exception) {}
                val loc = android.location.Location(provider).apply {
                    latitude = lat
                    longitude = lng
                    accuracy = 5f
                    time = System.currentTimeMillis()
                    elapsedRealtimeNanos = android.os.SystemClock.elapsedRealtimeNanos()
                    altitude = 10.0
                    bearing = 0f
                    speed = 0f
                }
                try { lm.setTestProviderLocation(provider, loc); any = true }
                catch (e: Exception) { Log.w("DeviceAgent", "setTestProviderLocation($provider): ${e.message}") }
            }
            any
        } catch (e: Exception) {
            Log.e("DeviceAgent", "setMockLocation failed: ${e.message}")
            false
        }
    }

    private fun handleProxyStart(writer: OutputStreamWriter, body: String) {
        val json = try { JSONObject(body) } catch (e: Exception) {
            respond(writer, 400, """{"error":"bad json: ${e.message?.replace("\"", "'")}"}""")
            return
        }
        // Accept a nested proxy{} object OR flat fields.
        val p = json.optJSONObject("proxy") ?: json
        val host = p.optString("host", "")
        val port = p.optInt("port", 0)
        if (host.isBlank() || port <= 0) {
            respond(writer, 400, """{"error":"host and port are required"}""")
            return
        }
        val dns = p.optString("dns", "8.8.8.8")
        // bypass-lan keeps the LAN (192.168/10/172 private ranges) OFF the tunnel so the
        // Mac<->phone HTTP control channel survives while the VPN is up. route:"all" would
        // capture the control socket and make the phone unreachable mid-job (the old ADB
        // daily got away with "all" because its control plane was the ADB transport, not Wi-Fi).
        val route = p.optString("route", "bypass-lan")
        val uname = p.optString("uname", p.optString("username", "anon"))
        val passwd = p.optString("passwd", "anon")

        if (AgentAccessibilityService.instance == null) {
            respond(writer, 503, """{"error":"accessibility/app context not available"}""")
            return
        }

        val t0 = System.currentTimeMillis()
        val started = startSocksDroid(host, port, dns, route, uname, passwd)

        // Poll tun0 up to ~12s (mirror of the Mac's wait_tunnel local check).
        var tunUp = false
        var tunAddr: String? = null
        if (started) {
            for (i in 0 until 12) {
                Thread.sleep(1000)
                val t = readTunInterface()
                if (t.first) { tunUp = true; tunAddr = t.second; break }
            }
        }
        // Egress check proves traffic actually flows through the chain (not just tun0 has an IP).
        val egress = if (tunUp) fetchEgressIp() else null

        val resp = JSONObject().apply {
            put("ok", started && tunUp)
            put("intent_sent", started)
            put("tun0_up", tunUp)
            put("tun0_addr", tunAddr ?: "")
            put("egress_ip", egress ?: "")
            put("proxy", JSONObject().apply {
                put("host", host); put("port", port); put("dns", dns); put("route", route)
            })
            put("took_ms", System.currentTimeMillis() - t0)
        }
        respond(writer, 200, resp.toString())
    }

    /** Best-effort stop. Without root the app can't `pm clear` SocksDroid; we try its
     *  stop action. Re-firing /proxy/start re-points the tunnel for the next job. */
    private fun handleProxyStop(writer: OutputStreamWriter) {
        val ctx = AgentAccessibilityService.instance
        var sent = false
        if (ctx != null) {
            try {
                val intent = Intent("net.typeblog.socks.ACTION_STOP_VPN").apply {
                    component = ComponentName("net.typeblog.socks", "net.typeblog.socks.AdbStartActivity")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                ctx.startActivity(intent)
                sent = true
            } catch (e: Exception) {
                Log.e("DeviceAgent", "stopSocksDroid failed: ${e.message}")
            }
        }
        Thread.sleep(1500)
        val t = readTunInterface()
        respond(writer, 200, JSONObject().apply {
            put("ok", true)
            put("stop_sent", sent)
            put("tun0_up", t.first)
            put("note", "stop is best-effort without root; re-fire /proxy/start to re-point")
        }.toString())
    }

    // ---- INVERTED control plane: phone-pull worker loop (CONTROL_MODE=http) ----
    // The phone drives: register -> poll Mac for a job -> bring its own proxy up ->
    // run -> push result back. All phone-initiated, so it works even while the VPN is
    // up (phone -> gost-on-Mac -> Mac) and a Wi-Fi flap just delays the next poll.

    @Volatile private var workerThread: Thread? = null
    @Volatile private var workerStop = false

    private fun handleAgentStart(writer: OutputStreamWriter, body: String) {
        val json = try { JSONObject(body) } catch (e: Exception) {
            respond(writer, 400, """{"error":"bad json: ${e.message?.replace("\"", "'")}"}"""); return
        }
        val mac = json.optString("mac", "")  // "host:port" of mac_job_server
        if (mac.isBlank()) {
            respond(writer, 400, """{"error":"mac (host:port) is required"}"""); return
        }
        val serial = json.optString("serial", "").ifBlank { currentWifiIp() ?: "unknown" }
        val intervalMs = (json.optDouble("interval_s", 5.0) * 1000).toLong()
        if (workerThread?.isAlive == true) {
            respond(writer, 200, """{"ok":true,"already_running":true}"""); return
        }
        workerStop = false
        workerThread = Thread { runWorkerLoop(mac, serial, intervalMs) }
            .also { it.isDaemon = true; it.start() }
        respond(writer, 200, JSONObject().apply {
            put("ok", true); put("started", true); put("mac", mac); put("serial", serial)
            put("interval_ms", intervalMs)
        }.toString())
    }

    private fun handleAgentStop(writer: OutputStreamWriter) {
        workerStop = true
        respond(writer, 200, """{"ok":true,"stopping":true}""")
    }

    private fun runWorkerLoop(mac: String, serial: String, intervalMs: Long) {
        val base = "http://$mac"
        Log.d("DeviceAgent", "worker start: mac=$mac serial=$serial interval=${intervalMs}ms")
        httpReq("POST", "$base/register", JSONObject().apply {
            put("serial", serial); put("ip", currentWifiIp() ?: ""); put("version", APP_VERSION_NAME)
        }.toString())
        while (!workerStop) {
            try {
                val (code, text) = httpReq("GET", "$base/next-job?serial=$serial", null)
                if (code == 200 && text.isNotBlank()) {
                    val job = JSONObject(text)
                    Log.d("DeviceAgent", "worker job ${job.optString("job_id")} type=${job.optString("type")}")
                    val result = processJob(job).apply {
                        put("serial", serial)
                        put("job_id", job.optString("job_id", ""))
                    }
                    httpReq("POST", "$base/result", result.toString())
                } else {
                    Thread.sleep(intervalMs)
                }
            } catch (e: Exception) {
                Log.e("DeviceAgent", "worker loop error: ${e.message}")
                Thread.sleep(intervalMs)
            }
        }
        Log.d("DeviceAgent", "worker stopped")
    }

    /** Run one job. Brings the proxy up if the job carries one (persistent VPN — no
     *  teardown needed). Real daily/audit/seo flows wire in here later; for now every
     *  type echoes a dry-run result that also proves the proxy chain (egress IP). */
    private fun processJob(job: JSONObject): JSONObject {
        val type = job.optString("type", "noop")
        var tunUp = false
        var egress: String? = null
        var gpsSet = false

        // Mock GPS first so Chrome/Google picks it up on navigation.
        val gps = job.optJSONObject("gps")
        val lat = gps?.optDouble("lat", Double.NaN) ?: job.optDouble("lat", Double.NaN)
        val lng = gps?.optDouble("lng", Double.NaN) ?: job.optDouble("lng", Double.NaN)
        if (!lat.isNaN() && !lng.isNaN()) {
            gpsSet = setMockLocation(lat, lng)
        }

        val proxy = job.optJSONObject("proxy")
        if (proxy != null) {
            val host = proxy.optString("host", "")
            val port = proxy.optInt("port", 0)
            if (host.isNotBlank() && port > 0) {
                startSocksDroid(
                    host, port, proxy.optString("dns", "8.8.8.8"),
                    proxy.optString("route", "all"),
                    proxy.optString("uname", proxy.optString("username", "anon")),
                    proxy.optString("passwd", "anon")
                )
                for (i in 0 until 12) {
                    Thread.sleep(1000)
                    if (readTunInterface().first) { tunUp = true; break }
                }
                if (tunUp) egress = fetchEgressIp()
            }
        }
        // Real SEO / Google SERP flow — drives Chrome through the proxy and
        // captures framed screenshots (proves the whole chain end-to-end).
        if (type == "seo") {
            val keyword = job.optString("keyword", "")
            val targetDomain = job.optString("targetDomain", "")
                .ifBlank { job.optString("bizUrl", "") }
                .let { if (it.isBlank() || it == "null") null else it }
            val result = SessionResult(platform = "google", status = "running", type = "seo")
            lastResult.set(result)
            executeGoogleSerpStatic(result, flowEngine, keyword, targetDomain)
            return JSONObject().apply {
                put("status", result.status)
                put("type", "seo")
                put("keyword", keyword)
                put("tun0_up", tunUp)
                put("egress_ip", egress ?: "")
                put("gps_set", gpsSet)
                put("challenge", result.challenge)
                put("error", result.error ?: "")
                put("steps", result.steps.size)
                put("screenshot_b64", result.screenshotB64 ?: "")
                put("screenshot_local_b64", result.screenshotLocalB64 ?: "")
                put("screenshot_organic_b64", result.screenshotOrganicB64 ?: "")
                put("serp", serpToJson(result.serp))
                put("device_version", APP_VERSION_NAME)
                put("ts", System.currentTimeMillis())
            }
        }

        return JSONObject().apply {
            put("status", "ok")
            put("type", type)
            put("dry_run", true)
            put("tun0_up", tunUp)
            put("egress_ip", egress ?: "")
            put("gps_set", gpsSet)
            put("keyword", job.optString("keyword", ""))
            put("device_version", APP_VERSION_NAME)
            put("wifiIp", currentWifiIp() ?: "")
            put("ts", System.currentTimeMillis())
        }
    }

    private fun httpReq(method: String, urlStr: String, body: String?): Pair<Int, String> {
        return try {
            val conn = (java.net.URL(urlStr).openConnection() as java.net.HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = 8000
                readTimeout = 30000
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                }
            }
            if (body != null) conn.outputStream.use { it.write(body.toByteArray()) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
            conn.disconnect()
            code to text
        } catch (e: Exception) {
            -1 to (e.message ?: "error")
        }
    }

    private fun currentWifiIp(): String? {
        // Prefer wlan0; fall back to first non-loopback IPv4 on a UP interface.
        return try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return null
            var fallback: String? = null
            for (iface in ifaces) {
                if (!iface.isUp || iface.isLoopback) continue
                for (addr in iface.inetAddresses) {
                    if (addr.isLoopbackAddress) continue
                    val host = addr.hostAddress ?: continue
                    if (host.contains(":")) continue  // skip IPv6
                    if (iface.name == "wlan0") return host
                    if (fallback == null) fallback = host
                }
            }
            fallback
        } catch (_: Exception) {
            null
        }
    }

    private fun readTunInterface(): Pair<Boolean, String?> {
        // /proc/net/dev tells us tun0 exists but not its IPv4 — Android blocks
        // ifconfig from non-root. Fall back to NetworkInterface API.
        return try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return false to null
            for (iface in ifaces) {
                if (iface.name != "tun0") continue
                if (!iface.isUp) return false to null
                val addr = iface.inetAddresses.toList()
                    .firstOrNull { !it.isLoopbackAddress && !(it.hostAddress?.contains(":") ?: false) }
                    ?.hostAddress
                return true to addr
            }
            false to null
        } catch (_: Exception) {
            false to null
        }
    }

    private fun respond(writer: OutputStreamWriter, code: Int, body: String) {
        val status = when (code) {
            200 -> "200 OK"
            400 -> "400 Bad Request"
            404 -> "404 Not Found"
            405 -> "405 Method Not Allowed"
            500 -> "500 Internal Server Error"
            else -> "$code"
        }
        val bodyBytes = body.toByteArray(Charsets.UTF_8)
        writer.write("HTTP/1.1 $status\r\n")
        writer.write("Content-Type: application/json; charset=utf-8\r\n")
        writer.write("Content-Length: ${bodyBytes.size}\r\n")
        writer.write("Connection: close\r\n")
        writer.write("\r\n")
        writer.write(body)
    }
}
