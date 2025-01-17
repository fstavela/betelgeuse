"""Betelgeuse unit tests."""
import click
import mock
import os
import pytest
import re

from click.testing import CliRunner
from betelgeuse import (
    INVALID_CHARS_REGEX,
    cli,
    create_xml_property,
    create_xml_testcase,
    default_config,
    load_custom_fields,
    map_steps,
    parse_junit,
    parse_test_results,
    validate_key_value_option,
)
from betelgeuse.config import BetelgeuseConfig
from io import StringIO
from xml.etree import ElementTree


JUNIT_XML = """<testsuite tests="4" skips="0">
    <testcase classname="foo1" name="test_passed" file="source.py" line="8">
    </testcase>
    <testcase classname="foo1" name="test_passed_no_id"></testcase>
    <testcase classname="foo2" name="test_skipped">
        <skipped message="Skipped message">...</skipped>
    </testcase>
    <testcase classname="foo3" name="test_failure">
        <failure type="Type" message="Failure message">...</failure>
    </testcase>
    <testcase classname="foo4" name="test_error">
        <error type="ExceptionName" message="Error message">...</error>
    </testcase>
</testsuite>
"""

TEST_MODULE = '''  # noqa: Q000
def test_something():
    """This test something."""

def test_something_else():
    """This test something else."""
'''


MULTIPLE_STEPS = """<ol>
  <li><p>First step</p></li>
  <li><p>Second step</p></li>
  <li><p>Third step</p></li>
</ol>
"""

MULTIPLE_EXPECTEDRESULTS = """<ol>
  <li><p>First step expected result.</p></li>
  <li><p>Second step expected result.</p></li>
  <li><p>Third step expected result.</p></li>
</ol>
"""

SINGLE_STEP = """<p>Single step</p>"""

SINGLE_EXPECTEDRESULT = """<p>Single step expected result.</p>"""

TEST_PLAN_OUTPUT = (
    'Betelgeuse stopped creating test plans because pylarion is not '
    'supported anymore. This command will be removed in a future release.\n'
)


@pytest.fixture
def cli_runner():
    """Return a `click`->`CliRunner` object."""
    return CliRunner()


def test_load_custom_fields():
    """Check if custom fields can be loaded using = notation."""
    assert load_custom_fields(('isautomated=true',)) == {
        'isautomated': 'true'
    }


def test_load_custom_fields_empty():
    """Check if empty value return empty dict for custom fields."""
    assert load_custom_fields(('',)) == {}


def test_load_custom_fields_none():
    """Check if None value return empty dict for custom fields."""
    assert load_custom_fields(None) == {}


def test_load_custom_fields_json():
    """Check if custom fields can be loaded using JSON data."""
    assert load_custom_fields(('{"isautomated":true}',)) == {
        'isautomated': True,
    }


def test_map_single_step():
    """Check if mapping single step works."""
    mapped = [(SINGLE_STEP, SINGLE_EXPECTEDRESULT)]
    assert map_steps(SINGLE_STEP, SINGLE_EXPECTEDRESULT) == mapped


def test_map_multiple_steps():
    """Check if mapping multiple steps works."""
    assert map_steps(MULTIPLE_STEPS, MULTIPLE_EXPECTEDRESULTS) == [
        ('<p>First step</p>', '<p>First step expected result.</p>'),
        ('<p>Second step</p>', '<p>Second step expected result.</p>'),
        ('<p>Third step</p>', '<p>Third step expected result.</p>'),
    ]


def test_get_multiple_steps_diff_items():
    """Check if parsing multiple steps of different items works."""
    multiple_steps = '\n'.join(MULTIPLE_STEPS.splitlines()[:-2] + ['</ol>\n'])
    assert map_steps(
        multiple_steps, MULTIPLE_EXPECTEDRESULTS) == [(
            '<ol>\n  <li><p>First step</p></li>\n  '
            '<li><p>Second step</p></li>\n</ol>\n',
            MULTIPLE_EXPECTEDRESULTS
        )]


