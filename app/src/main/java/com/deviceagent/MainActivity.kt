package com.deviceagent

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.text.method.ScrollingMovementMethod
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.app.Activity

class MainActivity : Activity() {

    private lateinit var logView: TextView
    private lateinit var statusText: TextView
    private lateinit var promptInput: EditText
    private var flowEngine: FlowEngine? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        logView = findViewById(R.id.log_text)
        logView.movementMethod = ScrollingMovementMethod()
        statusText = findViewById(R.id.status_text)
        promptInput = findViewById(R.id.prompt_input)

        // wire up logging
        AgentAccessibilityService.onLog = { msg ->
            runOnUiThread {
                appendLog(msg)
            }
        }

        findViewById<Button>(R.id.btn_open_accessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            appendLog("Opened accessibility settings - enable DeviceAgent")
        }

        findViewById<Button>(R.id.btn_reset_chrome).setOnClickListener {
            runFlow("Reset Chrome") { resetChrome() }
        }

        findViewById<Button>(R.id.btn_dismiss_fre).setOnClickListener {
            runFlow("Dismiss FRE") { dismissChromeFre() }
        }

        findViewById<Button>(R.id.btn_nav_gemini).setOnClickListener {
            runFlow("Nav Gemini") { navigateTo("gemini") }
        }

        findViewById<Button>(R.id.btn_nav_chatgpt).setOnClickListener {
            runFlow("Nav ChatGPT") { navigateTo("chatgpt") }
        }

        findViewById<Button>(R.id.btn_nav_perplexity).setOnClickListener {
            runFlow("Nav Perplexity") { navigateTo("perplexity") }
        }

        findViewById<Button>(R.id.btn_input_text).setOnClickListener {
            val text = promptInput.text.toString()
            runFlow("Input") { inputText(text) }
        }

        findViewById<Button>(R.id.btn_submit).setOnClickListener {
            runFlow("Submit") { submit() }
        }

        findViewById<Button>(R.id.btn_scroll).setOnClickListener {
            runFlow("Scroll") { scrollResponse(6) }
        }

        findViewById<Button>(R.id.btn_follow_up).setOnClickListener {
            val followUp = findViewById<EditText>(R.id.followup_input).text.toString()
            if (followUp.isBlank()) {
                appendLog("ERROR: Enter a follow-up text first")
                return@setOnClickListener
            }
            runFlow("Follow-Up") { sendFollowUp(followUp) }
        }

        findViewById<Button>(R.id.btn_backlink).setOnClickListener {
            val domain = findViewById<EditText>(R.id.backlink_input).text.toString()
            if (domain.isBlank()) {
                appendLog("ERROR: Enter a backlink domain first")
                return@setOnClickListener
            }
            runFlow("Backlink") { clickBacklink(domain) }
        }

        findViewById<Button>(R.id.btn_go_back).setOnClickListener {
            runFlow("Go Back") { goBack() }
        }

