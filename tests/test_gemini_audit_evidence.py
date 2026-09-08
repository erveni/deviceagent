"""Run the real pure-Kotlin guards with the locally cached compiler, no downloads."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GeminiAuditEvidenceTests(unittest.TestCase):
    def test_real_kotlin_guards(self):
        cache = Path.home() / '.gradle/caches/modules-2/files-2.1'
        jars = []
        for group, artifact, version in [
            ('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '2.0.21'),
            ('org.jetbrains.kotlin', 'kotlin-stdlib', '2.0.21'),
            ('org.jetbrains.kotlin', 'kotlin-script-runtime', '2.0.21'),
            ('org.jetbrains.kotlin', 'kotlin-reflect', '2.0.21'),
            ('org.jetbrains.intellij.deps', 'trove4j', '*'),
            ('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '*'),
            ('org.jetbrains', 'annotations', '*'),
        ]:
            found = sorted((cache / group / artifact).glob(version + '/*/*.jar'))
            if found:
                jars.append(str(found[-1]))
        if not any('kotlin-compiler-embeddable' in jar for jar in jars):
            self.skipTest('Local Kotlin compiler unavailable; run Gradle build before this test')
        cp = ':'.join(jars)
        # Kotlin 2.0's compiler does not understand the host's Java 25 version.
        java = '/opt/homebrew/opt/openjdk@17/bin/java'
        if not Path(java).exists():
            java = 'java'
        with tempfile.TemporaryDirectory(prefix='gemini-evidence-test-') as tmp:
            compiled = str(Path(tmp) / 'classes')
            result = subprocess.run([
                java, '-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                '-no-stdlib', '-no-reflect', '-classpath', cp, '-d', compiled,
                str(ROOT / 'app/src/main/java/com/deviceagent/GeminiAuditEvidence.kt'),
                str(ROOT / 'tests/GeminiAuditEvidenceCheck.kt'),
            ], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([java, '-cp', compiled + ':' + cp, 'GeminiAuditEvidenceCheckKt'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('18 Gemini audit evidence checks passed', result.stdout)

    def test_audit_reader_includes_deep_offscreen_answer_but_not_other_apps(self):
        source = (ROOT / 'app/src/main/java/com/deviceagent/FlowEngine.kt').read_text()
        reader = source.split('private fun getGeminiAuditPage()', 1)[1].split('fun inputText(', 1)[0]
        self.assertIn('depth > 64', reader)
        self.assertIn('remaining = 4000', reader)
        self.assertIn('cls == "android.webkit.WebView"', reader)
        self.assertIn('root.packageName?.toString() != "com.android.chrome"', reader)
        self.assertNotIn('getBoundsInScreen', reader)
        self.assertIn('finally { child.recycle() }', reader)

    def test_daily_does_not_use_audit_guards(self):
        source = (ROOT / 'app/src/main/java/com/deviceagent/AgentHttpServer.kt').read_text()
        daily = source.split('fun executeSessionStatic(', 1)[1].split('fun executeAuditSessionStatic(', 1)[0]
        for name in ('inputGeminiAudit', 'submitGeminiAudit', 'waitForGeminiAudit'):
            self.assertNotIn(name, daily)
