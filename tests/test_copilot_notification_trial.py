"""Exercise the test-only post-reset hook without importing fleet side effects."""
import ast
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import urllib.error

TREE=ast.parse((Path(__file__).resolve().parents[1]/'audit_dispatch_http.py').read_text())


class NotificationTrialTests(unittest.TestCase):
    def test_hook_runs_once_and_only_after_native_reset(self):
        callback=next(n for n in ast.walk(TREE) if isinstance(n,ast.FunctionDef) and n.name=='deny_after_native_reset')
        factory=ast.FunctionDef(name='factory',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
            body=[ast.parse('notification_applied_after_reset=False').body[0],callback,
                  ast.Return(value=ast.Name(id='deny_after_native_reset',ctx=ast.Load()))],decorator_list=[])
        adb=Mock(return_value=SimpleNamespace(returncode=0,stdout='android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_SET|USER_FIXED]'))
        namespace=dict(_adb=adb,re=re,serial='test',print=lambda *a,**k:None)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[factory],type_ignores=[])),'hook-only','exec'),namespace)
        hook=namespace['factory']()
        hook({'step_log':[]});self.assertEqual(adb.call_count,0)
        progress={'step_log':['[copilot] reset_edge OK 42s (total 42s)']}
        hook(progress);self.assertEqual(adb.call_count,2)
        hook(progress);self.assertEqual(adb.call_count,2)
        self.assertIn('set-permission-flags',adb.call_args_list[0].args)

    def test_async_hook_observes_progress_not_final_result(self):
        function=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='_post_audit_async')
        replies=iter([{'async':True},{'running':True,'step_log':['reset']},{'running':False,'status':'complete'}])
        request=SimpleNamespace(Request=lambda *a,**k:None,urlopen=lambda *a,**k:io.BytesIO(json.dumps(next(replies)).encode()))
        namespace=dict(json=json,urllib=SimpleNamespace(request=request,error=urllib.error),
            time=SimpleNamespace(time=lambda:0,sleep=lambda n:None),_http_timeout_for=lambda p:30,_POLL_EVERY_S=2)
        exec(compile(ast.Module(body=[function],type_ignores=[]),'poll-only','exec'),namespace)
        callback=Mock()
        result=namespace['_post_audit_async'](8765,{'platform':'copilot'},progress_callback=callback)
        self.assertEqual(result,{'status':'complete'})
        callback.assert_called_once_with({'running':True,'step_log':['reset']})


if __name__=='__main__':unittest.main()