        findViewById<Button>(R.id.btn_full_test).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running! Open accessibility settings first.")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString()
            statusText.text = "Running full flow..."
            val engine = FlowEngine(svc)
            engine.fullGeminiFlow(prompt) { status ->
                runOnUiThread {
                    appendLog(status)
                    statusText.text = status
                }
            }
        }

        findViewById<Button>(R.id.btn_daily_session).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running! Open accessibility settings first.")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString()
            val followUp = findViewById<EditText>(R.id.followup_input).text.toString().trim()
            val backlink = findViewById<EditText>(R.id.backlink_input).text.toString().trim()
            statusText.text = "Running daily session..."
            val engine = FlowEngine(svc)
            engine.fullDailySession(
                platform = "gemini",
                prompt = prompt,
                followUp = followUp.ifBlank { null },
                backlinkDomain = backlink.ifBlank { null }
            ) { status ->
                runOnUiThread {
                    appendLog(status)
                    statusText.text = status
                }
            }
        }

        findViewById<Button>(R.id.btn_perplexity_step).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running! Open accessibility settings first.")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString().ifBlank { "bilingual childcare San Francisco" }
            val followUp = findViewById<EditText>(R.id.followup_input).text.toString().trim()
            val backlink = findViewById<EditText>(R.id.backlink_input).text.toString().trim()
            statusText.text = "Perplexity step-by-step..."
            val engine = FlowEngine(svc)
            perplexityStepByStep(engine, svc, prompt, followUp.ifBlank { null }, backlink.ifBlank { null })
        }

        findViewById<Button>(R.id.btn_perplexity_input_only).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running!")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString().ifBlank { "bilingual childcare San Francisco" }
            val backlink = findViewById<EditText>(R.id.backlink_input).text.toString().trim()
            statusText.text = "Perplexity: test flow..."
            val engine = FlowEngine(svc)
            runDebugFlow(engine, svc, "perplexity", prompt, backlink.ifBlank { null })
        }

        findViewById<Button>(R.id.btn_chatgpt_test).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running!")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString().ifBlank { "bilingual childcare San Francisco" }
            val backlink = findViewById<EditText>(R.id.backlink_input).text.toString().trim()
            statusText.text = "ChatGPT: test flow..."
            val engine = FlowEngine(svc)
            runDebugFlow(engine, svc, "chatgpt", prompt, backlink.ifBlank { null })
        }

        findViewById<Button>(R.id.btn_gemini_test).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running!")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString().ifBlank { "bilingual childcare San Francisco" }
            val backlink = findViewById<EditText>(R.id.backlink_input).text.toString().trim()
            statusText.text = "Gemini: test flow..."
            val engine = FlowEngine(svc)
            runDebugFlow(engine, svc, "gemini", prompt, backlink.ifBlank { null })
        }

        findViewById<Button>(R.id.btn_all_three).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running!")
                return@setOnClickListener
            }
            val prompt = promptInput.text.toString().ifBlank { "bilingual childcare San Francisco" }
            val backlink = findViewById<EditText>(R.id.backlink_input).text.toString().trim()
            statusText.text = "Running ALL 3 platforms..."
            val engine = FlowEngine(svc)
            runAllThree(engine, svc, prompt, backlink.ifBlank { null })
        }

        findViewById<Button>(R.id.btn_screenshot).setOnClickListener {
            val svc = AgentAccessibilityService.instance
            if (svc == null) {
                appendLog("ERROR: Service not running!")
                return@setOnClickListener
            }
            Thread {
                val path = svc.saveScreenshot("manual_${System.currentTimeMillis()}")
                runOnUiThread {
                    if (path != null) {
                        appendLog("Screenshot saved: $path")
                    } else {
                        appendLog("ERROR: Screenshot failed")
                    }
                }
            }.start()
        }
    }

    private fun runFlow(name: String, block: FlowEngine.() -> Boolean) {
        val svc = AgentAccessibilityService.instance
        if (svc == null) {
            appendLog("ERROR: Service not running! Open accessibility settings first.")
            return
        }
        val engine = FlowEngine(svc)
        statusText.text = "Running: $name"
        Thread {
            try {
                val ok = engine.block()
                val result = if (ok) "OK" else "FAILED"
                runOnUiThread {
                    appendLog("[$name] $result")
                    statusText.text = "$name: $result"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    appendLog("[$name] ERROR: ${e.message}")
                    statusText.text = "$name: ERROR"
                }
            }
        }.start()
    }

    private fun appendLog(msg: String) {
        val timestamp = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
            .format(java.util.Date())
        logView.append("[$timestamp] $msg\n")
        // keep last 100 lines
        val lines = logView.text.split("\n")
        if (lines.size > 100) {
            logView.text = lines.takeLast(100).joinToString("\n")
        }
    }

    /** Debug flow for any platform with backlink */
    private fun runDebugFlow(
        engine: FlowEngine,
        svc: AgentAccessibilityService,
        platform: String,
        prompt: String,
        backlinkDomain: String?
    ) {
        Thread {
            fun step(name: String, block: () -> Boolean) {
                runOnUiThread { appendLog("→ $name..."); statusText.text = name }
                val ok = block()
                runOnUiThread { appendLog("→ $name: ${if (ok) "OK" else "FAILED"}") }
            }
            try {
                step("Reset Chrome") { engine.resetChrome() }
                Thread.sleep(500)

                step("Navigate $platform") { engine.navigateTo(platform) }
                Thread.sleep(if (platform == "chatgpt") 6000L else 3000L)

                step("Dismiss popups") { engine.dismissPlatformPopups(platform); true }
                Thread.sleep(500)

                step("Input prompt") { engine.inputText(prompt) }
                Thread.sleep(300)

                step("Submit") { engine.submit() }
                Thread.sleep(2000)

                step("Wait generation") { engine.waitForGeneration(timeoutSec = 120) }

                step("Scroll") { engine.scrollResponse(12) }

                if (!backlinkDomain.isNullOrBlank()) {
                    step("Click backlink ($backlinkDomain)") { engine.clickBacklink(backlinkDomain, platform) }
                }

                runOnUiThread {
                    appendLog("── $platform FLOW DONE ──")
                    statusText.text = "$platform: all done"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    appendLog("ERROR: ${e.message}")
                    statusText.text = "ERROR"
                }
            }
        }.start()
    }

    /** Run all 3 platforms sequentially */
    private fun runAllThree(
        engine: FlowEngine,
        svc: AgentAccessibilityService,
        prompt: String,
        backlinkDomain: String?
    ) {
        Thread {
            val platforms = listOf("gemini", "chatgpt", "perplexity")
            for ((index, platform) in platforms.withIndex()) {
                runOnUiThread {
                    appendLog("")
                    appendLog("══════════════════════════════════")
                    appendLog("PLATFORM ${index + 1}/3: ${platform.uppercase()}")
                    appendLog("══════════════════════════════════")
                    statusText.text = "[${index + 1}/3] $platform: starting..."
                }
                try {
                    runDebugFlowOnThread(engine, platform, prompt, backlinkDomain)
                } catch (e: Exception) {
                    runOnUiThread { appendLog("$platform FATAL: ${e.message}") }
                }
                if (index < 2) {
                    runOnUiThread { appendLog("Waiting before next platform...") }
                    Thread.sleep(3000)
                }
            }
            runOnUiThread {
                appendLog("")
                appendLog("══════════════════════════════════")
                appendLog("ALL 3 PLATFORMS DONE")
                appendLog("══════════════════════════════════")
                statusText.text = "ALL 3 DONE"
            }
        }.start()
    }

    /** Run debug flow on the current thread (called from background thread) */
    private fun runDebugFlowOnThread(
        engine: FlowEngine,
        platform: String,
        prompt: String,
        backlinkDomain: String?
    ) {
        fun step(name: String, block: () -> Boolean) {
            runOnUiThread { appendLog("→ $name..."); statusText.text = "$platform: $name" }
            val ok = block()
            runOnUiThread { appendLog("→ $name: ${if (ok) "OK" else "FAILED"}") }
        }
        step("Reset Chrome") { engine.resetChrome() }
        Thread.sleep(500)

        step("Navigate $platform") { engine.navigateTo(platform) }
        Thread.sleep(if (platform == "chatgpt") 6000L else 3000L)

        step("Dismiss popups") { engine.dismissPlatformPopups(platform); true }
        Thread.sleep(500)

        step("Input prompt") { engine.inputText(prompt) }
        Thread.sleep(300)

        step("Submit") { engine.submit() }
        Thread.sleep(2000)

        step("Wait generation") { engine.waitForGeneration(timeoutSec = 120) }

        step("Scroll") { engine.scrollResponse(12) }

        if (!backlinkDomain.isNullOrBlank()) {
            step("Click backlink ($backlinkDomain)") { engine.clickBacklink(backlinkDomain, platform) }
        }
    }

    /** Old Perplexity-only method kept for the step-by-step button */
    private fun perplexityStopAfterInput(
        engine: FlowEngine,
        svc: AgentAccessibilityService,
        prompt: String
    ) {
        runDebugFlow(engine, svc, "perplexity", prompt, "maeschildcare.com")
    }

    /** Step-by-step Perplexity flow with screenshot after each step */
    private fun perplexityStepByStep(
        engine: FlowEngine,
        svc: AgentAccessibilityService,
        prompt: String,
        followUp: String?,
        backlinkDomain: String?
    ) {
        Thread {
            fun step(name: String, screenshotName: String, block: () -> Boolean) {
                runOnUiThread {
                    appendLog("━━━ STEP: $name ━━━")
                    statusText.text = "Step: $name"
                }
                val ok = try {
                    block()
                } catch (e: Exception) {
                    runOnUiThread { appendLog("ERROR: ${e.message}") }
                    false
                }
                val result = if (ok) "OK" else "FAILED"
                // Take screenshot
                val ssPath = svc.saveScreenshot(screenshotName)
                runOnUiThread {
                    appendLog("[$name] $result | Screenshot: ${ssPath ?: "FAILED"}")
                    statusText.text = "$name: $result"
                }
            }

            try {
                // Step 1: Reset Chrome
                step("01_ResetChrome", "01_reset_chrome") {
                    engine.resetChrome()
                }
                Thread.sleep(500)

                // Step 2: Navigate to Perplexity
                step("02_NavigatePerplexity", "02_navigate_perplexity") {
                    engine.navigateTo("perplexity")
                }
                Thread.sleep(3000)

                // Step 3: Dismiss popups (Comet, Cookie, Sign-in)
                step("03_DismissPopups", "03_dismiss_popups") {
                    engine.dismissPlatformPopups("perplexity")
                    true
                }
                Thread.sleep(1000)

                // Step 4: Input prompt
                step("04_InputPrompt", "04_input_prompt") {
                    engine.inputText(prompt)
                }
                Thread.sleep(500)

                // Step 5: Submit
                step("05_Submit", "05_submitted") {
                    engine.submit()
                }
                Thread.sleep(2000)

                // Step 6: Wait for generation
                step("06_WaitGeneration", "06_generation") {
                    engine.waitForGeneration(timeoutSec = 120)
                }

                // Step 7: Scroll
                step("07_Scroll", "07_scrolled") {
                    engine.scrollResponse(6)
                }
                Thread.sleep(1000)

                // Step 8: Follow-up (optional)
                if (!followUp.isNullOrBlank()) {
                    step("08_FollowUp", "08_followup") {
                        engine.sendFollowUp(followUp)
                    }
                }

                // Step 9: Backlink (optional)
                if (!backlinkDomain.isNullOrBlank()) {
                    step("09_Backlink", "09_backlink") {
                        engine.clickBacklink(backlinkDomain, "perplexity")
                    }
                }

                runOnUiThread {
                    appendLog("━━━ PERPLEXITY STEP-BY-STEP DONE ━━━")
                    appendLog("Check screenshots in: ${svc.getExternalFilesDir(null)}/screenshots/")
                    statusText.text = "Perplexity: All steps done"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    appendLog("FATAL: ${e.message}")
                    statusText.text = "Perplexity: FATAL ERROR"
                }
            }
        }.start()
    }
}
