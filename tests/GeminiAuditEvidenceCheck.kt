import com.deviceagent.GeminiAuditEvidence as E

fun main() {
    val prompt = "You said\nTop 3 businesses. Example [RANK: 4/4]\nGemini said\n"
    val answer = "1. First shop\n2. Second shop\n3. Third shop\nTarget is outside the top three.\n[RANK: 4/4]"
    check(E.answer(prompt + "Connecting to Google Maps") == null)
    check(E.answer("Example [RANK: 4/4]") == null)
    check(E.answer(prompt + "Gemini is AI and can make mistakes.") == null)
    check(E.answer(prompt + answer) == answer)
    check(E.answer(prompt + answer + "\nGemini is AI and can make mistakes.\nAsk Gemini") == answer)
    check(E.answer(prompt + answer.replace("4/4", "5/4")) == null)
    check(E.answer(prompt + answer.replace("4/4", "0/4")) == null)
    check(E.answer(prompt + answer + "\n[RANK: 2/3]") == null)
    check(E.answer(prompt + answer + "\nstill streaming") == null)
    check(E.answer(prompt + answer.replace("3. Third shop\n", "")) == null)
    check(E.answer(prompt + answer + "\nGemini said\n" + answer) == null)
    // Actual Chrome accessibility exposes CSS list markers as separate nodes.
    check(E.answer(prompt + answer.replace("1. First", "1.\nFirst").replace("2. Second", "2.\nSecond").replace("3. Third", "3.\nThird")) != null)
    check(E.promptMatches("whole prompt", "whole prompt"))
    check(E.promptMatches("whole\n prompt", "whole prompt"))
    check(!E.promptMatches("whole", "whole prompt"))
    check(!E.promptMatches("whole prompt whole prompt", "whole prompt"))
    check(!E.promptMatches("Ask Gemini", "whole prompt"))
    check(!E.promptMatches("", ""))
    println("18 Gemini audit evidence checks passed")
}