def test_parse_junit():
    """Check if jUnit parsing works."""
    junit_xml = StringIO(JUNIT_XML)
    assert parse_junit(junit_xml) == [
        {'classname': 'foo1', 'name': 'test_passed', 'status': 'passed',
         'line': '8', 'file': 'source.py'},
        {'classname': 'foo1', 'name': 'test_passed_no_id', 'status': 'passed'},
        {'classname': 'foo2', 'message': 'Skipped message',
         'name': 'test_skipped', 'status': 'skipped'},
        {'classname': 'foo3', 'name': 'test_failure',
         'message': 'Failure message', 'status': 'failure', 'type': 'Type'},
        {'classname': 'foo4', 'name': 'test_error', 'message': 'Error message',
         'status': 'error', 'type': 'ExceptionName'}
    ]
    junit_xml.close()


def test_invalid_test_run_chars_regex():
    """Check if invalid test run characters are handled."""
    invalid_test_run_id = '\\/.:*"<>|~!@#$?%^&\'*()+`,='
    assert re.sub(INVALID_CHARS_REGEX, '', invalid_test_run_id) == ''


def test_parse_test_results():
    """Check if parsing test results works."""
    test_results = [
        {'status': u'passed',
         'name': 'test_positive_read',
         'classname': 'tests.api.test_ReadTestCase',
         'file': 'tests/api/test_foo.py',
         'time': '4.13224601746',
         'line': '521'},
        {'status': u'passed',
         'name': 'test_positive_delete',
         'classname': 'tests.api.test_ReadTestCase',
         'file': 'tests/api/test_foo.py',
         'time': '4.13224601746',
         'line': '538'},
        {'status': u'failure',
         'name': 'test_negative_read',
         'classname': 'tests.api.test_ReadTestCase',
         'file': 'tests/api/test_foo.py',
         'time': '4.13224601746',
         'line': '218'},
        {'status': u'skipped',
         'name': 'test_positive_update',
         'classname': 'tests.api.test_ReadTestCase',
         'file': 'tests/api/test_foo.py',
         'time': '4.13224601746',
         'line': '112'},
        {'status': u'error',
         'name': 'test_positive_create',
         'classname': 'tests.api.test_ReadTestCase',
         'file': 'tests/api/test_foo.py',
         'time': '4.13224601746',
         'line': '788'},
    ]
    summary = parse_test_results(test_results)
    assert summary['passed'] == 2
    assert summary['failure'] == 1
    assert summary['skipped'] == 1
    assert summary['error'] == 1


def test_test_plan(cli_runner):
    """Check if test-plan command runs with minimal parameters."""
    result = cli_runner.invoke(
        cli,
        [
            'test-plan',
            '--name', 'Test Plan Name',
            'PROJECT'
        ]
    )
    assert result.exit_code == 0
    assert result.stdout == TEST_PLAN_OUTPUT


def test_test_plan_with_custom_fields(cli_runner):
    """Check if test-plan command runs with custom_fields."""
    result = cli_runner.invoke(
        cli,
        [
            'test-plan',
            '--name',
            'Test Plan Name',
            '--custom-fields',
            'status=done',
            'PROJECT'
        ]
    )
    assert result.exit_code == 0
    assert result.stdout == TEST_PLAN_OUTPUT


def test_test_plan_with_parent(cli_runner):
    """Check if test-plan command runs when passing a parent test plan."""
    result = cli_runner.invoke(
        cli,
        [
            'test-plan',
            '--name', 'Test Plan Name',
            '--parent-name', 'Parent Test Plan Name',
            'PROJECT'
        ]
    )
    assert result.exit_code == 0
    assert result.stdout == TEST_PLAN_OUTPUT


def test_test_plan_with_iteration_type(cli_runner):
    """Check if test-plan command creates a iteration test plan."""
    result = cli_runner.invoke(
        cli,
        [
            'test-plan',
            '--name', 'Test Plan Name',
            '--plan-type', 'iteration',
            'PROJECT'
        ]
    )
    assert result.exit_code == 0
    assert result.stdout == TEST_PLAN_OUTPUT


def test_test_results(cli_runner):
    """Check if test results command works."""
    with cli_runner.isolated_filesystem():
        with open('results.xml', 'w') as handler:
            handler.write(JUNIT_XML)
        result = cli_runner.invoke(
            cli, ['test-results', '--path', 'results.xml'])
        assert result.exit_code == 0
        assert 'Error: 1\n' in result.output
        assert 'Failure: 1\n' in result.output
        assert 'Passed: 2\n' in result.output
        assert 'Skipped: 1\n' in result.output


