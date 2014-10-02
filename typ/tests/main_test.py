# Copyright 2014 Dirk Pranke. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import os
import StringIO
import sys

from typ import main
from typ import test_case
from typ.host import Host
from typ.version import VERSION
from typ.fakes.unittest_fakes import FakeTestLoader


PASSING_TEST = """
import unittest
class PassingTest(unittest.TestCase):
    def test_pass(self):
        pass
"""


FAILING_TEST = """
import unittest
class FailingTest(unittest.TestCase):
    def test_fail(self):
        self.fail()
"""


OUTPUT_TESTS = """
import sys
import unittest

class PassTest(unittest.TestCase):
  def test_out(self):
    sys.stdout.write("hello on stdout\\n")
    sys.stdout.flush()

  def test_err(self):
    sys.stderr.write("hello on stderr\\n")

class FailTest(unittest.TestCase):
 def test_out_err_fail(self):
    sys.stdout.write("hello on stdout\\n")
    sys.stdout.flush()
    sys.stderr.write("hello on stderr\\n")
    self.fail()
"""


SKIPS_AND_FAILURES = """
import sys
import unittest

class SkipMethods(unittest.TestCase):
    @unittest.skip('reason')
    def test_reason(self):
        self.fail()

    @unittest.skipIf(True, 'reason')
    def test_skip_if_true(self):
        self.fail()

    @unittest.skipIf(False, 'reason')
    def test_skip_if_false(self):
        self.fail()


class SkipSetup(unittest.TestCase):
    def setUp(self):
        self.skipTest('setup failed')

    def test_notrun(self):
        self.fail()


@unittest.skip('skip class')
class SkipClass(unittest.TestCase):
    def test_method(self):
        self.fail()

class SetupClass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.stdout.write('in setupClass\n')
        sys.stdout.flush()
        assert False, 'setupClass failed'

    def test_method1(self):
        pass

    def test_method2(self):
        pass

class ExpectedFailures(unittest.TestCase):
    @unittest.expectedFailure
    def test_fail(self):
        self.fail()

    @unittest.expectedFailure
    def test_pass(self):
        pass
"""

SETUP_AND_TEARDOWN = """
import unittest
from typ import test_case as typ_test_case

def setupProcess(child, context):
    if context is None:
        context = {'passed_in': False, 'calls': 0}
    child.host.print_('setupProcess(%d): %s' % (child.worker_num, context))
    context['calls'] += 1
    return context


def teardownProcess(child, context):
    child.host.print_('teardownProcess(%d): %s' % (child.worker_num, context))


class UnitTest(unittest.TestCase):
    def test_one(self):
        self.assertFalse(hasattr(self, 'host'))
        self.assertFalse(hasattr(self, 'context'))

    def test_two(self):
        pass


class TypTest(typ_test_case.TestCase):
    def test_one(self):
        self.assertNotEquals(self.child, None)
        self.assertGreaterEqual(self.context['calls'], 1)
        self.context['calls'] += 1

    def test_two(self):
        self.assertNotEquals(self.context, None)
        self.assertGreaterEqual(self.context['calls'], 1)
        self.context['calls'] += 1
"""


LOAD_TESTS = """
import unittest
def load_tests(_, _2, _3):
    class BaseTest(unittest.TestCase):
        pass

    def method_fail(self):
        self.fail()

    def method_pass(self):
        pass

    setattr(BaseTest, "test_fail", method_fail)
    setattr(BaseTest, "test_pass", method_pass)
    suite = unittest.TestSuite()
    suite.addTest(BaseTest("test_fail"))
    suite.addTest(BaseTest("test_pass"))
    return suite
"""


path_to_main = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')

