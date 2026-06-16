package com.deviceagent

import android.inputmethodservice.InputMethodService
import android.view.View

/**
 * Invisible IME used ONLY to inject text through a real [android.view.inputmethod.InputConnection]
 * via [commitText] — the same path a hardware/Gboard keyboard uses. This is the one input method
 * that produces genuine web `input` events; ACTION_SET_TEXT / clipboard-paste / `adb input` do not,
 * and the new logged-out Gemini deletes conversations entered that way.
 *
 * Enable + select for testing with:
 *   adb shell ime enable com.deviceagent/.AgentImeService
 *   adb shell ime set    com.deviceagent/.AgentImeService
 */
class AgentImeService : InputMethodService() {

    override fun onCreate() {
        super.onCreate()
        ImeBridge.register(this)
    }

    override fun onDestroy() {
        ImeBridge.unregister(this)
        super.onDestroy()
    }

    /** No keyboard UI — we only need the InputConnection. */
    override fun onCreateInputView(): View? = null

    fun commit(text: String): Boolean =
        currentInputConnection?.commitText(text, 1) == true

    fun hasConnection(): Boolean = currentInputConnection != null
}

/** Process-global bridge so [FlowEngine] can drive the IME without holding a reference. */
object ImeBridge {
    @Volatile private var ime: AgentImeService? = null

    fun register(service: AgentImeService) { ime = service }
    fun unregister(service: AgentImeService) { if (ime === service) ime = null }

    /** Wait until a field is focused and the IME is bound to it. */
    fun awaitConnection(timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (ime?.hasConnection() == true) return true
            Thread.sleep(100)
        }
        return false
    }

    fun commitText(text: String): Boolean = ime?.commit(text) == true
}