def test_test_results_default_path(cli_runner):
    """Check if test results in the default path works."""
    with cli_runner.isolated_filesystem():
        with open('junit-results.xml', 'w') as handler:
            handler.write(JUNIT_XML)
        result = cli_runner.invoke(cli, ['test-results'])
        assert result.exit_code == 0
        assert 'Error: 1\n' in result.output
        assert 'Failure: 1\n' in result.output
        assert 'Passed: 2\n' in result.output
        assert 'Skipped: 1\n' in result.output


def test_create_xml_property():
    """Check if create_xml_property creates the expected XML tag."""
    generated = ElementTree.tostring(
        create_xml_property('name', 'value'),
        encoding='unicode'
    )
    assert generated == '<property name="name" value="value" />'


def test_create_xml_testcase():
    """Check if create_xml_testcase creates the expected XML tag."""
    testcase = mock.MagicMock()
    testcase.name = 'test_it_works'
    testcase.parent_class = 'FeatureTestCase'
    testcase.testmodule = 'tests/test_feature.py'
    testcase.docstring = 'Test feature docstring'
    testcase.fields = {
        field: field for field in
        default_config.TESTCASE_FIELDS + default_config.TESTCASE_CUSTOM_FIELDS
    }
    config = BetelgeuseConfig()
    generated = ElementTree.tostring(
        create_xml_testcase(config, testcase, '{path}#{line_number}'),
        encoding='unicode'
    )
    assert generated == (
        '<testcase approver-ids="approvers" assignee-id="assignee" '
        'due-date="duedate" id="id" initial-estimate="initialestimate" '
        'status-id="status"><title>title</title>'
        '<description>description</description><linked-work-items>'
        '<linked-work-item lookup-method="name" role-id="verifies" '
        'workitem-id="requirement" /></linked-work-items><test-steps>'
        '<test-step><test-step-column id="step">steps</test-step-column>'
        '<test-step-column id="expectedResult">expectedresults'
        '</test-step-column></test-step></test-steps>'
        '<custom-fields>'
        '<custom-field content="arch" id="arch" />'
        '<custom-field content="automation_script" id="automation_script" />'
        '<custom-field content="caseautomation" id="caseautomation" />'
        '<custom-field content="casecomponent" id="casecomponent" />'
        '<custom-field content="caseimportance" id="caseimportance" />'
        '<custom-field content="caselevel" id="caselevel" />'
        '<custom-field content="caseposneg" id="caseposneg" />'
        '<custom-field content="setup" id="setup" />'
        '<custom-field content="subcomponent" id="subcomponent" />'
        '<custom-field content="subtype1" id="subtype1" />'
        '<custom-field content="subtype2" id="subtype2" />'
        '<custom-field content="tags" id="tags" />'
        '<custom-field content="tcmsarguments" id="tcmsarguments" />'
        '<custom-field content="tcmsbug" id="tcmsbug" />'
        '<custom-field content="tcmscaseid" id="tcmscaseid" />'
        '<custom-field content="tcmscategory" id="tcmscategory" />'
        '<custom-field content="tcmscomponent" id="tcmscomponent" />'
        '<custom-field content="tcmsnotes" id="tcmsnotes" />'
        '<custom-field content="tcmsplan" id="tcmsplan" />'
        '<custom-field content="tcmsreference" id="tcmsreference" />'
        '<custom-field content="tcmsrequirement" id="tcmsrequirement" />'
        '<custom-field content="tcmsscript" id="tcmsscript" />'
        '<custom-field content="tcmstag" id="tcmstag" />'
        '<custom-field content="teardown" id="teardown" />'
        '<custom-field content="testtier" id="testtier" />'
        '<custom-field content="testtype" id="testtype" />'
        '<custom-field content="upstream" id="upstream" />'
        '<custom-field content="variant" id="variant" />'
        '</custom-fields></testcase>'
    )