class TestCli(test_case.MainTestCase):
    prog = [sys.executable, path_to_main]

    def test_bad_arg(self):
        self.check(['--bad-arg'], ret=2)
        self.check(['-help'], ret=2)

    def test_bad_metadata(self):
        self.check(['--metadata', 'foo'], ret=2)

    def test_dryrun(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-n'], files=files, ret=0)

    def test_fail(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check([], files=files, ret=1)

    def test_file_list(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-f', '-'], files=files, stdin='pass_test\n', ret=0)
        self.check(['-f', '-'], files=files, stdin='pass_test.PassingTest\n',
                   ret=0)
        self.check(['-f', '-'], files=files,
                   stdin='pass_test.PassingTest.test_pass\n',
                   ret=0)
        files = {'pass_test.py': PASSING_TEST,
                 'test_list.txt': 'pass_test.PassingTest.test_pass\n'}
        self.check(['-f', 'test_list.txt'], files=files, ret=0)

    def test_find(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-l'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.py'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', './pass_test.py'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.PassingTest.test_pass'], files=files,
                   ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')

    def test_find_from_subdirs(self):
        files = {
            'foo/__init__.py': '',
            'foo/pass_test.py': PASSING_TEST,
            'bar/__init__.py': '',
            'bar/tmp': '',

        }
        self.check(['-l', '../foo/pass_test.py'], files=files, cwd='bar',
                   ret=0, out='foo.pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'foo'], files=files, cwd='bar',
                   ret=0, out='foo.pass_test.PassingTest.test_pass\n')
        self.check(['-l', '--path', '../foo', 'pass_test'],
                   files=files, cwd='bar', ret=0,
                   out='pass_test.PassingTest.test_pass\n')

    def test_help(self):
        self.check(['--help'], ret=0)

    def test_import_failure(self):
        self.check(['-l', 'foo'], ret=1, out='')

        files = {'foo.py': 'import unittest'}
        self.check(['-l', 'foo.bar'], files=files, ret=1, out='')

    def test_interrupt(self):
        files = {'interrupt_test.py': ('import unittest\n'
                                       'class Foo(unittest.TestCase):\n'
                                       '    def test_interrupt(self):\n'
                                       '        raise KeyboardInterrupt()\n')}
        self.check(['-j', '1'], files=files, ret=130,
                   err='interrupted, exiting\n')

    def test_load_tests_single_worker(self):
        files = {'load_test.py': LOAD_TESTS}
        self.check(['-j', '1', '-v'], files=files, ret=1, err='', rout=(
            '\[1/2\] load_test.BaseTest.test_fail failed:\n'
            '  Traceback \(most recent call last\):\n'
            '    File ".*load_test.py", line 8, in method_fail\n'
            '      self.fail\(\)\n'
            '  AssertionError: None\n'
            '\[2/2\] load_test.BaseTest.test_pass passed\n'
            '2 tests run, 1 failure.\n'))

    def test_load_tests_multiple_workers(self):
        files = {'load_test.py': LOAD_TESTS}
        _, out, _, _ = self.check([], files=files, ret=1, err='')

        # The output for this test is nondeterministic since we may run
        # two tests in parallel. So, we just test that some of the substrings
        # we care about are present.
        self.assertIn('test_pass passed', out)
        self.assertIn('test_fail failed', out)
        self.assertIn('2 tests run, 1 failure.\n', out)

    def test_missing_builder_name(self):
        self.check(['--test-results-server', 'localhost'], ret=2)

    def test_retry_limit(self):
        files = {'fail_test.py': FAILING_TEST}
        ret, out, _, _ = self.check(['--retry-limit', '2'], files=files)
        self.assertEqual(ret, 1)
        self.assertIn('Retrying failed tests', out)
        lines = out.splitlines()
        self.assertEqual(len([l for l in lines if 'test_fail failed:' in l]),
                         3)

    def test_isolate(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['--isolate', '*test_pass*'], files=files, ret=0)

    def test_skip(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check(['--skip', '*test_fail*'], files=files, ret=1,
                   out='No tests to run.\n')

        files = {'fail_test.py': FAILING_TEST,
                 'pass_test.py': PASSING_TEST}
        self.check(['--skip', '*test_fail*'], files=files, ret=0)

    def test_timing(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-t'], files=files, ret=0)

    def test_version(self):
        self.check('--version', ret=0, out=(VERSION + '\n'))

    def test_error(self):
        files = {'err_test.py': ('import unittest\n'
                                 'class ErrTest(unittest.TestCase):\n'
                                 '  def test_err(self):\n'
                                 '    foo = bar\n')}
        self.check([''], files=files, ret=1,
                   rout=('\[1/1\] err_test.ErrTest.test_err failed:\n'
                         '  Traceback \(most recent call last\):\n'
                         '    File ".*err_test.py", line 4, in test_err\n'
                         '      foo = bar\n'
                         '  NameError: global name \'bar\' is not defined\n'
                         '1 test run, 1 failure.\n'),
                   err='')


    def test_verbose(self):
        files = {'output_tests.py': OUTPUT_TESTS}
        self.check(['-vv', '-j', '1', 'output_tests.PassTest'],
                   files=files, ret=0,
                   out=('[1/2] output_tests.PassTest.test_err passed:\n'
                        '  hello on stderr\n'
                        '[2/2] output_tests.PassTest.test_out passed:\n'
                        '  hello on stdout\n'
                        '2 tests run, 0 failures.\n'),
                   err='')

    def test_ninja_status_env(self):
        files = {'output_tests.py': OUTPUT_TESTS}
        self.check(['-v', 'output_tests.PassTest.test_out'],
                   files=files, env={'NINJA_STATUS': 'ns: '},
                   out=('ns: output_tests.PassTest.test_out passed\n'
                        '1 test run, 0 failures.\n'))

    def test_output_for_failures(self):
        files = {'output_tests.py': OUTPUT_TESTS}
        self.check(
            ['output_tests.FailTest'],
            files=files,
            ret=1,
            rout=('\[1/1\] output_tests.FailTest.test_out_err_fail failed:\n'
                  '  hello on stdout\n'
                  '  hello on stderr\n'
                  '  Traceback \(most recent call last\):\n'
                  '    File ".*/output_tests.py", line 18, in '
                  'test_out_err_fail\n'
                  '      self.fail\(\)\n'
                  '  AssertionError: None\n'
                  '1 test run, 1 failure.\n'),
            err='')

    def test_debugger(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-d'], stdin='quit()\n', files=files, ret=0)

    def test_coverage(self):
        files = {'pass_test.py': PASSING_TEST}
        try:
            import coverage # pylint: disable=W0612
            self.check(['-c'], files=files, ret=0,
                       out=('[1/1] pass_test.PassingTest.test_pass passed\n'
                            '1 test run, 0 failures.\n'
                            '\n'
                            'Name        Stmts   Miss  Cover\n'
                            '-------------------------------\n'
                            'pass_test       4      0   100%\n'))
        except ImportError: # pragma: no cover
            self.check(['-c'], files=files, ret=1,
                       out='Error: coverage is not installed\n', err='')

    def test_skips_and_failures(self):
        files = {'sf_test.py': SKIPS_AND_FAILURES}
        # TODO: add real tests here.
        self.check([], files=files, ret=1)

    def test_setup_and_teardown_single_child(self):
        files = {'st_test.py': SETUP_AND_TEARDOWN}
        self.check(['--jobs', '1',
                    '--setup', 'st_test.setupProcess',
                    '--teardown', 'st_test.teardownProcess'],
                    files=files, ret=0, err='',
                    out=("setupProcess(1): {'passed_in': False, 'calls': 0}\n"
                         "[1/4] st_test.TypTest.test_one passed\n"
                         "[2/4] st_test.TypTest.test_two passed\n"
                         "[3/4] st_test.UnitTest.test_one passed\n"
                         "[4/4] st_test.UnitTest.test_two passed"
                         "teardownProcess(1): "
                         "{'passed_in': False, 'calls': 3}\n"
                         "\n"
                         "4 tests run, 0 failures.\n"))


class TestMain(TestCli):
    prog = []

    def make_host(self):
        return Host()

    def call(self, host, argv, stdin, env):
        host.stdin = StringIO.StringIO(stdin)
        if env:
            host.getenv = env.get
        host.capture_output(divert=not self.child.debugger)
        orig_sys_path = sys.path[:]
        loader = FakeTestLoader(host, orig_sys_path)

        try:
            ret = main.main(argv + ['-j', '1'], host, loader)
        finally:
            out, err = host.restore_output()
            sys.path = orig_sys_path

        return ret, out, err

    # TODO: figure out how to make these tests pass w/ trapping output.
    def test_debugger(self):
        pass

    def test_coverage(self):
        pass

    def test_error(self):
        pass

    def test_verbose(self):
        pass

    def test_output_for_failures(self):
        pass

    # TODO: These tests need to execute the real tests (they can't use a
    # FakeTestLoader and FakeTestCase) because we're testing
    # the side effects the tests have on setup and teardown.
    def test_load_tests_single_worker(self):
        pass

    def test_load_tests_multiple_workers(self):
        pass

    def test_setup_and_teardown_single_child(self):
        pass