def test_test_run(cli_runner):
    """Check if test run command works."""
    with cli_runner.isolated_filesystem():
        with open('junit_report.xml', 'w') as handler:
            handler.write(JUNIT_XML)
        with open('source.py', 'w') as handler:
            handler.write('')
        with mock.patch('betelgeuse.collector') as collector:
            testcases = [
                {'name': 'test_passed', 'testmodule': 'foo1'},
                {'name': 'test_passed_no_id', 'testmodule': 'foo1'},
                {'name': 'test_skipped', 'testmodule': 'foo2'},
                {'name': 'test_failure', 'testmodule': 'foo3'},
                {'name': 'test_error', 'testmodule': 'foo4'},
            ]
            return_value_testcases = []
            for test in testcases:
                t = mock.MagicMock()
                t.name = test['name']
                t.testmodule = test['testmodule']
                t.parent_class = None
                if test['name'] == 'test_passed_no_id':
                    t.fields = {}
                else:
                    t.fields = {'id': str(id(t))}
                return_value_testcases.append(t)

            collector.collect_tests.return_value = {
                'source.py': return_value_testcases,
            }
            result = cli_runner.invoke(
                cli,
                [
                    'test-run',
                    '--dry-run',
                    '--no-include-skipped',
                    '--custom-fields', 'field=value',
                    '--response-property', 'key=value',
                    '--status', 'inprogress',
                    '--test-run-id', 'test-run-id',
                    '--test-run-template-id', 'test-run-template-id',
                    '--test-run-title', 'test-run-title',
                    '--test-run-type-id', 'test-run-type-id',
                    'junit_report.xml',
                    'source.py',
                    'userid',
                    'projectid',
                    'importer.xml'
                ]
            )
            assert result.exit_code == 0, result.output()
            assert result.output.strip() == (
                'Was not able to find the ID for {0}, setting it to {0}'
                .format('foo1.test_passed_no_id')
            )
            collector.collect_tests.assert_called_once_with('source.py', ())
            assert os.path.isfile('importer.xml')
            root = ElementTree.parse('importer.xml').getroot()
            assert root.tag == 'testsuites'
            properties = root.find('properties')
            assert properties
            properties = [p.attrib for p in properties.findall('property')]
            expected = [
                {'name': 'polarion-custom-field', 'value': 'value'},
                {'name': 'polarion-custom-lookup-method-field-id',
                 'value': 'testCaseID'},
                {'name': 'polarion-dry-run', 'value': 'true'},
                {'name': 'polarion-include-skipped', 'value': 'false'},
                {'name': 'polarion-lookup-method', 'value': 'custom'},
                {'name': 'polarion-project-id', 'value': 'projectid'},
                {'name': 'polarion-response-key', 'value': 'value'},
                {'name': 'polarion-set-testrun-finished', 'value': 'false'},
                {'name': 'polarion-testrun-id', 'value': 'test-run-id'},
                {'name': 'polarion-testrun-template-id',
                 'value': 'test-run-template-id'},
                {'name': 'polarion-testrun-title', 'value': 'test-run-title'},
                {'name': 'polarion-testrun-type-id',
                 'value': 'test-run-type-id'},
                {'name': 'polarion-user-id', 'value': 'userid'},
            ]
            for p in properties:
                assert p in expected
            testsuite = root.find('testsuite')
            assert testsuite
            for index, testcase in enumerate(testsuite.findall('testcase')):
                properties = testcase.find('properties')
                assert properties
                p = properties.findall('property')
                assert len(p) == 1
                p = p[0]
                if testcase.attrib['name'] == 'test_passed_no_id':
                    polarion_testcase_id = 'foo1.test_passed_no_id'
                else:
                    polarion_testcase_id = id(return_value_testcases[index])
                assert p.attrib == {
                    'name': 'polarion-testcase-id',
                    'value': str(polarion_testcase_id),
                }


def test_validate_key_value_option():
    """Check if validate_key_value_option works."""
    # None value will be passed when the option is not specified.
    for value, result in (('key=value=', ('key', 'value=')), (None, None)):
        assert validate_key_value_option(
            None, mock.MagicMock(), value) == result


def test_validate_key_value_option_exception():
    """Check if validate_key_value_option validates invalid values."""
    option = mock.MagicMock()
    option.name = 'option_name'
    msg = 'option_name needs to be in format key=value'
    for value in ('value', ''):
        with pytest.raises(click.BadParameter) as excinfo:
            validate_key_value_option(None, option, value)
        assert excinfo.value.message == msg
